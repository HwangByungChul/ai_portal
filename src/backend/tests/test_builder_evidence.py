import asyncio
from uuid import uuid4,UUID
import pytest,psycopg
from psycopg.types.json import Jsonb
from app.builder.trials import TrialRepository,ManualAssessment
from app.builder.repository import BuilderRepository
from app.ai.repository import CallRepository
from app.ai.gateway import AiGateway
from app.ai.providers import MockProvider
from app.builder.execution import TrialExecutor
from app.db import open_meter_pool
from app.errors import AppError
from test_operations import ops_rows
from test_builder_trials import admit
from test_builder_profiles import body
from datetime import date

assessment={'correctness':4,'relevance':5,'expected_answer':'answer','verdict':'suitable','comment':'합성 업무 검토'}
async def finish(f,repo,ctx,run):
    ticket=await repo.claim(ctx,UUID(run),'mock')
    engine=TrialExecutor(repo,AiGateway(repo,MockProvider()),None)
    result=await engine.execute(ticket);await engine.finish(ticket,result)

def test_history_keyset_evidence_assess_append_and_compare(ops_rows):
    f=ops_rows
    async def check():
        async with open_meter_pool(f.db.runtime_dsn('ai_meter')) as meter:
            repo=CallRepository(f.pool,meter,date(2026,10,1));trials=TrialRepository(f.pool)
            ctx,saved,payload,a=await admit(f,repo);aid=UUID(saved['asset_id']);vid=UUID(saved['version_id']);arun=UUID(a['run_id'])
            pending=await trials.rpc(ctx,'builder_trial_history',(ctx.session_id,ctx.tenant_id,aid,None,1));assert len(pending['items'])==1
            assert not any(k in pending['items'][0] for k in ('result','messages','sources','assessment','question_hash'))
            with pytest.raises(AppError) as e:await trials.rpc(ctx,'builder_trial_assess',(ctx.session_id,ctx.tenant_id,arun,uuid4(),Jsonb(assessment)))
            assert e.value.status==409
            await finish(f,repo,ctx,a['run_id'])
            v=await trials.rpc(ctx,'builder_trial_evidence',(ctx.session_id,ctx.tenant_id,arun));assert len(v['result_hash'])==64 and v['assessment_count']==0 and 'messages' not in v
            client=uuid4();first=await trials.rpc(ctx,'builder_trial_assess',(ctx.session_id,ctx.tenant_id,arun,client,Jsonb(assessment)))
            assert not first['replayed'];assert (await trials.rpc(ctx,'builder_trial_assess',(ctx.session_id,ctx.tenant_id,arun,client,Jsonb(assessment))))=={**first,'replayed':True}
            with pytest.raises(AppError) as e:await trials.rpc(ctx,'builder_trial_assess',(ctx.session_id,ctx.tenant_id,arun,client,Jsonb({**assessment,'comment':'변경'})))
            assert e.value.status==409
            await trials.rpc(ctx,'builder_trial_assess',(ctx.session_id,ctx.tenant_id,arun,uuid4(),Jsonb({**assessment,'verdict':'needs_change'})))
            v=await trials.rpc(ctx,'builder_trial_evidence',(ctx.session_id,ctx.tenant_id,arun));assert v['assessment_count']==2 and v['assessments'][0]['assessment']['verdict']=='needs_change'
            later=body();later['profile']['developer_prompt']='새 검토 기준 {{rule}}'
            newer=await BuilderRepository(f.pool).call(ctx,'append',aid,body={**later,'expected_revision':1},trace=uuid4())
            b=await trials.admit(ctx,aid,UUID(newer['version_id']),{**payload,'client_send_id':str(uuid4())},date(2026,10,1),'mock',b'x'*32,uuid4());brun=UUID(b['run_id']);await finish(f,repo,ctx,b['run_id'])
            pages=await trials.rpc(ctx,'builder_trial_history',(ctx.session_id,ctx.tenant_id,aid,None,1));assert pages['items'][0]['run_id']==str(brun) and pages['next_cursor']==str(brun)
            rest=await trials.rpc(ctx,'builder_trial_history',(ctx.session_id,ctx.tenant_id,aid,brun,1));assert rest['items'][0]['run_id']==str(arun) and rest['next_cursor'] is None
            comparison=await trials.rpc(ctx,'builder_trial_compare',(ctx.session_id,ctx.tenant_id,arun,brun));assert all(comparison['conditions'].values())
            assert comparison['left']['profile_hash']!=comparison['right']['profile_hash'] and comparison['left']['assessments']==v['assessments']
            changed=await trials.admit(ctx,aid,UUID(newer['version_id']),{**payload,'client_send_id':str(uuid4()),'values':{**payload['values'],'question':'다른 질문'}},date(2026,10,1),'mock',b'x'*32,uuid4());await finish(f,repo,ctx,changed['run_id'])
            different=await trials.rpc(ctx,'builder_trial_compare',(ctx.session_id,ctx.tenant_id,arun,UUID(changed['run_id'])));assert not different['conditions']['same_question']
            _,other,_,c=await admit(f,repo);await finish(f,repo,ctx,c['run_id'])
            for args in [(arun,arun),(arun,UUID(c['run_id']))]:
                with pytest.raises(AppError) as e:await trials.rpc(ctx,'builder_trial_compare',(ctx.session_id,ctx.tenant_id,*args))
                assert e.value.status==422
            with pytest.raises(AppError) as e:await trials.rpc(ctx,'builder_trial_history',(ctx.session_id,ctx.tenant_id,aid,UUID(c['run_id']),1))
            assert e.value.status==404
            with f.db.admin_connection() as conn:
                with pytest.raises(psycopg.errors.CheckViolation):
                    with conn.transaction():conn.execute("UPDATE portal.builder_assessments SET rubric='manual-v1'")
                with pytest.raises(psycopg.errors.CheckViolation):
                    with conn.transaction():conn.execute('DELETE FROM portal.builder_assessments')
    f.run(check())

