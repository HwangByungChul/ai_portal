import asyncio
from datetime import date
from uuid import UUID,uuid4
from dataclasses import replace
import pytest
import psycopg
from app.ai.repository import CallRepository
from app.ai.providers import MockProvider
from app.db import open_meter_pool
from app.execution.manager import ExecutionManager
from app.execution.stream import StreamHub
from app.guardrails.service import GuardrailService
from app.tools.adapters import FixtureToolAdapter
from app.tools.registry import ToolRegistry
from app.tools.repository import ToolRepository
from app.tools.execution import ToolExecutionService
from app.workflows.repository import WorkflowRepository,WorkflowToolRepository
from app.workflows.service import WorkflowExecutionService
from app.workflows.bindings import child_request_id
from app.errors import AppError
from test_operations import ops_rows,headers
from test_published_agents import publish

class CountingProvider(MockProvider):
    def __init__(self):self.calls=0
    async def generate(self,*args):self.calls+=1;return await super().generate(*args)

class CountingTools(FixtureToolAdapter):
    def __init__(self):self.calls=0
    def handle_data_view_reader(self,args):self.calls+=1;return super().handle_data_view_reader(args)

async def prepared(f,meter,provider=None,tool=False,missing_values=False,pii_literal=False):
    calls=CallRepository(f.pool,meter,date(2026,10,1))
    owner,saved,_,_=await publish(f,calls)
    guardrails=GuardrailService(f.pool);adapter=CountingTools()
    tools=ToolExecutionService(ToolRepository(f.pool),ToolRegistry(adapter=adapter),'mock',guardrails)
    approver=await f.context('P-A','A');user=await f.context('A-U1','A')
    values={'question':{'node_id':'input'}}
    if not missing_values:values.update({'audience':'010-1234-5678' if pii_literal else '담당자','rule':'기준'})
    nodes=[{'node_id':'input','node_type':'input','title':'입력','config':{'input_key':'query'}}]
    if tool:
        descriptor=tools.descriptor('data_view_reader')
        proposal=await tools.repository.approval(owner,'submit',None,{'client_request_id':str(uuid4()),'descriptor':descriptor,'audience':'all','member_ids':[],'expected_head_revision':0})
        await tools.repository.approval(approver,'approve',proposal['request_id'],{'comment':'fixture review', 'expected_revision':1})
        nodes.append({'node_id':'tool','node_type':'read_tool','title':'읽기','config':{'tool_id':'data_view_reader','version_digest':descriptor['digest'],'arguments':{'view_name':'branch_daily_stats'}}})
    nodes += [{'node_id':'agent','node_type':'llm','title':'게시 Agent','config':{'asset_id':saved['asset_id'],'version_id':saved['version_id'],'publication_revision':1,'values':values}},
              {'node_id':'output','node_type':'output','title':'최종 결과','config':{'source':{'node_id':'agent','path':['text']}}}]
    definition={'workflow_id':str(uuid4()),'name':'fixture 승인 흐름','nodes':nodes,'edges':[{'source_node':a['node_id'],'target_node':b['node_id']} for a,b in zip(nodes,nodes[1:])]}
    from app.workflows.approved_models import ApprovedWorkflow
    definition=ApprovedWorkflow.model_validate(definition).model_dump(mode='json')
    repo=WorkflowRepository(f.pool)
    body={'workflow_id':definition['workflow_id'],'client_request_id':str(uuid4()),'definition':definition,'version_digest':repo.digest(definition),'audience':'all','member_ids':[],'expected_head_revision':0}
    proposal=await repo.approval(owner,'submit',None,body,'mock')
    await repo.approval(approver,'approve',UUID(proposal['version_id']),{'comment':'fixture review', 'expected_revision':1},'mock')
    provider=provider or CountingProvider()
    agent=ExecutionManager(calls,provider,'mock',StreamHub(),guardrails=guardrails)
    service=WorkflowExecutionService(repo,agent,tools,guardrails)
    return repo,service,agent,provider,adapter,user,approver,proposal,definition

