from fastapi.testclient import TestClient
from pydantic import SecretStr
from app.config import Settings
from app.main import create_app

HEADERS={'Origin':'http://127.0.0.1:5173','X-Requested-With':'ai-portal'}


def test_login_and_confirmed_logout(db_fixture):
    settings=Settings(web_dsn=SecretStr(db_fixture.db.runtime_dsn()),login_hmac_secret=SecretStr('a'*43))
    with TestClient(create_app(settings),base_url='http://127.0.0.1:8000',client=('127.0.0.1',50000)) as client:
        response=client.post('/api/v1/auth/login',headers=HEADERS,json={'login_id':'a-u1','password':db_fixture.passwords['A-U1']})
        assert response.status_code==200
        old=client.cookies.get('ai_session_dev')
        me=client.get('/api/v1/auth/me');assert me.status_code==200
        csrf=me.json()['data']['csrf_token']
        result=client.post('/api/v1/auth/logout',headers={**HEADERS,'X-CSRF-Token':csrf})
        assert result.status_code==200 and result.json()['data']['logout_confirmed'] is True
        client.cookies.set('ai_session_dev',old)
        assert client.get('/api/v1/auth/me').status_code==401

import asyncio
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime,timedelta,timezone
import hashlib
import json
import secrets
import time
from uuid import UUID
import pytest
import psycopg
from psycopg import sql
from app.auth.crypto import HASHER,new_secret,token_digest,window_digest
from app.auth.service import AuthService
from app.errors import AppError
from app.db import open_web_pool


def session_row(db,client):
    token=client.cookies.get('ai_session_dev')
    with db.db.admin_connection() as conn:
        return conn.execute('SELECT session_id,user_id,issued_at,last_activity_at,expires_at FROM security.sessions WHERE token_hash=%s',
                            (token_digest(token),)).fetchone()


@pytest.mark.parametrize('actor,exists',[('A-U1',True),('A-U2',True),('missing',False),('INACTIVE',True)])
def test_failed_credentials_have_same_response(client,db_fixture,actor,exists):
    password='wrong-password' if actor!='INACTIVE' else db_fixture.passwords[actor]
    result=client.post('/api/v1/auth/login',headers=HEADERS,json={'login_id':actor.lower(),'password':password})
    assert result.status_code==401 and result.json()['error']['code']=='LOGIN_FAILED'
    assert result.json()['error']['message']=='로그인 정보를 확인해 주세요.'
    assert 'set-cookie' not in result.headers
    assert result.headers['www-authenticate']=='Session realm="ai-portal"'


@pytest.mark.parametrize('actor,read,write',[('A-U1',False,False),('P-A',True,True),('P_READ_ONLY',True,False),('P_WRITE_ONLY',False,True),('P_NONE',False,False)])
def test_capabilities_are_current_and_independent(client,db_fixture,login,actor,read,write):
    login(client,actor)
    result=client.get('/api/v1/auth/me');assert result.status_code==200
    data=result.json()['data']
    assert data['capabilities']=={'can_view_platform_usage':read,'can_change_platform_availability':write}
    assert ('platform_availability' in data) is write
    assert not {'session_id','auth_revision','password','password_hash','session_token','cost','accounted_krw'} & set(data)
    if write: assert data['platform_availability']=={'enabled':True,'revision':1}
    with db_fixture.db.admin_connection() as conn:
        conn.execute('UPDATE security.platform_access SET active=false WHERE user_id=%s',(db_fixture.actor_ids[actor],))
    data=client.get('/api/v1/auth/me').json()['data']
    assert not any(data['capabilities'].values()) and 'platform_availability' not in data


