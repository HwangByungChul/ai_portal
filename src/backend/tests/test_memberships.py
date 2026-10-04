import asyncio
from concurrent.futures import ThreadPoolExecutor
import time
from uuid import uuid4
import pytest
from app.auth.crypto import window_digest
from app.db import open_web_pool
from app.errors import AppError
from app.tenants.repository import TenantRepository


def headers(f,tenant='A',csrf=None):
    result={'X-Tenant-ID':str(f.tenant_ids[tenant])}
    if csrf: result.update({'Origin':'http://127.0.0.1:5173','X-Requested-With':'ai-portal','X-CSRF-Token':csrf})
    return result


def change(client,f,csrf,target='A-U1',tenant='A',revision=1,role=None,active=False):
    path='/api/v1/admin/memberships/'+str(f.actor_ids[target])
    if role is not None:
        return client.put(path+'/role',headers=headers(f,tenant,csrf),json={'role':role,'expected_revision':revision})
    return client.patch(path,headers=headers(f,tenant,csrf),json={'active':active,'expected_revision':revision})


def stored(f,actor='A-U1',tenant='A'):
    with f.db.admin_connection() as conn:
        return conn.execute('SELECT role,active,revision FROM security.memberships WHERE tenant_id=%s AND user_id=%s',
            (f.tenant_ids[tenant],f.actor_ids[actor])).fetchone()


@pytest.mark.parametrize('actor,expected',[('DUAL',{'A','B'}),('A-U1',{'A'}),('NO_MEMBERS',set())])
def test_own_tenants(client,login,db_fixture,actor,expected):
    login(client,actor)
    reply=client.get('/api/v1/me/tenants')
    assert reply.status_code==200
    items=reply.json()['data']['items']
    assert {i['tenant_id'] for i in items}=={str(db_fixture.tenant_ids[x]) for x in expected}
    assert all(set(i)=={'tenant_id','display_name','effective_role','can_manage'} for i in items)
    assert reply.json()['meta']['tenant_id'] is None


@pytest.mark.parametrize('actor,role,manage',[('A-ADM','TADMIN',True),('P-A','PADMIN',True),('P_READ_ONLY','USER',False),('P_WRITE_ONLY','USER',False),('P_NONE','USER',False)])
def test_roles_are_current_tenant_scoped(client,login,db_fixture,actor,role,manage):
    login(client,actor)
    item=client.get('/api/v1/me/tenants').json()['data']['items'][0]
    assert item['effective_role']==role and item['can_manage']==manage
    reply=client.get('/api/v1/admin/memberships',headers=headers(db_fixture))
    assert reply.status_code==(200 if manage else 403)


@pytest.mark.parametrize('actor',['A-U1','DUAL','NO_MEMBERS'])
def test_user_cannot_administer(client,login,db_fixture,actor):
    csrf=login(client,actor)['csrf_token']
    assert client.get('/api/v1/admin/memberships',headers=headers(db_fixture)).status_code==403
    assert change(client,db_fixture,csrf).status_code==403
    assert change(client,db_fixture,csrf,role='TADMIN').status_code==403


def test_tadmin_can_toggle_only_ordinary_users(client,login,db_fixture):
    csrf=login(client,'A-ADM')['csrf_token']
    result=change(client,db_fixture,csrf)
    assert result.status_code==200 and result.json()['data']['revision']==2
    assert change(client,db_fixture,csrf,revision=2,active=True).status_code==200
    assert stored(db_fixture)==('USER',True,3)
    assert change(client,db_fixture,csrf,revision=3,role='TADMIN').status_code==403
    for target in ['A-ADM','DUAL-ADM','P-A','P_READ_ONLY']:
        assert change(client,db_fixture,csrf,target=target).status_code==403
    assert change(client,db_fixture,csrf,target='B-U1').status_code==404


def test_padmin_changes_role_and_demoted_cookie_loses_management(client,login,db_fixture,auth_settings):
    from fastapi.testclient import TestClient
    from app.main import create_app
    with TestClient(create_app(auth_settings),base_url='http://127.0.0.1:8000',client=('127.0.0.1',50001)) as other:
        login(other,'A-ADM')
        csrf=login(client,'P-A')['csrf_token']
        assert change(client,db_fixture,csrf,role='TADMIN').status_code==200
        assert change(client,db_fixture,csrf,role='USER',revision=2).status_code==200
        assert change(client,db_fixture,csrf,target='A-ADM',role='USER').status_code==200
        assert other.get('/api/v1/auth/me').status_code==200
        assert other.get('/api/v1/admin/memberships',headers=headers(db_fixture)).status_code==403
        assert other.get('/api/v1/me/tenants').json()['data']['items'][0]['effective_role']=='USER'
        assert client.get('/api/v1/admin/memberships',headers=headers(db_fixture,'B')).status_code==403


