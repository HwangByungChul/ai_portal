"""Real policy/meter integration; synthetic providers never contact a network."""
from datetime import date
from uuid import UUID,uuid4
from decimal import Decimal
import pytest
from app.db import open_index_pool,open_meter_pool
from app.ai.repository import CallRepository
from app.ai.gateway import AiGateway
from app.ai.rag_gateway import QueryGateway,generation
from app.ai.providers import MockProvider
from app.ai.rag_provider import RagMockProvider
from app.documents.embedding import EmbeddingGateway,MockEmbeddingProvider
from app.documents.repository import DocumentRepository
from app.documents.worker import DocumentWorker
from app.documents.storage import SourceStorage
from app.documents.search import SearchRepository
from app.conversations.repository import ConversationRepository
from test_operations import ops_rows
from test_document_ingest import metadata,RAW
from test_document_sharing import publish

PERIOD=date(2026,10,1)

@pytest.mark.parametrize('operation',['generate_general','embed_document','embed_query','generate_rag'])
@pytest.mark.parametrize('control',['project','tenant','disabled','config'])
@pytest.mark.parametrize('boundary',['before_reserve','after_reserve','after_dispatch'])
def test_four_operations_current_control_and_saved_meter(ops_rows,tmp_path,operation,control,boundary):
    f=ops_rows
    async def check():
        admin=await f.context('A-ADM','A');ctx=await f.context('A-U1','A');documents=DocumentRepository(f.pool,SourceStorage(tmp_path/'sources'),'x'*40)
        agent='general' if operation=='generate_general' else 'rules_rag'
        sources=()
        if operation in ('embed_query','generate_rag'):
            await publish(f,documents,admin)
            sources=await SearchRepository(documents).allowed(ctx,None,'mock')
        with f.db.admin_connection() as c:
            previous=c.execute("SELECT accounted_krw FROM ops.project_budget WHERE mode='mock'").fetchone()[0]
        changed=False;provider_calls=[]
        def change():
            nonlocal changed
            assert not changed;changed=True
            with f.db.admin_connection() as c:
                if control=='project':c.execute("UPDATE ops.project_budget SET stopped=true WHERE mode='mock'")
                elif control=='tenant':c.execute("UPDATE ops.tenant_budgets t SET stopped=true FROM ops.project_budget p WHERE p.budget_id=t.budget_id AND p.mode='mock' AND t.tenant_id=%s",(ctx.tenant_id,))
                elif control=='disabled':c.execute('UPDATE portal.agent_configs SET enabled=false WHERE tenant_id=%s AND agent_key=%s',(ctx.tenant_id,agent))
                else:c.execute('UPDATE portal.agent_configs SET config_version=config_version+1 WHERE tenant_id=%s AND agent_key=%s',(ctx.tenant_id,agent))
        class Embedding(MockEmbeddingProvider):
            async def embed(self,call,texts,tokens):
                provider_calls.append(call)
                if boundary=='after_dispatch':change()
                return await super().embed(call,texts,tokens)
        class Provider(MockProvider):
            async def generate(self,claim,messages,on_delta):
                provider_calls.append(claim.call_id)
                if boundary=='after_dispatch':change()
                return await super().generate(claim,messages,on_delta)
        async with open_index_pool(f.db.runtime_dsn('ai_index')) as index,open_meter_pool(f.db.runtime_dsn('ai_meter')) as meter:
            repo=CallRepository(f.pool,meter,PERIOD)
            if operation=='embed_document':
                ids=await documents.register(admin,metadata(),RAW);parent=UUID(ids['job_id'])
                gateway=EmbeddingGateway(index,meter,Embedding(),PERIOD);original=gateway.rpc
                async def rpc(name,args,meter=False):
                    if name=='document_embedding_permit' and boundary=='before_reserve':change()
                    result=await original(name,args,meter)
                    if name=='document_embedding_permit' and boundary=='after_reserve':change()
                    return result
                gateway.rpc=rpc
                try:await DocumentWorker(documents,gateway).run(admin,parent)
                except Exception:pass # State, dispatch count and ledger assertions below are the oracle.
            else:
                intake=await ConversationRepository(f.pool).admit(ctx,agent,None,uuid4(),'여신심사 담당 부서는?',PERIOD,'mock',bytes(32),uuid4(),documents=documents if sources else None)
                parent=UUID(intake['run_id']);ticket=await repo.claim(ctx,parent,'mock');original=repo._rpc
                async def rpc(pool,name,args,context=None):
                    relevant=name in ('call_reserve','rag_call_reserve')
                    if relevant and boundary=='before_reserve':change()
                    result=await original(pool,name,args,context)
                    if relevant and boundary=='after_reserve':change()
                    return result
                # RagCallRepository is an independent instance. Intercept the shared fixed
                # repository RPC at the class boundary, retaining actual PG transactions.
                from unittest.mock import patch
                async def class_rpc(instance,pool,name,args,context=None):return await rpc(pool,name,args,context)
                async def delta(text):pass
                with patch.object(CallRepository,'_rpc',class_rpc):
                    try:
                        if operation=='generate_general':await AiGateway(repo,Provider()).execute(ticket,delta)
                        elif operation=='embed_query':await QueryGateway(repo,Embedding()).execute(ticket,'여신심사 담당 부서는?',sources)
                        else:await generation(repo,Provider(),ticket,sources,[{'role':'user','content':'합성 제어 시험'}])
                    except Exception:pass
            assert changed
            fired=boundary=='after_dispatch' or (operation=='embed_document' and control=='config' and boundary=='before_reserve')
            assert len(provider_calls)==int(fired)
            with f.db.admin_connection() as c:
                key='job_id' if operation=='embed_document' else 'run_id'
                rows=c.execute('SELECT call_id,tenant_id,initiator_user_id,mode,execution_epoch,step_key,state,slot_held FROM ops.call_attempts WHERE '+key+'=%s',(parent,)).fetchall()
                assert len(rows)==int(boundary!='before_reserve' or fired)
                if rows:
                    row=rows[0];assert row[1]==ctx.tenant_id and row[2]==(admin.user_id if operation=='embed_document' else ctx.user_id) and row[3]=='mock'
                    epoch=c.execute('SELECT '+('lease_epoch FROM rag.jobs WHERE job_id' if operation=='embed_document' else 'execution_epoch FROM portal.runs WHERE run_id')+'=%s',(parent,)).fetchone()[0]
                    assert row[4]==epoch
                    assert row[5] and row[6]==('settled' if fired else 'released_no_dispatch') and not row[7]
                    events=c.execute('SELECT event_kind,count(*) FROM ops.usage_events WHERE call_id=%s GROUP BY event_kind',(row[0],)).fetchall()
                    assert dict(events)==({'reserve':1,'settle':1} if fired else {'reserve':1,'release':1})
                    if provider_calls:assert str(provider_calls[0])==str(row[0])
                reserved,accounted,slots=c.execute("SELECT reserved_krw,accounted_krw,active_slot FROM ops.project_budget WHERE mode='mock'").fetchone()
                assert reserved==0 and slots==0
                assert accounted>previous if fired else accounted==previous
                if operation=='embed_document':
                    published=c.execute('SELECT count(*) FROM security.document_publications WHERE document_id=%s AND active',(ids['document_id'],)).fetchone()[0]
                    assert published==int(control=='config' and boundary=='before_reserve')
    f.run(check())