def test_actual_budget_status_and_missing_row(client,db_fixture,login):
    login(client,'P_WRITE_ONLY')
    with db_fixture.db.admin_connection() as conn:
        conn.execute("UPDATE ops.project_budget SET stopped=true,revision=9 WHERE mode='mock'")
    result=client.get('/api/v1/auth/me');assert result.json()['data']['platform_availability']=={'enabled':False,'revision':9}
    with db_fixture.db.admin_connection() as conn: conn.execute("DELETE FROM ops.project_budget WHERE mode='mock'")
    result=client.get('/api/v1/auth/me')
    assert result.status_code==503 and result.json()['error']['code']=='STORAGE_UNAVAILABLE'
    client.cookies.clear();login(client,'P_READ_ONLY')
    assert client.get('/api/v1/auth/me').status_code==200


def test_no_members_account_can_login_but_has_no_tenant(client,db_fixture,login):
    login(client,'NO_MEMBERS');assert client.get('/api/v1/auth/me').status_code==200
    token=client.cookies.get('ai_session_dev')
    async def check():
        async with open_web_pool(db_fixture.db.runtime_dsn()) as pool:
            service=AuthService(pool,client.app.state.settings)
            with pytest.raises(AppError) as error: await service.resolve_tenant(token,db_fixture.tenant_ids['A'])
            assert error.value.code=='TENANT_FORBIDDEN'
            session=await service.validate(token)
            async with pool.connection() as conn:
                rows=await (await conn.execute('SELECT * FROM security.list_own_tenants(%s)',(session.session_id,))).fetchall()
                assert rows==[]
    db_fixture.run(check())


@pytest.mark.parametrize('case',['inactive','revision','revoked','absolute','idle'])
def test_current_session_expiry_and_revocation(client,db_fixture,login,case):
    login(client,'A-U1');row=session_row(db_fixture,client)
    with db_fixture.db.admin_connection() as conn:
        if case=='inactive': conn.execute('UPDATE security.accounts SET active=false WHERE user_id=%s',(row[1],))
        elif case=='revision': conn.execute('UPDATE security.accounts SET auth_revision=2 WHERE user_id=%s',(row[1],))
        elif case=='revoked': conn.execute('UPDATE security.sessions SET revoked_at=clock_timestamp() WHERE session_id=%s',(row[0],))
        else:
            now=datetime.now(timezone.utc)
            issued=now-timedelta(hours=8 if case=='absolute' else 1)
            last=now if case=='absolute' else now-timedelta(minutes=30)
            conn.execute('UPDATE security.sessions SET issued_at=%s,last_activity_at=%s,expires_at=%s WHERE session_id=%s',
                         (issued,last,issued+timedelta(hours=8),row[0]))
    result=client.get('/api/v1/auth/me');assert result.status_code==401
    assert result.json()['error']['code']=='AUTH_REQUIRED'


def test_polling_does_not_extend_idle_and_relogin_revokes_old(client,db_fixture,login):
    login(client,'A-U1');old=client.cookies.get('ai_session_dev');before=session_row(db_fixture,client)
    for _ in range(3): assert client.get('/api/v1/auth/me').status_code==200
    assert session_row(db_fixture,client)[3]==before[3]
    login(client,'A-U1');current=client.cookies.get('ai_session_dev');assert bool(current!=old)
    with db_fixture.db.admin_connection() as conn:
        row=conn.execute('SELECT revoked_at FROM security.sessions WHERE token_hash=%s',(token_digest(old),)).fetchone()
        assert row[0] is not None
        assert not conn.execute('SELECT 1 FROM security.sessions WHERE encode(token_hash,\'hex\')=%s',(old,)).fetchone()
    client.cookies.clear();client.cookies.set('ai_session_dev',old)
    assert client.get('/api/v1/auth/me').status_code==401


@pytest.mark.parametrize('headers',[{}, {'Origin':'http://evil.example','X-Requested-With':'ai-portal'}, {'Origin':HEADERS['Origin']},
 [('Origin',HEADERS['Origin']),('Origin',HEADERS['Origin']),('X-Requested-With','ai-portal')]])
