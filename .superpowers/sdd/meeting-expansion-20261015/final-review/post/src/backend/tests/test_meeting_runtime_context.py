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

@pytest.mark.parametrize('operation',['dispatch','quality'])
@pytest.mark.parametrize('winner',['fence','withdrawal'])
def test_selected_source_transaction_fence_independent_sessions(ops_rows,tmp_path,operation,winner):
    """Actual RPCs, independent owner sessions, deterministic database barriers."""
    import time
    import hashlib
    import psycopg
    from concurrent.futures import ThreadPoolExecutor
    from dataclasses import replace
    from psycopg.types.json import Jsonb
    from app.documents.repository import DocumentRepository
    from app.documents.storage import SourceStorage
    from app.ai.repository import digest
    f=ops_rows
    async def prepare():
        docs=DocumentRepository(f.pool,SourceStorage(tmp_path/'sources'),'fixture-secret','mock')
        async with open_meter_pool(f.db.runtime_dsn('ai_meter')) as meter:
            repo,workflow,agent,provider,_,user,approver,version,definition=await prepared(f,meter,provider=MeetingProvider())
            try:
                await bind(f,repo,version,definition,user,approver)
                # Neither RPC borrows the seed session. Different session rows avoid
                # touch_session serialization masking the selected-source race.
                sessions=[uuid4(),uuid4()]
                with f.db.admin_connection() as conn:
                    for session in sessions:
                        conn.execute('INSERT INTO security.sessions(session_id,token_hash,user_id,auth_revision,csrf_secret,issued_at,last_activity_at,expires_at) SELECT %s,%s,user_id,auth_revision,csrf_secret,issued_at,last_activity_at,expires_at FROM security.sessions WHERE session_id=%s',(session,uuid4().bytes+uuid4().bytes,user.session_id))
                actor=replace(user,session_id=sessions[0]);mutator=replace(user,session_id=sessions[1])
                registered=await docs.register(actor,{'client_upload_id':uuid4(),'title':'합성 잠금 자료','media_type':'text/plain'},MEMO.encode(),personal=True)
                ref={'document_id':registered['document_id'],'version_id':registered['version_id']}
                service=UseCaseExecutionService(workflow,docs)
                if operation=='dispatch':workflow.notify=lambda *args:None
                run=await service.submit(actor,'AGENT_03',MEMO,uuid4(),'2026-10-15',[ref]);parent=UUID(run['run_id'])
                if operation=='quality':
                    assert (await wait(workflow,actor,run['run_id']))['state']=='completed'
                    quality=await service.meetings.quality(actor,parent)
                    body=QualityReview(client_request_id=uuid4(),expected_review_revision=0,expected_run_revision=quality['run_revision'],result_digest=quality['result_digest'],accuracy='acceptable',omission='not_assessed',owner='not_assessed',deadline='not_assessed',comment='합성 동시성 검토')
                    name='meeting_quality_control';args=(actor.session_id,actor.tenant_id,'review',parent,Jsonb(body.model_dump(mode='json')));call=None
                else:
                    token=uuid4();work=await repo.runtime(actor,'claim',parent,token=token)
                    await repo.runtime(actor,'step',parent,{'node_id':'input'},token)
                    text=work['inputs']['query']
                    await repo.runtime(actor,'checkpoint',parent,{'node_id':'input','result':text},token)
                    await repo.runtime(actor,'step',parent,{'node_id':'agent'},token)
                    config=next(n['config'] for n in definition['nodes'] if n['node_id']=='agent')
                    child=await repo.child(actor,parent,'agent',token,config,{'question':text,'audience':'담당자','rule':'기준'},hashlib.sha256(b'fixture-window').digest())
                    ticket=await agent.repository.claim(actor,UUID(child['run_id']),'mock')
                    reserved=await agent.repository.reserve(ticket,b'x'*32);call=UUID(reserved['call_id'])
                    name='call_dispatch';args=(*agent.repository.worker_args(ticket),call,digest('fixture-dispatch'))
                    assert provider.calls==0
                return actor,mutator,ref,parent,name,args,call
            finally:await workflow.close();await agent.close()
    actor,mutator,ref,parent,name,args,call=f.run(prepare())
    barrier=936015
    with f.db.admin_connection() as observer, f.role_connection('ai_web') as op, f.role_connection('ai_web') as mutation, f.db.admin_connection() as controller:
        assert op.info.backend_pid!=mutation.info.backend_pid
        def identity(conn,ctx):
            assert conn.execute('SELECT * FROM security.current_membership(%s,%s)',(ctx.session_id,ctx.tenant_id)).fetchone()
            for key,value in [('app.user_id',ctx.user_id),('app.tenant_id',ctx.tenant_id),('app.session_id',ctx.session_id)]:conn.execute('SELECT set_config(%s,%s,true)',(key,str(value)))
            conn.execute("SET LOCAL statement_timeout='10s'")
        def protected():
            try:
                with op.transaction():
                    identity(op,actor)
                    if winner=='fence':op.execute("SELECT set_config('fixture.meeting_barrier','on',true)")
                    return op.execute('SELECT security.'+name+'('+','.join(['%s']*len(args))+')',args).fetchone()[0]
            except psycopg.Error as error:return error.sqlstate
        def withdraw():
            with mutation.transaction():
                identity(mutation,mutator)
                return mutation.execute('SELECT security.user_document_delete(%s,%s,%s,%s)',(mutator.session_id,mutator.tenant_id,UUID(str(ref['document_id'])),1)).fetchone()[0]
        def blocked(waiter,blocker):
            limit=time.monotonic()+4
            while time.monotonic()<limit:
                if observer.execute('SELECT %s=ANY(pg_blocking_pids(%s))',(blocker,waiter)).fetchone()[0]:return
                time.sleep(.01)
            pytest.fail('Controlled transaction barrier was not reached')
        # Test-only wrapper pauses after the real fence has acquired/rechecked
        # all selected rows, before call_dispatch/review writes can proceed.
        observer.execute('ALTER FUNCTION security.meeting_sources_guard(uuid,jsonb,boolean) RENAME TO fixture_meeting_sources_guard')
        observer.execute("""CREATE FUNCTION security.meeting_sources_guard(p_tenant uuid,p_documents jsonb,p_admission boolean) RETURNS boolean LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,security,pg_temp AS $$ BEGIN PERFORM security.fixture_meeting_sources_guard(p_tenant,p_documents,p_admission); IF current_setting('fixture.meeting_barrier',true)='on' THEN PERFORM pg_advisory_xact_lock(936015);END IF;RETURN true;END;$$""")
        observer.execute('ALTER FUNCTION security.meeting_sources_guard(uuid,jsonb,boolean) OWNER TO ai_policy_executor')
        observer.execute('REVOKE ALL ON FUNCTION security.meeting_sources_guard(uuid,jsonb,boolean) FROM PUBLIC,ai_web,ai_index,ai_meter')
        try:
            with ThreadPoolExecutor(max_workers=2) as workers:
                if winner=='fence':
                    with controller.transaction():
                        controller.execute('SELECT pg_advisory_xact_lock(%s)',(barrier,))
                        result=workers.submit(protected);blocked(op.info.backend_pid,controller.info.backend_pid)
                        deletion=workers.submit(withdraw);blocked(mutation.info.backend_pid,op.info.backend_pid)
                        assert not result.done() and not deletion.done()
                        assert observer.execute('SELECT count(*) FROM portal.meeting_quality_reviews WHERE parent_id=%s',(parent,)).fetchone()[0]==0
                        if call:assert observer.execute('SELECT state FROM ops.call_attempts WHERE call_id=%s',(call,)).fetchone()[0]=='reserved'
                    value=result.result(timeout=5);deletion.result(timeout=5)
                    assert value is True if operation=='dispatch' else value['review_revision']==1
                else:
                    with mutation.transaction():
                        identity(mutation,mutator)
                        mutation.execute('SELECT security.user_document_delete(%s,%s,%s,%s)',(mutator.session_id,mutator.tenant_id,UUID(str(ref['document_id'])),1))
                        result=workers.submit(protected);blocked(op.info.backend_pid,mutation.info.backend_pid)
                        assert not result.done()
                    assert result.result(timeout=5)=='D0404'
            expected=1 if operation=='quality' and winner=='fence' else 0
            assert observer.execute('SELECT count(*) FROM portal.meeting_quality_reviews WHERE parent_id=%s',(parent,)).fetchone()[0]==expected
            assert observer.execute("SELECT count(*) FROM ops.audit_events WHERE action='meeting.quality_review' AND opaque_target_id=%s",(parent,)).fetchone()[0]==expected
            if call:
                state=observer.execute('SELECT state FROM ops.call_attempts WHERE call_id=%s',(call,)).fetchone()[0]
                assert state==('dispatched' if winner=='fence' else 'reserved')
                claim,dispatched=observer.execute('SELECT dispatch_claim_hash,dispatched_at FROM ops.call_attempts WHERE call_id=%s',(call,)).fetchone()
                assert (claim is not None and dispatched is not None)==(winner=='fence')
        finally:
            observer.execute('DROP FUNCTION security.meeting_sources_guard(uuid,jsonb,boolean)')
            observer.execute('ALTER FUNCTION security.fixture_meeting_sources_guard(uuid,jsonb,boolean) RENAME TO meeting_sources_guard')