@pytest.mark.parametrize('actor,tenant,status',[('A-U1','A',403),('DUAL-ADM','A',404),('P-A','A',404),('DUAL-ADM','B',404)])
def test_evidence_other_actor_and_tenant_denied(ops_rows,actor,tenant,status):
    f=ops_rows
    async def check():
        async with open_meter_pool(f.db.runtime_dsn('ai_meter')) as meter:
            repo=CallRepository(f.pool,meter,date(2026,10,1));owner,saved,payload,data=await admit(f,repo);await finish(f,repo,owner,data['run_id']);ctx=await f.context(actor,tenant);t=TrialRepository(f.pool)
            for name,args in [('builder_trial_evidence',(UUID(data['run_id']),)),('builder_trial_assess',(UUID(data['run_id']),uuid4(),Jsonb(assessment))),('builder_trial_compare',(UUID(data['run_id']),uuid4()))]:
                with pytest.raises(AppError) as e:await t.rpc(ctx,name,(ctx.session_id,ctx.tenant_id,*args))
                assert e.value.status==status
    f.run(check())

def test_evidence_management_revocation_and_history_metadata(ops_rows):
    f=ops_rows
    async def check():
        async with open_meter_pool(f.db.runtime_dsn('ai_meter')) as meter:
            repo=CallRepository(f.pool,meter,date(2026,10,1));ctx,saved,_,data=await admit(f,repo);await finish(f,repo,ctx,data['run_id']);t=TrialRepository(f.pool)
            with f.db.admin_connection() as c:c.execute("UPDATE security.memberships SET role='USER' WHERE user_id=%s",(ctx.user_id,))
            for name,args in [('builder_trial_history',(UUID(saved['asset_id']),None,20)),('builder_trial_evidence',(UUID(data['run_id']),)),('builder_trial_assess',(UUID(data['run_id']),uuid4(),Jsonb(assessment)))]:
                with pytest.raises(AppError) as e:await t.rpc(ctx,name,(ctx.session_id,ctx.tenant_id,*args))
                assert e.value.status==403
    f.run(check())