@pytest.mark.parametrize('actor',['P-A','A-ADM'])
def test_self_and_platform_targets_protected_even_inactive(client,login,db_fixture,actor):
    csrf=login(client,actor)['csrf_token']
    assert change(client,db_fixture,csrf,target=actor).status_code==403
    assert change(client,db_fixture,csrf,target=actor,role='USER').status_code==403
    with db_fixture.db.admin_connection() as conn:
        conn.execute('UPDATE security.platform_access SET active=false WHERE user_id=%s',(db_fixture.actor_ids['P_READ_ONLY'],))
    assert change(client,db_fixture,csrf,target='P_READ_ONLY').status_code==403
    assert change(client,db_fixture,csrf,target='P_READ_ONLY',role='TADMIN').status_code==403


def test_revoked_membership_removes_only_that_organization(client,login,db_fixture,auth_settings):
    from fastapi.testclient import TestClient
    from app.main import create_app
    login(client,'DUAL')
    with TestClient(create_app(auth_settings),base_url='http://127.0.0.1:8000',client=('127.0.0.1',50002)) as admin:
        csrf=login(admin,'A-ADM')['csrf_token']
        assert change(admin,db_fixture,csrf,target='DUAL').status_code==200
    assert client.get('/api/v1/auth/me').status_code==200
    assert {i['tenant_id'] for i in client.get('/api/v1/me/tenants').json()['data']['items']}=={str(db_fixture.tenant_ids['B'])}
    reply=client.get('/api/v1/admin/memberships',headers=headers(db_fixture))
    assert reply.status_code==403 and reply.json()['meta']['tenant_id'] is None
    assert db_fixture.run(db_fixture.context('DUAL','B')).tenant_id==db_fixture.tenant_ids['B']


@pytest.mark.parametrize('values',[[],[('X-Tenant-ID','bad')],[('X-Tenant-ID','10000000-0000-4000-8000-00000000000a')]*2])
def test_tenant_header_no_fallback(client,login,db_fixture,values):
    login(client,'DUAL-ADM')
    reply=client.get('/api/v1/admin/memberships',headers=values)
    assert reply.status_code==422 and reply.json()['meta']['tenant_id'] is None


@pytest.mark.parametrize('query',['?limit=0','?limit=51','?limit=x','?cursor=x','?limit=1&limit=2','?cursor=10000000-0000-4000-8000-00000000000a&cursor=10000000-0000-4000-8000-00000000000b'])
def test_query_validation(client,login,db_fixture,query):
    login(client,'A-ADM')
    assert client.get('/api/v1/admin/memberships'+query,headers=headers(db_fixture)).status_code==422


@pytest.mark.parametrize('body',[{'active':'false','expected_revision':1},{'active':0,'expected_revision':1},
 {'active':False,'expected_revision':True},{'active':False,'expected_revision':'1'},
 {'active':False,'expected_revision':0},{'active':False,'expected_revision':9223372036854775808},
 {'active':False,'expected_revision':1,'user_id':'untrusted-secret'}])
def test_mutation_input_strict_and_redacted(client,login,db_fixture,body):
    csrf=login(client,'P-A')['csrf_token']
    reply=client.patch('/api/v1/admin/memberships/'+str(db_fixture.actor_ids['A-U1']),headers=headers(db_fixture,csrf=csrf),json=body)
    assert reply.status_code==422 and 'untrusted-secret' not in reply.text
    assert stored(db_fixture)==('USER',True,1)


def test_no_platform_role_assignment(client,login,db_fixture):
    csrf=login(client,'P-A')['csrf_token']
    assert change(client,db_fixture,csrf,role='PADMIN').status_code==422