@pytest.mark.parametrize('proof',['forged','old_epoch','foreign','revoked','dispatched'])
def test_embedding_release_is_call_bound_and_never_releases_dispatched(ops_rows,tmp_path,proof):
    f=ops_rows
    async def check():
        admin=await f.context('A-ADM','A');documents=DocumentRepository(f.pool,SourceStorage(tmp_path/'sources'),'x'*40)
        ids=await documents.register(admin,metadata(),RAW)
        async with open_index_pool(f.db.runtime_dsn('ai_index')) as index,open_meter_pool(f.db.runtime_dsn('ai_meter')) as meter:
            gateway=EmbeddingGateway(index,meter,MockEmbeddingProvider(),PERIOD);original=gateway.rpc;observed=[]
            async def rpc(name,args,meter=False):
                result=await original(name,args,meter)
                if name=='document_embedding_permit':
                    tenant,job,epoch,claim=args[:4];call=UUID(result['call_id']);bound=(tenant,job,epoch,claim,call)
                    bad=(f.tenant_ids['B'],job,epoch,claim,call) if proof=='foreign' else (tenant,job,epoch+1,claim,call) if proof=='old_epoch' else (tenant,job,epoch,b'z'*32,call)
                    assert not await original('document_embedding_release',bad)
                    observed.append(call)
                    if proof!='dispatched':
                        if proof=='revoked':f.mutate_access(admin,'revoked')
                        assert await original('document_embedding_release',bound)
                        assert not await original('document_embedding_release',bound)
                if name=='document_embedding_dispatch' and proof=='dispatched':
                    assert not await original('document_embedding_release',(*args[:4],args[4]))
                return result
            gateway.rpc=rpc
            try:await DocumentWorker(documents,gateway).run(admin,UUID(ids['job_id']))
            except Exception:
                assert proof!='dispatched'
            assert len(observed)==1
            with f.db.admin_connection() as c:
                assert c.execute('SELECT state,slot_held FROM ops.call_attempts WHERE call_id=%s',(observed[0],)).fetchone()==('settled' if proof=='dispatched' else 'released_no_dispatch',False)
                assert c.execute("SELECT reserved_krw,active_slot FROM ops.project_budget WHERE mode='mock'").fetchone()==(Decimal(0),0)
                assert c.execute('SELECT count(*) FROM ops.usage_events WHERE call_id=%s AND event_kind=%s',(observed[0],'settle' if proof=='dispatched' else 'release')).fetchone()[0]==1
    f.run(check())


