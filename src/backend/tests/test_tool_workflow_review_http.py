from uuid import UUID,uuid4
import pytest
from app.tools.repository import ToolRepository
from app.tools.execution import ToolExecutionService
from app.tools.registry import ToolRegistry
from app.guardrails.service import GuardrailService
from app.errors import AppError
from app.approval_reviews.repository import ReviewRepository
from test_operations import headers,ops_rows

async def pending(f):
    ctx=await f.context('A-ADM','A');repo=ToolRepository(f.pool)
    service=ToolExecutionService(repo,ToolRegistry(),'mock',GuardrailService(f.pool))
    result=await repo.approval(ctx,'submit',None,{'client_request_id':str(uuid4()),'descriptor':service.descriptor('data_view_reader'),'audience':'all','member_ids':[],'expected_head_revision':0})
    return result['request_id']

def test_exact_detail_access_and_comment_decision(client,login,ops_rows):
    f=ops_rows;rid=f.run(pending(f));path='/api/v1/admin/tool-approvals/'+rid
    login(client,'A-U1');assert client.get(path,headers=headers(f)).status_code==403
    login(client,'B-ADM');assert client.get(path,headers=headers(f,'B')).status_code==404
    csrf=login(client,'A-ADM')['csrf_token'];h=headers(f,csrf=csrf)
    detail=client.get(path,headers=h);assert detail.status_code==200,detail.text
    d=detail.json()['data'];assert not d['can_approve'] and not d['can_reject'] and d['diff']['baseline_available'] is False
    assert client.post(path+'/decision',headers=h,json={'decision':'approve','expected_revision':1,'comment':'own review'}).status_code==403
    csrf=login(client,'P-A')['csrf_token'];h=headers(f,csrf=csrf)
    d=client.get(path,headers=h).json()['data'];assert d['can_approve'] and d['can_reject']
    for note in ['', '   ', 'x'*501, 'bad\u0000comment']:
        assert client.post(path+'/decision',headers=h,json={'decision':'approve','expected_revision':1,'comment':note}).status_code==422
    assert client.post(path+'/decision',headers=h,json={'decision':'approve','expected_revision':1}).status_code==422
    body={'decision':'approve','expected_revision':1,'comment':'  reviewed  '}
    approved=client.post(path+'/decision',headers=h,json=body);assert approved.status_code==200,approved.text
    assert client.post(path+'/decision',headers=h,json=body).json()['data']['replayed']
    assert client.post(path+'/decision',headers=h,json=body|{'comment':'different'}).status_code==409
    d=client.get(path,headers=h).json()['data'];assert d['history'][-1]['comment']=='reviewed' and d['can_revoke'] and d['validation']['valid']
    revoked=client.post('/api/v1/admin/tools/data_view_reader/revoke',headers=h,json={'expected_revision':1,'comment':'retired'})
    assert revoked.status_code==200,revoked.text
    assert client.post('/api/v1/admin/tools/data_view_reader/revoke',headers=h,json={'expected_revision':1,'comment':'retired'}).json()['data']['replayed']
    d=client.get(path,headers=h).json()['data'];assert d['request']['status']=='approved' and d['current_head']['enabled'] is False and d['history'][-1]['action']=='revoke' and not d['validation']['valid']

def test_scoped_pages_search_and_more_than_fifty_deep_link(client,login,ops_rows):
    f=ops_rows;rid=f.run(pending(f))
    with f.db.admin_connection() as conn:
        conn.execute("INSERT INTO portal.tool_approvals(tenant_id,request_id,requester_id,client_request_id,tool_id,descriptor,request_body,audience,member_ids,expected_head_revision) SELECT tenant_id,gen_random_uuid(),requester_id,gen_random_uuid(),tool_id,descriptor,request_body,audience,member_ids,0 FROM portal.tool_approvals CROSS JOIN generate_series(1,60) WHERE request_id=%s",(rid,))
    login(client,'P-A');h=headers(f);path='/api/v1/admin/tool-approvals'
    first=client.get(path+'?limit=20&status=pending',headers=h).json()['data'];assert len(first['items'])==20 and first['next_cursor']
    second=client.get(path,headers=h,params={'limit':20,'status':'pending','cursor':first['next_cursor']}).json()['data']
    assert not set(x['request_id'] for x in first['items'])&set(x['request_id'] for x in second['items'])
    assert client.get(path+'/'+rid,headers=h).status_code==200
    for params in [{'cursor':first['next_cursor']+'x','status':'pending'},{'cursor':first['next_cursor'],'status':'approved'},{'limit':51},{'q':'x'*121}]:assert client.get(path,headers=h,params=params).status_code==422
    exact=client.get(path,headers=h,params={'q':rid}).json()['data'];assert len(exact['items'])==1 and exact['items'][0]['request_id']==rid
    assert client.get(path+'?limit=1&limit=2',headers=h).status_code==422

