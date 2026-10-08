from uuid import UUID,uuid4
from datetime import date
from dataclasses import replace
import json,asyncio
import pytest,psycopg
from app.ai.repository import CallRepository,ExecutionError,digest
from app.ai.summary_provider import SummaryMockProvider,SummaryOpenAIProvider
from app.execution.document_summary import SummaryExecutor
from app.execution.summary_repository import SummaryRepository
from app.execution.exports import markdown_attachment
from app.documents.repository import DocumentRepository
from app.documents.storage import SourceStorage
from app.documents.sharing import SharingRepository
from app.db import open_meter_pool,tenant_transaction
from app.errors import AppError
from app.conversations.repository import ConversationRepository
from test_operations import ops_rows
from test_document_sharing import publish
from test_document_ingest import metadata

PERIOD=date(2026,10,1)
RAW='첫째 안내는 원문 확인이다.\n둘째 일정은 2026년 10월 7일이다.\n셋째 검토 금액은 100억원이다.\n넷째 문서는 보존한다.'.encode()
def setup(f,tmp_path):return DocumentRepository(f.pool,SourceStorage(tmp_path/'sources'),'x'*40)
async def admit(f,docs,ctx,ids,send=None,count=3,parent=None,expected=None):
    return await SummaryRepository(docs).admit(ctx,{'document_id':UUID(ids['document_id']),'version_id':UUID(ids['version_id'])},count,send or uuid4(),PERIOD,'mock',b'x'*32,uuid4(),parent,expected)
async def execute(f,docs,ctx,ids,provider=None):
    data=await admit(f,docs,ctx,ids)
    async with open_meter_pool(f.db.runtime_dsn('ai_meter')) as meter:
        repo=CallRepository(f.pool,meter,PERIOD);ticket=await repo.claim(ctx,UUID(data['run_id']),'mock');assert ticket.task_kind=='document_summary'
        engine=SummaryExecutor(repo,docs,provider or SummaryMockProvider());result=await engine.execute(ticket);assert await engine.finish(ticket,result)
    return data,ticket,result

def test_complete_ordinary_no_graph_single_call_and_private_acl(ops_rows,tmp_path):
    f=ops_rows
    async def check():
        admin=await f.context('A-ADM','A');ctx=await f.context('A-U1','A');docs=setup(f,tmp_path)
        ids=await publish(f,docs,admin,metadata(visibility='private',owner_user_id=ctx.user_id),RAW)
        data,ticket,result=await execute(f,docs,ctx,ids)
        view=await SummaryRepository(docs).read(ctx,ticket.run.run_id)
        assert view['result']['text']==result.body and view['content_status']=='final' and len(view['evidence'])==3
        for x in view['evidence']:
            loc=x['location'];assert x['quote']==RAW.decode()[loc['start_offset']:loc['end_offset']]
            assert x['source_url']==f'/api/v1/document-summaries/{ticket.run.run_id}/evidence/{x["ordinal"]}/source'
            assert x['source_media_type']=='text/plain'
        attachment=markdown_attachment(view,'safe-request')
        assert attachment.headers['content-disposition']=='attachment; filename="summary.md"' and attachment.headers['cache-control']=='no-store' and 'text/markdown' in attachment.headers['content-type']
        for actor,org in [('A-ADM','A'),('A-U2','A'),('B-U1','B')]:
            with pytest.raises(AppError) as error:await SummaryRepository(docs).read(await f.context(actor,org),ticket.run.run_id)
            assert error.value.status==404
        async with tenant_transaction(f.pool,ctx) as c:
            assert await (await c.execute("SELECT body FROM portal.messages WHERE run_id=%s AND role='assistant'",(ticket.run.run_id,))).fetchone() is None
            ordinary=(await (await c.execute("SELECT security.run_read(%s,%s,'run',%s,NULL,20) AS data",(ctx.session_id,ctx.tenant_id,ticket.run.run_id))).fetchone())['data'];assert ordinary['result'] is None and ordinary['content_status']=='unavailable'
        with f.db.admin_connection() as c:
            assert c.execute('SELECT count(*) FROM rag.relations WHERE index_id=%s',(UUID(ids['index_id']),)).fetchone()[0]==0
            assert c.execute("SELECT operation,state FROM ops.call_attempts WHERE run_id=%s",(ticket.run.run_id,)).fetchall()==[('generate_rag','settled')]
    f.run(check())

@pytest.mark.parametrize('case',['extra','unknown_id','duplicate','prose','over512'])
def test_invalid_model_outputs_meter_once_no_body(ops_rows,tmp_path,case):
    f=ops_rows
    class Bad(SummaryMockProvider):
        calls=0
        async def generate(self,*args):
            self.calls+=1;out=await super().generate(*args)
            body={'extra':'{"selected_ids":["U0"],"extra":"999억원"}','unknown_id':'{"selected_ids":["bad"]}','duplicate':'{"selected_ids":["U0","U0"]}','prose':'made up prose','over512':'x '*600}[case]
            return replace(out,body=body)
    async def check():
        ctx=await f.context('A-U1','A');docs=setup(f,tmp_path);ids=await publish(f,docs,await f.context('A-ADM','A'),raw=RAW);data=await admit(f,docs,ctx,ids);provider=Bad()
        async with open_meter_pool(f.db.runtime_dsn('ai_meter')) as meter:
            repo=CallRepository(f.pool,meter,PERIOD);ticket=await repo.claim(ctx,UUID(data['run_id']),'mock');engine=SummaryExecutor(repo,docs,provider)
            with pytest.raises(ExecutionError,match='SUMMARY_OUTPUT_INVALID'):await engine.execute(ticket)
            with pytest.raises(ExecutionError):await engine.execute(ticket)
            await repo.fail(ticket,'SUMMARY_OUTPUT_INVALID')
        assert provider.calls==1
        with f.db.admin_connection() as c:
            assert c.execute('SELECT result FROM portal.summary_requests WHERE run_id=%s',(ticket.run.run_id,)).fetchone()==(None,)
            assert c.execute('SELECT state FROM ops.call_attempts WHERE run_id=%s',(ticket.run.run_id,)).fetchall()==[('settled',)]
    f.run(check())