def test_protected_markers_stay_out_of_public_errors_and_usage(client,login,ops_rows,caplog):
    from test_operations import headers
    f=ops_rows;marker='T280-FAKE-KEY-BODY-PROTECTED-62913';csrf=login(client,'A-ADM')['csrf_token']
    response=client.patch('/api/v1/admin/agents/general',headers=headers(f,csrf=csrf),json={'expected_revision':1,'name':'합성 설정','key':marker})
    assert response.status_code==422 and marker not in response.text
    with f.db.admin_connection() as c:
        from psycopg.types.json import Jsonb
        c.execute("UPDATE portal.agent_configs SET settings=%s WHERE tenant_id=%s AND agent_key='general'",(Jsonb({'name':'합성 설정','description':'합성 설명','instructions':marker}),f.tenant_ids['A']))
    login(client,'A-U1')
    for path in ('/agents','/usage/me','/admin/usage','/admin/agents/general'):
        response=client.get('/api/v1'+path,headers=headers(f));assert marker not in response.text
    login(client,'B-ADM')
    response=client.get('/api/v1/admin/agents/general',headers=headers(f,'B'));assert response.status_code==200 and marker not in response.text
    assert marker not in caplog.text


def test_retry_reuses_settled_checkpoint_without_new_call_and_can_publish(ops_rows,tmp_path):
    f=ops_rows
    async def check():
        admin=await f.context('A-ADM','A');documents=DocumentRepository(f.pool,SourceStorage(tmp_path/'sources'),'x'*40);ids=await documents.register(admin,metadata(),RAW);parent=UUID(ids['job_id'])
        class Counting(MockEmbeddingProvider):
            def __init__(self):self.calls=0
            async def embed(self,*args):self.calls+=1;return await super().embed(*args)
        async with open_index_pool(f.db.runtime_dsn('ai_index')) as index,open_meter_pool(f.db.runtime_dsn('ai_meter')) as meter:
            first=Counting();worker=DocumentWorker(documents,EmbeddingGateway(index,meter,first,PERIOD));save=worker._save_batch
            async def fail_after_checkpoint(ticket,*args):
                await save(ticket,*args)
                await documents.job(admin,parent,'fail',ticket['epoch'],ticket['claim'],{'code':'INDEX_INTERRUPTED'})
                raise RuntimeError('synthetic interruption after settled checkpoint')
            worker._save_batch=fail_after_checkpoint
            with pytest.raises(RuntimeError):await worker.run(admin,parent)
            view=await documents.job(admin,parent);assert view['state']=='failed' and first.calls==1
            with f.db.admin_connection() as c:before=c.execute("SELECT accounted_krw,reserved_krw,active_slot FROM ops.project_budget WHERE mode='mock'").fetchone()
            child=uuid4();await documents.rpc(admin,'document_retry',(admin.session_id,admin.tenant_id,parent,uuid4(),view['revision'],b'h'*32,child,'mock'))
            second=Counting();await DocumentWorker(documents,EmbeddingGateway(index,meter,second,PERIOD)).run(admin,child)
            assert (await documents.job(admin,child))['state']=='completed' and (await documents.job(admin,parent))['state']=='failed' and second.calls==0
            with f.db.admin_connection() as c:
                assert c.execute("SELECT accounted_krw,reserved_krw,active_slot FROM ops.project_budget WHERE mode='mock'").fetchone()==before
                assert c.execute('SELECT count(*) FROM ops.call_attempts').fetchone()[0]==1
                assert c.execute('SELECT count(*) FROM security.document_publications WHERE document_id=%s AND active',(ids['document_id'],)).fetchone()[0]==1
    f.run(check())