def test_login_origin_and_required_header(client,db_fixture,headers):
    response=client.post('/api/v1/auth/login',headers=headers,json={'login_id':'a-u1','password':db_fixture.passwords['A-U1']})
    assert response.status_code==403 and 'set-cookie' not in response.headers


@pytest.mark.parametrize('csrf',[None,'wrong','한글', 'x'*200])
def test_valid_logout_requires_csrf(client,db_fixture,login,csrf):
    login(client,'A-U1')
    headers={**HEADERS}
    if csrf is not None: headers['X-CSRF-Token']=csrf.encode('utf-8')
    result=client.post('/api/v1/auth/logout',headers=headers)
    assert result.status_code==403 and 'set-cookie' not in result.headers
    assert client.get('/api/v1/auth/me').status_code==200


def test_invalid_repeat_logout_still_requires_origin(client):
    result=client.post('/api/v1/auth/logout');assert result.status_code==403
    result=client.post('/api/v1/auth/logout',headers=HEADERS)
    assert result.status_code==200 and result.json()['data']=={'logout_confirmed':True}


@pytest.mark.parametrize('cookie',[b'ai_session_dev=bad',b'ai_session_dev=\xff',b'ai_session_dev='+b'x'*9000,
 b'ai_session_dev='+b'x'*43+b'; ai_session_dev='+b'y'*43,b'__Host-ai_session='+b'x'*43])
def test_invalid_cookie_is_safe_401(client,cookie):
    result=client.get('/api/v1/auth/me',headers=[(b'cookie',cookie)])
    assert result.status_code==401 and result.json()['error']['code']=='AUTH_REQUIRED'


@pytest.mark.parametrize('body',[{'login_id':'a-u1','password':'s'*129},{'login_id':'a'*65,'password':'do-not-echo'},
 {'login_id':'a-u1','password':'do-not-echo','unknown-do-not-echo':'do-not-echo'}])
def test_input_errors_never_echo_values(client,body):
    result=client.post('/api/v1/auth/login',headers=HEADERS,json=body)
    assert result.status_code==422
    assert 'do-not-echo' not in result.text and 's'*129 not in result.text
    assert set(result.json())=={'error','meta'}
    assert set(result.json()['error']['field_paths']) <= {'password','login_id','body'}


def test_form_json_failure_and_duplicate_csrf(client,db_fixture,login):
    result=client.post('/api/v1/auth/login',headers=HEADERS,data={'login_id':'a-u1','password':'secret-marker'})
    assert result.status_code in (400,422) and 'secret-marker' not in result.text
    result=client.post('/api/v1/auth/login',headers={**HEADERS,'Content-Type':'application/json'},content='{"password":"secret-marker"')
    assert result.status_code==422 and 'secret-marker' not in result.text
    csrf=login(client,'A-U1')['csrf_token']
    result=client.post('/api/v1/auth/logout',headers=[*HEADERS.items(),('X-CSRF-Token',csrf),('X-CSRF-Token',csrf)])
    assert result.status_code==403


def test_input_window_failures_commit_and_success_reset(client,db_fixture,login):
    for _ in range(4):
        assert client.post('/api/v1/auth/login',headers=HEADERS,json={'login_id':'a-u1','password':'wrong'}).status_code==401
    login(client,'A-U1')
    for _ in range(5):
        assert client.post('/api/v1/auth/login',headers=HEADERS,json={'login_id':'a-u1','password':'wrong'}).status_code==401
    result=client.post('/api/v1/auth/login',headers=HEADERS,json={'login_id':'a-u1','password':db_fixture.passwords['A-U1']})
    assert result.status_code==429 and int(result.headers['retry-after'])>=1
    with db_fixture.db.admin_connection() as conn:
        assert conn.execute("SELECT count FROM security.login_windows WHERE purpose='login_input'").fetchone()[0]==5
        conn.execute("UPDATE security.login_windows SET window_started_at=clock_timestamp()-interval '15 minutes' WHERE purpose='login_input'")
    login(client,'A-U1')