def test_send_replay_conflict_regenerate_distinct_parent(ops_rows,tmp_path):
    f=ops_rows
    async def check():
        ctx=await f.context('A-U1','A');docs=setup(f,tmp_path);ids=await publish(f,docs,await f.context('A-ADM','A'),raw=RAW);send=uuid4();first=await admit(f,docs,ctx,ids,send);retry=await admit(f,docs,ctx,ids,send)
        assert first['run_id']==retry['run_id'] and retry['replayed']
        with pytest.raises(AppError,match='SEND_ID_CONFLICT'):await admit(f,docs,ctx,ids,send,5)
        with pytest.raises(AppError):await ConversationRepository(f.pool).admit(ctx,'rules_rag',UUID(first['conversation_id']),uuid4(),'ordinary prompt',PERIOD,'mock',b'x'*32,uuid4(),documents=docs)
        async with open_meter_pool(f.db.runtime_dsn('ai_meter')) as meter:
            repo=CallRepository(f.pool,meter,PERIOD);ticket=await repo.claim(ctx,UUID(first['run_id']),'mock');engine=SummaryExecutor(repo,docs,SummaryMockProvider());result=await engine.execute(ticket);assert await engine.finish(ticket,result)
        old=await SummaryRepository(docs).read(ctx,ticket.run.run_id);regen_send=uuid4();new=await admit(f,docs,ctx,ids,regen_send,parent=ticket.run.run_id,expected=old['revision'])
        assert new['run_id']!=first['run_id'] and new['conversation_id']!=first['conversation_id']
        replay=await admit(f,docs,ctx,ids,regen_send,parent=ticket.run.run_id,expected=old['revision']);assert replay['replayed']
        assert (await SummaryRepository(docs).request(ctx,UUID(new['run_id'])))['parent_run_id']==first['run_id']
    f.run(check())

@pytest.mark.parametrize('when',['before_claim','during_provider','before_finish','after_finish'])
def test_shared_source_revocation_every_gate(ops_rows,tmp_path,when):
    f=ops_rows
    class Provider(SummaryMockProvider):
        async def generate(self,*args):
            out=await super().generate(*args)
            if when=='during_provider':
                with f.db.admin_connection() as c:c.execute('UPDATE security.share_grants SET active=false,revoked_at=clock_timestamp()')
            return out
    async def check():
        a=await f.context('A-ADM','A');ctx=await f.context('B-U1','B');docs=setup(f,tmp_path);ids=await publish(f,docs,a,raw=RAW);sharing=SharingRepository(docs);grant=await sharing.control(a,UUID(ids['document_id']),UUID(ids['version_id']),'issue',f.tenant_ids['B'],expected=1,request=uuid4());data=await admit(f,docs,ctx,ids)
        async def revoke():await sharing.control(a,action='revoke',grant=UUID(grant['grant_id']),expected=1,request=uuid4())
        async with open_meter_pool(f.db.runtime_dsn('ai_meter')) as meter:
            repo=CallRepository(f.pool,meter,PERIOD)
            if when=='before_claim':
                await revoke()
                with pytest.raises(ExecutionError):await repo.claim(ctx,UUID(data['run_id']),'mock')
                return
            ticket=await repo.claim(ctx,UUID(data['run_id']),'mock');engine=SummaryExecutor(repo,docs,Provider());result=await engine.execute(ticket)
            if when=='before_finish':await revoke()
            if when in ('during_provider','before_finish'):
                with pytest.raises((ExecutionError,AppError)):await engine.finish(ticket,result)
                await repo.fail(ticket,'EXECUTION_BLOCKED')
            else:
                assert await engine.finish(ticket,result);await revoke()
            for action in (lambda:SummaryRepository(docs).read(ctx,ticket.run.run_id),lambda:SummaryRepository(docs).request(ctx,ticket.run.run_id),lambda:admit(f,docs,ctx,ids,send=uuid4())):
                with pytest.raises(AppError) as error:await action()
                assert error.value.status==404
        with f.db.admin_connection() as c:
            assert c.execute('SELECT count(*) FROM portal.summary_evidence').fetchone()[0]==(3 if when=='after_finish' else 0)
    f.run(check())

@pytest.mark.parametrize('case',['canonical_corrupt','original_corrupt','source_policy','policy_unavailable','candidate_limit','input_limit','fragment','empty'])
def test_source_policy_and_whole_input_boundaries_before_dispatch(ops_rows,tmp_path,case,monkeypatch):
    f=ops_rows
    async def check():
        ctx=await f.context('A-U1','A');docs=setup(f,tmp_path)
        raw=('# heading only').encode() if case=='empty' else ('완전한 단위이다.\n'*129).encode() if case=='candidate_limit' else ('word '*600+'.').encode() if case=='fragment' else RAW
        ids=await publish(f,docs,await f.context('A-ADM','A'),metadata(media_type='text/markdown') if case=='empty' else None,raw)
        if case=='canonical_corrupt':
            with f.db.admin_connection() as c:key=c.execute('SELECT source_object_key FROM rag.document_versions WHERE version_id=%s',(UUID(ids['version_id']),)).fetchone()[0]
            path=docs.storage.root/key;path.write_bytes(b'changed')
        if case=='original_corrupt':
            from app.documents.storage import SourceStorageError
            monkeypatch.setattr(docs.storage,'read',lambda *_:(_ for _ in ()).throw(SourceStorageError('fixed')))
        if case=='source_policy':monkeypatch.setattr('app.execution.summary_repository.require_summary_policy',lambda *_:(_ for _ in ()).throw(AppError('DOCUMENT_POLICY_BLOCKED',422)))
        if case=='policy_unavailable':monkeypatch.setattr('app.policies.document_ingest.evaluate_document_policy',lambda *_:(_ for _ in ()).throw(RuntimeError('fixed')))
        if case=='input_limit':monkeypatch.setattr('app.execution.summary_repository.general_token_count',lambda *_:6001)
        if case=='empty':
            _,ticket,result=await execute(f,docs,ctx,ids);assert result.answer_kind=='insufficient_evidence'
        else:
            with pytest.raises(AppError) as err:await admit(f,docs,ctx,ids)
            assert err.value.status==(503 if case in ('canonical_corrupt','original_corrupt','policy_unavailable') else 422)
        with f.db.admin_connection() as c:assert c.execute('SELECT count(*) FROM ops.call_attempts WHERE run_id IS NOT NULL').fetchone()[0]==0
    f.run(check())

