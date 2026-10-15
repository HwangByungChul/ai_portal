from dataclasses import FrozenInstanceError
from uuid import UUID,uuid4
import hashlib
import json
import pytest
import psycopg
from psycopg.types.json import Jsonb
from app.db import tenant_transaction
from app.ai.repository import CallRepository,digest
from app.conversations.repository import ConversationRepository
from test_operations import ops_rows,headers
from test_conversations import submit,cancel_run


def alias(f,tenant='A',agent='general'):
    return str(UUID(hashlib.md5((str(f.tenant_ids[tenant])+':portal-agent:'+agent).encode()).hexdigest()))


def test_binding_alias_replay_and_immutable_history(client,login,ops_rows):
    f=ops_rows;csrf=login(client,'A-U1')['csrf_token'];send=str(uuid4())
    first=submit(client,f,csrf,client_send_id=send);assert first.status_code==202
    data=first.json()['data'];binding=data['asset_binding']
    assert binding['source']=='legacy' and binding['asset_id']==alias(f)
    assert binding['revision']==1 and len(binding['config_hash'])==64
    expected=str(UUID(hashlib.md5((alias(f)+':revision:1:'+binding['config_hash']).encode()).hexdigest()))
    assert binding['version_id']==expected
    same=submit(client,f,csrf,client_send_id=send,asset_id=alias(f));assert same.status_code==202
    assert same.json()['data']['run_id']==data['run_id'] and same.json()['data']['asset_binding']==binding
    assert cancel_run(client,f,csrf,data['run_id']).json()['data']['asset_binding']==binding
    with f.db.admin_connection() as conn:
        cfg=conn.execute("SELECT settings FROM portal.agent_configs WHERE tenant_id=%s AND agent_key='general'",(f.tenant_ids['A'],)).fetchone()[0]
        cfg['instructions']='changed-private-instruction';conn.execute("UPDATE portal.agent_configs SET settings=%s,config_version=2 WHERE tenant_id=%s AND agent_key='general'",(Jsonb(cfg),f.tenant_ids['A']))
    assert submit(client,f,csrf,client_send_id=send,asset_id=alias(f)).json()['data']['asset_binding']==binding
    for path in ['/runs/'+data['run_id'],'/runs/by-send/'+send]:
        reply=client.get('/api/v1'+path,headers=headers(f));assert reply.status_code==200
        assert reply.json()['data']['asset_binding']==binding
        assert 'instruction' not in json.dumps(reply.json()['data']['asset_binding'])
    fresh=submit(client,f,csrf,asset_id=alias(f));assert fresh.status_code==202
    new=fresh.json()['data']['asset_binding']
    assert new['asset_id']==binding['asset_id'] and new['revision']==2 and new['version_id']!=binding['version_id'] and new['config_hash']!=binding['config_hash']


@pytest.mark.parametrize('kind',['random','other_agent','other_tenant','draft'])
def test_unapproved_or_wrong_selector_has_no_side_effects(client,login,ops_rows,kind):
    f=ops_rows;csrf=login(client,'A-U1')['csrf_token']
    selected=str(uuid4())
    if kind=='other_agent':selected=alias(f,agent='rules_rag')
    if kind=='other_tenant':selected=alias(f,tenant='B')
    if kind=='draft':
        async def create():
            from app.assets.repository import AssetRepository
            ctx=await f.context('A-ADM','A')
            return await AssetRepository(f.pool).call(ctx,'create',uuid4(),{'client_request_id':str(uuid4()),'config':{'name':'draft','description':'','instructions':'draft-private','execution_kind':'general'}},uuid4())
        selected=f.run(create())['asset_id']
    tables=['portal.runs','portal.messages','ops.call_attempts','ops.usage_events','ops.audit_events']
    with f.db.admin_connection() as conn:before=[conn.execute('SELECT count(*) FROM '+t).fetchone()[0] for t in tables]
    reply=submit(client,f,csrf,asset_id=selected);assert reply.status_code==404
    with f.db.admin_connection() as conn:assert [conn.execute('SELECT count(*) FROM '+t).fetchone()[0] for t in tables]==before


@pytest.mark.parametrize('delta',[{'asset_id':'bad'},{'asset_revision':1},{'asset_config_hash':'a'*64},{'agent_key':'draft'}])
def test_binding_inputs_are_server_controlled(client,login,ops_rows,delta):
    f=ops_rows;csrf=login(client,'A-U1')['csrf_token'];assert submit(client,f,csrf,**delta).status_code==422