def test_ip_window_success_does_not_reset_and_forwarding_is_ignored(client,db_fixture):
    login_response=client.post('/api/v1/auth/login',headers=HEADERS,json={'login_id':'a-u1','password':db_fixture.passwords['A-U1']})
    assert login_response.status_code==200
    for index in range(29):
        # Unique missing IDs stay below the independent per-ID limit.
        response=client.post('/api/v1/auth/login',headers={**HEADERS,'X-Forwarded-For':f'192.0.2.{index+1}'},
                             json={'login_id':f'missing-{index}','password':'wrong'})
        assert response.status_code==401
    result=client.post('/api/v1/auth/login',headers=HEADERS,json={'login_id':'a-u1','password':db_fixture.passwords['A-U1']})
    assert result.status_code==429
    with db_fixture.db.admin_connection() as conn:
        rows=conn.execute("SELECT count,key_digest FROM security.login_windows WHERE purpose='login_ip'").fetchall()
        assert len(rows)==1 and rows[0][0]==30
    assert '192.0.2' not in result.text


def test_concurrent_input_failures_stop_at_five(db_fixture,auth_settings):
    async def check():
        async with open_web_pool(db_fixture.db.runtime_dsn(),size=4) as pool:
            service=AuthService(pool,auth_settings)
            async def attempt(i):
                try: await service.login('a-u1','wrong',None,f'192.0.2.{i}')
                except AppError as error: return error.status
                return 200
            outcomes=await asyncio.gather(*(attempt(i) for i in range(8)))
            assert sorted(outcomes)==[401]*5+[429]*3
    db_fixture.run(check())
    with db_fixture.db.admin_connection() as conn:
        assert conn.execute("SELECT count FROM security.login_windows WHERE purpose='login_input'").fetchone()[0]==5


def test_logout_storage_failure_is_unconfirmed_and_retryable(client,db_fixture,login):
    csrf=login(client,'A-U1')['csrf_token']
    with db_fixture.db.admin_connection() as conn:
        conn.execute("ALTER TABLE ops.audit_events ADD CONSTRAINT reject_logout CHECK(action<>'logout') NOT VALID")
    result=client.post('/api/v1/auth/logout',headers={**HEADERS,'X-CSRF-Token':csrf})
    assert result.status_code==503 and 'set-cookie' not in result.headers
    assert 'logout_confirmed' not in result.json().get('data',{})
    assert result.json()['error']['retryable'] is True
    assert client.get('/api/v1/auth/me').status_code==200
    with db_fixture.db.admin_connection() as conn: conn.execute('ALTER TABLE ops.audit_events DROP CONSTRAINT reject_logout')
    assert client.post('/api/v1/auth/logout',headers={**HEADERS,'X-CSRF-Token':csrf}).status_code==200


def test_login_audit_failure_rolls_back_new_and_previous_session(client,db_fixture,login):
    login(client,'A-U1');old=client.cookies.get('ai_session_dev')
    with db_fixture.db.admin_connection() as conn:
        count=conn.execute('SELECT count(*) FROM security.sessions').fetchone()[0]
        conn.execute("ALTER TABLE ops.audit_events ADD CONSTRAINT reject_login CHECK(action<>'login') NOT VALID")
    result=client.post('/api/v1/auth/login',headers=HEADERS,json={'login_id':'a-u1','password':db_fixture.passwords['A-U1']})
    assert result.status_code==503 and 'set-cookie' not in result.headers
    assert client.get('/api/v1/auth/me').status_code==200
    with db_fixture.db.admin_connection() as conn:
        assert conn.execute('SELECT count(*) FROM security.sessions').fetchone()[0]==count
        assert conn.execute('SELECT revoked_at IS NULL FROM security.sessions WHERE token_hash=%s',(token_digest(old),)).fetchone()[0]


