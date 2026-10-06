from uuid import UUID,uuid4
from datetime import date
import json
import pytest
from app.documents.repository import DocumentRepository
from app.documents.storage import SourceStorage
from app.documents.embedding import MockEmbeddingProvider
from app.documents.sharing import SharingRepository
from app.conversations.repository import ConversationRepository
from app.ai.repository import CallRepository,ExecutionError
from app.ai.rag_provider import RagMockProvider
from app.execution.rag import RagExecutor
from app.db import open_meter_pool,tenant_transaction
from app.errors import AppError
from test_operations import ops_rows
from test_document_sharing import publish

async def execute(f,documents,ctx,prompt='여신심사 담당 부서는?',refs=None,provider=None):
    intake=await ConversationRepository(f.pool).admit(ctx,'rules_rag',None,uuid4(),prompt,date(2026,10,1),'mock',b'x'*32,uuid4(),refs=refs,documents=documents)
    async with open_meter_pool(f.db.runtime_dsn('ai_meter')) as meter:
        repo=CallRepository(f.pool,meter,date(2026,10,1));ticket=await repo.claim(ctx,UUID(intake['run_id']),'mock');assert ticket.agent=='rules_rag'
        engine=RagExecutor(repo,documents,MockEmbeddingProvider(),provider or RagMockProvider())
        result=await engine.execute(ticket);assert await engine.finish(ticket,result)
    return intake,result,ticket

def test_rag_answer_is_sealed_before_read_and_current_revoke_hides_raw_body(ops_rows,tmp_path):
    f=ops_rows
    async def check():
        a=await f.context('A-ADM','A');b=await f.context('B-U1','B');documents=DocumentRepository(f.pool,SourceStorage(tmp_path/'sources'),'x'*40)
        ids=await publish(f,documents,a);share=SharingRepository(documents)
        grant=await share.control(a,UUID(ids['document_id']),UUID(ids['version_id']),'issue',f.tenant_ids['B'],expected=1,request=uuid4())
        admitted,result,ticket=await execute(f,documents,b);assert result.answer_kind=='answer' and '팀' in result.body and '[1]' in result.body
        async with tenant_transaction(f.pool,b) as c:
            assert (await (await c.execute("SELECT body FROM portal.messages WHERE run_id=%s AND role='assistant'",(ticket.run.run_id,))).fetchone())['body']==result.body
        await share.control(a,action='revoke',grant=UUID(grant['grant_id']),expected=1,request=uuid4())
        async with tenant_transaction(f.pool,b) as c:
            assert await (await c.execute("SELECT body FROM portal.messages WHERE run_id=%s AND role='assistant'",(ticket.run.run_id,))).fetchone() is None
            view=(await (await c.execute("SELECT security.run_read(%s,%s,'run',%s,NULL,20) AS data",(b.session_id,b.tenant_id,ticket.run.run_id))).fetchone())['data'];assert view['state']=='completed' and view['content_status']=='unavailable' and view['result'] is None
        with f.db.admin_connection() as c:
            assert c.execute('SELECT provenance_sealed,source_count FROM portal.runs WHERE run_id=%s',(ticket.run.run_id,)).fetchone()==(True,1)
            assert c.execute("SELECT count(*) FROM ops.call_attempts WHERE run_id=%s AND operation IN ('embed_query','generate_rag') AND state='settled'",(ticket.run.run_id,)).fetchone()[0]==2
    f.run(check())

@pytest.mark.parametrize('case',['no_source','unsupported','foreign_ref','bad_fact','free_text'])
def test_rag_hold_deny_and_typed_failure(ops_rows,tmp_path,case):
    f=ops_rows
    class Bad(RagMockProvider):
        async def generate(self,claim,messages,on_delta):
            from dataclasses import replace
            out=await super().generate(claim,messages,on_delta)
            return replace(out,body='검증되지 않은 자유 문장' if case=='free_text' else json.dumps({'answer_kind':'answer','selected_fact_ids':['invented']}))
    async def check():
        ctx=await f.context('A-U1','A');a=await f.context('A-ADM','A');documents=DocumentRepository(f.pool,SourceStorage(tmp_path/'sources'),'x'*40)
        ids=None if case=='no_source' else await publish(f,documents,a)
        if case=='foreign_ref':
            with pytest.raises(AppError) as error:await execute(f,documents,await f.context('B-U1','B'),refs=[{'document_id':UUID(ids['document_id']),'version_id':UUID(ids['version_id'])}])
            assert error.value.status==404
        elif case in ('bad_fact','free_text'):
            with pytest.raises(ExecutionError,match='ANSWER_EVIDENCE_INVALID'):await execute(f,documents,ctx,provider=Bad())
        else:
            admitted,result,ticket=await execute(f,documents,ctx,prompt='여신심사 금액 상한은?' if case=='unsupported' else '여신심사 담당 부서는?');assert result.answer_kind=='insufficient_evidence'
        with f.db.admin_connection() as c:
            if case=='foreign_ref':assert c.execute('SELECT count(*) FROM portal.runs').fetchone()[0]==0
            if case in ('bad_fact','free_text'):assert c.execute("SELECT count(*) FROM portal.messages WHERE role='assistant'").fetchone()[0]==0
            if case in ('unsupported','no_source'):assert c.execute("SELECT count(*) FROM ops.call_attempts WHERE operation='generate_rag'").fetchone()[0]==0
    f.run(check())