@pytest.mark.parametrize('case',['cancel','unknown','missing_usage','bad_seal','rag_bypass'])
def test_fencing_unknown_and_seal_boundaries(ops_rows,tmp_path,case):
    f=ops_rows
    class Provider(SummaryMockProvider):
        calls=0
        async def generate(self,*args):
            self.calls+=1
            if case=='unknown':raise TimeoutError()
            out=await super().generate(*args);return replace(out,receipt=None) if case=='missing_usage' else out
    async def check():
        ctx=await f.context('A-U1','A');docs=setup(f,tmp_path);ids=await publish(f,docs,await f.context('A-ADM','A'),raw=RAW);data=await admit(f,docs,ctx,ids);provider=Provider()
        async with open_meter_pool(f.db.runtime_dsn('ai_meter')) as meter:
            repo=CallRepository(f.pool,meter,PERIOD);ticket=await repo.claim(ctx,UUID(data['run_id']),'mock');engine=SummaryExecutor(repo,docs,provider)
            if case=='rag_bypass':
                async with tenant_transaction(f.pool,ctx) as c:
                    for sql,args in [('SELECT security.rag_call_reserve(%s,%s,%s,%s,%s,%s,%s,%s,%s)',(*repo.worker_args(ticket),PERIOD,b'x'*32,'embed_query',__import__('psycopg').types.json.Jsonb([]))),('SELECT security.rag_finish(%s,%s,%s,%s,%s,%s,%s,%s)',(*repo.worker_args(ticket),'made up','insufficient_evidence',__import__('psycopg').types.json.Jsonb([]))),('SELECT security.execution_finish(%s,%s,%s,%s,%s,%s)',(*repo.worker_args(ticket),'made up'))]:
                        with pytest.raises(psycopg.Error):
                            async with c.transaction():await c.execute(sql,args)
                assert provider.calls==0;return
            if case=='unknown':
                with pytest.raises(ExecutionError):await engine.execute(ticket)
                with pytest.raises(ExecutionError):await engine.execute(ticket)
                await repo.fail(ticket,'PROVIDER_ERROR')
            else:
                result=await engine.execute(ticket)
                if case=='cancel':
                    view=await SummaryRepository(docs).read(ctx,ticket.run.run_id);await ConversationRepository(f.pool).cancel(ctx,ticket.run.run_id,view['revision'],uuid4())
                if case=='bad_seal':result=replace(result,body='1. invented 999억원')
                if case in ('cancel','bad_seal'):
                    with pytest.raises(ExecutionError):await engine.finish(ticket,result)
                    await repo.fail(ticket,'SUMMARY_OUTPUT_INVALID')
                else:assert await engine.finish(ticket,result)
            assert provider.calls==1
        with f.db.admin_connection() as c:
            state,end=c.execute('SELECT state,provider_end_status FROM ops.call_attempts WHERE run_id=%s',(ticket.run.run_id,)).fetchone()
            assert state==('usage_unknown' if case in ('unknown','missing_usage') else 'settled')
            if case=='unknown':assert end=='unknown'
            assert c.execute('SELECT count(*) FROM portal.summary_evidence').fetchone()[0]==(3 if case=='missing_usage' else 0)
    f.run(check())

def test_summary_catalog_security(ops_rows):
    f=ops_rows;f.verify_catalog()
    with f.db.admin_connection() as c:
        for table in ('portal.summary_requests','portal.summary_evidence'):
            assert c.execute("SELECT has_table_privilege(%s,%s,'SELECT')",('ai_meter',table)).fetchone()[0] is False
            assert c.execute("SELECT has_table_privilege(%s,%s,'UPDATE')",('ai_web',table)).fetchone()[0] is False
        assert c.execute("SELECT count(*) FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace WHERE n.nspname='portal' AND c.relname IN ('summary_requests','summary_evidence') AND c.relrowsecurity AND c.relforcerowsecurity").fetchone()[0]==2
    assert SummaryOpenAIProvider.max_completion_tokens==512

@pytest.mark.parametrize('media',['application/pdf','application/vnd.openxmlformats-officedocument.wordprocessingml.document','application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'])
def test_structured_original_leaf_locations_and_pair_integrity(ops_rows,tmp_path,media):
    from pdf_support import pdf_bytes
    from docx_support import docx_bytes,p
    from xlsx_support import xlsx_bytes,cell
    from app.execution.summary_repository import stored
    f=ops_rows
    async def check():
        ctx=await f.context('A-U1','A');docs=setup(f,tmp_path);a=await f.context('A-ADM','A')
        raw=pdf_bytes(['Ordinary original content.']) if media=='application/pdf' else docx_bytes(p('일반 안내 원문이다.')+p('확인 후 보존한다.')) if 'wordprocessingml' in media else xlsx_bytes([('안내',cell('일반 안내 원문이다.'))])
        ids=await publish(f,docs,a,metadata(media_type=media),raw);_,ticket,result=await execute(f,docs,ctx,ids)
        view=await SummaryRepository(docs).read(ctx,ticket.run.run_id);assert result.answer_kind=='answer' and view['evidence']
        for item in view['evidence']:
            assert item['source_media_type']==media
            if media=='application/pdf':assert item['page_start']==1 and item['page_end']==1
            else:assert item['structure_locations'] and all(x['kind']!='sheet' for x in item['structure_locations'])
        async with tenant_transaction(f.pool,ctx) as c:
            row=await (await c.execute('SELECT tenant_id,document_id,version_id,title,media_type,source_object_key,source_sha256,byte_length,character_length,source_mapping FROM rag.document_versions WHERE version_id=%s',(UUID(ids['version_id']),))).fetchone()
            assert docs.storage.read_original(stored(row))==raw
        original=(docs.storage.root/row['source_object_key']).with_name('original');original.write_bytes(b'changed original')
        with pytest.raises(AppError,match='STORAGE_UNAVAILABLE'):await SummaryRepository(docs).read(ctx,ticket.run.run_id)
    f.run(check())

def test_summary_http_contract_export_source_revoke_and_generic_paths(ops_rows,auth_settings):
    import time
    from pydantic import SecretStr
    from fastapi.testclient import TestClient
    from app.main import create_app
    f=ops_rows;docs=DocumentRepository(f.pool,SourceStorage(auth_settings.source_root),auth_settings.login_hmac_secret.get_secret_value())
    ids=f.run(publish(f,docs,f.run(f.context('A-ADM','A')),raw=RAW));settings=auth_settings.model_copy(update={'execution_enabled':True,'meter_dsn':SecretStr(f.db.runtime_dsn('ai_meter'))})
    with TestClient(create_app(settings),base_url='http://127.0.0.1:8000',client=('127.0.0.1',50000)) as client:
        def login(actor):
            rep=client.post('/api/v1/auth/login',headers={'Origin':settings.origin,'X-Requested-With':'ai-portal'},json={'login_id':actor.lower(),'password':f.passwords[actor]});assert rep.status_code==200
            return {'Origin':settings.origin,'X-Requested-With':'ai-portal','X-CSRF-Token':rep.json()['data']['csrf_token'],'X-Tenant-ID':str(f.tenant_ids['A'])}
        headers=login('A-U1');body={'client_send_id':str(uuid4()),'document_ref':{k:ids[k] for k in ('document_id','version_id')},'bullet_count':3}
        for delta in ({'bullet_count':True},{'task_kind':'document_summary'},{'prompt':'invented'},{'model':'arbitrary'}):assert client.post('/api/v1/document-summaries',headers=headers,json=body|delta).status_code==422
        rep=client.post('/api/v1/document-summaries',headers=headers,json=body);assert rep.status_code==201;assert set(rep.json()['data'])=={'run_id','state','revision','replayed'};run=rep.json()['data']['run_id']
        for _ in range(100):
            view=client.get('/api/v1/document-summaries/'+run,headers=headers).json()['data']
            if view['is_terminal']:break
            time.sleep(.02)
        assert view['state']=='completed' and view['content_status']=='final' and len(view['evidence'])==3
        assert view['result']['text'].startswith('1. 첫째')
        retry=client.post('/api/v1/document-summaries',headers=headers,json=body);assert retry.status_code==200 and retry.json()['data']['replayed']
        assert client.post('/api/v1/document-summaries',headers=headers,json=body|{'bullet_count':5}).status_code==409
        export=client.get('/api/v1/document-summaries/'+run+'/export?format=md',headers=headers);assert export.status_code==200 and export.headers['content-disposition']=='attachment; filename="summary.md"' and export.headers['x-content-type-options']=='nosniff'
        assert all(x not in export.text for x in ('source_object_key','tenants/','postgresql://','selected_ids'))
        source=client.get(view['evidence'][0]['source_url'],headers=headers);assert source.status_code==200 and source.content==RAW
        ordinary=client.get('/api/v1/runs/'+run,headers=headers).json()['data'];assert ordinary['result'] is None and ordinary['content_status']=='unavailable'
        assert client.get('/api/v1/runs/'+run+'/evidence',headers=headers).status_code==404
        msg=client.get('/api/v1/conversations/'+view['conversation_id']+'/messages',headers=headers);assert msg.status_code==200 and '100억원' not in msg.text and '첫째' not in msg.text
        feedback=client.get('/api/v1/runs/'+run+'/feedback',headers=headers);assert feedback.status_code==409
        regen=client.post('/api/v1/document-summaries/'+run+'/regenerate',headers=headers,json={'client_send_id':str(uuid4()),'expected_revision':view['revision']});assert regen.status_code==201 and regen.json()['data']['run_id']!=run
        with f.db.admin_connection() as c:c.execute('UPDATE security.document_publications SET active=false WHERE document_id=%s',(UUID(ids['document_id']),))
        assert client.get('/api/v1/document-summaries/'+run,headers=headers).status_code==404
        assert client.get('/api/v1/document-summaries/'+run+'/export?format=md',headers=headers).status_code==404
        assert client.get(view['evidence'][0]['source_url'],headers=headers).status_code==404
        assert client.post('/api/v1/document-summaries/'+run+'/regenerate',headers=headers,json={'client_send_id':str(uuid4()),'expected_revision':view['revision']}).status_code==404