def test_review_and_audit_failure_rollback(db_fixture):
    f=db_fixture;rid=f.run(pending(f))
    async def decide():
        ctx=await f.context('P-A','A');return await ToolRepository(f.pool).approval(ctx,'approve',rid,{'expected_revision':1,'comment':'review'})
    with f.db.admin_connection() as conn:conn.execute('DROP POLICY review_scope ON portal.approval_reviews')
    with pytest.raises(AppError) as err:f.run(decide())
    assert err.value.status==503
    with f.db.admin_connection() as conn:
        assert conn.execute('SELECT status,revision FROM portal.tool_approvals WHERE request_id=%s',(rid,)).fetchone()==('pending',1)
        assert conn.execute("SELECT count(*) FROM ops.audit_events WHERE action='tool.approved'").fetchone()[0]==0
        assert conn.execute('SELECT count(*) FROM portal.tool_heads').fetchone()[0]==0

def test_audit_failure_rollback_leaves_no_review(db_fixture):
    f=db_fixture;rid=f.run(pending(f))
    with f.db.admin_connection() as conn:
        conn.execute("CREATE FUNCTION ops.reject_test_audit() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN IF NEW.action='tool.approved' THEN RAISE EXCEPTION 'TEST_AUDIT_FAILURE';END IF;RETURN NEW;END;$$")
        conn.execute('CREATE TRIGGER reject_test_audit BEFORE INSERT ON ops.audit_events FOR EACH ROW EXECUTE FUNCTION ops.reject_test_audit()')
    async def check():
        ctx=await f.context('P-A','A');return await ToolRepository(f.pool).approval(ctx,'approve',rid,{'expected_revision':1,'comment':'review'})
    with pytest.raises(AppError):f.run(check())
    with f.db.admin_connection() as conn:
        assert conn.execute('SELECT count(*) FROM portal.approval_reviews').fetchone()[0]==0
        assert conn.execute('SELECT status FROM portal.tool_approvals WHERE request_id=%s',(rid,)).fetchone()[0]=='pending'

def test_support_and_strict_validation_auth(client,login,ops_rows):
    f=ops_rows;login(client,'A-U1')
    for kind in ['tool','workflow']:assert client.get('/api/v1/admin/'+kind+'-approvals/submission-support',headers=headers(f)).status_code==403
    login(client,'A-ADM')
    tools=client.get('/api/v1/admin/tool-approvals/submission-support',headers=headers(f));assert tools.status_code==200,tools.text
    assert len(tools.json()['data']['items'])==3
    flows=client.get('/api/v1/admin/workflow-approvals/submission-support',headers=headers(f));assert flows.status_code==200,flows.text
    assert flows.json()['data']['meeting_contract']['use_case_id']=='AGENT_03'


