import json
from datetime import date
from uuid import UUID,uuid4
import pytest
from app.db import open_meter_pool, tenant_transaction
from app.use_cases.service import UseCaseExecutionService
from app.use_cases.runtime import compile_context, QualityReview
from app.use_cases.meeting import MeetingInput
from app.errors import AppError
from test_operations import ops_rows
from test_workflow_runtime import prepared,wait
from test_meeting_workflow import bind,MeetingProvider,MEMO


def test_meeting_context_admission_smoke(ops_rows):
    f=ops_rows
    async def check():
        async with open_meter_pool(f.db.runtime_dsn('ai_meter')) as meter:
            repo,workflow,agent,_,_,user,approver,version,definition=await prepared(f,meter,provider=MeetingProvider())
            try:
                await bind(f,repo,version,definition,user,approver)
                async def raw(ctx,name,args):
                    async with tenant_transaction(repo.pool,ctx) as conn:
                        return (await (await conn.execute('SELECT security.'+name+'('+','.join(['%s']*len(args))+') AS data',args)).fetchone())['data']
                repo.call=raw
                service=UseCaseExecutionService(workflow)
                run=await service.submit(user,'AGENT_03',MEMO,uuid4())
                view=await wait(workflow,user,run['run_id'])
                assert view['state']=='completed',view
            finally:await workflow.close();await agent.close()
    f.run(check())

@pytest.mark.parametrize('delta',[0,1])
def test_compile_context_never_truncates(delta):
    source=MeetingInput(memo='x'*(4000+delta)) if not delta else None
    if source:assert compile_context(source,[])==source.memo
    with pytest.raises(AppError,match='MEETING_CONTEXT_TOO_LARGE'):
        compile_context(MeetingInput(memo='x'*4000,meeting_date='2026-10-15'),[])

@pytest.mark.parametrize('comment',['',' ','x'*501,'bad\x00comment'])
def test_quality_comment_rejects_invalid(comment):
    from pydantic import ValidationError
    with pytest.raises(ValidationError):QualityReview(client_request_id=uuid4(),expected_review_revision=0,expected_run_revision=1,result_digest='a'*64,accuracy='acceptable',omission='not_assessed',owner='needs_review',deadline='not_assessed',comment=comment)