def test_normalized_login_and_private_token_storage(client,db_fixture):
    result=client.post('/api/v1/auth/login',headers=HEADERS,json={'login_id':' A-U1 ','password':db_fixture.passwords['A-U1']})
    assert result.status_code==200
    token=client.cookies.get('ai_session_dev')
    assert token not in result.text and db_fixture.passwords['A-U1'] not in result.text
    cookie=result.headers['set-cookie'].lower()
    assert 'httponly' in cookie and 'samesite=lax' in cookie and 'path=/' in cookie and 'secure' not in cookie and 'domain=' not in cookie
    with db_fixture.db.admin_connection() as conn:
        row=conn.execute('SELECT octet_length(token_hash),expires_at-issued_at FROM security.sessions WHERE token_hash=%s',(token_digest(token),)).fetchone()
        assert row==(32,timedelta(hours=8))
    assert result.headers['cache-control']=='no-store' and result.headers['x-request-id']==result.json()['meta']['request_id']


def test_https_cookie_and_profile_confusion(db_fixture):
    settings=Settings(profile='https',origin='https://portal.example',web_dsn=SecretStr(db_fixture.db.runtime_dsn()),login_hmac_secret=SecretStr(new_secret()))
    with TestClient(create_app(settings),base_url='https://portal.example',client=('127.0.0.1',50000)) as client:
        result=client.post('/api/v1/auth/login',headers={'Origin':settings.origin,'X-Requested-With':'ai-portal'},
                           json={'login_id':'a-u1','password':db_fixture.passwords['A-U1']})
        assert result.status_code==200
        cookie=result.headers['set-cookie'].lower();assert '__host-ai_session=' in cookie and 'secure' in cookie and 'httponly' in cookie and 'domain=' not in cookie
        assert client.get('/api/v1/auth/me').status_code==200
        client.cookies.set('ai_session_dev','x'*43)
        assert client.get('/api/v1/auth/me').status_code==401


def test_startup_needs_auth_credentials():
    for settings in [Settings(),Settings(web_dsn=SecretStr('unused')),Settings(login_hmac_secret=SecretStr(new_secret()))]:
        with pytest.raises(ValueError,match='AUTH_CONFIGURATION_REQUIRED'): create_app(settings)


def test_concurrent_ip_window_has_fixed_limit(db_fixture,auth_settings):
    digest=window_digest(auth_settings.login_hmac_secret.get_secret_value(),'login_ip','ip','192.0.2.1')
    with db_fixture.db.admin_connection() as conn:
        conn.execute("INSERT INTO security.login_windows(purpose,key_kind,key_digest,window_started_at,count) VALUES('login_ip','ip',%s,clock_timestamp(),27)",(digest,))
    async def check():
        async with open_web_pool(db_fixture.db.runtime_dsn(),size=4) as pool:
            service=AuthService(pool,auth_settings)
            async def attempt(i):
                try: await service.login(f'missing-{i}','wrong',None,'192.0.2.1')
                except AppError as error: return error.status
                return 200
            assert sorted(await asyncio.gather(*(attempt(i) for i in range(8))))==[401]*3+[429]*5
    db_fixture.run(check())
    with db_fixture.db.admin_connection() as conn:
        assert conn.execute("SELECT count FROM security.login_windows WHERE purpose='login_ip'").fetchone()[0]==30


def test_account_revision_change_during_verification_cannot_issue(client,db_fixture,monkeypatch):
    from app.auth import service as module
    original=module.verify_password
    def verify_and_revoke(encoded,password):
        result=original(encoded,password)
        with db_fixture.db.admin_connection() as conn:
            conn.execute('UPDATE security.accounts SET auth_revision=auth_revision+1 WHERE user_id=%s',(db_fixture.actor_ids['A-U1'],))
        return result
    monkeypatch.setattr(module,'verify_password',verify_and_revoke)
    result=client.post('/api/v1/auth/login',headers=HEADERS,json={'login_id':'a-u1','password':db_fixture.passwords['A-U1']})
    assert result.status_code==401 and 'set-cookie' not in result.headers
    with db_fixture.db.admin_connection() as conn:
        assert conn.execute('SELECT count(*) FROM security.sessions').fetchone()[0]==13


