import asyncio
from datetime import date
from uuid import uuid4,UUID
import pytest
from psycopg.types.json import Jsonb
from app.builder.repository import BuilderRepository
from app.builder.trials import TrialRepository
from app.builder.execution import TrialExecutor
from app.ai.repository import CallRepository,ExecutionError,digest
from app.ai.gateway import AiGateway
from app.ai.providers import MockProvider
from app.ai.rag_provider import RagMockProvider
from app.ai.types import ProviderOutcome
from app.execution.rag import RagExecutor
from app.execution.manager import ExecutionManager
from app.execution.stream import StreamHub
from app.db import open_meter_pool,tenant_transaction
from app.documents.repository import DocumentRepository
from app.documents.storage import SourceStorage
from app.documents.embedding import MockEmbeddingProvider
from test_document_sharing import publish
from test_operations import ops_rows
from test_builder_profiles import body,signed,save

async def admit(f,repo,kind='general',refs=None,purpose='generate',client=None):
    ctx=await f.context('A-ADM','A');value=body();value['config']['execution_kind']=kind;value['profile']['model_ref']='default_'+kind;value['profile']['document_refs']=refs or []
    saved=await BuilderRepository(repo.web_pool).call(ctx,'create',body=value,trace=uuid4())
    payload={'client_send_id':str(client or uuid4()),'purpose':purpose,'values':{'audience':'{{rule}}','rule':'검토','question':'여신심사 담당 부서는?'}}
    data=await TrialRepository(repo.web_pool).admit(ctx,UUID(saved['asset_id']),UUID(saved['version_id']),payload,date(2026,10,1),'mock',b'x'*32,uuid4())
    return ctx,saved,payload,data

@pytest.mark.parametrize('case',['general','search','rag','empty_search','empty_rag'])
def test_actual_gateway_trial_and_exact_binding(ops_rows,tmp_path,case):
    f=ops_rows
    async def check():
        async with open_meter_pool(f.db.runtime_dsn('ai_meter')) as meter:
            repo=CallRepository(f.pool,meter,date(2026,10,1));documents=DocumentRepository(f.pool,SourceStorage(tmp_path/'sources'),'x'*40)
            refs=[]
            if case in ('search','rag'):
                ids=await publish(f,documents,await f.context('A-ADM','A'));refs=[{k:ids[k] for k in ('document_id','version_id')}]
            ctx,saved,payload,data=await admit(f,repo,'general' if case=='general' else 'rules_rag',refs,'search' if 'search' in case else 'generate')
            ticket=await repo.claim(ctx,UUID(data['run_id']),'mock');assert ticket.task_kind=='builder_trial'
            assert ticket.asset_binding.version_id==UUID(saved['version_id']) and ticket.messages[0]['content']=='시스템 {{rule}}'
            assert [m['role'] for m in ticket.messages]==['system','developer','user']
            engine=TrialExecutor(repo,AiGateway(repo,MockProvider()),RagExecutor(repo,documents,MockEmbeddingProvider(),RagMockProvider()))
            result=await engine.execute(ticket);assert await engine.finish(ticket,result)
            view=await TrialRepository(f.pool).read(ctx,ticket.run.run_id);assert view['state']=='completed' and view['content_status']=='final' and view['result']==result
            assert view['asset_binding']['source']=='builder_trial' and view['profile_hash']==saved['profile_hash']
            replay=await TrialRepository(f.pool).admit(ctx,UUID(saved['asset_id']),UUID(saved['version_id']),payload,date(2026,10,1),'mock',b'x'*32,uuid4());assert replay['replayed'] and replay['run_id']==data['run_id']
            async with tenant_transaction(f.pool,ctx) as conn:
                await conn.execute("SELECT set_config('app.run_scope','owner',true)")
                assert await (await conn.execute('SELECT conversation_id FROM portal.conversations WHERE conversation_id=%s',(UUID(data['conversation_id']),))).fetchone() is None
            with f.db.admin_connection() as conn:
                calls=conn.execute('SELECT operation,state FROM ops.call_attempts WHERE run_id=%s',(ticket.run.run_id,)).fetchall()
                assert len(calls)==({'general':1,'search':1,'rag':2,'empty_search':0,'empty_rag':0}[case]) and all(x[1]=='settled' for x in calls)
            if case=='search':assert result['candidates']
            if case.startswith('empty'):assert result['answer_kind']=='insufficient_evidence'
    f.run(check())

