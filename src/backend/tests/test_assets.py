from concurrent.futures import ThreadPoolExecutor
from uuid import uuid4
import json
import psycopg
import pytest
from test_operations import headers,stored_agent
from test_auth_restart import running_server


def config(**changes):
    return {'name':'합성 새 Agent','description':'합성 등록 설명','instructions':'private-asset-instruction-marker','execution_kind':'general',**changes}


def create(client,login,f,actor='A-ADM',body=None,tenant='A'):
    csrf=login(client,actor)['csrf_token']
    return client.post('/api/v1/admin/assets',headers=headers(f,tenant,csrf),json=body or {'client_request_id':str(uuid4()),'config':config()})


def test_create_versions_and_replay_are_immutable(client,login,db_fixture):
    f=db_fixture;old=stored_agent(f);body={'client_request_id':str(uuid4()),'config':config()}
    reply=create(client,login,f,body=body);assert reply.status_code==201
    receipt=reply.json()['data'];aid=receipt['asset_id'];assert receipt['revision']==1 and len(receipt['config_hash'])==64
    replay=create(client,login,f,body=body);assert replay.status_code==200 and replay.json()['data']['asset_id']==aid
    assert create(client,login,f,body={**body,'config':config(name='다른 내용')}).status_code==409
    csrf=client.get('/api/v1/auth/me').json()['data']['csrf_token'];h=headers(f,csrf=csrf)
    new={'client_request_id':str(uuid4()),'expected_revision':1,'config':config(name='합성 수정 Agent')}
    assert client.post('/api/v1/admin/assets/'+aid+'/versions',headers=h,json=new).status_code==201
    again=client.post('/api/v1/admin/assets/'+aid+'/versions',headers=h,json=new)
    assert again.status_code==200 and again.json()['data']['replayed']
    assert client.post('/api/v1/admin/assets/'+aid+'/versions',headers=h,json={**new,'client_request_id':str(uuid4())}).status_code==409
    detail=client.get('/api/v1/admin/assets/'+aid,headers=h).json()['data']
    assert detail['latest_revision']==2 and detail['state']=='draft' and detail['config']==new['config']
    assert [x['revision'] for x in detail['versions']]==[2,1]
    assert receipt['config_hash']==detail['versions'][1]['config_hash']
    assert all('config' not in x for x in detail['versions'])
    with f.db.admin_connection() as conn:
        versions=conn.execute('SELECT revision,config FROM portal.asset_versions WHERE asset_id=%s ORDER BY revision',(aid,)).fetchall()
        assert versions==[(1,body['config']),(2,new['config'])]
        rows=conn.execute("SELECT action,revisions FROM ops.audit_events WHERE opaque_target_id=%s ORDER BY created_at",(aid,)).fetchall()
        assert len(rows)==2 and {x[0] for x in rows}=={'asset.create','asset.version'}
        assert 'private-asset-instruction-marker' not in json.dumps(rows)
        assert conn.execute('SELECT count(*) FROM ops.call_attempts').fetchone()[0]==0
    assert stored_agent(f)==old


@pytest.mark.parametrize('actor,tenant,status',[('A-U1','A',403),('P_READ_ONLY','A',403),('P-A','B',403),('B-ADM','A',403)])
def test_asset_management_scope(client,login,db_fixture,actor,tenant,status):
    f=db_fixture
    assert create(client,login,f,actor=actor,tenant=tenant).status_code==status
    assert client.get('/api/v1/admin/assets',headers=headers(f,tenant)).status_code==status


def test_cross_tenant_detail_cursor_and_append_are_hidden(client,login,db_fixture):
    f=db_fixture;aid=create(client,login,f).json()['data']['asset_id'];csrf=login(client,'B-ADM')['csrf_token'];h=headers(f,'B',csrf)
    assert client.get('/api/v1/admin/assets/'+aid,headers=h).status_code==404
    assert client.get('/api/v1/admin/assets?cursor='+aid,headers=h).status_code==404
    assert client.post('/api/v1/admin/assets/'+aid+'/versions',headers=h,json={'client_request_id':str(uuid4()),'expected_revision':1,'config':config()}).status_code==404