@pytest.mark.parametrize('removed',['Origin','X-Requested-With','X-CSRF-Token'])
def test_write_guards(client,login,db_fixture,removed):
    csrf=login(client,'P-A')['csrf_token'];h=headers(db_fixture,csrf=csrf);h.pop(removed)
    assert client.patch('/api/v1/admin/memberships/'+str(db_fixture.actor_ids['A-U1']),headers=h,
        json={'active':False,'expected_revision':1}).status_code==403
    assert stored(db_fixture)==('USER',True,1)


def test_list_pagination_minimal_current_scope(client,login,db_fixture):
    login(client,'DUAL-ADM');seen=[];cursor=None
    while True:
        reply=client.get('/api/v1/admin/memberships',headers=headers(db_fixture),params={'limit':2,**({'cursor':cursor} if cursor else {})})
        assert reply.status_code==200 and reply.json()['meta']['tenant_id']==str(db_fixture.tenant_ids['A'])
        data=reply.json()['data']
        assert all(set(i)=={'user_id','display_name','role','active','revision'} for i in data['items'])
        seen.extend(i['user_id'] for i in data['items']);cursor=data['next_cursor']
        if cursor is None: break
    with db_fixture.db.admin_connection() as conn:
        expected=[str(x[0]) for x in conn.execute('SELECT user_id FROM security.memberships WHERE tenant_id=%s ORDER BY user_id',(db_fixture.tenant_ids['A'],)).fetchall()]
    assert seen==expected and len(seen)==len(set(seen)) and str(db_fixture.actor_ids['B-U1']) not in seen
    assert reply.headers['cache-control']=='no-store'


def test_revision_and_missing_target_after_authorization(client,login,db_fixture):
    csrf=login(client,'P-A')['csrf_token']
    assert change(client,db_fixture,csrf).status_code==200
    reply=change(client,db_fixture,csrf,revision=1,active=True)
    assert reply.status_code==409 and reply.json()['error']['code']=='REVISION_CONFLICT'
    assert change(client,db_fixture,csrf,target='B-U1',revision=999).status_code==404
    assert stored(db_fixture)==('USER',False,2)


def test_concurrent_same_revision_has_one_commit_and_audit(client,login,db_fixture):
    csrf=login(client,'P-A')['csrf_token']
    with ThreadPoolExecutor(max_workers=2) as executor:
        futures=[executor.submit(change,client,db_fixture,csrf) for _ in range(2)]
        assert sorted(f.result().status_code for f in futures)==[200,409]
    assert stored(db_fixture)==('USER',False,2)
    with db_fixture.db.admin_connection() as conn:
        assert conn.execute("SELECT count(*) FROM ops.audit_events WHERE action='membership_active'").fetchone()[0]==1


def test_audit_failure_rolls_back_membership_revision_and_idle(client,login,db_fixture):
    csrf=login(client,'P-A')['csrf_token']
    with db_fixture.db.admin_connection() as conn:
        before=conn.execute('SELECT last_activity_at FROM security.sessions WHERE user_id=%s ORDER BY issued_at DESC LIMIT 1',(db_fixture.actor_ids['P-A'],)).fetchone()[0]
        conn.execute("ALTER TABLE ops.audit_events ADD CONSTRAINT fail_membership CHECK(action NOT LIKE 'membership_%') NOT VALID")
    reply=change(client,db_fixture,csrf)
    assert reply.status_code==503 and reply.json()['error']['retryable'] and 'fail_membership' not in reply.text
    assert stored(db_fixture)==('USER',True,1)
    with db_fixture.db.admin_connection() as conn:
        after=conn.execute('SELECT last_activity_at FROM security.sessions WHERE user_id=%s ORDER BY issued_at DESC LIMIT 1',(db_fixture.actor_ids['P-A'],)).fetchone()[0]
    assert before==after


def test_get_does_not_touch_idle_but_successful_change_does(client,login,db_fixture):
    csrf=login(client,'P-A')['csrf_token']
    with db_fixture.db.admin_connection() as conn:
        before=conn.execute('SELECT last_activity_at FROM security.sessions WHERE user_id=%s ORDER BY issued_at DESC LIMIT 1',(db_fixture.actor_ids['P-A'],)).fetchone()[0]
    assert client.get('/api/v1/me/tenants').status_code==200
    assert client.get('/api/v1/admin/memberships',headers=headers(db_fixture)).status_code==200
    with db_fixture.db.admin_connection() as conn:
        assert conn.execute('SELECT last_activity_at FROM security.sessions WHERE user_id=%s ORDER BY issued_at DESC LIMIT 1',(db_fixture.actor_ids['P-A'],)).fetchone()[0]==before
    assert change(client,db_fixture,csrf).status_code==200
    with db_fixture.db.admin_connection() as conn:
        assert conn.execute('SELECT last_activity_at FROM security.sessions WHERE user_id=%s ORDER BY issued_at DESC LIMIT 1',(db_fixture.actor_ids['P-A'],)).fetchone()[0]>before