@pytest.mark.parametrize('case',['cancel','revoke','disable','unknown','stop','restart','duplicate','config_changed'])
def test_trial_failure_meter_and_recovery(ops_rows,case):
    f=ops_rows
    async def check():
        async with open_meter_pool(f.db.runtime_dsn('ai_meter')) as meter:
            repo=CallRepository(f.pool,meter,date(2026,10,1));ctx,saved,payload,data=await admit(f,repo);run=UUID(data['run_id']);ticket=await repo.claim(ctx,run,'mock')
            if case in ('revoke','disable','stop','config_changed'):
                with f.db.admin_connection() as c:
                    if case=='revoke':c.execute("UPDATE security.memberships SET role='USER' WHERE user_id=%s",(ctx.user_id,))
                    elif case=='disable':c.execute("UPDATE portal.agent_configs SET enabled=false WHERE tenant_id=%s",(ctx.tenant_id,))
                    elif case=='config_changed':c.execute("UPDATE portal.agent_configs SET config_version=config_version+1 WHERE tenant_id=%s",(ctx.tenant_id,))
                    else:c.execute('UPDATE ops.project_budget SET stopped=true')
                assert (await AiGateway(repo,MockProvider()).execute(ticket,lambda t:asyncio.sleep(0))).safe_error_code
                await repo.fail(ticket,'EXECUTION_BLOCKED')
            elif case=='cancel':
                async with tenant_transaction(f.pool,ctx) as c:
                    await c.execute('SELECT security.builder_trial_read(%s,%s,%s)',(ctx.session_id,ctx.tenant_id,run))
                    await c.execute('SELECT security.run_cancel(%s,%s,%s,2,%s)',(ctx.session_id,ctx.tenant_id,run,uuid4()))
                with pytest.raises(ExecutionError):await repo.reserve(ticket,b'z'*32)
            elif case=='restart':
                reserved=await repo.reserve(ticket,b'z'*32);claim=await repo.dispatch(ticket,UUID(reserved['call_id']))
                async with f.pool.connection() as leader:
                        await leader.execute('SELECT pg_advisory_lock(202610,4)')
                        try:await leader.execute("SELECT security.execution_recover('mock')")
                        finally:await leader.execute('SELECT pg_advisory_unlock(202610,4)')
            elif case=='unknown':
                class Unknown(MockProvider):
                    async def generate(self,*args):return ProviderOutcome(None,None,'unknown','STREAM_INTERRUPTED')
                out=await AiGateway(repo,Unknown()).execute(ticket,lambda t:asyncio.sleep(0));assert out.safe_error_code
                await repo.fail(ticket,out.safe_error_code)
            else:
                out=await AiGateway(repo,MockProvider()).execute(ticket,lambda t:asyncio.sleep(0));assert out.body
                assert (await AiGateway(repo,MockProvider()).execute(ticket,lambda t:asyncio.sleep(0))).safe_error_code=='EXECUTION_BLOCKED'
                await TrialExecutor(repo,None,None).finish(ticket,{'kind':'generation','text':out.body,'answer_kind':'answer'})
            with f.db.admin_connection() as c:
                calls=c.execute('SELECT state FROM ops.call_attempts WHERE run_id=%s',(run,)).fetchall()
                assert len(calls)<=1
                if case in ('unknown','restart'):assert calls==[('usage_unknown',)]
                assert c.execute('SELECT active_slot FROM ops.tenant_budgets WHERE tenant_id=%s AND active_slot>0',(ctx.tenant_id,)).fetchone()==((1,) if case in ('unknown','restart') else None)
    f.run(check())

def test_trial_http_idempotence_csrf_and_private_scope(client,login,ops_rows):
    f=ops_rows;h=signed(client,login,f);saved=save(client,h,body()).json()['data'];path='/api/v1/admin/builder/assets/'+saved['asset_id']+'/versions/'+saved['version_id']+'/trials'
    value={'client_send_id':str(uuid4()),'purpose':'generate','values':{'audience':'직원','rule':'확인','question':'질문'}}
    response=client.post(path,headers=h,json=value);assert response.status_code==201,response.json();run=response.json()['data']['run_id']
    assert client.post(path,headers=h,json=value).json()['data']['replayed']
    assert client.post(path,headers=h,json={**value,'values':{**value['values'],'question':'변경'}}).status_code==409
    assert client.post(path,headers={k:v for k,v in h.items() if k!='X-CSRF-Token'},json=value).status_code==403
    assert client.get('/api/v1/admin/builder/trials/'+run,headers=h).json()['data']['state']=='accepted'
    assert client.post('/api/v1/admin/builder/trials/'+run+'/cancel',headers=h,json={'expected_revision':1}).status_code==200
    other=signed(client,login,f,'A-U1');assert client.get('/api/v1/admin/builder/trials/'+run,headers=other).status_code==403

