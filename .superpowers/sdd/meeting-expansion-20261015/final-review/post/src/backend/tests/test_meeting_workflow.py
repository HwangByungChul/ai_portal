import json
from uuid import UUID,uuid4
from dataclasses import replace
import pytest
from app.db import open_meter_pool
from app.errors import AppError
from app.use_cases.service import UseCaseExecutionService
from app.use_cases.meeting import meeting_contract
from test_operations import ops_rows
from test_workflow_runtime import prepared,wait,CountingProvider

MEMO='자료를 검토하기로 했다.'
RESULT={'decisions':[{'text':'자료 검토','quote':MEMO,'source_ref':'memo'}],'unresolved':[],'actions':[]}

class MeetingProvider(CountingProvider):
    async def generate(self,*args):return replace(await super().generate(*args),body=json.dumps(RESULT,ensure_ascii=False))

async def bind(f,repo,version,definition,user,approver):
    owner=await f.context('A-ADM','A')
    body={'workflow_id':definition['workflow_id'],'client_request_id':str(uuid4()),'definition':definition,'version_digest':repo.digest(definition),'audience':'all','member_ids':[],'expected_head_revision':1,'use_case_id':'AGENT_03','expected_use_case_revision':0}
    proposal=await repo.approval(owner,'submit',None,body,'mock')
    with pytest.raises(AppError) as rejected:await repo.approval(owner,'approve',UUID(proposal['version_id']),{'comment':'fixture review', 'expected_revision':1},'mock')
    assert rejected.value.status==403
    await repo.approval(approver,'approve',UUID(proposal['version_id']),{'comment':'fixture review', 'expected_revision':1},'mock')
    await repo.approval(approver,'approve',UUID(proposal['version_id']),{'comment':'fixture review', 'expected_revision':1},'mock')
    return proposal


def test_meeting_approval_execution_replay_current_gate_and_owner(ops_rows):
    f=ops_rows
    async def check():
        async with open_meter_pool(f.db.runtime_dsn('ai_meter')) as meter:
            repo,workflow,agent,provider,_,user,approver,version,definition=await prepared(f,meter,provider=MeetingProvider())
            service=UseCaseExecutionService(workflow)
            try:
                assert await service.ready(user,'AGENT_03') is None
                proposal=await bind(f,repo,version,definition,user,approver)
                binding=await service.ready(user,'AGENT_03')
                assert binding['version_id']==proposal['version_id'] and binding['use_case_digest']==meeting_contract()['manifest_digest']
                assert await service.ready(user,'AGENT_01') is None
                client=uuid4();run=await service.submit(user,'AGENT_03',MEMO,client)
                view=await wait(workflow,user,run['run_id'])
                assert view['state']=='completed' and view['result']==RESULT,view
                replay=await service.submit(user,'AGENT_03',MEMO,client)
                assert replay['run_id']==run['run_id'] and replay['replayed'] and provider.calls==1
                with pytest.raises(AppError) as conflict:await service.submit(user,'AGENT_03','변경 메모',client)
                assert conflict.value.status==409
                other=await f.context('A-U2','A')
                with pytest.raises(AppError):await service.read(other,'AGENT_03',UUID(run['run_id']))
                with pytest.raises(AppError):await service.read(user,'AGENT_01',UUID(run['run_id']))
                with f.db.admin_connection() as conn:
                    assert conn.execute('SELECT revision FROM portal.use_case_heads').fetchone()[0]==1
                    assert conn.execute("SELECT count(*) FROM ops.call_attempts WHERE state='settled'").fetchone()[0]>=1
                await repo.approval(approver,'revoke',None,{'workflow_id':definition['workflow_id'],'comment':'fixture review', 'expected_revision':2},'mock')
                assert await service.ready(user,'AGENT_03') is None
                assert (await service.read(user,'AGENT_03',UUID(run['run_id'])))['result'] is None
            finally:await workflow.close();await agent.close()
    f.run(check())


def test_direct_workflow_api_also_rejects_unconfirmed_meeting_output(ops_rows):
    f=ops_rows
    class InvalidProvider(CountingProvider):
        async def generate(self,*args):return replace(await super().generate(*args),body=json.dumps({'decisions':[{'text':'가짜 결정','quote':'원문에 없는 문장'}],'unresolved':[],'actions':[]}))
    async def check():
        async with open_meter_pool(f.db.runtime_dsn('ai_meter')) as meter:
            repo,workflow,agent,provider,_,user,approver,version,definition=await prepared(f,meter,provider=InvalidProvider())
            try:
                proposal=await bind(f,repo,version,definition,user,approver)
                run=await workflow.admit(user,UUID(proposal['version_id']),uuid4(),{'query':MEMO})
                view=await wait(workflow,user,run['run_id'])
                assert view['state']=='failed' and view['result'] is None and provider.calls==1,view
            finally:await workflow.close();await agent.close()
    f.run(check())


def test_meeting_parent_can_be_cancelled_before_dispatch(ops_rows):
    f=ops_rows
    async def check():
        async with open_meter_pool(f.db.runtime_dsn('ai_meter')) as meter:
            repo,workflow,agent,provider,_,user,approver,version,definition=await prepared(f,meter,provider=MeetingProvider())
            service=UseCaseExecutionService(workflow)
            try:
                await bind(f,repo,version,definition,user,approver)
                workflow.notify=lambda *args:None
                run=await service.submit(user,'AGENT_03',MEMO,uuid4())
                cancelled=await service.cancel(user,'AGENT_03',UUID(run['run_id']),run['revision'])
                assert cancelled['state']=='cancelled'
                assert (await service.read(user,'AGENT_03',UUID(run['run_id'])))['result'] is None
            finally:await workflow.close();await agent.close()
    f.run(check())


