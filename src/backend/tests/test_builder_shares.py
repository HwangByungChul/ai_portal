from uuid import UUID,uuid4
from datetime import date
import pytest,psycopg
from psycopg.types.json import Jsonb
from app.builder.trials import TrialRepository
from app.builder.shares import ShareRepository
from app.ai.repository import CallRepository
from app.db import open_meter_pool
from app.errors import AppError
from test_operations import ops_rows
from test_builder_trials import admit
from test_builder_evidence import finish
from test_builder_evaluations import spec,save

async def share(t,ctx,action='submit',sid=None,body=None,mode='mock'):
    return await ShareRepository(t.pool).call(ctx,action,UUID(sid) if sid else None,body or {},mode)
async def setup(f,repo,terms=None):
    ctx,saved,payload,data=await admit(f,repo);await finish(f,repo,ctx,data['run_id']);t=TrialRepository(f.pool)
    case=await save(t,ctx,saved,spec(payload,terms=terms or ['모의 AI 응답']))
    evaluation=await t.rpc(ctx,'builder_case_evaluate',(ctx.session_id,ctx.tenant_id,UUID(case['case_id']),UUID(data['run_id'])))
    body={'client_request_id':str(uuid4()),'run_id':data['run_id'],'evaluation_id':evaluation['evaluation_id'],'consent':True}
    return ctx,saved,t,body,evaluation

@pytest.mark.parametrize('terms,expected',[(['모의 AI 응답'],True),(['없는 기대문구'],False)])
def test_consented_share_minimum_exact_binding_replay_and_withdraw(ops_rows,terms,expected):
    f=ops_rows
    async def check():
        async with open_meter_pool(f.db.runtime_dsn('ai_meter')) as meter:
            repo=CallRepository(f.pool,meter,date(2026,10,1));ctx,saved,t,body,e=await setup(f,repo,terms);assert e['passed']==expected
            first=await share(t,ctx,body=body);assert not first['replayed'];sid=first['share_id']
            assert (await share(t,ctx,body=body))=={**first,'replayed':True}
            reviewer=await f.context('P-A','A');view=await share(t,reviewer,'detail',sid);snap=view['snapshot']
            assert not view['can_withdraw'] and all(view['current_conditions'].values())
            assert snap['asset_binding']['version_id']==saved['version_id'] and snap['evaluation']['evaluation_id']==e['evaluation_id']
            assert snap['evaluation']['case_hash']==e['case_hash'] and snap['result_hash']==e['result_hash']
            assert all(set(x)=={'rule','passed'} for x in snap['evaluation']['checks'])
            assert '모의 AI 응답' not in str(snap) and not any(k in snap for k in ('result','messages','values','spec','assessments','price_snapshots'))
            for name,args in [('builder_trial_evidence',(UUID(body['run_id']),)),('builder_case_read',(UUID(e['case_id']),))]:
                with pytest.raises(AppError) as denied:await t.rpc(reviewer,name,(reviewer.session_id,reviewer.tenant_id,*args))
                assert denied.value.status==404
            with pytest.raises(AppError) as denied:await share(t,reviewer,'withdraw',sid,{'expected_revision':1})
            assert denied.value.status==403
            page=await share(t,reviewer,'list');assert page['items'][0]['share_id']==sid and 'snapshot' not in page['items'][0]
            with pytest.raises(AppError) as conflict:await share(t,ctx,'withdraw',sid,{'expected_revision':2})
            assert conflict.value.status==409
            withdrawn=await share(t,ctx,'withdraw',sid,{'expected_revision':1});assert withdrawn['revision']==2
            assert (await share(t,ctx,'withdraw',sid,{'expected_revision':1}))['replayed']
            assert (await share(t,reviewer,'detail',sid))['snapshot'] is None
            with f.db.admin_connection() as c:
                assert c.execute('SELECT count(*) FROM portal.builder_evidence_shares').fetchone()[0]==1
                assert c.execute('SELECT count(*) FROM ops.call_attempts').fetchone()[0]==1
                for command in ['DELETE FROM portal.builder_evidence_shares',"UPDATE portal.builder_evidence_shares SET snapshot='{}'"]:
                    with pytest.raises(psycopg.errors.CheckViolation):
                        with c.transaction():c.execute(command)
    f.run(check())