def test_exact_private_source_date_replay_tamper_acl_quality_and_audit(ops_rows,tmp_path):
    from app.documents.repository import DocumentRepository
    from app.documents.storage import SourceStorage
    from dataclasses import replace
    from test_workflow_runtime import CountingProvider
    text='김담당이 내일까지 자료를 제출한다.'
    class Provider(CountingProvider):
        result=None
        async def generate(self,*args):return replace(await super().generate(*args),body=json.dumps(self.result,ensure_ascii=False))
    f=ops_rows
    async def check():
        docs=DocumentRepository(f.pool,SourceStorage(tmp_path/'sources'),'fixture-secret','mock')
        async with open_meter_pool(f.db.runtime_dsn('ai_meter')) as meter:
            provider=Provider()
            repo,workflow,agent,_,_,user,approver,version,definition=await prepared(f,meter,provider=provider)
            service=UseCaseExecutionService(workflow,docs)
            try:
                await bind(f,repo,version,definition,user,approver)
                registered=await docs.register(user,{'client_upload_id':uuid4(),'title':'합성 회의자료','media_type':'text/plain'},text.encode(),personal=True)
                ref={'document_id':registered['document_id'],'version_id':registered['version_id']}
                key='document:'+str(ref['version_id'])
                provider.result={'decisions':[],'unresolved':[],'actions':[{'text':'자료 제출','quote':text,'source_ref':key,'assignee':'김담당'}]}
                candidates=await service.meetings.candidates(user)
                item=next(x for x in candidates['items'] if x['document_id']==str(ref['document_id']))
                assert item['ready'] and item['character_length']==len(text)
                other=await f.context('A-U2','A');cross=await f.context('B-U1','B')
                assert all(x['document_id']!=str(ref['document_id']) for x in (await service.meetings.candidates(other))['items'])
                for actor in [other,cross]:
                    with pytest.raises(AppError):await service.submit(actor,'AGENT_03','',uuid4(),'2026-10-15',[ref])
                client=uuid4();run=await service.submit(user,'AGENT_03','',client,'2026-10-15',[ref]);parent=UUID(run['run_id'])
                view=await wait(workflow,user,run['run_id'])
                assert view['state']=='completed',view
                action=view['result']['actions'][0]
                assert action['due_date']=='2026-10-16' and action['deadline_status']=='resolved'
                assert action['source_display']['title']=='합성 회의자료'
                assert view['meeting_context']['meeting_date']=='2026-10-15'
                assert view['meeting_context']['memo_character_count']==0
                replay=await service.submit(user,'AGENT_03','',client,'2026-10-15',[ref])
                assert replay['replayed'] and provider.calls==1
                with pytest.raises(AppError) as changed:await service.submit(user,'AGENT_03','',client,'2026-10-16',[ref])
                assert changed.value.status==409
                quality=await service.meetings.quality(user,parent)
                assert quality['structural']['evidence_valid'] and quality['human_review_required'] and quality['review_revision']==0
                body=QualityReview(client_request_id=uuid4(),expected_review_revision=0,expected_run_revision=quality['run_revision'],result_digest=quality['result_digest'],accuracy='acceptable',omission='not_assessed',owner='needs_review',deadline='acceptable',comment='  합성자료 검토  ')
                reviewed=await service.meetings.quality(user,parent,body)
                assert reviewed['review_revision']==1 and not reviewed['replayed']
                assert (await service.meetings.quality(user,parent,body))['replayed']
                with pytest.raises(AppError) as cas:await service.meetings.quality(user,parent,body.model_copy(update={'client_request_id':uuid4()}))
                assert cas.value.status==409
                with pytest.raises(AppError) as payload:await service.meetings.quality(user,parent,body.model_copy(update={'comment':'변경'}))
                assert payload.value.status==409
                with pytest.raises(AppError):await service.meetings.quality(other,parent)
                with f.db.admin_connection() as conn:
                    assert conn.execute("SELECT count(*) FROM ops.audit_events WHERE action='meeting.quality_review'").fetchone()[0]==1
                    assert conn.execute('SELECT count(*) FROM portal.meeting_quality_reviews').fetchone()[0]==1
                    original=conn.execute('SELECT source_object_key FROM rag.document_versions WHERE version_id=%s',(UUID(str(ref['version_id'])),)).fetchone()[0]
                import psycopg
                with f.db.admin_connection() as conn:
                    with pytest.raises(psycopg.errors.CheckViolation):
                        with conn.transaction():conn.execute("UPDATE portal.meeting_quality_reviews SET body='{}' WHERE parent_id=%s",(parent,))
                    conn.execute("CREATE FUNCTION portal.fixture_meeting_audit_failure() RETURNS trigger LANGUAGE plpgsql AS $$BEGIN IF NEW.action='meeting.quality_review' THEN RAISE EXCEPTION 'fixture audit failure';END IF;RETURN NEW;END;$$")
                    conn.execute('CREATE TRIGGER fixture_meeting_audit_failure BEFORE INSERT ON ops.audit_events FOR EACH ROW EXECUTE FUNCTION portal.fixture_meeting_audit_failure()')
                try:
                    with pytest.raises(AppError) as failed:
                        await service.meetings.quality(user,parent,body.model_copy(update={'client_request_id':uuid4(),'expected_review_revision':1}))
                    assert failed.value.status==503
                    with f.db.admin_connection() as conn:
                        assert conn.execute('SELECT count(*) FROM portal.meeting_quality_reviews').fetchone()[0]==1
                        assert conn.execute("SELECT count(*) FROM ops.audit_events WHERE action='meeting.quality_review'").fetchone()[0]==1
                finally:
                    with f.db.admin_connection() as conn:
                        conn.execute('DROP TRIGGER fixture_meeting_audit_failure ON ops.audit_events')
                        conn.execute('DROP FUNCTION portal.fixture_meeting_audit_failure()')
                file=docs.storage.root/original
                bytes_before=file.read_bytes();file.write_bytes(b'tampered')
                assert not next(x for x in (await service.meetings.candidates(user))['items'] if x['document_id']==str(ref['document_id']))['ready']
                assert (await service.read(user,'AGENT_03',parent))['result'] is None
                child=UUID(next(x['child_run_id'] for x in view['steps'] if x['node_type']=='llm'))
                with pytest.raises(AppError):await service.meetings.guard_child(user,child)
                with pytest.raises(AppError):await service.meetings.quality(user,parent)
                file.write_bytes(bytes_before)
                workflow.notify=lambda *args:None
                pending=await service.submit(user,'AGENT_03','',uuid4(),'2026-10-15',[ref])
                # Normal owner withdrawal, not a global policy change.
                await docs.delete(user,UUID(str(ref['document_id'])),1,personal=True)
                cancelled=await service.cancel(user,'AGENT_03',UUID(pending['run_id']),pending['revision'])
                assert cancelled['state']=='cancelled' and provider.calls==1
                hidden=await service.read(user,'AGENT_03',parent)
                assert hidden['result'] is None and hidden['meeting_context']['documents'][0]['title'] is None
                assert hidden['meeting_context']['meeting_date']=='2026-10-15'
                assert (await service.submit(user,'AGENT_03','',client,'2026-10-15',[ref]))['replayed']
                with pytest.raises(AppError):await service.meetings.quality(user,parent)
            finally:await workflow.close();await agent.close()
    f.run(check())