def test_actual_factory_meeting_http_csrf_poll_replay_and_owner(ops_rows,auth_settings,monkeypatch):
    import time
    from fastapi.testclient import TestClient
    from pydantic import SecretStr
    from app.main import create_app
    from support import login
    from test_operations import headers
    f=ops_rows
    async def setup():
        async with open_meter_pool(f.db.runtime_dsn('ai_meter')) as meter:
            repo,workflow,agent,_,_,user,approver,version,definition=await prepared(f,meter)
            try:await bind(f,repo,version,definition,user,approver)
            finally:await workflow.close();await agent.close()
    f.run(setup())
    monkeypatch.setattr('app.main.MockProvider',MeetingProvider)
    monkeypatch.setattr('app.ai.routing.MockProvider',MeetingProvider)
    settings=auth_settings.model_copy(update={'execution_enabled':True,'meter_dsn':SecretStr(f.db.runtime_dsn('ai_meter'))})
    with TestClient(create_app(settings),base_url='http://127.0.0.1:8000',client=('127.0.0.1',50000)) as client:
        csrf=login(client,'A-U1',f.passwords)['csrf_token'];h=headers(f,csrf=csrf)
        catalog=client.get('/api/v1/use-cases',headers=headers(f)).json()['data']['items']
        assert [row['use_case_id'] for row in catalog if row['execution_ready']]==['AGENT_03']
        path='/api/v1/use-cases/AGENT_03';body={'prompt':MEMO,'client_request_id':str(uuid4())}
        assert client.post(path+'/execute',headers=headers(f),json=body).status_code==403
        reply=client.post(path+'/execute',headers=h,json=body)
        assert reply.status_code==202,reply.text
        parent=reply.json()['data']['run_id']
        for _ in range(80):
            view=client.get(path+'/runs/'+parent,headers=headers(f))
            assert view.status_code==200,view.text
            if view.json()['data']['is_terminal']:break
            time.sleep(.05)
        assert view.json()['data']['state']=='completed' and view.json()['data']['result']==RESULT,view.text
        assert client.post(path+'/execute',headers=h,json=body).status_code==200
        assert client.get('/api/v1/use-cases/AGENT_01/runs/'+parent,headers=headers(f)).status_code==404
        login(client,'A-U2',f.passwords)
        assert client.get(path+'/runs/'+parent,headers=headers(f)).status_code==404


def test_case_head_conflict_cannot_approve_another_workflow(ops_rows):
    from copy import deepcopy
    f=ops_rows
    async def check():
        async with open_meter_pool(f.db.runtime_dsn('ai_meter')) as meter:
            repo,workflow,agent,_,_,user,approver,version,definition=await prepared(f,meter)
            owner=await f.context('A-ADM','A')
            try:
                proposals=[]
                for _ in range(2):
                    other=deepcopy(definition);other['workflow_id']=str(uuid4())
                    body={'workflow_id':other['workflow_id'],'client_request_id':str(uuid4()),'definition':other,'version_digest':repo.digest(other),'audience':'all','member_ids':[],'expected_head_revision':0,'use_case_id':'AGENT_03','expected_use_case_revision':0}
                    proposals.append(await repo.approval(owner,'submit',None,body,'mock'))
                await repo.approval(approver,'approve',UUID(proposals[0]['version_id']),{'comment':'fixture review', 'expected_revision':1},'mock')
                with pytest.raises(AppError) as conflict:await repo.approval(approver,'approve',UUID(proposals[1]['version_id']),{'comment':'fixture review', 'expected_revision':1},'mock')
                assert conflict.value.status==409
                with f.db.admin_connection() as conn:
                    assert conn.execute('SELECT status FROM portal.workflow_versions WHERE version_id=%s',(UUID(proposals[1]['version_id']),)).fetchone()[0]=='pending'
                assert (await repo.meeting(user))['version_id']==proposals[0]['version_id']
            finally:await workflow.close();await agent.close()
    f.run(check())

@pytest.mark.parametrize('bad_binding',['output_from_input','literal_only_model'])
def test_case_submission_requires_memo_to_model_and_model_to_output(ops_rows,bad_binding):
    from copy import deepcopy
    f=ops_rows
    async def check():
        async with open_meter_pool(f.db.runtime_dsn('ai_meter')) as meter:
            repo,workflow,agent,_,_,_,_,_,definition=await prepared(f,meter)
            owner=await f.context('A-ADM','A');bad=deepcopy(definition)
            if bad_binding=='output_from_input':bad['nodes'][-1]['config']['source']={'node_id':'input','path':[]}
            else:bad['nodes'][1]['config']['values']['question']='고정 메모'
            body={'workflow_id':bad['workflow_id'],'client_request_id':str(uuid4()),'definition':bad,'version_digest':repo.digest(bad),'audience':'all','member_ids':[],'expected_head_revision':1,'use_case_id':'AGENT_03','expected_use_case_revision':0}
            try:
                with pytest.raises(AppError) as invalid:await repo.approval(owner,'submit',None,body,'mock')
                assert invalid.value.status==422
                with f.db.admin_connection() as conn:
                    assert conn.execute('SELECT count(*) FROM portal.workflow_versions').fetchone()[0]==1
                    assert conn.execute('SELECT count(*) FROM portal.use_case_heads').fetchone()[0]==0
            finally:await workflow.close();await agent.close()
    f.run(check())