@pytest.mark.parametrize('actor,tenant,status',[('A-U1','A',403),('DUAL-ADM','A',404),('DUAL-ADM','B',404),('P_READ_ONLY','A',403)])
def test_share_current_role_and_scope(ops_rows,actor,tenant,status):
    f=ops_rows
    async def check():
        async with open_meter_pool(f.db.runtime_dsn('ai_meter')) as meter:
            ctx,saved,t,body,e=await setup(f,CallRepository(f.pool,meter,date(2026,10,1)));receipt=await share(t,ctx,body=body);other=await f.context(actor,tenant)
            with pytest.raises(AppError) as error:await share(t,other,'detail',receipt['share_id'])
            assert error.value.status==status
            with f.db.admin_connection() as c:c.execute("UPDATE security.memberships SET role='USER' WHERE tenant_id=%s AND user_id=%s",(ctx.tenant_id,ctx.user_id))
            with pytest.raises(AppError) as error:await share(t,ctx,'withdraw',receipt['share_id'],{'expected_revision':1})
            assert error.value.status==403
    f.run(check())

def test_share_exact_evaluation_and_current_version_mode(ops_rows):
    f=ops_rows
    async def check():
        async with open_meter_pool(f.db.runtime_dsn('ai_meter')) as meter:
            repo=CallRepository(f.pool,meter,date(2026,10,1));ctx,saved,t,body,e=await setup(f,repo)
            for changes in [{'consent':False},{'run_id':None},{'client_request_id':None},{'consent':True,'extra':True}]:
                with pytest.raises(AppError) as error:await share(t,ctx,body=body|changes)
                assert error.value.status==422
            with pytest.raises(AppError) as error:await share(t,ctx,body=body,mode='real')
            assert error.value.status==409
            _,second,t,other,other_e=await setup(f,repo)
            with pytest.raises(AppError) as error:await share(t,ctx,body=body|{'evaluation_id':other_e['evaluation_id']})
            assert error.value.status==409
            first=await share(t,ctx,body=body)
            with pytest.raises(AppError) as error:await share(t,ctx,body=other|{'client_request_id':body['client_request_id']})
            assert error.value.status==409
            # A later policy revision is a visible mismatch, never a rewritten snapshot.
            with f.db.admin_connection() as c:c.execute("UPDATE portal.agent_configs SET config_version=config_version+1 WHERE tenant_id=%s AND agent_key='general'",(ctx.tenant_id,))
            view=await share(t,await f.context('P-A','A'),'detail',first['share_id']);assert not view['current_conditions']['same_policy'] and view['snapshot']['policy_revision']==1
    f.run(check())

def test_share_http_consent_csrf_queries_no_store(client,login,ops_rows):
    from test_builder_profiles import signed
    f=ops_rows
    async def prepare():
        async with open_meter_pool(f.db.runtime_dsn('ai_meter')) as meter:return await setup(f,CallRepository(f.pool,meter,date(2026,10,1)))
    ctx,saved,t,body,e=f.run(prepare());h=signed(client,login,f);path='/api/v1/admin/builder/evidence-shares'
    assert client.post(path,headers={k:v for k,v in h.items() if k!='X-CSRF-Token'},json=body).status_code==403
    assert client.post(path,headers=h,json=body|{'consent':False}).status_code==422
    first=client.post(path,headers=h,json=body);assert first.status_code==201;sid=first.json()['data']['share_id']
    assert client.post(path,headers=h,json=body).status_code==200
    assert client.get(path+'?extra=1',headers=h).status_code==422
    assert client.get(path+'?cursor='+sid+'&cursor='+sid,headers=h).status_code==422
    view=client.get(path+'/'+sid,headers=h);assert view.status_code==200 and view.headers['cache-control']=='no-store'
    assert client.post(path+'/'+sid+'/withdraw',headers=h,json={'expected_revision':1}).status_code==200

