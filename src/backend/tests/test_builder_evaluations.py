from uuid import UUID,uuid4
from datetime import date
import pytest,psycopg
from psycopg.types.json import Jsonb
from app.builder.trials import TrialRepository
from app.builder.evaluations import CaseRequest
from app.ai.repository import CallRepository
from app.db import open_meter_pool
from app.errors import AppError
from test_operations import ops_rows
from test_builder_trials import admit
from test_builder_evidence import finish

def spec(payload,expected='answer',terms=None,sources=None,purpose='generate'):
    return {'name':'업무 평가 사례','values':payload['values'],'purpose':purpose,'criteria':{'expected_answer':expected,'required_terms':terms or [],'forbidden_terms':['절대 없는 금지문구'],'required_sources':sources or []}}
async def save(t,ctx,saved,value,client=None):
    return await t.rpc(ctx,'builder_case_save',(ctx.session_id,ctx.tenant_id,UUID(saved['asset_id']),UUID(saved['version_id']),client or uuid4(),Jsonb(value)))

def test_saved_case_exact_trial_checks_replay_and_immutability(ops_rows):
    f=ops_rows
    async def check():
        async with open_meter_pool(f.db.runtime_dsn('ai_meter')) as meter:
            repo=CallRepository(f.pool,meter,date(2026,10,1));ctx,saved,payload,data=await admit(f,repo);t=TrialRepository(f.pool);run=UUID(data['run_id']);value=spec(payload,terms=['모의 AI 응답']);client=uuid4();case=await save(t,ctx,saved,value,client);cid=UUID(case['case_id'])
            assert not case['replayed'] and (await save(t,ctx,saved,value,client))=={**case,'replayed':True}
            with pytest.raises(AppError) as e:await save(t,ctx,saved,{**value,'name':'다른 사례'},client)
            assert e.value.status==409
            listing=await t.rpc(ctx,'builder_case_list',(ctx.session_id,ctx.tenant_id,UUID(saved['asset_id']),UUID(saved['version_id']),None));assert len(listing['items'])==1 and 'spec' not in listing['items'][0]
            assert (await t.rpc(ctx,'builder_case_read',(ctx.session_id,ctx.tenant_id,cid)))['spec']==value
            with pytest.raises(AppError) as e:await t.rpc(ctx,'builder_case_evaluate',(ctx.session_id,ctx.tenant_id,cid,run))
            assert e.value.status==409
            await finish(f,repo,ctx,data['run_id']);checked=await t.rpc(ctx,'builder_case_evaluate',(ctx.session_id,ctx.tenant_id,cid,run));assert checked['passed'] and checked['engine']=='literal-v1' and not checked['replayed']
            assert (await t.rpc(ctx,'builder_case_evaluate',(ctx.session_id,ctx.tenant_id,cid,run)))=={**checked,'replayed':True}
            view=await t.rpc(ctx,'builder_trial_evidence',(ctx.session_id,ctx.tenant_id,run));assert view['automatic_check_count']==1 and view['automatic_checks'][0]['result_hash']==view['result_hash'] and view['assessments']==[]
            badcase=await save(t,ctx,saved,spec(payload,terms=['실제로 없는 기대 주장']));bad=await t.rpc(ctx,'builder_case_evaluate',(ctx.session_id,ctx.tenant_id,UUID(badcase['case_id']),run));assert not bad['passed']
            for criteria in [{**value['criteria'],'forbidden_terms':['실제 모델 호출']},{**value['criteria'],'expected_answer':'insufficient_evidence'}]:
                negative=await save(t,ctx,saved,{**value,'criteria':criteria})
                rejected=await t.rpc(ctx,'builder_case_evaluate',(ctx.session_id,ctx.tenant_id,UUID(negative['case_id']),run));assert not rejected['passed']
            wrong=await save(t,ctx,saved,{**value,'values':{**value['values'],'question':'다른 질문'}})
            with pytest.raises(AppError) as e:await t.rpc(ctx,'builder_case_evaluate',(ctx.session_id,ctx.tenant_id,UUID(wrong['case_id']),run))
            assert e.value.status==409
            _,other,_,another=await admit(f,repo);await finish(f,repo,ctx,another['run_id'])
            with pytest.raises(AppError) as e:await t.rpc(ctx,'builder_case_evaluate',(ctx.session_id,ctx.tenant_id,cid,UUID(another['run_id'])))
            assert e.value.status==409
            with f.db.admin_connection() as c:
                assert c.execute('SELECT count(*) FROM ops.call_attempts WHERE run_id=%s',(run,)).fetchone()[0]==1
                for table in ['builder_cases','builder_evaluations']:
                    with pytest.raises(psycopg.errors.CheckViolation):
                        with c.transaction():c.execute('DELETE FROM portal.'+table)
                    with pytest.raises(psycopg.errors.CheckViolation):
                        with c.transaction():c.execute('UPDATE portal.'+table+' SET owner_user_id=owner_user_id')
    f.run(check())