@pytest.mark.parametrize('phase',['before_claim','before_finish','after_finish'])
def test_trial_document_revoke_blocks_calls_results_and_replay_but_not_cancel(ops_rows,tmp_path,phase):
    from app.errors import AppError
    f=ops_rows
    async def check():
        async with open_meter_pool(f.db.runtime_dsn('ai_meter')) as meter:
            repo=CallRepository(f.pool,meter,date(2026,10,1));docs=DocumentRepository(f.pool,SourceStorage(tmp_path/'sources'),'x'*40);ctx=await f.context('A-ADM','A');ids=await publish(f,docs,ctx)
            ctx,saved,payload,data=await admit(f,repo,'rules_rag',[{k:ids[k] for k in ('document_id','version_id')}],'search');run=UUID(data['run_id']);trials=TrialRepository(f.pool)
            if phase=='before_claim':
                await docs.delete(ctx,UUID(ids['document_id']),1)
                with pytest.raises(ExecutionError):await repo.claim(ctx,run,'mock')
            else:
                ticket=await repo.claim(ctx,run,'mock');engine=TrialExecutor(repo,AiGateway(repo,MockProvider()),RagExecutor(repo,docs,MockEmbeddingProvider(),RagMockProvider()));result=await engine.execute(ticket)
                if phase=='after_finish':assert await engine.finish(ticket,result)
                await docs.delete(ctx,UUID(ids['document_id']),1)
                if phase=='before_finish':
                    with pytest.raises(ExecutionError):await engine.finish(ticket,result)
            with pytest.raises(AppError):await trials.read(ctx,run)
            with pytest.raises(AppError):await trials.admit(ctx,UUID(saved['asset_id']),UUID(saved['version_id']),payload,date(2026,10,1),'mock',b'x'*32,uuid4())
            with f.db.admin_connection() as c:
                revision=c.execute('SELECT revision FROM portal.runs WHERE run_id=%s',(run,)).fetchone()[0]
                assert c.execute('SELECT count(*) FROM ops.call_attempts WHERE run_id=%s',(run,)).fetchone()[0]==(0 if phase=='before_claim' else 1)
            cancelled=await trials.rpc(ctx,'builder_trial_cancel',(ctx.session_id,ctx.tenant_id,run,revision,uuid4()));assert cancelled['state'] in ('cancelled','cancel_requested','completed')
            if phase=='before_finish':await repo.fail(ticket,'EXECUTION_BLOCKED')
    f.run(check())

@pytest.mark.parametrize('case',['complete','cancel','late_revoke'])
def test_trial_manager_uses_private_branch_and_current_role(ops_rows,case):
    from app.db import open_web_pool
    from app.ai.types import UsageReceipt
    f=ops_rows
    async def check():
        async with open_web_pool(f.db.runtime_dsn(),size=4) as web,open_meter_pool(f.db.runtime_dsn('ai_meter')) as meter:
            repo=CallRepository(web,meter,date(2026,10,1))
            class Controlled(MockProvider):
                def __init__(self):self.entered=asyncio.Event();self.release=asyncio.Event();self.calls=0
                async def generate(self,claim,messages,on_delta):
                    self.calls+=1;self.entered.set()
                    if case!='complete':await self.release.wait()
                    return ProviderOutcome('합성 시험 결과',UsageReceipt(120,40,160,'gpt-4o-mini','default',None),'observed',None)
            provider=Controlled();manager=ExecutionManager(repo,provider,'mock',StreamHub());await manager.start()
            try:
                ctx,saved,payload,data=await admit(f,repo);run=UUID(data['run_id']);manager.notify(ctx,run);await asyncio.wait_for(provider.entered.wait(),3)
                if case=='cancel':
                    state=await TrialRepository(web).read(ctx,run);await TrialRepository(web).rpc(ctx,'builder_trial_cancel',(ctx.session_id,ctx.tenant_id,run,state['revision'],uuid4()));manager.cancel(ctx,run)
                elif case=='late_revoke':
                    with f.db.admin_connection() as c:c.execute("UPDATE security.memberships SET role='USER' WHERE user_id=%s",(ctx.user_id,))
                    provider.release.set()
                await asyncio.wait_for(asyncio.gather(*list(manager.tasks.values())),5)
                with f.db.admin_connection() as c:
                    state=c.execute('SELECT state FROM portal.runs WHERE run_id=%s',(run,)).fetchone()[0];result=c.execute('SELECT result FROM portal.builder_trials WHERE run_id=%s',(run,)).fetchone()[0]
                    assert state=={'complete':'completed','cancel':'cancelled','late_revoke':'failed'}[case]
                    assert (result is not None)==(case=='complete') and provider.calls==1
                    assert c.execute('SELECT state FROM ops.call_attempts WHERE run_id=%s',(run,)).fetchone()[0]==('usage_unknown' if case=='cancel' else 'settled')
            finally:await manager.close()
    f.run(check())
