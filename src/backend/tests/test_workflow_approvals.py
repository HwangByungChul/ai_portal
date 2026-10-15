from uuid import uuid4
from test_operations import headers,ops_rows


def test_catalog_and_approval_queue_are_scoped(client,login,db_fixture):
    f=db_fixture
    csrf=login(client,'A-U1')['csrf_token']
    catalog=client.get('/api/v1/workflows/catalog',headers=headers(f))
    assert catalog.status_code==200 and catalog.json()['data']['items']==[]
    assert client.get('/api/v1/admin/workflow-approvals',headers=headers(f)).status_code==403
    csrf=login(client,'A-ADM')['csrf_token']
    queue=client.get('/api/v1/admin/workflow-approvals',headers=headers(f))
    assert queue.status_code==200 and queue.json()['data']['items']==[]
    login(client,'B-ADM')
    assert client.get('/api/v1/workflows/catalog',headers=headers(f,'B')).status_code==200


def test_workflow_validate_and_run_never_accept_client_execution_dag(client,login,db_fixture):
    f=db_fixture;csrf=login(client,'A-ADM')['csrf_token'];h=headers(f,csrf=csrf)
    old={'workflow':{'workflow_id':'untrusted','name':'old client DAG','nodes':[{'node_id':'i','node_type':'input','title':'질문','config':{'input_key':'query'}},{'node_id':'o','node_type':'output','title':'응답','config':{}}],'edges':[{'source_node':'i','target_node':'o'}]},'inputs':{'query':'test'}}
    blocked=client.post('/api/v1/workflows/run',headers=h,json=old)
    assert blocked.status_code==409 and blocked.json()['error']['code']=='EXECUTION_NOT_READY'
    reply=client.post('/api/v1/workflows/run',headers=h,json={'version_id':str(uuid4()),'client_request_id':str(uuid4()),'inputs':{}})
    assert reply.status_code==409 and reply.json()['error']['code']=='EXECUTION_NOT_READY'
    malformed={'definition':{'workflow_id':str(uuid4()),'name':'strict','nodes':[
      {'node_id':'input','node_type':'input','title':'입력','config':{'input_key':'query'}},
      {'node_id':'model','node_type':'llm','title':'모델','config':{'asset_id':str(uuid4()),'version_id':str(uuid4()),'publication_revision':1,'model_id':'caller-selected'}},
      {'node_id':'output','node_type':'output','title':'출력','config':{'source':{'node_id':'model'}}}],
      'edges':[{'source_node':'input','target_node':'model'},{'source_node':'model','target_node':'output'}]},
      'client_request_id':str(uuid4()),'expected_head_revision':0}
    rejected=client.post('/api/v1/admin/workflow-approvals',headers=h,json=malformed)
    assert rejected.status_code==422


def test_version_submission_idempotency_and_other_padmin_approval(client,login,ops_rows):
    from datetime import date
    from uuid import uuid4
    from app.ai.repository import CallRepository
    from app.db import open_meter_pool
    from test_published_agents import publish
    f=ops_rows
    async def setup_published():
        async with open_meter_pool(f.db.runtime_dsn('ai_meter')) as meter:
            _,saved,_,_=await publish(f,CallRepository(f.pool,meter,date(2026,10,1)))
            return saved
    saved=f.run(setup_published())
    workflow_id=str(uuid4());client_id=str(uuid4())
    definition={'workflow_id':workflow_id,'name':'승인 기반 문서 흐름','description':'fixture 검증',
      'nodes':[{'node_id':'input','node_type':'input','title':'질문','config':{'input_key':'query'}},
       {'node_id':'agent','node_type':'llm','title':'게시 Agent','config':{'asset_id':saved['asset_id'],'version_id':saved['version_id'],'publication_revision':1,'values':{'question':{'node_id':'input'}}}},
       {'node_id':'output','node_type':'output','title':'결과','config':{'source':{'node_id':'agent','path':['text']}}}],
      'edges':[{'source_node':'input','target_node':'agent'},{'source_node':'agent','target_node':'output'}], 'max_steps':3}
    body={'definition':definition,'client_request_id':client_id,'audience':'all','member_ids':[],'expected_head_revision':0}
    csrf=login(client,'A-ADM')['csrf_token'];h=headers(f,csrf=csrf);path='/api/v1/admin/workflow-approvals'
    first=client.post(path,headers=h,json=body)
    assert first.status_code==200,first.text
    first_data=first.json()['data'];assert first_data['status']=='pending' and not first_data['replayed']
    replay=client.post(path,headers=h,json=body)
    assert replay.status_code==200 and replay.json()['data']['version_id']==first_data['version_id'] and replay.json()['data']['replayed']
    version_id=first_data['version_id']
    assert client.post(path+'/'+version_id+'/decision',headers=h,json={'decision':'approve','comment':'fixture review', 'expected_revision':1}).status_code==403
    approver=login(client,'P-A')['csrf_token'];ah=headers(f,csrf=approver)
    approved=client.post(path+'/'+version_id+'/decision',headers=ah,json={'decision':'approve','comment':'fixture review', 'expected_revision':1})
    assert approved.status_code==200 and approved.json()['data']['status']=='approved' and approved.json()['data']['revision']==2 and approved.json()['data']['version_revision']==1
    catalog=client.get('/api/v1/workflows/catalog',headers=headers(f))
    items=catalog.json()['data']['items'];assert len(items)==1 and items[0]['version_id']==version_id
    with f.db.admin_connection() as conn:
        assert conn.execute("SELECT count(*) FROM ops.audit_events WHERE action='workflow.approved'").fetchone()[0]==1
        row=conn.execute('SELECT revision,decision_revision,status FROM portal.workflow_versions WHERE version_id=%s',(version_id,)).fetchone()
        assert row==(1,2,'approved')
