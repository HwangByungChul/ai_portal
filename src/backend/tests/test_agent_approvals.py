from uuid import uuid4
from concurrent.futures import ThreadPoolExecutor
import psycopg
import pytest
from test_operations import headers, stored_agent, ops_rows
from test_auth_restart import running_server


def proposal(**changes):
    return {'client_request_id': str(uuid4()), 'agent_key': 'general', 'expected_revision': 1,
            'name': '새 승인 설정', 'description': '합성 배포 검증', 'instructions': '합성 지시문', 'reason': '합성 변경 목적', **changes}


def submit(client, login, f, actor='A-ADM', body=None):
    csrf = login(client, actor)['csrf_token']
    return client.post('/api/v1/admin/agent-deployments', headers=headers(f, csrf=csrf), json=body or proposal())


def decide(client, login, f, request_id, actor='P-A', decision='approve', revision=1, comment='검토 완료'):
    csrf = login(client, actor)['csrf_token']
    return client.post('/api/v1/admin/agent-deployments/'+request_id+'/decision',
                       headers=headers(f, csrf=csrf), json={'decision': decision, 'expected_revision': revision, 'comment': comment})


def test_approval_is_atomic_idempotent_and_preserves_stop(client, login, db_fixture):
    f = db_fixture; body = proposal()
    first = submit(client, login, f, body=body)
    assert first.status_code == 201
    request_id = first.json()['data']['request_id']
    assert stored_agent(f)[1] == 1
    repeated = client.post('/api/v1/admin/agent-deployments', headers=headers(f, csrf=client.get('/api/v1/auth/me').json()['data']['csrf_token']), json=body)
    assert repeated.status_code == 200 and repeated.json()['data']['request_id'] == request_id
    changed = {**body, 'name': '다른 내용'}
    assert submit(client, login, f, body=changed).status_code == 409
    # Requester and non-PADMIN cannot decide their own or another request.
    assert decide(client, login, f, request_id, actor='A-ADM').status_code == 403
    approved = decide(client, login, f, request_id)
    assert approved.status_code == 200 and approved.json()['data']['deployed_version'] == 2
    enabled, version, settings = stored_agent(f)
    assert not enabled and version == 2 and settings['name'] == body['name']
    assert decide(client, login, f, request_id).json()['data']['replayed']
    assert stored_agent(f)[1] == 2
    assert decide(client, login, f, request_id, decision='reject').status_code == 409
    with f.db.admin_connection() as conn:
        assert conn.execute("SELECT count(*) FROM ops.audit_events WHERE action='agent_deployment_approved'").fetchone()[0] == 1


@pytest.mark.parametrize('actor,tenant,status',[('A-U1','A',403),('P_READ_ONLY','A',403),('P-A','B',403),('B-ADM','A',403)])
def test_scope_denial(client,login,db_fixture,actor,tenant,status):
    f=db_fixture;csrf=login(client,actor)['csrf_token']
    assert client.post('/api/v1/admin/agent-deployments',headers=headers(f,tenant,csrf),json=proposal()).status_code==status
    assert client.get('/api/v1/admin/agent-deployments',headers=headers(f,tenant)).status_code==status


def test_self_approval_and_cross_org_id_hidden(client,login,db_fixture):
    f=db_fixture;reply=submit(client,login,f,actor='P-A');rid=reply.json()['data']['request_id']
    assert decide(client,login,f,rid).status_code==403
    login(client,'B-ADM')
    assert client.get('/api/v1/admin/agent-deployments/'+rid,headers=headers(f,'B')).status_code==404
    assert client.get('/api/v1/admin/agent-deployments?cursor='+rid,headers=headers(f,'B')).status_code==404


def test_stale_version_reject_and_immutable_snapshot(client,login,db_fixture):
    f=db_fixture;first=submit(client,login,f);rid=first.json()['data']['request_id']
    csrf=login(client,'A-ADM')['csrf_token']
    assert client.put('/api/v1/admin/agents/general/availability',headers=headers(f,csrf=csrf),json={'enabled':False,'expected_revision':1}).status_code==200
    assert decide(client,login,f,rid).status_code==409
    assert decide(client,login,f,rid,decision='reject').status_code==200
    detail=client.get('/api/v1/admin/agent-deployments/'+rid,headers=headers(f)).json()['data']
    assert detail['status']=='rejected' and detail['current_version']==2 and detail['base_version']==1
    assert detail['proposed']['name']=='새 승인 설정' and detail['previous']!=detail['proposed']


def test_concurrent_different_proposals_only_one_deploys(client,login,db_fixture):
    f=db_fixture;rids=[submit(client,login,f).json()['data']['request_id'] for _ in range(2)]
    csrf=login(client,'P-A')['csrf_token']
    def send(rid):return client.post('/api/v1/admin/agent-deployments/'+rid+'/decision',headers=headers(f,csrf=csrf),json={'decision':'approve','expected_revision':1,'comment':'동시 승인 검증'})
    with ThreadPoolExecutor(max_workers=2) as pool:replies=list(pool.map(send,rids))
    assert sorted(r.status_code for r in replies)==[200,409]
    assert stored_agent(f)[1]==2


def test_direct_http_and_db_bypass_denied(client,login,db_fixture):
    f=db_fixture;csrf=login(client,'A-ADM')['csrf_token']
    reply=client.patch('/api/v1/admin/agents/general',headers=headers(f,csrf=csrf),json={'name':'우회 변경','expected_revision':1})
    assert reply.status_code==409 and reply.json()['error']['code']=='APPROVAL_REQUIRED'
    with f.role_connection('ai_web') as conn:
        for statement in ['SELECT * FROM portal.agent_deployments','UPDATE portal.agent_deployments SET status=\'approved\'',"SELECT security.operations_mutate_internal(NULL,NULL,NULL,NULL,NULL,NULL,NULL,NULL,NULL)"]:
            with pytest.raises(psycopg.errors.InsufficientPrivilege):
                conn.execute(statement)
    for role in ['ai_index','ai_meter']:
        with f.role_connection(role) as conn:
            with pytest.raises(psycopg.errors.InsufficientPrivilege):
                conn.execute("SELECT security.agent_deployment(NULL,NULL,'list',NULL,'{}','2026-10-01','mock',NULL)")
    assert stored_agent(f)[1]==1