def test_current_deletion_config_and_atomic_save_guard(ops_rows,tmp_path):
    f=ops_rows
    async def check():
        ctx=await f.context('A-U1','A');docs=setup(f,tmp_path);ids=await publish(f,docs,await f.context('A-ADM','A'),raw=RAW)
        data=await admit(f,docs,ctx,ids)
        async with open_meter_pool(f.db.runtime_dsn('ai_meter')) as meter:
            repo=CallRepository(f.pool,meter,PERIOD);ticket=await repo.claim(ctx,UUID(data['run_id']),'mock');engine=SummaryExecutor(repo,docs,SummaryMockProvider());result=await engine.execute(ticket)
            with f.db.admin_connection() as c:
                c.execute("CREATE FUNCTION portal.dp07_save_fail() RETURNS trigger LANGUAGE plpgsql AS $$BEGIN RAISE EXCEPTION 'fixed fault';END;$$; CREATE TRIGGER dp07_save_fail BEFORE UPDATE ON portal.summary_requests FOR EACH ROW EXECUTE FUNCTION portal.dp07_save_fail()")
            with pytest.raises(ExecutionError):await engine.finish(ticket,result)
            with f.db.admin_connection() as c:
                assert c.execute('SELECT count(*) FROM portal.summary_evidence').fetchone()[0]==0
                assert c.execute('SELECT result FROM portal.summary_requests').fetchone()==(None,)
                c.execute('DROP TRIGGER dp07_save_fail ON portal.summary_requests')
            assert await engine.finish(ticket,result)
        await ConversationRepository(f.pool).mutate(ctx,UUID(data['conversation_id']),{},0,True,uuid4())
        with pytest.raises(AppError) as error:await SummaryRepository(docs).read(ctx,ticket.run.run_id)
        assert error.value.status==404
        with pytest.raises(AppError):await SummaryRepository(docs).request(ctx,ticket.run.run_id)
    f.run(check())

@pytest.mark.parametrize('case',['running_cancel','result_policy','config_changed','epoch_changed'])
def test_mid_run_cancellation_policy_and_fencing_keep_cost(ops_rows,tmp_path,case,monkeypatch):
    f=ops_rows
    class Provider(SummaryMockProvider):
        def __init__(self):self.started=asyncio.Event();self.calls=0
        async def generate(self,*args):
            self.calls+=1;self.started.set()
            if case=='running_cancel':await asyncio.Event().wait()
            return await super().generate(*args)
    async def check():
        ctx=await f.context('A-U1','A');docs=setup(f,tmp_path);ids=await publish(f,docs,await f.context('A-ADM','A'),raw=RAW);data=await admit(f,docs,ctx,ids);provider=Provider()
        async with open_meter_pool(f.db.runtime_dsn('ai_meter')) as meter:
            repo=CallRepository(f.pool,meter,PERIOD);ticket=await repo.claim(ctx,UUID(data['run_id']),'mock');engine=SummaryExecutor(repo,docs,provider)
            if case=='running_cancel':
                work=asyncio.create_task(engine.execute(ticket));await provider.started.wait()
                view=await SummaryRepository(docs).read(ctx,ticket.run.run_id)
                await ConversationRepository(f.pool).cancel(ctx,ticket.run.run_id,view['revision'],uuid4());work.cancel()
                with pytest.raises(ExecutionError):await work
                await repo.fail(ticket,'EXECUTION_INTERRUPTED')
            elif case=='result_policy':
                def fail(title,body):
                    if body.startswith('1. '):raise AppError('DOCUMENT_POLICY_BLOCKED',422)
                monkeypatch.setattr('app.execution.document_summary.require_summary_policy',fail)
                with pytest.raises(ExecutionError,match='DOCUMENT_POLICY_BLOCKED'):await engine.execute(ticket)
                await repo.fail(ticket,'DOCUMENT_POLICY_BLOCKED')
            else:
                result=await engine.execute(ticket)
                with f.db.admin_connection() as c:
                    if case=='config_changed':c.execute("UPDATE portal.agent_configs SET config_version=config_version+1 WHERE tenant_id=%s AND agent_key='rules_rag'",(ctx.tenant_id,))
                    else:c.execute('UPDATE portal.runs SET execution_epoch=execution_epoch+1 WHERE run_id=%s',(ticket.run.run_id,))
                with pytest.raises(ExecutionError):await engine.finish(ticket,result)
            assert provider.calls==1
        with f.db.admin_connection() as c:
            assert c.execute('SELECT count(*) FROM portal.summary_evidence').fetchone()[0]==0
            state,slot=c.execute('SELECT state,slot_held FROM ops.call_attempts WHERE run_id=%s',(ticket.run.run_id,)).fetchone()
            assert state==('usage_unknown' if case=='running_cancel' else 'settled')
            if case=='running_cancel':
                assert slot and c.execute('SELECT state FROM portal.runs WHERE run_id=%s',(ticket.run.run_id,)).fetchone()[0]=='cancelled'
                assert c.execute("SELECT sum(delta_reserved_krw),sum(delta_accounted_krw) FROM ops.usage_events u JOIN ops.call_attempts c USING(tenant_id,call_id) WHERE c.run_id=%s",(ticket.run.run_id,)).fetchone()==(__import__('decimal').Decimal('3.64'),__import__('decimal').Decimal('0'))
    f.run(check())