@pytest.mark.parametrize('permitted',[False,True])
def test_share_reviewer_own_private_source_acl_and_withdraw_after_delete(ops_rows,tmp_path,permitted):
    from app.documents.repository import DocumentRepository
    from app.documents.storage import SourceStorage
    from app.documents.embedding import MockEmbeddingProvider
    from app.ai.rag_provider import RagMockProvider
    from app.ai.gateway import AiGateway
    from app.ai.providers import MockProvider
    from app.builder.execution import TrialExecutor
    from app.execution.rag import RagExecutor
    from test_document_sharing import publish
    from test_document_ingest import metadata
    f=ops_rows
    async def check():
        async with open_meter_pool(f.db.runtime_dsn('ai_meter')) as meter:
            repo=CallRepository(f.pool,meter,date(2026,10,1));docs=DocumentRepository(f.pool,SourceStorage(tmp_path/'sources'),'x'*40);ctx=await f.context('A-ADM','A')
            reviewer=await f.context('P-A','A')
            ids=await publish(f,docs,ctx,metadata(visibility='private',owner_user_id=ctx.user_id,reader_ids=[reviewer.user_id] if permitted else []));refs=[{k:ids[k] for k in ('document_id','version_id')}]
            ctx,saved,payload,data=await admit(f,repo,'rules_rag',refs,'search');t=TrialRepository(f.pool)
            ticket=await repo.claim(ctx,UUID(data['run_id']),'mock');engine=TrialExecutor(repo,AiGateway(repo,MockProvider()),RagExecutor(repo,docs,MockEmbeddingProvider(),RagMockProvider()));await engine.finish(ticket,await engine.execute(ticket))
            case=await save(t,ctx,saved,spec(payload,sources=refs,purpose='search'));e=await t.rpc(ctx,'builder_case_evaluate',(ctx.session_id,ctx.tenant_id,UUID(case['case_id']),UUID(data['run_id'])))
            body={'client_request_id':str(uuid4()),'run_id':data['run_id'],'evaluation_id':e['evaluation_id'],'consent':True};first=await share(t,ctx,body=body);reviewer=await f.context('P-A','A')
            assert len((await share(t,reviewer,'list'))['items'])==1
            if permitted:
                view=await share(t,reviewer,'detail',first['share_id']);assert view['snapshot']['sources'][0]['version_id']==ids['version_id']
            else:
                with pytest.raises(AppError) as denied:await share(t,reviewer,'detail',first['share_id'])
                assert denied.value.status==404
            await docs.delete(ctx,UUID(ids['document_id']),1)
            with pytest.raises(AppError) as denied:await share(t,reviewer,'detail',first['share_id'])
            assert denied.value.status==404
            with pytest.raises(AppError) as denied:await share(t,ctx,body=body)
            assert denied.value.status==404
            assert (await share(t,ctx,'withdraw',first['share_id'],{'expected_revision':1}))['status']=='withdrawn'
            assert (await share(t,reviewer,'detail',first['share_id']))['snapshot'] is None
    f.run(check())

def test_share_cursor_queue_failed_checks_and_old_version(ops_rows):
    from app.builder.repository import BuilderRepository
    from test_builder_profiles import body as profile_body
    f=ops_rows
    async def check():
        async with open_meter_pool(f.db.runtime_dsn('ai_meter')) as meter:
            repo=CallRepository(f.pool,meter,date(2026,10,1));ctx,saved,t,body,e=await setup(f,repo)
            receipts=[await share(t,ctx,body=body|{'client_request_id':str(uuid4())}) for _ in range(20)]
            with pytest.raises(AppError):await share(t,ctx,body=body)
            await share(t,ctx,'withdraw',receipts[0]['share_id'],{'expected_revision':1})
            last=await share(t,ctx,body=body);page=await share(t,ctx,'list');assert len(page['items'])==20 and page['next_cursor']
            rest=await share(t,ctx,'list',body={'cursor':page['next_cursor']});assert len(rest['items'])==1 and rest['next_cursor'] is None
            with pytest.raises(AppError) as denied:await share(t,ctx,'list',body={'cursor':str(uuid4())})
            assert denied.value.status==404
            # Immutable old evidence remains visible with a mismatch flag; new submissions require latest version.
            value=profile_body();value['expected_revision']=1
            await BuilderRepository(f.pool).call(ctx,'append',UUID(saved['asset_id']),body=value,trace=uuid4())
            view=await share(t,ctx,'detail',last['share_id']);assert not view['current_conditions']['latest_version']
            with pytest.raises(AppError) as conflict:await share(t,ctx,body=body)
            assert conflict.value.status==409
    f.run(check())