def test_workflow_manifest_current_dependency_and_rejection(ops_rows):
    from app.db import open_meter_pool
    from app.assets.deployments import DeploymentRepository
    from app.use_cases.meeting import meeting_contract
    from test_workflow_runtime import prepared
    f=ops_rows
    async def check():
        async with open_meter_pool(f.db.runtime_dsn('ai_meter')) as meter:
            repo,service,agent,_,_,user,approver,version,definition=await prepared(f,meter)
            try:
                owner=await f.context('A-ADM','A')
                proposal=await repo.approval(owner,'submit',None,{'workflow_id':definition['workflow_id'],'client_request_id':str(uuid4()),'definition':definition,'version_digest':repo.digest(definition),'audience':'all','member_ids':[],'expected_head_revision':1,'use_case_id':'AGENT_03','expected_use_case_revision':0},'mock')
                reviews=ReviewRepository(repo,'workflow');detail=await reviews.detail(approver,UUID(proposal['version_id']))
                assert detail['request']['manifest_snapshot']==meeting_contract() and detail['can_approve']
                assert detail['request']['use_case_digest']==meeting_contract()['manifest_digest']
                assert (await reviews.detail(approver,UUID(version['version_id'])))['request']['manifest_snapshot'] is None
                asset=next(n['config']['asset_id'] for n in definition['nodes'] if n['node_type']=='llm')
                await DeploymentRepository(f.pool).call(approver,'retire',UUID(asset),{'expected_revision':1},'mock')
                detail=await reviews.detail(approver,UUID(proposal['version_id']))
                assert not detail['can_approve'] and detail['can_reject'] and any(x['code']=='DEPENDENCY_UNAVAILABLE' for x in detail['validation']['checks'])
                with pytest.raises(AppError):await repo.approval(approver,'approve',UUID(proposal['version_id']),{'expected_revision':1,'comment':'review'},'mock')
                rejected=await repo.approval(approver,'reject',UUID(proposal['version_id']),{'expected_revision':1,'comment':'dependency unavailable'},'mock')
                assert rejected['status']=='rejected'
                replay=await repo.approval(approver,'reject',UUID(proposal['version_id']),{'expected_revision':1,'comment':'dependency unavailable'},'mock');assert replay['replayed']
                with pytest.raises(AppError) as err:await repo.approval(approver,'reject',UUID(proposal['version_id']),{'expected_revision':1,'comment':'changed'},'mock')
                assert err.value.status==409
            finally:await service.close();await agent.close()
    f.run(check())


def test_legacy_decision_comment_missing_and_review_append_only(db_fixture):
    import psycopg
    f=db_fixture;rid=f.run(pending(f))
    with f.db.admin_connection() as conn:
        conn.execute("UPDATE portal.tool_approvals SET status='approved',revision=2,decided_by=%s,decided_at=clock_timestamp() WHERE request_id=%s",(f.actor_ids['P-A'],rid))
    async def read():
        ctx=await f.context('P-A','A');return await ReviewRepository(ToolRepository(f.pool),'tool').detail(ctx,UUID(rid))
    data=f.run(read());assert data['history'][-1]['action']=='approved' and data['history'][-1]['comment'] is None
    async def replay():
        ctx=await f.context('P-A','A');return await ToolRepository(f.pool).approval(ctx,'approve',rid,{'expected_revision':1,'comment':'cannot backfill'})
    with pytest.raises(AppError) as err:f.run(replay())
    assert err.value.status==409
    with f.db.admin_connection() as conn:
        assert conn.execute('SELECT count(*) FROM portal.approval_reviews').fetchone()[0]==0
        conn.execute("INSERT INTO portal.approval_reviews(tenant_id,kind,target_id,actor_id,action,expected_revision,comment,result) VALUES(%s,'tool',%s,%s,'approve',1,'review','{}')",(f.tenant_ids['A'],rid,f.actor_ids['P-A']))
        for statement in ['UPDATE portal.approval_reviews SET comment=comment','DELETE FROM portal.approval_reviews']:
            with pytest.raises(psycopg.errors.CheckViolation):
                with conn.transaction():conn.execute(statement)