@pytest.mark.parametrize('change',[{'name':' '},{'instructions':'i'*2001},{'reason':''},{'expected_revision':True},{'expected_revision':'1'},{'role':'PADMIN'},{'name':'\x00'},{'model':'external'}])
def test_strict_payload(client,login,db_fixture,change):
    f=db_fixture;csrf=login(client,'A-ADM')['csrf_token']
    reply=client.post('/api/v1/admin/agent-deployments',headers=headers(f,csrf=csrf),json=proposal(**change))
    assert reply.status_code==422
    assert '합성 지시문' not in reply.text


def test_listing_pagination_redacts_instructions(client,login,db_fixture):
    f=db_fixture
    for _ in range(3):assert submit(client,login,f).status_code==201
    reply=client.get('/api/v1/admin/agent-deployments?limit=2',headers=headers(f))
    assert reply.status_code==200 and 'instructions' not in reply.text and '합성 지시문' not in reply.text
    data=reply.json()['data'];assert len(data['items'])==2 and data['next_cursor']
    second=client.get('/api/v1/admin/agent-deployments?limit=2&cursor='+data['next_cursor'],headers=headers(f)).json()['data']
    assert len(second['items'])==1 and second['next_cursor'] is None
    assert {x['request_id'] for x in data['items']}.isdisjoint({x['request_id'] for x in second['items']})


def test_revoked_approval_and_failed_audit_roll_back(client,login,db_fixture):
    f=db_fixture;rid=submit(client,login,f).json()['data']['request_id']
    csrf=login(client,'P-A')['csrf_token']
    with f.db.admin_connection() as conn:
        conn.execute("UPDATE security.managed_tenants SET active=false WHERE tenant_id=%s AND user_id=%s",(f.tenant_ids['A'],f.actor_ids['P-A']))
    assert client.post('/api/v1/admin/agent-deployments/'+rid+'/decision',headers=headers(f,csrf=csrf),json={'decision':'approve','expected_revision':1,'comment':'권한 회수 검증'}).status_code==403
    with f.db.admin_connection() as conn:
        conn.execute("UPDATE security.managed_tenants SET active=true WHERE tenant_id=%s AND user_id=%s",(f.tenant_ids['A'],f.actor_ids['P-A']))
        conn.execute("CREATE FUNCTION security.fail_deployment_audit() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN IF NEW.action='agent_deployment_approved' THEN RAISE EXCEPTION 'audit rejected'; END IF; RETURN NEW; END $$")
        conn.execute('CREATE TRIGGER fail_deployment_audit BEFORE INSERT ON ops.audit_events FOR EACH ROW EXECUTE FUNCTION security.fail_deployment_audit()')
    assert decide(client,login,f,rid).status_code==503
    assert stored_agent(f)[1]==1
    assert client.get('/api/v1/admin/agent-deployments/'+rid,headers=headers(f)).json()['data']['status']=='pending'


def test_approved_settings_are_sealed_in_next_run(client,login,ops_rows):
    f=ops_rows;rid=submit(client,login,f).json()['data']['request_id']
    assert decide(client,login,f,rid).status_code==200
    csrf=login(client,'A-U1')['csrf_token']
    reply=client.post('/api/v1/runs',headers=headers(f,csrf=csrf),json={'client_send_id':str(uuid4()),'agent_key':'general','prompt':'합성 스냅샷 확인'})
    assert reply.status_code==202 and reply.json()['data']['config_version']==2
    with f.db.admin_connection() as conn:
        value=conn.execute('SELECT config_snapshot FROM portal.runs WHERE run_id=%s',(reply.json()['data']['run_id'],)).fetchone()[0]
        assert value['instructions']=='합성 지시문'
        assert conn.execute('SELECT count(*) FROM ops.call_attempts').fetchone()[0]==0


def test_request_and_decision_survive_real_http_restart(running_server):
    import httpx
    live=running_server;f=live.fixture
    with httpx.Client(base_url='http://127.0.0.1:8000',timeout=12,trust_env=False) as requester,httpx.Client(base_url='http://127.0.0.1:8000',timeout=12,trust_env=False) as approver:
        csrf=live.login(requester,'A-ADM')
        body=proposal()
        first=requester.post('/api/v1/admin/agent-deployments',headers=headers(f,csrf=csrf),json=body)
        assert first.status_code==201;rid=first.json()['data']['request_id']
        live.restart()
        assert requester.get('/api/v1/admin/agent-deployments/'+rid,headers=headers(f)).json()['data']['status']=='pending'
        csrf=live.login(approver,'P-A');decision={'decision':'approve','expected_revision':1,'comment':'재시작 후 승인'}
        assert approver.post('/api/v1/admin/agent-deployments/'+rid+'/decision',headers=headers(f,csrf=csrf),json=decision).status_code==200
        live.restart()
        detail=approver.get('/api/v1/admin/agent-deployments/'+rid,headers=headers(f)).json()['data']
        assert detail['status']=='approved' and detail['deployed_version']==2 and detail['comment']==decision['comment']
        assert approver.post('/api/v1/admin/agent-deployments/'+rid+'/decision',headers=headers(f,csrf=csrf),json=decision).json()['data']['replayed']
        assert stored_agent(f)[1]==2