def test_paginated_metadata_has_stable_legacy_aliases_and_no_private_prompt(client,login,db_fixture):
    f=db_fixture
    for _ in range(3):assert create(client,login,f).status_code==201
    items=[];cursor=None
    for _ in range(4):
        reply=client.get('/api/v1/admin/assets?limit=2'+('&cursor='+cursor if cursor else ''),headers=headers(f))
        assert reply.status_code==200 and 'instructions' not in reply.text and 'private-asset' not in reply.text
        data=reply.json()['data'];items+=data['items'];cursor=data['next_cursor']
        if cursor is None:break
    assert len(items)==5 and len({x['asset_id'] for x in items})==5
    legacy=[x for x in items if x['state']=='legacy'];assert {x['legacy_agent_key'] for x in legacy}=={'general','rules_rag'}
    again=client.get('/api/v1/admin/assets',headers=headers(f)).json()['data']['items']
    assert {x['asset_id'] for x in legacy}=={x['asset_id'] for x in again if x['state']=='legacy'}
    csrf=client.get('/api/v1/auth/me').json()['data']['csrf_token']
    assert client.post('/api/v1/admin/assets/'+legacy[0]['asset_id']+'/versions',headers=headers(f,csrf=csrf),json={'client_request_id':str(uuid4()),'expected_revision':1,'config':config()}).json()['error']['code']=='ASSET_LEGACY_READ_ONLY'


@pytest.mark.parametrize('change',[{'name':' '},{'instructions':'i'*2001},{'name':'\x00'},{'name':'\ud800'},{'execution_kind':'external_url'},{'model':'external'},{'name':True},{'instructions':None}])
def test_strict_config(client,login,db_fixture,change):
    f=db_fixture;csrf=login(client,'A-ADM')['csrf_token']
    reply=client.post('/api/v1/admin/assets',headers={**headers(f,csrf=csrf),'Content-Type':'application/json'},content=json.dumps({'client_request_id':str(uuid4()),'config':config(**change)}).encode())
    assert reply.status_code==422 and 'private-asset-instruction-marker' not in reply.text


@pytest.mark.parametrize('revision',[True,'1',0,1001,None])
def test_strict_revision(client,login,db_fixture,revision):
    f=db_fixture;aid=create(client,login,f).json()['data']['asset_id'];csrf=client.get('/api/v1/auth/me').json()['data']['csrf_token']
    assert client.post('/api/v1/admin/assets/'+aid+'/versions',headers=headers(f,csrf=csrf),json={'client_request_id':str(uuid4()),'expected_revision':revision,'config':config()}).status_code==422


def test_query_and_transport_limits(client,login,db_fixture):
    f=db_fixture;csrf=login(client,'A-ADM')['csrf_token'];h=headers(f,csrf=csrf)
    for query in ['?limit=2&limit=3','?unknown=1','?limit=51','?cursor=bad']:
        assert client.get('/api/v1/admin/assets'+query,headers=h).status_code==422
    body={'client_request_id':str(uuid4()),'config':config()}
    assert client.post('/api/v1/admin/assets',headers=headers(f),json=body).status_code==403
    assert client.post('/api/v1/admin/assets',headers={**h,'Origin':'http://evil.invalid'},json=body).status_code==403
    assert client.post('/api/v1/admin/assets',headers={**h,'Content-Type':'application/json'},content=b' '*32769).status_code==413


def test_concurrent_versions_only_one_wins(client,login,db_fixture):
    f=db_fixture;aid=create(client,login,f).json()['data']['asset_id'];csrf=client.get('/api/v1/auth/me').json()['data']['csrf_token']
    def send(i):return client.post('/api/v1/admin/assets/'+aid+'/versions',headers=headers(f,csrf=csrf),json={'client_request_id':str(uuid4()),'expected_revision':1,'config':config(name='동시 수정 '+str(i))})
    with ThreadPoolExecutor(max_workers=2) as pool:replies=list(pool.map(send,range(2)))
    assert sorted(x.status_code for x in replies)==[201,409]
    assert client.get('/api/v1/admin/assets/'+aid,headers=headers(f)).json()['data']['latest_revision']==2


def test_db_bypass_and_version_mutation_denied(db_fixture):
    f=db_fixture
    for role in ['ai_web','ai_index','ai_meter']:
        with f.role_connection(role) as conn:
            for table in ['assets','asset_versions','asset_registry_records']:
                with pytest.raises(psycopg.errors.InsufficientPrivilege):conn.execute('SELECT * FROM portal.'+table)
            if role!='ai_web':
                with pytest.raises(psycopg.errors.InsufficientPrivilege):conn.execute("SELECT security.asset_registry(NULL,NULL,'list',NULL,'{}',NULL)")
    with f.db.admin_connection() as conn:
        for privilege in ['UPDATE','DELETE']:
            assert not conn.execute("SELECT has_table_privilege('ai_policy_executor','portal.asset_versions',%s)",(privilege,)).fetchone()[0]