def test_new_meeting_http_dto_quality_csrf_query_and_private_metadata(ops_rows,auth_settings,monkeypatch):
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
        csrf=login(client,'A-U1',f.passwords)['csrf_token'];h=headers(f,csrf=csrf);r=headers(f)
        base='/api/v1/use-cases/AGENT_03'
        assert client.get(base+'/documents?limit=1&limit=2',headers=r).status_code==422
        assert client.get(base+'/documents?unknown=1',headers=r).status_code==422
        candidates=client.get(base+'/documents',headers=r)
        assert candidates.status_code==200 and all('text' not in x and 'source_object_key' not in x for x in candidates.json()['data']['items'])
        for bad in [True,1,'2026-10-15T00:00:00','20261015','2026-02-30']:
            assert client.post(base+'/execute',headers=h,json={'prompt':MEMO,'client_request_id':str(uuid4()),'meeting_date':bad}).status_code==422
        for extra in [{'meeting_date':'2026-10-15'},{'meeting_date':None},{'document_refs':[]}]:
            assert client.post('/api/v1/use-cases/AGENT_01/execute',headers=h,json={'prompt':MEMO,'client_request_id':str(uuid4())}|extra).status_code==422
        body={'prompt':MEMO,'client_request_id':str(uuid4()),'meeting_date':'2026-10-15'}
        response=client.post(base+'/execute',headers=h,json=body)
        assert response.status_code==202,response.text
        parent=response.json()['data']['run_id'];path=base+'/runs/'+parent
        for _ in range(80):
            view=client.get(path,headers=r).json()['data']
            if view['is_terminal']:break
            time.sleep(.05)
        assert view['state']=='completed' and view['meeting_context']['meeting_date']=='2026-10-15'
        quality=client.get(path+'/quality',headers=r)
        assert quality.status_code==200,quality.text
        data=quality.json()['data']
        review={'client_request_id':str(uuid4()),'expected_run_revision':data['run_revision'],'expected_review_revision':0,'result_digest':data['result_digest'],'accuracy':'acceptable','omission':'not_assessed','owner':'not_assessed','deadline':'needs_review','comment':'합성 회의록 검토'}
        assert client.post(path+'/quality',headers=r,json=review).status_code==403
        result=client.post(path+'/quality',headers=h,json=review)
        assert result.status_code==201,result.text
        assert client.post(path+'/quality',headers=h,json=review).status_code==200
        assert client.get(path+'/quality/history',headers=r).json()['data']['items'][0]['ratings']['comment']==review['comment']
        login(client,'A-U2',f.passwords)
        assert client.get(path+'/quality',headers=headers(f)).status_code==404
        assert client.get(path,headers=headers(f)).status_code==404