@pytest.mark.parametrize('initial,current',[('mock','real'),('real','mock')])
def test_tool_decision_uses_current_server_mode(client,login,ops_rows,initial,current):
    f=ops_rows
    async def submit():
        ctx=await f.context('A-ADM','A');repo=ToolRepository(f.pool)
        service=ToolExecutionService(repo,ToolRegistry(),initial,None)
        return await repo.approval(ctx,'submit',None,{'client_request_id':str(uuid4()),'descriptor':service.descriptor('data_view_reader'),'audience':'all','member_ids':[],'expected_head_revision':0})
    rid=f.run(submit())['request_id'];path='/api/v1/admin/tool-approvals/'+rid
    client.app.state.settings.mode=current
    client.app.state.tool_control.mode=current
    csrf=login(client,'P-A')['csrf_token'];h=headers(f,csrf=csrf)
    assert not client.get(path,headers=h).json()['data']['can_approve']
    body={'decision':'approve','expected_revision':1,'comment':'current contract review'}
    result=client.post(path+'/decision',headers=h,json=body)
    assert result.status_code==409,result.text
    with f.db.admin_connection() as conn:
        assert conn.execute('SELECT status FROM portal.tool_approvals WHERE request_id=%s',(rid,)).fetchone()[0]=='pending'
        assert conn.execute('SELECT count(*) FROM portal.tool_heads').fetchone()[0]==0
        assert conn.execute('SELECT count(*) FROM portal.approval_reviews').fetchone()[0]==0
    assert client.post(path+'/decision',headers=h,json=body|{'decision':'reject'}).status_code==200


@pytest.mark.parametrize('revocation',['membership','account'])
def test_tool_current_audience_required_at_decision(client,login,ops_rows,revocation):
    f=ops_rows
    async def submit():
        ctx=await f.context('A-ADM','A');repo=ToolRepository(f.pool)
        descriptor=ToolExecutionService(repo,ToolRegistry(),'mock',None).descriptor('data_view_reader')
        return await repo.approval(ctx,'submit',None,{'client_request_id':str(uuid4()),'descriptor':descriptor,'audience':'restricted','member_ids':[str(f.actor_ids['A-U1'])],'expected_head_revision':0})
    rid=f.run(submit())['request_id'];path='/api/v1/admin/tool-approvals/'+rid
    csrf=login(client,'P-A')['csrf_token'];h=headers(f,csrf=csrf)
    assert client.get(path,headers=h).json()['data']['can_approve']
    with f.db.admin_connection() as conn:
        if revocation=='account':conn.execute('UPDATE security.accounts SET active=false WHERE user_id=%s',(f.actor_ids['A-U1'],))
        elif revocation=='membership':conn.execute('UPDATE security.memberships SET active=false WHERE tenant_id=%s AND user_id=%s',(f.tenant_ids['A'],f.actor_ids['A-U1']))
    detail=client.get(path,headers=h).json()['data'];assert not detail['can_approve'] and detail['can_reject']
    body={'decision':'approve','expected_revision':1,'comment':'audience review'}
    result=client.post(path+'/decision',headers=h,json=body);assert result.status_code==409,result.text
    with f.db.admin_connection() as conn:
        assert conn.execute('SELECT status FROM portal.tool_approvals WHERE request_id=%s',(rid,)).fetchone()[0]=='pending'
        assert conn.execute('SELECT count(*) FROM portal.tool_heads').fetchone()[0]==0
        assert conn.execute('SELECT count(*) FROM portal.approval_reviews').fetchone()[0]==0
        assert conn.execute("SELECT count(*) FROM ops.audit_events WHERE action='tool.approved'").fetchone()[0]==0
    assert client.post(path+'/decision',headers=h,json=body|{'decision':'reject'}).status_code==200


def test_strict_workflow_validation_http(client,login,ops_rows):
    from copy import deepcopy
    f=ops_rows;path='/api/v1/workflows/approved/validate'
    definition={'workflow_id':str(uuid4()),'name':'typed graph','nodes':[
        {'node_id':'input','node_type':'input','title':'입력','config':{}},
        {'node_id':'agent','node_type':'llm','title':'Agent','config':{'asset_id':str(uuid4()),'version_id':str(uuid4()),'publication_revision':1,'values':{'question':{'node_id':'input'}}}},
        {'node_id':'output','node_type':'output','title':'출력','config':{'source':{'node_id':'agent','path':['text']}}}],
        'edges':[{'source_node':'input','target_node':'agent'},{'source_node':'agent','target_node':'output'}]}
    csrf=login(client,'A-U1')['csrf_token']
    assert client.post(path,headers=headers(f,csrf=csrf),json=definition).status_code==403
    csrf=login(client,'A-ADM')['csrf_token'];h=headers(f,csrf=csrf)
    assert client.post(path,headers=headers(f),json=definition).status_code==403
    result=client.post(path,headers=h,json=definition);assert result.status_code==200,result.text
    assert result.json()['data']['execution_order']==['input','agent','output']
    malformed=deepcopy(definition);malformed['nodes'][1]['config']['values']['question']={'node_id':'output'}
    assert client.post(path,headers=h,json=malformed).status_code==422
    cycle=deepcopy(definition);cycle['edges'].append({'source_node':'output','target_node':'agent'})
    assert client.post(path,headers=h,json=cycle).status_code==422