@pytest.mark.parametrize('case',['late_agent','late_share','bad_quote','bad_relation','unknown_query','search_failure','missing_usage'])
def test_rag_failure_boundaries_preserve_calls_and_do_not_publish(ops_rows,tmp_path,case):
    from dataclasses import replace
    f=ops_rows
    class Query(MockEmbeddingProvider):
        def __init__(self):self.calls=0
        async def embed(self,claim,texts,tokens):
            self.calls+=1
            if case=='unknown_query':raise TimeoutError()
            return await super().embed(claim,texts,tokens)
    class Provider(RagMockProvider):
        def __init__(self):self.calls=0
        async def generate(self,claim,messages,on_delta):
            self.calls+=1;out=await super().generate(claim,messages,on_delta)
            with f.db.admin_connection() as c:
                if case=='late_agent':c.execute("UPDATE portal.agent_configs SET enabled=false WHERE tenant_id=%s AND agent_key='rules_rag'",(f.tenant_ids['B'],))
                if case=='late_share':c.execute('UPDATE security.share_grants SET active=false,revoked_at=clock_timestamp()')
            return replace(out,receipt=None) if case=='missing_usage' else out
    async def check():
        a=await f.context('A-ADM','A');ctx=await f.context('B-U1','B');documents=DocumentRepository(f.pool,SourceStorage(tmp_path/'sources'),'x'*40)
        ids=await publish(f,documents,a);await SharingRepository(documents).control(a,UUID(ids['document_id']),UUID(ids['version_id']),'issue',f.tenant_ids['B'],expected=1,request=uuid4())
        intake=await ConversationRepository(f.pool).admit(ctx,'rules_rag',None,uuid4(),'여신심사 담당 부서는?',date(2026,10,1),'mock',b'x'*32,uuid4(),documents=documents)
        async with open_meter_pool(f.db.runtime_dsn('ai_meter')) as meter:
            repo=CallRepository(f.pool,meter,date(2026,10,1));ticket=await repo.claim(ctx,UUID(intake['run_id']),'mock');query=Query();provider=Provider();engine=RagExecutor(repo,documents,query,provider)
            if case=='search_failure':
                async def fail(*args):raise RuntimeError('fixed fault')
                engine.search.packets=fail
            if case in ('unknown_query','search_failure'):
                with pytest.raises(ExecutionError,match='SEARCH_FAILED'):await engine.execute(ticket)
                if case=='unknown_query':
                    with pytest.raises(ExecutionError):await engine.execute(ticket)
                assert query.calls==1 and provider.calls==0
                await repo.fail(ticket,'SEARCH_FAILED')
            else:
                result=await engine.execute(ticket)
                if case in ('bad_quote','bad_relation'):
                    proof=dict(result.evidence[0]);proof['quote' if case=='bad_quote' else 'relation_id']='not-the-original' if case=='bad_quote' else str(uuid4());result=replace(result,evidence=(proof,))
                if case=='missing_usage':assert await engine.finish(ticket,result)
                else:
                    with pytest.raises(ExecutionError):await engine.finish(ticket,result)
                    await repo.fail(ticket,'ANSWER_EVIDENCE_INVALID' if case in ('bad_quote','bad_relation') else 'EXECUTION_BLOCKED')
                assert query.calls==1 and provider.calls==1
        with f.db.admin_connection() as c:
            if case=='missing_usage':
                assert c.execute('SELECT state,provenance_sealed FROM portal.runs WHERE run_id=%s',(ticket.run.run_id,)).fetchone()==('completed',True)
                assert c.execute("SELECT state,provider_end_status,slot_held FROM ops.call_attempts WHERE run_id=%s AND operation='generate_rag'",(ticket.run.run_id,)).fetchone()==('usage_unknown','observed',False)
            else:
                assert c.execute("SELECT count(*) FROM portal.messages WHERE role='assistant'").fetchone()[0]==0
                assert c.execute('SELECT count(*) FROM portal.answer_evidence').fetchone()[0]==0
                assert c.execute('SELECT state FROM portal.runs WHERE run_id=%s',(ticket.run.run_id,)).fetchone()[0]=='failed'
    f.run(check())


def test_two_source_answer_revoke_one_hides_entire_body(ops_rows,tmp_path):
    f=ops_rows
    async def check():
        a=await f.context('A-ADM','A');b=await f.context('B-U1','B');documents=DocumentRepository(f.pool,SourceStorage(tmp_path/'sources'),'x'*40);sharing=SharingRepository(documents)
        grants=[]
        for raw in ['여신심사의 위험 검토 승인 부서는 위험팀이다.','여신심사의 기록 보관 담당 부서는 기록팀이다.']:
            ids=await publish(f,documents,a,raw=raw.encode())
            grants.append(await sharing.control(a,UUID(ids['document_id']),UUID(ids['version_id']),'issue',f.tenant_ids['B'],expected=1,request=uuid4()))
        _,result,ticket=await execute(f,documents,b,prompt='여신심사의 위험 검토 승인과 기록 보관 담당 부서는?')
        # Ask both supported predicates explicitly; scope remains distinct by source version.
        assert result.answer_kind=='answer'
        assert len({x['document_id'] for x in result.evidence})==2
        with f.db.admin_connection() as c:
            used=c.execute('SELECT document_id FROM portal.answer_evidence WHERE run_id=%s LIMIT 1',(ticket.run.run_id,)).fetchone()[0]
            chosen=c.execute('SELECT grant_id,revision FROM security.share_grants WHERE document_id=%s AND active',(used,)).fetchone()
        await sharing.control(a,action='revoke',grant=chosen[0],expected=chosen[1],request=uuid4())
        async with tenant_transaction(f.pool,b) as c:
            assert await (await c.execute("SELECT body FROM portal.messages WHERE run_id=%s AND role='assistant'",(ticket.run.run_id,))).fetchone() is None
    f.run(check())