@pytest.mark.parametrize('kind',['search','generate','empty','legacy_search'])
def test_rag_expected_sources_and_insufficient_evidence(ops_rows,tmp_path,kind):
    from app.documents.repository import DocumentRepository
    from app.documents.storage import SourceStorage
    from app.documents.embedding import MockEmbeddingProvider
    from app.ai.rag_provider import RagMockProvider
    from app.ai.gateway import AiGateway
    from app.ai.providers import MockProvider
    from app.builder.execution import TrialExecutor
    from app.execution.rag import RagExecutor
    from test_document_sharing import publish
    f=ops_rows
    async def check():
        async with open_meter_pool(f.db.runtime_dsn('ai_meter')) as meter:
            repo=CallRepository(f.pool,meter,date(2026,10,1));docs=DocumentRepository(f.pool,SourceStorage(tmp_path/'sources'),'x'*40);ctx=await f.context('A-ADM','A');refs=[]
            if kind!='empty':
                ids=await publish(f,docs,ctx);refs=[{k:ids[k] for k in ('document_id','version_id')}]
            ctx,saved,payload,data=await admit(f,repo,'rules_rag',refs,'search' if kind!='generate' else 'generate');t=TrialRepository(f.pool);run=UUID(data['run_id']);value=spec(payload,'insufficient_evidence' if kind=='empty' else 'answer',sources=refs,purpose=payload['purpose']);case=await save(t,ctx,saved,value)
            ticket=await repo.claim(ctx,run,'mock');engine=TrialExecutor(repo,AiGateway(repo,MockProvider()),RagExecutor(repo,docs,MockEmbeddingProvider(),RagMockProvider()));result=await engine.execute(ticket)
            if kind=='legacy_search':
                for candidate in result['candidates']:candidate.pop('source')
            await engine.finish(ticket,result)
            checked=await t.rpc(ctx,'builder_case_evaluate',(ctx.session_id,ctx.tenant_id,UUID(case['case_id']),run));assert checked['passed']==(kind!='legacy_search')
            if kind=='legacy_search':assert any(not x['passed'] and x['rule']=='required_source' for x in checked['checks'])
            if kind!='empty':
                await docs.delete(ctx,UUID(refs[0]['document_id']),1)
                for name,args in [('builder_case_read',(UUID(case['case_id']),)),('builder_case_evaluate',(UUID(case['case_id']),run))]:
                    with pytest.raises(AppError) as e:await t.rpc(ctx,name,(ctx.session_id,ctx.tenant_id,*args))
                    assert e.value.status==404
                with pytest.raises(AppError):await save(t,ctx,saved,value)
    f.run(check())

@pytest.mark.parametrize('actor,tenant,status',[('A-U1','A',403),('DUAL-ADM','A',404),('P-A','A',404),('DUAL-ADM','B',404)])
def test_case_owner_tenant_and_current_management(ops_rows,actor,tenant,status):
    f=ops_rows
    async def check():
        async with open_meter_pool(f.db.runtime_dsn('ai_meter')) as meter:
            repo=CallRepository(f.pool,meter,date(2026,10,1));owner,saved,payload,data=await admit(f,repo);t=TrialRepository(f.pool);case=await save(t,owner,saved,spec(payload));ctx=await f.context(actor,tenant)
            for name,args in [('builder_case_read',(UUID(case['case_id']),)),('builder_case_evaluate',(UUID(case['case_id']),UUID(data['run_id'])))]:
                with pytest.raises(AppError) as e:await t.rpc(ctx,name,(ctx.session_id,ctx.tenant_id,*args))
                assert e.value.status==status
            with f.db.admin_connection() as c:c.execute("UPDATE security.memberships SET role='USER' WHERE user_id=%s",(owner.user_id,))
            with pytest.raises(AppError) as e:await t.rpc(owner,'builder_case_read',(owner.session_id,owner.tenant_id,UUID(case['case_id'])))
            assert e.value.status==403
    f.run(check())