def test_waiting_mutation_rechecks_committed_demotion(client,login,db_fixture):
    csrf=login(client,'A-ADM')['csrf_token']
    with ThreadPoolExecutor(max_workers=1) as executor:
        with db_fixture.db.admin_connection() as conn:
            with conn.transaction():
                conn.execute("UPDATE security.memberships SET role='USER',revision=revision+1 WHERE tenant_id=%s AND user_id=%s",(db_fixture.tenant_ids['A'],db_fixture.actor_ids['A-ADM']))
                future=executor.submit(change,client,db_fixture,csrf)
                deadline=time.monotonic()+1.5;waiting=False
                while time.monotonic()<deadline:
                    with db_fixture.db.admin_connection() as observe:
                        waiting=observe.execute("SELECT EXISTS(SELECT 1 FROM pg_stat_activity WHERE datname=%s AND usename='ai_web' AND wait_event_type='Lock' AND query LIKE 'SELECT * FROM security.mutate_membership%%')",(db_fixture.db.name,)).fetchone()[0]
                    if waiting: break
                    time.sleep(.01)
                assert waiting
            # Commit revocation while the request is genuinely queued on a row lock.
        assert future.result().status_code==403
    assert stored(db_fixture)==('USER',True,1)


def test_quota_120_then_429_relogin_does_not_reset_and_tenants_independent(client,login,db_fixture):
    login(client,'DUAL-ADM')
    for _ in range(120):
        assert client.get('/api/v1/admin/memberships',headers=headers(db_fixture)).status_code==200
    reply=client.get('/api/v1/admin/memberships',headers=headers(db_fixture))
    assert reply.status_code==429 and 1<=int(reply.headers['retry-after'])<=60
    login(client,'DUAL-ADM')
    assert client.get('/api/v1/admin/memberships',headers=headers(db_fixture)).status_code==429
    assert client.get('/api/v1/admin/memberships',headers=headers(db_fixture,'B')).status_code==200
    login(client,'A-ADM')
    assert client.get('/api/v1/admin/memberships',headers=headers(db_fixture)).status_code==200
    with db_fixture.db.admin_connection() as conn:
        conn.execute("UPDATE security.login_windows SET window_started_at=clock_timestamp()-interval '61 seconds' WHERE purpose='http_read'")
    assert client.get('/api/v1/admin/memberships',headers=headers(db_fixture)).status_code==200


def test_read_quota_concurrent_boundary(db_fixture,auth_settings):
    async def check():
        ctx=await db_fixture.context('A-ADM','A')
        digest=window_digest(auth_settings.login_hmac_secret.get_secret_value(),'http_read','principal',str(ctx.user_id)+':'+str(ctx.tenant_id))
        with db_fixture.db.admin_connection() as conn:
            conn.execute("INSERT INTO security.login_windows VALUES('http_read','principal',%s,clock_timestamp(),119)",(digest,))
        async with open_web_pool(db_fixture.db.runtime_dsn(),size=2) as pool:
            repo=TenantRepository(pool)
            async def get():
                try: await repo.members(ctx,None,20,digest);return 200
                except AppError as error: return error.status
            assert sorted(await asyncio.gather(get(),get()))==[200,429]
    db_fixture.run(check())
    with db_fixture.db.admin_connection() as conn:
        assert conn.execute("SELECT count FROM security.login_windows WHERE purpose='http_read'").fetchone()[0]==120