def test_binding_rls_worker_and_update_guard(client,login,ops_rows):
    f=ops_rows;csrf=login(client,'A-U1')['csrf_token'];reply=submit(client,f,csrf);assert reply.status_code==202
    data=reply.json()['data'];rid=UUID(data['run_id']);binding=data['asset_binding']
    async def check():
        from datetime import date
        from dataclasses import replace
        ctx=await f.context('A-U1','A')
        with f.db.admin_connection() as conn:origin=conn.execute('SELECT origin_session_id FROM portal.runs WHERE run_id=%s',(rid,)).fetchone()[0]
        ctx=replace(ctx,session_id=origin);repo=CallRepository(f.pool,None,date(2026,10,1))
        t=await repo.claim(ctx,rid,'mock');assert t is not None
        assert str(t.asset_binding.asset_id)==binding['asset_id'] and t.asset_binding.revision==t.run.config_revision==binding['revision']
        assert t.asset_binding.config_hash==binding['config_hash']
        with pytest.raises(FrozenInstanceError):t.asset_binding.revision=99
        for field,value in [('asset_revision','99'),('asset_config_hash',"'"+'a'*64+"'"),('asset_id',"'"+str(uuid4())+"'"),('asset_version_id',"'"+str(uuid4())+"'")]:
            with f.db.admin_connection() as conn:
                with pytest.raises(psycopg.errors.CheckViolation):conn.execute('UPDATE portal.runs SET '+field+'='+value+' WHERE run_id=%s',(rid,))
        async with tenant_transaction(f.pool,ctx) as conn:
            out=await (await conn.execute('SELECT security.run_asset_resolve(%s,%s,%s,%s) AS id',(ctx.session_id,ctx.tenant_id,'rules_rag',None))).fetchone()
            assert str(out['id'])==alias(f,agent='rules_rag')
        await repo.fail(t,'EXECUTION_INTERRUPTED')
    f.run(check())
    login(client,'A-U2');assert client.get('/api/v1/runs/'+data['run_id'],headers=headers(f)).status_code==404
    login(client,'B-ADM');assert client.get('/api/v1/runs/'+data['run_id'],headers=headers(f,'B')).status_code==404


def test_resolver_direct_rpc_rechecks_session_and_tenant(ops_rows):
    f=ops_rows
    async def check():
        ctx=await f.context('A-U1','A')
        cases=[(ctx.session_id,f.tenant_ids['B'],'general',None),(ctx.session_id,ctx.tenant_id,'general',uuid4()),(ctx.session_id,ctx.tenant_id,'draft',None)]
        for args in cases:
            async with tenant_transaction(f.pool,ctx) as conn:
                with pytest.raises(psycopg.Error):await conn.execute('SELECT security.run_asset_resolve(%s,%s,%s,%s)',args)
        f.mutate_access(ctx,'revoked')
        with pytest.raises((psycopg.Error,ValueError)):
            async with tenant_transaction(f.pool,ctx) as conn:await conn.execute('SELECT security.run_asset_resolve(%s,%s,%s,%s)',(ctx.session_id,ctx.tenant_id,'general',None))
    f.run(check())


@pytest.mark.parametrize('kind',['rag','summary'])
def test_rag_and_document_summary_binding_matches_worker(ops_rows,tmp_path,kind):
    f=ops_rows
    async def check():
        from test_dp07_acceptance import setup,execute as summarize,RAW
        from test_rag_execution import execute as rag
        from test_document_sharing import publish
        docs=setup(f,tmp_path);admin=await f.context('A-ADM','A');ctx=await f.context('A-U1','A')
        ids=await publish(f,docs,admin,raw=RAW)
        if kind=='summary':data,ticket,result=await summarize(f,docs,ctx,ids)
        else:
            from datetime import date
            from app.db import open_meter_pool
            from app.documents.embedding import MockEmbeddingProvider
            from app.ai.rag_provider import RagMockProvider
            from app.execution.rag import RagExecutor
            data=await ConversationRepository(f.pool).admit(ctx,'rules_rag',None,uuid4(),'여신심사 담당 부서는?',date(2026,10,1),'mock',b'x'*32,uuid4(),documents=docs,asset_id=UUID(alias(f,agent='rules_rag')))
            async with open_meter_pool(f.db.runtime_dsn('ai_meter')) as meter:
                repo=CallRepository(f.pool,meter,date(2026,10,1));ticket=await repo.claim(ctx,UUID(data['run_id']),'mock')
                engine=RagExecutor(repo,docs,MockEmbeddingProvider(),RagMockProvider());result=await engine.execute(ticket);assert await engine.finish(ticket,result)
        binding=data['asset_binding']
        assert binding['asset_id']==alias(f,agent='rules_rag')
        assert str(ticket.asset_binding.asset_id)==binding['asset_id']
        assert ticket.asset_binding.revision==ticket.run.config_revision==binding['revision']
        assert ticket.asset_binding.config_hash==binding['config_hash']
    f.run(check())


@pytest.mark.parametrize('settings',[{}, {'instructions':''}])
def test_effective_default_instructions_are_fingerprinted(client,login,ops_rows,settings):
    f=ops_rows
    with f.db.admin_connection() as conn:conn.execute("UPDATE portal.agent_configs SET settings=%s WHERE tenant_id=%s AND agent_key='general'",(Jsonb(settings),f.tenant_ids['A']))
    csrf=login(client,'A-U1')['csrf_token'];reply=submit(client,f,csrf);assert reply.status_code==202
    data=reply.json()['data']
    with f.db.admin_connection() as conn:
        expected=conn.execute("SELECT encode(sha256(convert_to(jsonb_build_object('name','일반 대화','description','','instructions','사용자 질문에 간결하고 정확하게 답변하세요.','execution_kind','general')::text,'UTF8')),'hex'),config_snapshot->>'instructions' FROM portal.runs WHERE run_id=%s",(UUID(data['run_id']),)).fetchone()
    assert expected[1]=='사용자 질문에 간결하고 정확하게 답변하세요.'
    assert data['asset_binding']['config_hash']==expected[0]