def test_workflow_audience_revoked_before_decision(ops_rows):
    from app.db import open_meter_pool
    from test_workflow_runtime import prepared
    f=ops_rows
    async def check():
        async with open_meter_pool(f.db.runtime_dsn('ai_meter')) as meter:
            repo,service,agent,_,_,user,approver,version,definition=await prepared(f,meter)
            try:
                owner=await f.context('A-ADM','A')
                proposal=await repo.approval(owner,'submit',None,{'workflow_id':definition['workflow_id'],'client_request_id':str(uuid4()),'definition':definition,'version_digest':repo.digest(definition),'audience':'restricted','member_ids':[str(f.actor_ids['A-U1'])],'expected_head_revision':1},'mock')
                target=UUID(proposal['version_id']);reviews=ReviewRepository(repo,'workflow')
                assert (await reviews.detail(approver,target))['can_approve']
                with f.db.admin_connection() as conn:conn.execute('UPDATE security.memberships SET active=false WHERE tenant_id=%s AND user_id=%s',(f.tenant_ids['A'],f.actor_ids['A-U1']))
                assert not (await reviews.detail(approver,target))['can_approve']
                with pytest.raises(AppError) as error:await repo.approval(approver,'approve',target,{'expected_revision':1,'comment':'review'},'mock')
                assert error.value.status==409
                with f.db.admin_connection() as conn:
                    assert conn.execute('SELECT status FROM portal.workflow_versions WHERE version_id=%s',(target,)).fetchone()[0]=='pending'
                    assert conn.execute('SELECT count(*) FROM portal.approval_reviews WHERE target_id=%s',(target,)).fetchone()[0]==0
                    assert conn.execute('SELECT version_id FROM portal.workflow_heads WHERE workflow_id=%s',(definition['workflow_id'],)).fetchone()[0]==UUID(version['version_id'])
                assert (await repo.approval(approver,'reject',target,{'expected_revision':1,'comment':'audience unavailable'},'mock'))['status']=='rejected'
            finally:await service.close();await agent.close()
    f.run(check())

def test_approved_workflow_current_head_and_case_identity(ops_rows):
    from app.db import open_meter_pool
    from test_workflow_runtime import prepared
    f=ops_rows
    async def check():
        async with open_meter_pool(f.db.runtime_dsn('ai_meter')) as meter:
            repo,service,agent,_,_,user,approver,version,definition=await prepared(f,meter)
            try:
                owner=await f.context('A-ADM','A');reviews=ReviewRepository(repo,'workflow')
                async def submit(head,case):
                    return await repo.approval(owner,'submit',None,{'workflow_id':definition['workflow_id'],'client_request_id':str(uuid4()),'definition':definition,'version_digest':repo.digest(definition),'audience':'all','member_ids':[],'expected_head_revision':head,'use_case_id':'AGENT_03','expected_use_case_revision':case},'mock')
                first=await submit(1,0);target=UUID(first['version_id']);stale=await submit(1,0)
                await repo.approval(approver,'approve',target,{'expected_revision':1,'comment':'approved current'},'mock')
                assert (await reviews.detail(approver,target))['validation']['valid']
                detail=await reviews.detail(approver,UUID(stale['version_id']))
                assert not detail['validation']['valid'] and {'HEAD_CHANGED','CASE_CHANGED'} <= {x['code'] for x in detail['validation']['checks']}
                second=await submit(2,1);second_id=UUID(second['version_id'])
                await repo.approval(approver,'approve',second_id,{'expected_revision':1,'comment':'replacement'},'mock')
                detail=await reviews.detail(approver,target)
                assert not detail['validation']['valid'] and {'HEAD_CHANGED','CASE_CHANGED'} <= {x['code'] for x in detail['validation']['checks']}
                assert (await reviews.detail(approver,second_id))['validation']['valid']
                await repo.approval(approver,'revoke',None,{'workflow_id':definition['workflow_id'],'expected_revision':3,'comment':'retired'},'mock')
                assert not (await reviews.detail(approver,second_id))['validation']['valid']
            finally:await service.close();await agent.close()
    f.run(check())