def test_revocation_and_audit_failure_roll_back(client,login,db_fixture):
    f=db_fixture;aid=create(client,login,f,actor='P-A').json()['data']['asset_id'];csrf=client.get('/api/v1/auth/me').json()['data']['csrf_token'];h=headers(f,csrf=csrf)
    body={'client_request_id':str(uuid4()),'expected_revision':1,'config':config(name='회수 후 변경')}
    with f.db.admin_connection() as conn:conn.execute('UPDATE security.managed_tenants SET active=false WHERE tenant_id=%s AND user_id=%s',(f.tenant_ids['A'],f.actor_ids['P-A']))
    assert client.post('/api/v1/admin/assets/'+aid+'/versions',headers=h,json=body).status_code==403
    with f.db.admin_connection() as conn:
        conn.execute('UPDATE security.managed_tenants SET active=true WHERE tenant_id=%s AND user_id=%s',(f.tenant_ids['A'],f.actor_ids['P-A']))
        conn.execute("CREATE FUNCTION security.fail_asset_audit() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN IF NEW.action LIKE 'asset.%%' THEN RAISE EXCEPTION 'audit rejected'; END IF; RETURN NEW; END $$")
        conn.execute('CREATE TRIGGER fail_asset_audit BEFORE INSERT ON ops.audit_events FOR EACH ROW EXECUTE FUNCTION security.fail_asset_audit()')
    assert client.post('/api/v1/admin/assets/'+aid+'/versions',headers=h,json=body).status_code==503
    assert client.get('/api/v1/admin/assets/'+aid,headers=h).json()['data']['latest_revision']==1
    assert create(client,login,f).status_code==503
    with f.db.admin_connection() as conn:assert conn.execute('SELECT count(*) FROM portal.assets').fetchone()[0]==1


def test_unapproved_dynamic_asset_cannot_execute(client,login,db_fixture):
    f=db_fixture;aid=create(client,login,f).json()['data']['asset_id'];csrf=login(client,'A-U1')['csrf_token']
    reply=client.post('/api/v1/runs',headers=headers(f,csrf=csrf),json={'client_send_id':str(uuid4()),'agent_key':aid,'prompt':'합성 실행 거부 확인'})
    assert reply.status_code==422
    with f.db.admin_connection() as conn:assert conn.execute('SELECT count(*) FROM ops.call_attempts').fetchone()[0]==0


def test_versions_survive_http_restart(running_server):
    import httpx
    live=running_server;f=live.fixture
    with httpx.Client(base_url='http://127.0.0.1:8000',timeout=12,trust_env=False) as client:
        csrf=live.login(client,'A-ADM');h=headers(f,csrf=csrf)
        body={'client_request_id':str(uuid4()),'config':config()}
        created=client.post('/api/v1/admin/assets',headers=h,json=body);assert created.status_code==201;aid=created.json()['data']['asset_id']
        live.restart()
        assert client.post('/api/v1/admin/assets',headers=h,json=body).json()['data']['asset_id']==aid
        new={'client_request_id':str(uuid4()),'expected_revision':1,'config':config(name='재시작 수정')}
        assert client.post('/api/v1/admin/assets/'+aid+'/versions',headers=h,json=new).status_code==201
        live.restart()
        assert client.get('/api/v1/admin/assets/'+aid,headers=h).json()['data']['latest_revision']==2
        assert client.post('/api/v1/admin/assets/'+aid+'/versions',headers=h,json=new).json()['data']['replayed']


@pytest.mark.parametrize('actor',['A-U1','P_READ_ONLY','B-ADM'])
def test_direct_rpc_cannot_bypass_fresh_tenant_authority(db_fixture,actor):
    from psycopg.types.json import Jsonb
    f=db_fixture
    with f.role_connection('ai_web') as conn:
        with conn.transaction():
            for key,value in [('app.user_id',f.actor_ids[actor]),('app.session_id',f.state.session_ids[actor]),('app.tenant_id',f.tenant_ids['A'])]:
                conn.execute('SELECT set_config(%s,%s,true)',(key,str(value)))
            with pytest.raises(psycopg.Error) as error:
                conn.execute("SELECT security.asset_registry(%s,%s,'create',%s,%s,%s)",(f.state.session_ids[actor],f.tenant_ids['A'],uuid4(),Jsonb({'client_request_id':str(uuid4()),'config':config()}),uuid4()))
            assert error.value.sqlstate=='A0403'
    with f.db.admin_connection() as conn:assert conn.execute('SELECT count(*) FROM portal.assets').fetchone()[0]==0