def test_existing_title_metadata_capability_is_owner_tenant_user_owned_only(ops_rows,tmp_path):
    f=ops_rows
    async def check():
        docs=setup(f,tmp_path);ctx=await f.context('A-U1','A');a=await f.context('A-ADM','A')
        personal=await docs.register(ctx,{'client_upload_id':uuid4(),'title':'자기 개인문서 메타데이터','media_type':'text/plain'},RAW,personal=True)
        await docs.register(a,metadata(title='관리 조직문서 메타데이터'),RAW)
        rows=(await docs.personal_listing(ctx,'documents',None,20))['items'];assert len(rows)==1 and rows[0]['title']=='자기 개인문서 메타데이터' and rows[0]['publication_state']=='unpublished'
        for actor,tenant in [('A-U2','A'),('A-ADM','A'),('B-U1','B')]:assert (await docs.personal_listing(await f.context(actor,tenant),'documents',None,20))['items']==[]
        async with tenant_transaction(f.pool,ctx) as c:
            assert await (await c.execute('SELECT title FROM rag.document_versions WHERE version_id=%s',(UUID(personal['version_id']),))).fetchall()==[]
    f.run(check())

def test_summary_recovery_preserves_unknown_debt_and_never_redispatches(ops_rows,tmp_path):
    f=ops_rows
    class Provider(SummaryMockProvider):
        calls=0
        async def generate(self,*args):self.calls+=1;raise TimeoutError()
    async def check():
        ctx=await f.context('A-U1','A');docs=setup(f,tmp_path);ids=await publish(f,docs,await f.context('A-ADM','A'),raw=RAW);data=await admit(f,docs,ctx,ids)
        async with open_meter_pool(f.db.runtime_dsn('ai_meter')) as meter:
            repo=CallRepository(f.pool,meter,PERIOD);ticket=await repo.claim(ctx,UUID(data['run_id']),'mock');provider=Provider();engine=SummaryExecutor(repo,docs,provider)
            with pytest.raises(ExecutionError):await engine.execute(ticket)
            async with f.pool.connection() as leader:
                assert (await (await leader.execute('SELECT pg_try_advisory_lock(202610,4) AS ok')).fetchone())['ok']
                try:
                    async with leader.transaction():await leader.execute('SELECT security.execution_recover(%s)',('mock',))
                finally:await leader.execute('SELECT pg_advisory_unlock(202610,4)')
            view=await SummaryRepository(docs).read(ctx,ticket.run.run_id);assert view['state']=='interrupted' and view['result'] is None and view['evidence']==[]
            with pytest.raises(ExecutionError):await engine.execute(ticket)
            assert provider.calls==1
        with f.db.admin_connection() as c:
            assert c.execute('SELECT state,execution_epoch FROM portal.runs WHERE run_id=%s',(ticket.run.run_id,)).fetchone()==('interrupted',2)
            assert c.execute('SELECT state,slot_held,reserved_krw FROM ops.call_attempts WHERE run_id=%s',(ticket.run.run_id,)).fetchone()==('usage_unknown',True,__import__('decimal').Decimal('3.64'))
    f.run(check())

def test_concurrent_summary_send_has_one_run_and_one_generation(ops_rows,tmp_path):
    from app.db import open_web_pool
    f=ops_rows
    async def check():
        docs=setup(f,tmp_path);ctx=await f.context('A-U1','A');ids=await publish(f,docs,await f.context('A-ADM','A'),raw=RAW);send=uuid4()
        async def submit():
            async with open_web_pool(f.db.runtime_dsn()) as pool:
                scoped=DocumentRepository(pool,docs.storage,'x'*40)
                return await admit(f,scoped,ctx,ids,send)
        left,right=await asyncio.gather(submit(),submit())
        assert left['run_id']==right['run_id'] and sum(x['replayed'] for x in (left,right))==1
        async with open_meter_pool(f.db.runtime_dsn('ai_meter')) as meter:
            repo=CallRepository(f.pool,meter,PERIOD);ticket=await repo.claim(ctx,UUID(left['run_id']),'mock');engine=SummaryExecutor(repo,docs,SummaryMockProvider());result=await engine.execute(ticket);assert await engine.finish(ticket,result)
        with f.db.admin_connection() as c:
            assert c.execute('SELECT count(*) FROM portal.summary_requests').fetchone()[0]==1
            assert c.execute('SELECT count(*) FROM ops.call_attempts WHERE run_id=%s',(UUID(left['run_id']),)).fetchone()[0]==1
    f.run(check())

@pytest.mark.parametrize('mutation',['quote','location','source_sha256'])
def test_summary_sql_seal_rejects_forged_exact_source_proof(ops_rows,tmp_path,mutation):
    from common_core.ai_pipeline.summary.render import render_extracts
    f=ops_rows
    async def check():
        ctx=await f.context('A-U1','A');docs=setup(f,tmp_path);ids=await publish(f,docs,await f.context('A-ADM','A'),raw=RAW);data=await admit(f,docs,ctx,ids)
        async with open_meter_pool(f.db.runtime_dsn('ai_meter')) as meter:
            repo=CallRepository(f.pool,meter,PERIOD);ticket=await repo.claim(ctx,UUID(data['run_id']),'mock');engine=SummaryExecutor(repo,docs,SummaryMockProvider());result=await engine.execute(ticket)
            proofs=[dict(x) for x in result.evidence]
            if mutation=='quote':proofs[0]['quote']='존재하지 않는 원문 999억원이다.'
            elif mutation=='location':proofs[0]['location']=proofs[0]['location']|{'start_offset':proofs[0]['location']['start_offset']+1}
            else:proofs[0]['source_sha256']='ff'*32
            forged=replace(result,evidence=tuple(proofs),body=render_extracts(tuple(x['quote'] for x in proofs)))
            with pytest.raises(ExecutionError,match='SUMMARY_OUTPUT_INVALID'):await engine.finish(ticket,forged)
            await repo.fail(ticket,'SUMMARY_OUTPUT_INVALID')
        with f.db.admin_connection() as c:
            assert c.execute('SELECT count(*) FROM portal.summary_evidence').fetchone()[0]==0
            assert c.execute('SELECT result FROM portal.summary_requests WHERE run_id=%s',(ticket.run.run_id,)).fetchone()==(None,)
            assert c.execute('SELECT state FROM ops.call_attempts WHERE run_id=%s',(ticket.run.run_id,)).fetchone()==('settled',)
    f.run(check())