def test_control_window_cannot_raise_limits_and_touch_requires_context(client,db_fixture,login):
    login(client,'A-U1');token=client.cookies.get('ai_session_dev')
    async def check():
        async with open_web_pool(db_fixture.db.runtime_dsn()) as pool:
            service=AuthService(pool,client.app.state.settings)
            session=await service.validate(token)
            async with pool.connection() as conn:
                with pytest.raises(psycopg.errors.InvalidParameterValue):
                    await conn.execute("SELECT * FROM security.record_login_window('login_ip','ip',%s,1000,true)",(b'0'*32,))
                row=await (await conn.execute('SELECT security.touch_session(%s) AS allowed',(session.session_id,))).fetchone()
                assert row['allowed'] is False
            ctx=await service.resolve_tenant(token,db_fixture.tenant_ids['A'])
            from app.db import tenant_transaction
            async with tenant_transaction(pool,ctx) as conn:
                assert (await (await conn.execute('SELECT security.touch_session(%s) AS allowed',(session.session_id,))).fetchone())['allowed'] is True
    db_fixture.run(check())


@pytest.mark.parametrize('field',['login_id','password'])
def test_invalid_unicode_is_safe_login_failure(client,db_fixture,field):
    body={'login_id':'a-u1','password':db_fixture.passwords['A-U1']};body[field]='\ud800'
    result=client.post('/api/v1/auth/login',headers={**HEADERS,'Content-Type':'application/json'},content=json.dumps(body))
    expected=(422,'REQUEST_INVALID') if field=='login_id' else (401,'LOGIN_FAILED')
    assert (result.status_code,result.json()['error']['code'])==expected


def test_connection_loss_is_503_and_never_confirms_logout(client,db_fixture,login):
    csrf=login(client,'A-U1')['csrf_token']
    client.portal.call(client.app.state.pool.close)
    for path,method,headers,body in [
        ('/api/v1/auth/me','get',{},None),
        ('/api/v1/auth/logout','post',{**HEADERS,'X-CSRF-Token':csrf},None),
        ('/api/v1/auth/login','post',HEADERS,{'login_id':'a-u1','password':db_fixture.passwords['A-U1']})]:
        kwargs={'headers':headers}
        if body: kwargs['json']=body
        result=getattr(client,method)(path,**kwargs)
        assert result.status_code==503 and result.json()['error']['code']=='STORAGE_UNAVAILABLE'
        assert 'set-cookie' not in result.headers and 'data' not in result.json()
    assert client.get('/api/v1/health').status_code==200


def test_cookie_derived_tenant_context_checks_current_membership(client,db_fixture,login):
    login(client,'DUAL');token=client.cookies.get('ai_session_dev')
    async def check():
        async with open_web_pool(db_fixture.db.runtime_dsn()) as pool:
            service=AuthService(pool,client.app.state.settings)
            for tenant in ('A','B'):
                ctx=await service.resolve_tenant(token,db_fixture.tenant_ids[tenant])
                assert ctx.user_id==db_fixture.actor_ids['DUAL'] and ctx.effective_role=='USER'
            with db_fixture.db.admin_connection() as conn:
                conn.execute('UPDATE security.memberships SET active=false WHERE tenant_id=%s AND user_id=%s',
                             (db_fixture.tenant_ids['A'],db_fixture.actor_ids['DUAL']))
            with pytest.raises(AppError) as error: await service.resolve_tenant(token,db_fixture.tenant_ids['A'])
            assert error.value.status==403
            assert (await service.resolve_tenant(token,db_fixture.tenant_ids['B'])).tenant_id==db_fixture.tenant_ids['B']
    db_fixture.run(check())
    assert client.get('/api/v1/auth/me').status_code==200