async def wait(service,ctx,run):
    task=service.tasks.get((ctx.tenant_id,UUID(run)))
    if task:await asyncio.wait_for(asyncio.shield(task),8)
    return await service.read(ctx,UUID(run))


def test_parent_tool_agent_checkpoint_and_exact_single_meter_replay(ops_rows):
    f=ops_rows
    async def check():
        async with open_meter_pool(f.db.runtime_dsn('ai_meter')) as meter:
            repo,service,agent,provider,adapter,user,_,version,_=await prepared(f,meter,tool=True)
            try:
                client=uuid4();first=await service.admit(user,UUID(version['version_id']),client,{'query':'업무 질문'})
                view=await wait(service,user,first['run_id'])
                assert view['state']=='completed',view
                assert all(s['state']=='succeeded' for s in view['steps']) and view['result_access']=='final'
                assert provider.calls==adapter.calls==1 and '모의 AI 응답' in view['result']
                repeat=await service.admit(user,UUID(version['version_id']),client,{'query':'업무 질문'})
                assert repeat['run_id']==first['run_id'] and repeat['replayed'] and provider.calls==adapter.calls==1
                with pytest.raises(AppError) as conflict:await service.admit(user,UUID(version['version_id']),client,{'query':'변경 질문'})
                assert conflict.value.status==409
                other=await f.context('A-U2','A')
                with pytest.raises(AppError) as hidden:await service.read(other,UUID(first['run_id']))
                assert hidden.value.status==404
                assert 'inputs' not in view and 'worker_token' not in view and 'context_snapshot' not in view
                assert all('result' not in s for s in view['steps'])
                child=next(s['child_run_id'] for s in view['steps'] if s['node_type']=='llm')
                with f.db.admin_connection() as conn:
                    assert conn.execute("SELECT count(*) FROM ops.call_attempts WHERE run_id=%s AND state='settled'",(child,)).fetchone()[0]==1
                    assert conn.execute('SELECT count(*) FROM portal.workflow_runs').fetchone()[0]==1
                    assert conn.execute('SELECT count(*) FROM portal.tool_receipts').fetchone()[0]==1
                # Parent-bound receipt cannot be driven through the standalone public Tool capability.
                bound=next(s['tool_client_id'] for s in view['steps'] if s['node_type']=='read_tool')
                with pytest.raises(AppError):await service.tools.read(user,'data_view_reader',UUID(bound))
            finally:await service.close();await agent.close()
    f.run(check())


def test_workflow_revoke_after_tool_stops_child_and_hides_saved_content(ops_rows):
    f=ops_rows
    async def check():
        async with open_meter_pool(f.db.runtime_dsn('ai_meter')) as meter:
            repo,service,agent,provider,adapter,user,approver,version,definition=await prepared(f,meter,tool=True)
            original=repo.child
            async def revoke_before_child(*args,**kwargs):
                await repo.approval(approver,'revoke',None,{'workflow_id':definition['workflow_id'],'comment':'fixture review', 'expected_revision':1},'mock')
                return await original(*args,**kwargs)
            repo.child=revoke_before_child
            try:
                first=await service.admit(user,UUID(version['version_id']),uuid4(),{'query':'회수 확인'})
                view=await wait(service,user,first['run_id'])
                assert view['state']=='blocked' and provider.calls==0 and adapter.calls==1,view
                assert view['steps'][-1]['state']=='skipped' and view['result'] is None
            finally:await service.close();await agent.close()
    f.run(check())


def test_child_validation_failure_has_no_provider_or_downstream(ops_rows):
    f=ops_rows
    async def check():
        async with open_meter_pool(f.db.runtime_dsn('ai_meter')) as meter:
            _,service,agent,provider,_,user,_,version,_=await prepared(f,meter,missing_values=True)
            try:
                first=await service.admit(user,UUID(version['version_id']),uuid4(),{'query':'변수 누락'})
                view=await wait(service,user,first['run_id'])
                assert view['state']=='failed' and provider.calls==0 and view['steps'][-1]['state']=='skipped',view
                assert '변수 누락' not in str(view)
            finally:await service.close();await agent.close()
    f.run(check())