def test_job_metadata_lock_does_not_authorize_settings_write(ops_rows,tmp_path):
    import psycopg
    f=ops_rows;admin=f.run(f.context('A-ADM','A'));documents=DocumentRepository(f.pool,SourceStorage(tmp_path/'sources'),'x'*40)
    ids=f.run(documents.register(admin,metadata(),RAW));job=UUID(ids['job_id']);claim=b'k'*32;ticket=f.run(documents.job(admin,job,'claim',claim=claim))
    with f.db.admin_connection() as c:
        c.execute("""CREATE FUNCTION security.t283_test_forbidden_write(t uuid,j uuid,e bigint,w bytea) RETURNS void
        LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,security,pg_temp AS $$BEGIN
        PERFORM security.execution_scope(t);PERFORM security.document_worker_guard(t,j,e,w);
        UPDATE portal.agent_configs SET enabled=enabled WHERE tenant_id=t AND agent_key='rules_rag';
        END;$$;
        ALTER FUNCTION security.t283_test_forbidden_write(uuid,uuid,bigint,bytea) OWNER TO ai_policy_executor;
        REVOKE ALL ON FUNCTION security.t283_test_forbidden_write(uuid,uuid,bigint,bytea) FROM PUBLIC;
        GRANT EXECUTE ON FUNCTION security.t283_test_forbidden_write(uuid,uuid,bigint,bytea) TO ai_index;""")
    try:
        with f.role_connection('ai_index') as c:
            with pytest.raises(psycopg.errors.InsufficientPrivilege):c.execute('SELECT security.t283_test_forbidden_write(%s,%s,%s,%s)',(admin.tenant_id,job,ticket['epoch'],claim))
        with f.db.admin_connection() as c:assert c.execute("SELECT enabled,config_version FROM portal.agent_configs WHERE tenant_id=%s AND agent_key='rules_rag'",(admin.tenant_id,)).fetchone()==(True,1)
    finally:
        with f.db.admin_connection() as c:c.execute('DROP FUNCTION security.t283_test_forbidden_write(uuid,uuid,bigint,bytea)')