def test_dynamic_tool_registration_review_replay_and_fail_closed(client, login, ops_rows):
    from uuid import uuid4

    f = ops_rows
    csrf = login(client, 'A-ADM')['csrf_token']
    h = headers(f, csrf=csrf)
    tool_id = 'dynamic_review_gate_test'
    registration = {
        'tool_id': tool_id,
        'name': '격리 검토 테스트 도구',
        'description': '동적 승인 gate HTTP 검증용 합성 Tool',
        'source_type': 'custom_mcp',
        'input_schema': {'type': 'object', 'properties': {'query': {'type': 'string'}}},
        'raw_meta': {'test_fixture': True},
        'dev_profile': {'base_endpoint_url': 'https://dev.example.invalid/mcp'},
        'prd_profile': {'base_endpoint_url': 'https://prd.example.invalid/mcp'},
    }
    registered = client.post('/api/v1/tools/auto-wrap/register', headers=h, json=registration)
    assert registered.status_code == 200, registered.text

    support = client.get('/api/v1/admin/tool-approvals/submission-support', headers=h)
    assert support.status_code == 200, support.text
    item = next(x for x in support.json()['data']['items'] if x['tool_id'] == tool_id)
    assert item['dynamic'] is True and item['risk_class'] == 'financial_side_effect'
    assert item['execution_ready'] is False

    body = {
        'tool_id': tool_id,
        'client_request_id': str(uuid4()),
        'audience': 'all',
        'member_ids': [],
        'expected_head_revision': 0,
    }
    submitted = client.post('/api/v1/admin/tool-approvals', headers=h, json=body)
    assert submitted.status_code == 200, submitted.text
    result = submitted.json()['data']
    assert result['status'] == 'pending' and result['replayed'] is False
    assert result['execution_ready'] is False
    request_id = result['request_id']

    replay = client.post('/api/v1/admin/tool-approvals', headers=h, json=body)
    assert replay.status_code == 200, replay.text
    assert replay.json()['data']['request_id'] == request_id
    assert replay.json()['data']['replayed'] is True

    login(client, 'B-ADM')
    other_tenant = client.get(f'/api/v1/admin/tool-approvals/{request_id}', headers=headers(f, 'B'))
    assert other_tenant.status_code == 404, other_tenant.text

    csrf = login(client, 'P-A')['csrf_token']
    h = headers(f, csrf=csrf)
    detail = client.get(f'/api/v1/admin/tool-approvals/{request_id}', headers=h)
    assert detail.status_code == 200, detail.text
    assert detail.json()['data']['can_approve'] is False
    assert detail.json()['data']['request']['descriptor']['risk_policy_id'] == 'dynamic-default-v1'
    assert detail.json()['data']['request']['descriptor']['approval_scope'] == 'registration_review_only'
    approved = client.post(f'/api/v1/admin/tool-approvals/{request_id}/decision', headers=h,
                           json={'decision': 'approve', 'expected_revision': 1, 'comment': '위험 분류 확인'})
    assert approved.status_code == 409 and approved.json()['error']['code'] == 'TOOL_DYNAMIC_REVIEW_ONLY'

    import psycopg
    with f.db.admin_connection() as conn:
        with pytest.raises(psycopg.Error, match='TOOL_DYNAMIC_REVIEW_ONLY'):
            conn.execute("UPDATE portal.tool_approvals SET status='approved' WHERE request_id=%s", (request_id,))

    rejected = client.post(f'/api/v1/admin/tool-approvals/{request_id}/decision', headers=h,
                           json={'decision': 'reject', 'expected_revision': 1, 'comment': '격리 검증 반려'})
    assert rejected.status_code == 200, rejected.text
    assert rejected.json()['data']['status'] == 'rejected'