def test_parent_cancel_propagates_to_dispatched_agent_without_replay(ops_rows):
    f=ops_rows
    class WaitingProvider(CountingProvider):
        def __init__(self):super().__init__();self.started=asyncio.Event()
        async def generate(self,*args):
            self.calls+=1;self.started.set();await asyncio.Event().wait()
    async def check():
        async with open_meter_pool(f.db.runtime_dsn('ai_meter')) as meter:
            provider=WaitingProvider();_,service,agent,_,_,user,_,version,_=await prepared(f,meter,provider=provider)
            try:
                client=uuid4();first=await service.admit(user,UUID(version['version_id']),client,{'query':'취소 검증'})
                await asyncio.wait_for(provider.started.wait(),8)
                active=await service.read(user,UUID(first['run_id']))
                cancelled=await service.cancel(user,UUID(first['run_id']),active['revision'])
                assert cancelled['state']=='cancelled'
                await asyncio.gather(*list(service.tasks.values()),return_exceptions=True)
                await asyncio.gather(*list(agent.tasks.values()),return_exceptions=True)
                replay=await service.admit(user,UUID(version['version_id']),client,{'query':'취소 검증'})
                assert replay['state']=='cancelled' and provider.calls==1
                with f.db.admin_connection() as conn:
                    assert conn.execute("SELECT state FROM portal.runs WHERE task_kind='asset_chat'").fetchone()[0] in ('cancelled','failed','blocked')
            finally:await service.close();await agent.close()
    f.run(check())


@pytest.mark.parametrize('output_action',['mask','block'])
def test_input_policy_creates_no_parent_and_output_is_masked(ops_rows,output_action):
    f=ops_rows
    class PhoneProvider(CountingProvider):
        async def generate(self,*args):return replace(await super().generate(*args),body='담당 연락처 010-1234-5678')
    async def check():
        async with open_meter_pool(f.db.runtime_dsn('ai_meter')) as meter:
            _,service,agent,provider,_,user,approver,version,_=await prepared(f,meter,provider=PhoneProvider())
            if output_action=='block':
                from app.guardrails.repository import GuardrailRepository
                policies=GuardrailRepository(f.pool);head=await policies.get_policy(approver)
                await policies.update_policy(approver,uuid4(),head['revision'],{'output_pii_action':'block'})
            try:
                with pytest.raises(AppError) as blocked:await service.admit(user,UUID(version['version_id']),uuid4(),{'query':'전화 010-1234-5678'})
                assert blocked.value.code=='GUARDRAIL_INPUT_BLOCKED'
                with f.db.admin_connection() as conn:assert conn.execute('SELECT count(*) FROM portal.workflow_runs').fetchone()[0]==0
                data=await service.admit(user,UUID(version['version_id']),uuid4(),{'query':'안전 질문'})
                view=await wait(service,user,data['run_id'])
                assert view['state']==('completed' if output_action=='mask' else 'blocked') and '010-1234-5678' not in str(view) and provider.calls==1,view
            finally:await service.close();await agent.close()
    f.run(check())