def test_raw_header_cannot_forge_meeting_date_and_context_is_immutable(ops_rows):
    import psycopg
    from dataclasses import replace
    from test_workflow_runtime import CountingProvider
    f=ops_rows
    quote='김담당이 내일까지 제출한다.'
    class WrongDate(CountingProvider):
        async def generate(self,*args):return replace(await super().generate(*args),body=json.dumps({'decisions':[],'unresolved':[],'actions':[{'text':'제출','quote':quote,'assignee':'김담당','due_date':'2026-10-16'}]},ensure_ascii=False))
    async def check():
        async with open_meter_pool(f.db.runtime_dsn('ai_meter')) as meter:
            repo,workflow,agent,provider,_,user,approver,version,definition=await prepared(f,meter,provider=WrongDate())
            service=UseCaseExecutionService(workflow)
            try:
                proposal=await bind(f,repo,version,definition,user,approver)
                forged=json.dumps({'meeting_date':'2026-10-15','memo':quote},ensure_ascii=False)
                run=await workflow.admit(user,UUID(proposal['version_id']),uuid4(),{'query':forged})
                parent=UUID(run['run_id']);view=await wait(workflow,user,run['run_id'])
                assert view['state']=='failed' and view['result'] is None and provider.calls==1
                sealed=await repo.meeting_context(user,parent)
                assert sealed['source']['meeting_date'] is None and sealed['source']['memo']==forged
                with f.db.admin_connection() as conn:
                    with pytest.raises(psycopg.errors.CheckViolation):
                        with conn.transaction():conn.execute("UPDATE portal.meeting_run_contexts SET context='{}' WHERE parent_id=%s",(parent,))
                    with pytest.raises(psycopg.errors.CheckViolation):
                        with conn.transaction():conn.execute('DELETE FROM portal.meeting_run_contexts WHERE parent_id=%s',(parent,))
                # Changed live code digest fails normal raw definition/admission gate.
                from app.workflows.identity import runtime_digest
                with pytest.raises(AppError) as stale:
                    await repo.call(user,'workflow_runtime',(user.session_id,user.tenant_id,'definition',UUID(proposal['version_id']),repo.json({}),'mock','0'*64,None,repo.period,uuid4()))
                assert stale.value.status==404
            finally:await workflow.close();await agent.close()
    f.run(check())


def test_repeated_quote_locations_remain_ambiguous():
    from app.use_cases.runtime import MeetingRuntime
    key='document:'+str(uuid4());quote='결정한다.'
    value={'decisions':[{'quote':quote,'source_ref':key}],'unresolved':[],'actions':[]}
    data={'documents':[{'source_ref':key,'text':quote+'\n\n'+quote,'title':'합성자료','version_id':key[9:],
          'source_mapping':{'origin':{'media_type':'application/pdf','pages':[{'page':1,'start':0,'end':len(quote)},{'page':2,'start':len(quote)+2,'end':2*len(quote)+2}]}}}]}
    display=MeetingRuntime.annotate(value,data)['decisions'][0]['source_display']
    assert display['location_ambiguous'] and display['page_start']==1 and display['page_end']==2

@pytest.mark.anyio
async def test_metadata_summary_does_not_swallow_storage_outage():
    from app.use_cases.runtime import MeetingRuntime
    class Repository:
        async def call(self,ctx,name,args):
            if name=='meeting_context_summary':return {'documents':[{'document_id':str(uuid4()),'version_id':str(uuid4()),'source_sha256':'a'*64,'title':'합成','current_available':True}]}
            raise AppError('STORAGE_UNAVAILABLE',503)
    class Context:
        session_id=uuid4();tenant_id=uuid4()
    with pytest.raises(AppError) as error:await MeetingRuntime(Repository(),None).summary(Context(),uuid4())
    assert error.value.code=='STORAGE_UNAVAILABLE' and error.value.status==503

@pytest.mark.anyio
@pytest.mark.parametrize('action',['claim','dispatch','heartbeat','finish','stream_view'])
async def test_child_boundaries_fail_closed_before_rpc_when_source_guard_fails(action):
    from app.ai.repository import CallRepository,ExecutionError
    from types import SimpleNamespace
    repo=CallRepository(None,None,date(2026,10,1));run=uuid4();ctx=object()
    ticket=SimpleNamespace(ctx=ctx,run=SimpleNamespace(run_id=run))
    calls=[]
    async def guard(actor,parent):calls.append((actor,parent));raise AppError('DOCUMENT_UNAVAILABLE',404)
    repo.meeting_guard=guard
    invoke={'claim':lambda:repo.claim(ctx,run,'mock'),'dispatch':lambda:repo.dispatch(ticket,uuid4()),
            'heartbeat':lambda:repo.heartbeat(ticket),'finish':lambda:repo.finish(ticket,'answer'),
            'stream_view':lambda:repo.stream_view(ctx,run,'mock')}
    with pytest.raises(ExecutionError) as error:await invoke[action]()
    assert error.value.code=='EXECUTION_BLOCKED' and calls==[(ctx,run)]