@pytest.mark.parametrize('change',[{'correctness':0},{'correctness':True},{'relevance':6},{'comment':'x'*1001},{'extra':'x'},{'verdict':'approved'}])
def test_manual_assessment_bounded_schema(change):
    from pydantic import ValidationError
    with pytest.raises(ValidationError):ManualAssessment(client_request_id=uuid4(),**{**assessment,**change})


def test_document_withdrawal_keeps_minimal_history_but_blocks_evidence_and_assess(ops_rows,tmp_path):
    from app.documents.repository import DocumentRepository
    from app.documents.storage import SourceStorage
    from app.documents.embedding import MockEmbeddingProvider
    from app.ai.rag_provider import RagMockProvider
    from app.execution.rag import RagExecutor
    from test_document_sharing import publish
    f=ops_rows
    async def check():
        async with open_meter_pool(f.db.runtime_dsn('ai_meter')) as meter:
            repo=CallRepository(f.pool,meter,date(2026,10,1));docs=DocumentRepository(f.pool,SourceStorage(tmp_path/'sources'),'x'*40);ctx=await f.context('A-ADM','A');ids=await publish(f,docs,ctx)
            ctx,saved,payload,data=await admit(f,repo,'rules_rag',[{k:ids[k] for k in ('document_id','version_id')}],'search');run=UUID(data['run_id']);t=TrialRepository(f.pool)
            ticket=await repo.claim(ctx,run,'mock');engine=TrialExecutor(repo,AiGateway(repo,MockProvider()),RagExecutor(repo,docs,MockEmbeddingProvider(),RagMockProvider()));result=await engine.execute(ticket);await engine.finish(ticket,result)
            before=await t.rpc(ctx,'builder_trial_evidence',(ctx.session_id,ctx.tenant_id,run));assert before['sources'] and before['result']['candidates']
            client=uuid4();await t.rpc(ctx,'builder_trial_assess',(ctx.session_id,ctx.tenant_id,run,client,Jsonb(assessment)))
            await docs.delete(ctx,UUID(ids['document_id']),1)
            history=await t.rpc(ctx,'builder_trial_history',(ctx.session_id,ctx.tenant_id,UUID(saved['asset_id']),None,20));assert len(history['items'])==1 and 'sources' not in history['items'][0]
            for name,args in [('builder_trial_evidence',(run,)),('builder_trial_assess',(run,client,Jsonb(assessment))),('builder_trial_compare',(run,uuid4()))]:
                with pytest.raises(AppError) as e:await t.rpc(ctx,name,(ctx.session_id,ctx.tenant_id,*args))
                assert e.value.status==404
    f.run(check())

def test_evidence_http_csrf_query_validation_and_owner_no_store(client,login,ops_rows):
    from test_builder_profiles import signed
    f=ops_rows
    async def setup():
        async with open_meter_pool(f.db.runtime_dsn('ai_meter')) as meter:
            repo=CallRepository(f.pool,meter,date(2026,10,1));ctx,saved,_,data=await admit(f,repo);await finish(f,repo,ctx,data['run_id']);return saved,data
    saved,data=f.run(setup());h=signed(client,login,f);run=data['run_id'];base='/api/v1/admin/builder/'
    get=client.get(base+'trials/'+run+'/evidence',headers=h);assert get.status_code==200 and get.headers['cache-control']=='no-store'
    for query in ('?limit=0','?limit=21','?unknown=1','?cursor=bad'):
        assert client.get(base+'assets/'+saved['asset_id']+'/trials'+query,headers=h).status_code==422
    assert client.get(base+'trials/'+run+'/evidence?extra=1',headers=h).status_code==422
    review={**assessment,'client_request_id':str(uuid4())}
    assert client.post(base+'trials/'+run+'/assessments',headers={k:v for k,v in h.items() if k!='X-CSRF-Token'},json=review).status_code==403
    first=client.post(base+'trials/'+run+'/assessments',headers=h,json=review);assert first.status_code==201
    assert client.post(base+'trials/'+run+'/assessments',headers=h,json=review).status_code==200
    assert client.post(base+'trial-comparisons',headers=h,json={'left':run,'right':run}).status_code==422