def test_concurrent_a_b_member_lists_do_not_mix(client,login,db_fixture):
    login(client,'DUAL-ADM')
    with ThreadPoolExecutor(max_workers=2) as executor:
        futures={t:executor.submit(client.get,'/api/v1/admin/memberships',headers=headers(db_fixture,t)) for t in ['A','B']}
        for tenant,future in futures.items():
            reply=future.result();assert reply.status_code==200
            ids={i['user_id'] for i in reply.json()['data']['items']}
            assert str(db_fixture.actor_ids['A-U1']) in ids if tenant=='A' else str(db_fixture.actor_ids['A-U1']) not in ids
            assert str(db_fixture.actor_ids['B-U1']) in ids if tenant=='B' else str(db_fixture.actor_ids['B-U1']) not in ids
            assert reply.json()['meta']['tenant_id']==str(db_fixture.tenant_ids[tenant])


def test_managed_tenant_revocation_removes_admin_not_global_capabilities(client,login,db_fixture):
    login(client,'P-A')
    with db_fixture.db.admin_connection() as conn:
        conn.execute('UPDATE security.managed_tenants SET active=false WHERE user_id=%s',(db_fixture.actor_ids['P-A'],))
    assert client.get('/api/v1/admin/memberships',headers=headers(db_fixture)).status_code==403
    item=client.get('/api/v1/me/tenants').json()['data']['items'][0]
    assert item['effective_role']=='USER' and not item['can_manage']
    assert all(client.get('/api/v1/auth/me').json()['data']['capabilities'].values())


def test_inactive_session_no_tenants(client,login,db_fixture):
    login(client,'A-U1')
    with db_fixture.db.admin_connection() as conn:
        conn.execute('UPDATE security.accounts SET active=false WHERE user_id=%s',(db_fixture.actor_ids['A-U1'],))
    assert client.get('/api/v1/me/tenants').status_code==401
    assert client.get('/api/v1/admin/memberships',headers=headers(db_fixture)).status_code==401


def test_untrusted_authority_headers_cannot_promote_user(client,login,db_fixture):
    csrf=login(client,'A-U1')['csrf_token']
    h=headers(db_fixture,csrf=csrf);h.update({'X-User-ID':str(db_fixture.actor_ids['P-A']),'X-Role':'PADMIN'})
    reply=client.patch('/api/v1/admin/memberships/'+str(db_fixture.actor_ids['B-U1']),headers=h,
        json={'active':False,'expected_revision':999})
    assert reply.status_code==403 and reply.json()['error']['code']!='RESOURCE_NOT_FOUND'


def test_lock_timeout_is_retryable_and_does_not_modify(client,login,db_fixture):
    csrf=login(client,'P-A')['csrf_token']
    with ThreadPoolExecutor(max_workers=1) as executor:
        with db_fixture.db.admin_connection() as conn:
            with conn.transaction():
                conn.execute('SELECT 1 FROM security.memberships WHERE tenant_id=%s AND user_id=%s FOR UPDATE',
                    (db_fixture.tenant_ids['A'],db_fixture.actor_ids['A-U1']))
                reply=executor.submit(change,client,db_fixture,csrf).result(timeout=4)
                assert reply.status_code==503 and reply.json()['error']['retryable']
                assert 'lock' not in reply.text.lower()
    assert stored(db_fixture)==('USER',True,1)


def test_control_functions_deny_index_meter_and_missing_context(db_fixture):
    import psycopg
    queries=[('SELECT * FROM security.list_memberships(%s,%s,NULL,20)',(uuid4(),db_fixture.tenant_ids['A'])),
             ('SELECT * FROM security.record_http_read_window(%s,%s,%s)',(uuid4(),db_fixture.tenant_ids['A'],bytes(32))),
             ('SELECT * FROM security.mutate_membership(%s,%s,%s,%s,%s,%s,%s,%s)',
              (uuid4(),db_fixture.tenant_ids['A'],db_fixture.actor_ids['A-U1'],'active',False,None,1,uuid4()))]
    for role in ['ai_index','ai_meter']:
        with db_fixture.role_connection(role) as conn:
            for query,args in queries:
                with pytest.raises(psycopg.errors.InsufficientPrivilege): conn.execute(query,args)
    async def check():
        ctx=await db_fixture.context('P-A','A')
        async with db_fixture.pool.connection() as conn:
            with pytest.raises(psycopg.Error) as error:
                await conn.execute('SELECT * FROM security.mutate_membership(%s,%s,%s,%s,%s,%s,%s,%s)',
                    (ctx.session_id,ctx.tenant_id,db_fixture.actor_ids['A-U1'],'active',False,None,1,uuid4()))
            assert error.value.sqlstate=='A0403'
    db_fixture.run(check())