@pytest.mark.parametrize('case',['limit','not_ready'])
def test_summary_new_error_http_contract(ops_rows,auth_settings,monkeypatch,case):
    from fastapi.testclient import TestClient
    from app.main import create_app
    f=ops_rows;settings=auth_settings.model_copy(update={'execution_enabled':False})
    docs=DocumentRepository(f.pool,SourceStorage(settings.source_root),settings.login_hmac_secret.get_secret_value())
    ids=f.run(publish(f,docs,f.run(f.context('A-ADM','A')),raw=RAW))
    with TestClient(create_app(settings),base_url='http://127.0.0.1:8000',client=('127.0.0.1',50000)) as client:
        login=client.post('/api/v1/auth/login',headers={'Origin':settings.origin,'X-Requested-With':'ai-portal'},json={'login_id':'a-u1','password':f.passwords['A-U1']});assert login.status_code==200
        headers={'Origin':settings.origin,'X-Requested-With':'ai-portal','X-CSRF-Token':login.json()['data']['csrf_token'],'X-Tenant-ID':str(f.tenant_ids['A'])}
        if case=='limit':monkeypatch.setattr('app.execution.summary_repository.general_token_count',lambda *_:6001)
        reply=client.post('/api/v1/document-summaries',headers=headers,json={'client_send_id':str(uuid4()),'document_ref':{k:ids[k] for k in ('document_id','version_id')},'bullet_count':3})
        if case=='not_ready':
            assert reply.status_code==201
            reply=client.get('/api/v1/document-summaries/'+reply.json()['data']['run_id']+'/export?format=md',headers=headers)
        assert reply.status_code==({'limit':422,'not_ready':409}[case])
        error=reply.json()['error'];assert error['code']==({'limit':'SUMMARY_LIMIT_EXCEEDED','not_ready':'SUMMARY_NOT_READY'}[case])
        assert error['message'] and error['retryable'] is False
        assert reply.headers['cache-control']=='no-store' and '첫째' not in reply.text


def test_summary_unfired_cleanup_failure_latches_manager_and_blocks_new_admission(ops_rows,auth_settings,monkeypatch):
    from decimal import Decimal
    from fastapi.testclient import TestClient
    from app.main import create_app
    from app.ai.rag_gateway import RagCallRepository
    from app.ai.providers import MockProvider
    from app.execution.manager import ExecutionManager
    from app.execution.stream import StreamHub
    f=ops_rows;settings=auth_settings.model_copy(update={'execution_enabled':False})
    docs=DocumentRepository(f.pool,SourceStorage(settings.source_root),settings.login_hmac_secret.get_secret_value())
    snapshots=[];failures=[];dispatches=[];releases=[]
    class Provider(SummaryMockProvider):
        calls=0
        async def generate(self,*args):self.calls+=1;return await super().generate(*args)
    class Repository(CallRepository):
        async def fail(self,ticket,code):
            saved=await super().fail(ticket,code);failures.append((code,saved));return saved
    def debt(run_id):
        with f.db.admin_connection() as c:
            return (
                c.execute('SELECT state,slot_held,reserved_krw,dispatched_at FROM ops.call_attempts WHERE run_id=%s',(run_id,)).fetchall(),
                c.execute("SELECT reserved_krw,accounted_krw,active_slot FROM ops.project_budget WHERE mode='mock'").fetchall(),
                c.execute("SELECT t.reserved_krw,t.accounted_krw,t.active_slot FROM ops.tenant_budgets t JOIN ops.project_budget p USING(budget_id) WHERE p.mode='mock' ORDER BY t.tenant_id").fetchall(),
                c.execute('SELECT event_kind,delta_reserved_krw,delta_accounted_krw FROM ops.usage_events u JOIN ops.call_attempts c USING(tenant_id,call_id) WHERE c.run_id=%s ORDER BY u.created_at',(run_id,)).fetchall(),
            )
    async def reject_dispatch(repo,ticket,call_id):
        dispatches.append(call_id);snapshots.append(debt(ticket.run.run_id));raise ExecutionError('PERMIT_EXPIRED')
    async def failed_release(repo,ticket,call_id):
        releases.append(call_id);raise ExecutionError('LEDGER_UNAVAILABLE')
    monkeypatch.setattr(RagCallRepository,'dispatch',reject_dispatch)
    monkeypatch.setattr(RagCallRepository,'release_unfired',failed_release)
    async def check():
        ctx=await f.context('A-U1','A');ids=await publish(f,docs,await f.context('A-ADM','A'),raw=RAW)
        other_ids=await publish(f,docs,await f.context('B-ADM','B'),raw=RAW)
        data=await admit(f,docs,ctx,ids);run_id=UUID(data['run_id']);provider=Provider()
        async with open_meter_pool(f.db.runtime_dsn('ai_meter')) as meter:
            repo=Repository(f.pool,meter,PERIOD);engine=SummaryExecutor(repo,docs,provider)
            manager=ExecutionManager(repo,MockProvider(),'mock',StreamHub(),summary=engine)
            await manager._run(ctx,run_id)
            assert failures==[('LEDGER_UNAVAILABLE',True)]
            assert provider.calls==0 and len(dispatches)==1 and releases==dispatches
            assert engine.stop_latch and manager.gateway.stop_latch
            assert snapshots[0]==debt(run_id)
            assert snapshots[0][0]==[('reserved',True,Decimal('3.64'),None)]
            assert snapshots[0][1][0][0]==Decimal('3.64') and snapshots[0][1][0][2]==1
            assert any(reserved==0 and slot==0 for reserved,accounted,slot in snapshots[0][2])  # Another tenant has capacity.
            assert snapshots[0][3]==[('reserve',Decimal('3.64'),Decimal('0'))]
            view=await SummaryRepository(docs).read(ctx,run_id)
            assert view['state']=='failed' and view['error_code']=='LEDGER_UNAVAILABLE' and view['result'] is None and view['evidence']==[]
            manager.notify(ctx,uuid4());assert manager.tasks=={}
            await engine.provider.close();await manager.gateway.provider.close()
        return manager,other_ids,run_id
    manager,other_ids,run_id=f.run(check())
    with TestClient(create_app(settings),base_url='http://127.0.0.1:8000',client=('127.0.0.1',50000)) as client:
        client.app.state.execution=manager
        login=client.post('/api/v1/auth/login',headers={'Origin':settings.origin,'X-Requested-With':'ai-portal'},json={'login_id':'b-u1','password':f.passwords['B-U1']});assert login.status_code==200
        headers={'Origin':settings.origin,'X-Requested-With':'ai-portal','X-CSRF-Token':login.json()['data']['csrf_token'],'X-Tenant-ID':str(f.tenant_ids['B'])}
        reply=client.post('/api/v1/document-summaries',headers=headers,json={'client_send_id':str(uuid4()),'document_ref':{k:other_ids[k] for k in ('document_id','version_id')},'bullet_count':3})
        assert reply.status_code==503 and reply.json()['error']['code']=='PROJECT_STOPPED'
    assert snapshots[0]==debt(run_id)
    with f.db.admin_connection() as c:
        assert c.execute('SELECT count(*) FROM portal.summary_requests').fetchone()[0]==1
        assert c.execute('SELECT count(*) FROM portal.summary_evidence').fetchone()[0]==0