def test_lease_expiry_and_recovery_never_redispatch_accepted_child(ops_rows):
    f=ops_rows
    async def check():
        async with open_meter_pool(f.db.runtime_dsn('ai_meter')) as meter:
            repo,service,agent,provider,_,user,_,version,definition=await prepared(f,meter)
            try:
                data=await repo.runtime(user,'admit',body={'version_id':version['version_id'],'client_request_id':str(uuid4()),'inputs':{'query':'복구 질문'}})
                parent=UUID(data['run_id']);token=uuid4()
                await repo.runtime(user,'claim',parent,token=token)
                await repo.runtime(user,'step',parent,{'node_id':'input'},token)
                await repo.runtime(user,'checkpoint',parent,{'node_id':'input','result':'복구 질문'},token)
                await repo.runtime(user,'step',parent,{'node_id':'agent'},token)
                config=next(n['config'] for n in definition['nodes'] if n['node_type']=='llm')
                child=await repo.child(user,parent,'agent',token,config,{'question':'복구 질문','audience':'담당자','rule':'기준'},b'z'*32)
                with f.db.admin_connection() as conn:conn.execute("UPDATE portal.workflow_runs SET lease_until=clock_timestamp()-interval '1 second'")
                with pytest.raises(AppError) as blocked:await repo.runtime(user,'heartbeat',parent,token=token)
                assert blocked.value.code=='WORKFLOW_BLOCKED'
                assert (await repo.recover())['interrupted']==1
                await agent._run(user,UUID(child['run_id']))
                view=await service.read(user,parent)
                assert view['state']=='interrupted' and provider.calls==0 and view['result'] is None
                assert (await repo.recover())['interrupted']==0
            finally:await service.close();await agent.close()
    f.run(check())


def test_workflow_helpers_and_private_tables_are_not_web_capabilities(db_fixture):
    f=db_fixture
    with f.role_connection('ai_web') as conn:
        for statement in ['SELECT * FROM portal.workflow_runs','SELECT * FROM portal.workflow_steps',"SELECT security.workflow_bindings(NULL,NULL,NULL,NULL)","SELECT security.workflow_approval_control_v047(NULL,NULL,NULL,NULL,'{}',NULL,NULL)","SELECT security.published_run_guard_v047(NULL,NULL,NULL)"]:
            with pytest.raises(psycopg.errors.InsufficientPrivilege):conn.execute(statement)
    f.verify_catalog()


def test_completed_content_is_hidden_after_revoke_and_runtime_code_change(ops_rows):
    f=ops_rows
    async def check():
        async with open_meter_pool(f.db.runtime_dsn('ai_meter')) as meter:
            repo,service,agent,provider,_,user,approver,version,definition=await prepared(f,meter)
            try:
                data=await service.admit(user,UUID(version['version_id']),uuid4(),{'query':'최종 권한 확인'})
                assert (await wait(service,user,data['run_id']))['result_access']=='final'
                from unittest.mock import patch
                with patch('app.workflows.repository.runtime_digest',return_value='a'*64):
                    with pytest.raises(AppError):await service.admit(user,UUID(version['version_id']),uuid4(),{'query':'코드 변경'})
                await repo.approval(approver,'revoke',None,{'workflow_id':definition['workflow_id'],'comment':'fixture review', 'expected_revision':1},'mock')
                view=await service.read(user,UUID(data['run_id']))
                assert view['state']=='completed' and view['result'] is None and view['result_access']=='unavailable'
                assert (await repo.approval(user,'catalog',None,{},'mock'))['items']==[] and provider.calls==1
            finally:await service.close();await agent.close()
    f.run(check())


def test_concurrent_admissions_reuse_one_parent_and_one_child(ops_rows):
    f=ops_rows
    async def check():
        async with open_meter_pool(f.db.runtime_dsn('ai_meter')) as meter:
            _,service,agent,provider,_,user,_,version,_=await prepared(f,meter)
            try:
                client=uuid4();one,two=await asyncio.gather(*[service.admit(user,UUID(version['version_id']),client,{'query':'동시 요청'}) for _ in range(2)])
                assert one['run_id']==two['run_id']
                assert (await wait(service,user,one['run_id']))['state']=='completed' and provider.calls==1
            finally:await service.close();await agent.close()
    f.run(check())