@pytest.mark.parametrize('criteria',[{'required_terms':['']},{'required_terms':['a']*11},{'required_terms':['a','a']},{'required_terms':['a'],'forbidden_terms':['a']},{'required_terms':['a'*201]},{'expected_answer':'approved'},{'required_sources':[{'document_id':'bad','version_id':'bad'}]},{'extra':True}])
def test_case_schema_invalid(criteria):
    from pydantic import ValidationError
    with pytest.raises(ValidationError):CaseRequest(client_request_id=uuid4(),name='평가',values={},criteria={'expected_answer':'answer',**criteria})

def test_case_http_validation_csrf_and_source_scope(client,login,ops_rows):
    from test_builder_profiles import signed
    f=ops_rows
    async def setup():
        async with open_meter_pool(f.db.runtime_dsn('ai_meter')) as meter:
            repo=CallRepository(f.pool,meter,date(2026,10,1));ctx,saved,payload,data=await admit(f,repo);await finish(f,repo,ctx,data['run_id']);return saved,payload,data
    saved,payload,data=f.run(setup());h=signed(client,login,f);path='/api/v1/admin/builder/assets/'+saved['asset_id']+'/versions/'+saved['version_id']+'/evaluation-cases';value={**spec(payload),'client_request_id':str(uuid4())}
    assert client.post(path,headers={k:v for k,v in h.items() if k!='X-CSRF-Token'},json=value).status_code==403
    first=client.post(path,headers=h,json=value);assert first.status_code==201
    assert client.post(path,headers=h,json=value).status_code==200
    assert client.get(path+'?extra=1',headers=h).status_code==422
    cid=first.json()['data']['case_id'];assert client.get('/api/v1/admin/builder/evaluation-cases/'+cid,headers=h).headers['cache-control']=='no-store'
    checked=client.post('/api/v1/admin/builder/evaluation-cases/'+cid+'/checks',headers=h,json={'run_id':data['run_id']});assert checked.status_code==201 and checked.json()['data']['passed']
    assert client.post('/api/v1/admin/builder/evaluation-cases/'+cid+'/checks',headers=h,json={'run_id':data['run_id'],'passed':True}).status_code==422
    send={'client_send_id':str(uuid4())};route='/api/v1/admin/builder/evaluation-cases/'+cid+'/trials'
    trial=client.post(route,headers=h,json=send);assert trial.status_code==201
    again=client.post(route,headers=h,json=send);assert again.status_code==200 and again.json()['data']['run_id']==trial.json()['data']['run_id']
    assert client.post(route,headers=h,json={**send,'purpose':'search'}).status_code==422
    outside={**value,'client_request_id':str(uuid4()),'criteria':{**value['criteria'],'required_sources':[{'document_id':str(uuid4()),'version_id':str(uuid4())}]}}
    assert client.post(path,headers=h,json=outside).status_code==422


def test_case_cursor_and_server_side_rule_validation(ops_rows):
    f=ops_rows
    async def check():
        async with open_meter_pool(f.db.runtime_dsn('ai_meter')) as meter:
            repo=CallRepository(f.pool,meter,date(2026,10,1));ctx,saved,payload,data=await admit(f,repo);t=TrialRepository(f.pool);value=spec(payload)
            ids=[(await save(t,ctx,saved,{**value,'name':str(i)}))['case_id'] for i in range(21)]
            page=await t.rpc(ctx,'builder_case_list',(ctx.session_id,ctx.tenant_id,UUID(saved['asset_id']),UUID(saved['version_id']),None));assert len(page['items'])==20 and page['items'][0]['case_id']==ids[-1]
            rest=await t.rpc(ctx,'builder_case_list',(ctx.session_id,ctx.tenant_id,UUID(saved['asset_id']),UUID(saved['version_id']),UUID(page['next_cursor'])));assert len(rest['items'])==1 and rest['items'][0]['case_id']==ids[0] and rest['next_cursor'] is None
            for change in [{'required_terms':['']},{'required_terms':['a','a']},{'required_terms':['a'],'forbidden_terms':['a']},{'required_sources':[{'document_id':str(uuid4()),'version_id':str(uuid4())}]}]:
                with pytest.raises(AppError) as e:await save(t,ctx,saved,{**value,'criteria':{**value['criteria'],**change}})
                assert e.value.status==422
            with pytest.raises(AppError) as e:await t.rpc(ctx,'builder_case_list',(ctx.session_id,ctx.tenant_id,UUID(saved['asset_id']),UUID(saved['version_id']),uuid4()))
            assert e.value.status==404
    f.run(check())