@pytest.mark.parametrize('phase',['execute','finish'])
def test_summary_auth_required_maps_to_safe_terminal_code(monkeypatch,phase):
    from types import SimpleNamespace
    async def denied(*args):raise AppError('AUTH_REQUIRED',401)
    engine=SummaryExecutor(None,SimpleNamespace(pool=None),SummaryMockProvider())
    monkeypatch.setattr(engine.summary,'request',denied)
    ticket=SimpleNamespace(ctx=None,run=SimpleNamespace(run_id=uuid4()))
    async def check():
        with pytest.raises(ExecutionError,match='^EXECUTION_BLOCKED$'):
            if phase=='execute':await engine.execute(ticket)
            else:await engine.finish(ticket,None)
        assert not engine.stop_latch
    asyncio.run(check())


@pytest.mark.parametrize('loss,phase',
    [(loss,phase) for loss in ('revoked','membership','source') for phase in ('after_claim','during_provider')]
    +[(loss,phase) for loss in ('revoked','membership') for phase in ('after_request_execute','after_request_finish')]
    +[(loss,phase) for loss in ('revoked','membership') for phase in ('before_claim','before_claim_rpc','before_reserve','before_dispatch','before_finish_rpc','heartbeat')])
def test_summary_manager_authority_loss_terminalizes_without_ledger_latch(ops_rows,tmp_path,monkeypatch,phase,loss):
    from app.db import open_web_pool
    from dataclasses import asdict
    from decimal import Decimal
    from types import SimpleNamespace
    from app.ai.providers import MockProvider
    from app.execution.manager import ExecutionManager
    from app.execution.stream import StreamHub
    from app.execution.summary_routes import ensure_execution
    f=ops_rows;failures=[]
    class Provider(SummaryMockProvider):
        def __init__(self):
            self.calls=0;self.started=asyncio.Event();self.release=asyncio.Event();self.block=True;self.outcome=None
        async def generate(self,*args):
            self.calls+=1;self.started.set()
            if self.block:await self.release.wait()
            self.outcome=await super().generate(*args);return self.outcome
    async def check():
        ctx=await f.context('A-U1','A');other=await f.context('B-U1','B');docs=setup(f,tmp_path)
        ids=await publish(f,docs,await f.context('A-ADM','A'),raw=RAW)
        other_ids=await publish(f,docs,await f.context('B-ADM','B'),raw=RAW)
        provider=Provider();provider.block=phase in ('during_provider','heartbeat');generated=phase in ('during_provider','after_request_finish','before_finish_rpc','heartbeat')
        heartbeat_gate=asyncio.Event();original_sleep=asyncio.sleep
        if phase=='heartbeat':
            async def sleep(delay,*args):
                if delay==20:await heartbeat_gate.wait()
                else:await original_sleep(delay,*args)
            monkeypatch.setattr('app.execution.manager.asyncio.sleep',sleep)
        def revoke():
            if loss=='source':
                with f.db.admin_connection() as c:
                    c.execute('UPDATE security.document_access SET deleted_at=clock_timestamp() WHERE tenant_id=%s AND document_id=%s',(ctx.tenant_id,UUID(ids['document_id'])))
            else:f.mutate_access(ctx,loss)
        class Repository(CallRepository):
            async def claim(self,actor,run,mode):
                if phase=='before_claim' and run==run_id:revoke()
                ticket=await super().claim(actor,run,mode)
                if phase=='after_claim' and run==run_id:
                    assert ticket is not None;revoke()
                return ticket
            async def fail(self,ticket,code):
                saved=await super().fail(ticket,code);failures.append((code,saved));return saved
            async def reject(self,actor,run,mode,code):
                saved=await super().reject(actor,run,mode,code);failures.append((code,saved));return saved
        original_rpc=CallRepository._rpc;rpc_losses=[]
        async def rpc(repository,pool,name,args,actor=None):
            target={'before_claim_rpc':'summary_claim','before_reserve':'summary_call_reserve','before_dispatch':'call_dispatch','before_finish_rpc':'summary_finish'}.get(phase)
            if name==target and len(args)>2 and args[2]==run_id:
                rpc_losses.append(name);revoke()
            return await original_rpc(repository,pool,name,args,actor)
        monkeypatch.setattr(CallRepository,'_rpc',rpc)
        async with open_web_pool(f.db.runtime_dsn()) as web,open_meter_pool(f.db.runtime_dsn('ai_meter')) as meter:
            repo=Repository(web,meter,PERIOD);engine=SummaryExecutor(repo,docs,provider)
            manager=ExecutionManager(repo,MockProvider(),'mock',StreamHub(),summary=engine)
            original_request=engine.summary.request;request_calls=0
            async def request(actor,run):
                nonlocal request_calls
                data=await original_request(actor,run)
                if run==run_id:
                    request_calls+=1
                    if (phase=='after_request_execute' and request_calls==1) or (phase=='after_request_finish' and request_calls==2):revoke()
                return data
            engine.summary.request=request
            await manager.start()
            try:
                data=await admit(f,docs,ctx,ids);run_id=UUID(data['run_id'])
                manager.notify(ctx,run_id)
                if phase in ('during_provider','heartbeat'):
                    await asyncio.wait_for(provider.started.wait(),5)
                    with f.db.admin_connection() as c:
                        assert c.execute('SELECT state FROM portal.runs WHERE run_id=%s',(run_id,)).fetchone()==('running',)
                    revoke()
                    if phase=='heartbeat':heartbeat_gate.set()
                    else:provider.release.set()
                await asyncio.wait_for(asyncio.gather(*list(manager.tasks.values())),10);await asyncio.sleep(0)
                expected_code='EXECUTION_INTERRUPTED' if phase=='heartbeat' else 'EXECUTION_BLOCKED'
                assert failures==[(expected_code,True)]
                if phase in ('before_claim_rpc','before_reserve','before_dispatch','before_finish_rpc'):assert len(rpc_losses)==1
                assert provider.calls==int(generated)
                if phase.startswith('after_request_'):assert request_calls==(2 if generated else 1)
                assert not engine.stop_latch and not manager.gateway.stop_latch and not manager.tasks and not manager.hub.drafts
                with f.db.admin_connection() as c:
                    assert c.execute('SELECT state,stage,safe_error_code,ended_at IS NOT NULL FROM portal.runs WHERE run_id=%s',(run_id,)).fetchone()==('blocked' if phase in ('before_claim','before_claim_rpc') else 'failed','terminal',expected_code,True)
                    assert c.execute('SELECT result FROM portal.summary_requests WHERE run_id=%s',(run_id,)).fetchone()==(None,)
                    assert c.execute('SELECT count(*) FROM portal.summary_evidence WHERE run_id=%s',(run_id,)).fetchone()[0]==0
                    assert c.execute("SELECT count(*) FROM portal.messages WHERE run_id=%s AND role='assistant'",(run_id,)).fetchone()[0]==0
                    attempts=c.execute('SELECT operation,state,provider_end_status,slot_held,usage_snapshot FROM ops.call_attempts WHERE run_id=%s',(run_id,)).fetchall()
                    if phase=='heartbeat':
                        assert attempts==[('generate_rag','usage_unknown','unknown',True,None)]
                        assert c.execute('SELECT event_kind FROM ops.usage_events u JOIN ops.call_attempts a USING(tenant_id,call_id) WHERE a.run_id=%s ORDER BY u.created_at',(run_id,)).fetchall()==[('reserve',),('mark_unknown',)]
                    elif phase=='before_dispatch':
                        assert attempts==[('generate_rag','released_no_dispatch','not_started',False,None)]
                        assert c.execute('SELECT event_kind FROM ops.usage_events u JOIN ops.call_attempts a USING(tenant_id,call_id) WHERE a.run_id=%s ORDER BY u.created_at',(run_id,)).fetchall()==[('reserve',),('release',)]
                    elif generated:
                        assert attempts==[('generate_rag','settled','observed',False,asdict(provider.outcome.receipt))]
                        assert c.execute('SELECT event_kind FROM ops.usage_events u JOIN ops.call_attempts a USING(tenant_id,call_id) WHERE a.run_id=%s ORDER BY u.created_at',(run_id,)).fetchall()==[('reserve',),('settle',)]
                    else:assert attempts==[]
                    debt=Decimal('3.64') if phase=='heartbeat' else Decimal(0);slot=int(phase=='heartbeat')
                    assert c.execute("SELECT stopped,stop_latch,reserved_krw,active_slot FROM ops.project_budget WHERE mode='mock'").fetchone()==(False,False,debt,slot)
                    assert c.execute("SELECT sum(t.reserved_krw),sum(t.active_slot) FROM ops.tenant_budgets t JOIN ops.project_budget p USING(budget_id) WHERE p.mode='mock'").fetchone()==(debt,slot)
                with pytest.raises(AppError) as denied:await SummaryRepository(docs).read(ctx,run_id)
                assert denied.value.status==(404 if loss=='source' else 403)
                assert ensure_execution(SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(execution=manager)))) is manager
                provider.block=False
                other_data=await admit(f,docs,other,other_ids);other_run=UUID(other_data['run_id'])
                manager.notify(other,other_run)
                await asyncio.wait_for(asyncio.gather(*list(manager.tasks.values())),10);await asyncio.sleep(0)
                view=await SummaryRepository(docs).read(other,other_run)
                assert view['state']=='completed' and view['result'] is not None and len(view['evidence'])==3
                assert provider.calls==int(generated)+1
                assert not engine.stop_latch and not manager.gateway.stop_latch and not manager.tasks
            finally:
                provider.release.set();await manager.close()
    f.run(check())