def test_rejection_survives_retired_dependency_and_replays_decision(ops_rows):
    f=ops_rows
    async def check():
        async with open_meter_pool(f.db.runtime_dsn('ai_meter')) as meter:
            repo,service,agent,_,_,_,approver,_,definition=await prepared(f,meter)
            try:
                owner=await f.context('A-ADM','A')
                body={'workflow_id':definition['workflow_id'],'client_request_id':str(uuid4()),'definition':definition,'version_digest':repo.digest(definition),'audience':'all','member_ids':[],'expected_head_revision':1}
                pending=await repo.approval(owner,'submit',None,body,'mock')
                from app.assets.deployments import DeploymentRepository
                asset=next(n['config']['asset_id'] for n in definition['nodes'] if n['node_type']=='llm')
                await DeploymentRepository(f.pool).call(approver,'retire',UUID(asset),{'expected_revision':1},'mock')
                with pytest.raises(AppError):await repo.approval(approver,'approve',UUID(pending['version_id']),{'comment':'fixture review', 'expected_revision':1},'mock')
                rejected=await repo.approval(approver,'reject',UUID(pending['version_id']),{'comment':'fixture review', 'expected_revision':1},'mock')
                assert rejected['status']=='rejected'
                assert (await repo.approval(approver,'reject',UUID(pending['version_id']),{'comment':'fixture review', 'expected_revision':1},'mock'))['replayed']
            finally:await service.close();await agent.close()
    f.run(check())


def test_real_factory_http_admission_replay_poll_and_csrf(ops_rows,auth_settings):
    import time
    from fastapi.testclient import TestClient
    from pydantic import SecretStr
    from app.main import create_app
    from support import login
    f=ops_rows
    async def setup():
        async with open_meter_pool(f.db.runtime_dsn('ai_meter')) as meter:
            _,service,agent,_,_,_,_,version,_=await prepared(f,meter)
            await service.close();await agent.close();return version
    version=f.run(setup())
    settings=auth_settings.model_copy(update={'execution_enabled':True,'meter_dsn':SecretStr(f.db.runtime_dsn('ai_meter'))})
    with TestClient(create_app(settings),base_url='http://127.0.0.1:8000',client=('127.0.0.1',50000)) as client:
        csrf=login(client,'A-U1',f.passwords)['csrf_token'];h=headers(f,csrf=csrf)
        body={'version_id':version['version_id'],'client_request_id':str(uuid4()),'inputs':{'query':'실제 HTTP 흐름'}}
        assert client.post('/api/v1/workflows/run',headers=headers(f),json=body).status_code==403
        reply=client.post('/api/v1/workflows/run',headers=h,json=body)
        assert reply.status_code==202,reply.text
        run=reply.json()['data']['run_id']
        for _ in range(80):
            record=client.get('/api/v1/workflows/runs/'+run,headers=headers(f))
            assert record.status_code==200,record.text
            if record.json()['data']['is_terminal']:break
            time.sleep(.05)
        assert record.json()['data']['state']=='completed',record.text
        replay=client.post('/api/v1/workflows/run',headers=h,json=body)
        assert replay.status_code==200 and replay.json()['data']['replayed']
        login(client,'A-U2',f.passwords)
        assert client.get('/api/v1/workflows/runs/'+run,headers=headers(f)).status_code==404


def test_child_admission_and_checkpoint_reference_roll_back_together(ops_rows):
    f=ops_rows
    async def check():
        async with open_meter_pool(f.db.runtime_dsn('ai_meter')) as meter:
            repo,service,agent,_,_,user,_,version,definition=await prepared(f,meter)
            try:
                data=await repo.runtime(user,'admit',body={'version_id':version['version_id'],'client_request_id':str(uuid4()),'inputs':{'query':'원자성 확인'}})
                parent=UUID(data['run_id']);token=uuid4()
                await repo.runtime(user,'claim',parent,token=token)
                await repo.runtime(user,'step',parent,{'node_id':'input'},token)
                await repo.runtime(user,'checkpoint',parent,{'node_id':'input','result':'원자성 확인'},token)
                await repo.runtime(user,'step',parent,{'node_id':'agent'},token)
                with f.db.admin_connection() as conn:conn.execute('DROP POLICY audit_published_run ON ops.audit_events')
                config=next(n['config'] for n in definition['nodes'] if n['node_type']=='llm')
                with pytest.raises(AppError) as unavailable:await repo.child(user,parent,'agent',token,config,{'question':'원자성 확인','audience':'담당자','rule':'기준'},b'w'*32)
                assert unavailable.value.status==503
                with f.db.admin_connection() as conn:
                    assert conn.execute("SELECT count(*) FROM portal.runs WHERE task_kind='asset_chat'").fetchone()[0]==0
                    assert conn.execute('SELECT child_run_id FROM portal.workflow_steps WHERE node_id=%s',('agent',)).fetchone()[0] is None
            finally:await service.close();await agent.close()
    f.run(check())


def test_cancel_dispatched_tool_records_unknown_and_never_starts_agent(ops_rows):
    import threading
    f=ops_rows
    async def check():
        async with open_meter_pool(f.db.runtime_dsn('ai_meter')) as meter:
            _,service,agent,provider,adapter,user,_,version,_=await prepared(f,meter,tool=True)
            started=threading.Event();release=threading.Event();handler=service.tools.registry.get('data_view_reader').handler
            def pending(arguments):
                started.set();release.wait(3);return handler(arguments)
            service.tools.registry.get('data_view_reader').handler=pending
            try:
                client=uuid4();data=await service.admit(user,UUID(version['version_id']),client,{'query':'도구 취소'})
                for _ in range(200):
                    if started.is_set():break
                    await asyncio.sleep(.01)
                assert started.is_set()
                current=await service.read(user,UUID(data['run_id']))
                assert (await service.cancel(user,UUID(data['run_id']),current['revision']))['state']=='cancelled'
                release.set();await asyncio.gather(*list(service.tasks.values()),return_exceptions=True)
                repeat=await service.admit(user,UUID(version['version_id']),client,{'query':'도구 취소'})
                assert repeat['state']=='cancelled' and provider.calls==0
                with f.db.admin_connection() as conn:
                    assert conn.execute('SELECT state,result FROM portal.tool_receipts').fetchone()==('unknown',None)
            finally:release.set();await service.close();await agent.close()
    f.run(check())


def test_legacy_approved_version_cannot_gain_code_seal_by_submission_replay(ops_rows):
    from psycopg.types.json import Jsonb
    f=ops_rows
    async def check():
        async with open_meter_pool(f.db.runtime_dsn('ai_meter')) as meter:
            repo,service,agent,_,_,_,_,_,definition=await prepared(f,meter)
            try:
                owner=await f.context('A-ADM','A');workflow=uuid4();version=uuid4();client=uuid4()
                legacy=definition|{'workflow_id':str(workflow)}
                with f.db.admin_connection() as conn:
                    conn.execute('INSERT INTO portal.workflows(tenant_id,workflow_id,owner_id,client_request_id) VALUES(%s,%s,%s,%s)',(owner.tenant_id,workflow,owner.user_id,client))
                    conn.execute("INSERT INTO portal.workflow_versions(tenant_id,workflow_id,version_id,revision,decision_revision,created_by,client_request_id,definition,version_digest,audience,member_ids,expected_head_revision,status) VALUES(%s,%s,%s,1,2,%s,%s,%s,%s,'all','{}',0,'approved')",(owner.tenant_id,workflow,version,owner.user_id,client,Jsonb(legacy),repo.digest(legacy)))
                    conn.execute('INSERT INTO portal.workflow_heads(tenant_id,workflow_id,version_id,revision) VALUES(%s,%s,%s,1)',(owner.tenant_id,workflow,version))
                with pytest.raises(AppError) as conflict:
                    await repo.approval(owner,'submit',None,{'workflow_id':str(workflow),'client_request_id':str(client),'definition':legacy,'version_digest':repo.digest(legacy),'audience':'all','member_ids':[],'expected_head_revision':0},'mock')
                assert conflict.value.status==409
                with f.db.admin_connection() as conn:assert conn.execute('SELECT runtime_digest FROM portal.workflow_versions WHERE version_id=%s',(version,)).fetchone()[0] is None
            finally:await service.close();await agent.close()
    f.run(check())