@pytest.mark.parametrize('phase',['execute','finish'])
@pytest.mark.parametrize('context_loss',[True,False])
def test_summary_context_value_error_is_narrowly_normalized(monkeypatch,phase,context_loss):
    from types import SimpleNamespace
    message='CONTEXT_UNAVAILABLE' if context_loss else 'unexpected-save-error'
    async def denied(*args):raise ValueError(message)
    engine=SummaryExecutor(None,SimpleNamespace(pool=None),SummaryMockProvider())
    monkeypatch.setattr(engine.summary,'request',denied)
    ticket=SimpleNamespace(ctx=None,run=SimpleNamespace(run_id=uuid4()))
    async def check():
        expected=ExecutionError if context_loss or phase=='execute' else ValueError
        code='EXECUTION_BLOCKED' if context_loss else 'SUMMARY_OUTPUT_INVALID' if phase=='execute' else message
        with pytest.raises(expected,match='^'+code+'$'):
            if phase=='execute':await engine.execute(ticket)
            else:await engine.finish(ticket,None)
        assert not engine.stop_latch
    asyncio.run(check())


@pytest.mark.parametrize('operation',['rpc','claim','dispatch'])
@pytest.mark.parametrize('failure',['context','value','sql'])
def test_shared_repository_context_denial_preserves_fault_classification(monkeypatch,operation,failure):
    from contextlib import asynccontextmanager
    from types import SimpleNamespace
    from app.ai.repository import DispatchUncertain
    @asynccontextmanager
    async def denied(*args):
        if failure=='sql':raise psycopg.OperationalError('synthetic-sql-unavailable')
        raise ValueError('CONTEXT_UNAVAILABLE' if failure=='context' else 'unexpected-ledger-error')
        yield
    monkeypatch.setattr('app.ai.repository.tenant_transaction',denied)
    ctx=SimpleNamespace(session_id=uuid4(),tenant_id=uuid4())
    repo=CallRepository(None,None,PERIOD)
    ticket=SimpleNamespace(ctx=ctx,worker='synthetic-worker',run=SimpleNamespace(origin_session_id=ctx.session_id,tenant_id=ctx.tenant_id,run_id=uuid4(),epoch=1))
    async def check():
        expected=ExecutionError if failure=='context' or operation=='rpc' else (DispatchUncertain if operation=='dispatch' else (psycopg.OperationalError if failure=='sql' else ValueError))
        with pytest.raises(expected) as error:
            if operation=='rpc':await repo._rpc(None,'summary_call_reserve',(),ctx)
            elif operation=='claim':await repo.claim(ctx,ticket.run.run_id,'mock')
            else:await repo.dispatch(ticket,uuid4())
        if failure=='context':assert type(error.value) is ExecutionError and error.value.code=='EXECUTION_BLOCKED'
        elif operation in ('rpc','dispatch'):assert error.value.code=='LEDGER_UNAVAILABLE'
    asyncio.run(check())


@pytest.mark.parametrize('code',['EXECUTION_BLOCKED','LEDGER_UNAVAILABLE','USAGE_INVALID'])
def test_heartbeat_only_authority_denial_avoids_stop_latch(monkeypatch,code):
    from types import SimpleNamespace
    from app.ai.providers import MockProvider
    from app.execution.manager import ExecutionManager
    from app.execution.stream import StreamHub
    async def denied(*args):raise ExecutionError(code)
    async def no_wait(*args):pass
    monkeypatch.setattr('app.execution.manager.asyncio.sleep',no_wait)
    async def check():
        repo=SimpleNamespace(heartbeat=denied);manager=ExecutionManager(repo,MockProvider(),'mock',StreamHub())
        work=asyncio.get_running_loop().create_future()
        await manager._heartbeat(None,work)
        assert work.cancelled() and manager.gateway.stop_latch==(code!='EXECUTION_BLOCKED')
    asyncio.run(check())