def test_read_of_expired_parent_seals_interrupted_without_child_dispatch(ops_rows):
    f=ops_rows
    async def check():
        async with open_meter_pool(f.db.runtime_dsn('ai_meter')) as meter:
            repo,service,agent,provider,_,user,_,version,_=await prepared(f,meter)
            try:
                data=await repo.runtime(user,'admit',body={'version_id':version['version_id'],'client_request_id':str(uuid4()),'inputs':{'query':'만료 조회'}})
                parent=UUID(data['run_id']);await repo.runtime(user,'claim',parent,token=uuid4())
                with f.db.admin_connection() as conn:conn.execute("UPDATE portal.workflow_runs SET lease_until=clock_timestamp()-interval '1 second'")
                view=await service.read(user,parent)
                assert view['state']=='interrupted' and view['is_terminal'] and provider.calls==0
                assert all(s['state']=='skipped' for s in view['steps'])
            finally:await service.close();await agent.close()
    f.run(check())


def test_llm_system_role_bound_literal_is_checked_before_child_admission(ops_rows):
    f=ops_rows
    async def check():
        async with open_meter_pool(f.db.runtime_dsn('ai_meter')) as meter:
            _,service,agent,provider,_,user,_,version,_=await prepared(f,meter,pii_literal=True)
            try:
                data=await service.admit(user,UUID(version['version_id']),uuid4(),{'query':'안전한 사용자 질문'})
                view=await wait(service,user,data['run_id'])
                assert view['state']=='blocked' and provider.calls==0 and view['result'] is None,view
                assert all(s['child_run_id'] is None for s in view['steps'])
                with f.db.admin_connection() as conn:assert conn.execute("SELECT count(*) FROM portal.runs WHERE task_kind='asset_chat'").fetchone()[0]==0
            finally:await service.close();await agent.close()
    f.run(check())


def test_revoke_between_admission_and_claim_terminates_parent_without_dispatch(ops_rows):
    f=ops_rows
    async def check():
        async with open_meter_pool(f.db.runtime_dsn('ai_meter')) as meter:
            repo,service,agent,provider,adapter,user,approver,version,definition=await prepared(f,meter,tool=True)
            try:
                first=await repo.runtime(user,'admit',body={'version_id':version['version_id'],'client_request_id':str(uuid4()),'inputs':{'query':'시작 전 회수'}})
                await repo.approval(approver,'revoke',None,{'workflow_id':definition['workflow_id'],'comment':'fixture review', 'expected_revision':1},'mock')
                service.notify(user,first['run_id'])
                view=await wait(service,user,first['run_id'])
                assert view['state']=='blocked' and view['is_terminal'] and provider.calls==adapter.calls==0,view
                assert all(step['state']=='skipped' for step in view['steps'])
            finally:await service.close();await agent.close()
    f.run(check())


def test_read_of_expired_unclaimed_parent_releases_queue_without_dispatch(ops_rows):
    f=ops_rows
    async def check():
        async with open_meter_pool(f.db.runtime_dsn('ai_meter')) as meter:
            repo,service,agent,provider,_,user,_,version,_=await prepared(f,meter)
            try:
                first=await repo.runtime(user,'admit',body={'version_id':version['version_id'],'client_request_id':str(uuid4()),'inputs':{'query':'시작 전 중단'}})
                with f.db.admin_connection() as conn:
                    conn.execute("UPDATE portal.workflow_runs SET created_at=clock_timestamp()-interval '1201 seconds'")
                view=await service.read(user,UUID(first['run_id']))
                assert view['state']=='interrupted' and view['is_terminal'] and provider.calls==0
                assert all(step['state']=='skipped' for step in view['steps'])
            finally:await service.close();await agent.close()
    f.run(check())
