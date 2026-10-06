from uuid import uuid4
import pytest
from test_operations import headers, ops_rows


def create(client, f, login, actor='A-U1', client_id=None):
    csrf=login(client,actor)['csrf_token']
    response=client.post('/api/v1/conversations',headers=headers(f,'A',csrf),json={'agent_key':'general',**({'client_conversation_id':str(client_id)} if client_id else {})})
    assert response.status_code==201
    return response.json()['data']['conversation_id'],csrf


def test_metadata_owner_revision_replay_and_private_access(client,ops_rows,login):
    f=ops_rows;id,csrf=create(client,f,login);path='/api/v1/conversations/'+id
    body={'title':' 합성 제목 ','pinned':True,'expected_revision':0}
    reply=client.patch(path,headers=headers(f,'A',csrf),json=body)
    assert reply.status_code==200
    assert reply.json()['data']['title']=='합성 제목'
    assert reply.json()['data']['pinned'] is True and reply.json()['data']['metadata_revision']==1
    replay=client.patch(path,headers=headers(f,'A',csrf),json=body)
    assert replay.status_code==200 and replay.json()['data']['replayed']
    assert client.patch(path,headers=headers(f,'A',csrf),json={**body,'title':'다른 제목'}).status_code==409
    assert client.patch(path,headers=headers(f),json=body).status_code==403
    for actor in ['A-U2','P-A','A-ADM']:
        token=login(client,actor)['csrf_token']
        assert client.patch(path,headers=headers(f,'A',token),json={'title':'침입','expected_revision':1}).status_code in (403,404)
    token=login(client,'B-U1')['csrf_token']
    assert client.patch(path,headers=headers(f,'B',token),json={'title':'침입','expected_revision':1}).status_code==404
    with f.db.admin_connection() as conn:
        row=conn.execute("SELECT revisions FROM ops.audit_events WHERE action='conversation_updated' AND opaque_target_id=%s",(id,)).fetchone()
        assert row==({'metadata_revision':1},)


@pytest.mark.parametrize('delta',[{'title':''},{'title':'a'*121},{'title':'a\n b'},{'title':'\x00'},{'title':None},{'pinned':1},{'owner_user_id':str(uuid4())},{}])
def test_invalid_metadata_has_no_mutation(client,ops_rows,login,delta):
    f=ops_rows;id,csrf=create(client,f,login)
    assert client.patch('/api/v1/conversations/'+id,headers=headers(f,'A',csrf),json={**delta,'expected_revision':0}).status_code==422
    with f.db.admin_connection() as conn:
        assert conn.execute('SELECT metadata_revision FROM portal.conversations WHERE conversation_id=%s',(id,)).fetchone()==(0,)


def test_title_search_pin_order_and_bound_cursor(client,ops_rows,login):
    f=ops_rows
    for title in ['alpha','ALPHA 100%_','beta']:
        id,csrf=create(client,f,login)
        assert client.patch('/api/v1/conversations/'+id,headers=headers(f,'A',csrf),json={'title':title,'pinned':title=='alpha','expected_revision':0}).status_code==200
    reply=client.get('/api/v1/conversations?q=alpha&limit=1',headers=headers(f)).json()['data']
    assert reply['items'][0]['title']=='alpha' and reply['next_cursor']
    cursor=reply['next_cursor']
    second=client.get('/api/v1/conversations',headers=headers(f),params={'q':'alpha','limit':1,'cursor':cursor}).json()['data']
    assert [x['title'] for x in second['items']]==['ALPHA 100%_']
    assert client.get('/api/v1/conversations',headers=headers(f),params={'q':'beta','cursor':cursor}).status_code==422
    assert len(client.get('/api/v1/conversations',headers=headers(f),params={'q':'%_'}).json()['data']['items'])==1
    assert len(client.get('/api/v1/conversations?pinned=true',headers=headers(f)).json()['data']['items'])==1
    login(client,'A-U2')
    assert client.get('/api/v1/conversations',headers=headers(f),params={'q':'alpha','cursor':cursor}).status_code==422


def test_delete_hides_messages_replays_and_direct_reads_but_preserves_records(client,ops_rows,login):
    f=ops_rows;cid=uuid4();id,csrf=create(client,f,login,client_id=cid);path='/api/v1/conversations/'+id
    with f.db.admin_connection() as conn:
        before=conn.execute('SELECT count(*) FROM portal.messages').fetchone()
    deleted=client.request('DELETE',path,headers=headers(f,'A',csrf),json={'expected_revision':0})
    assert deleted.status_code==200 and deleted.json()['data']['deleted']
    assert client.request('DELETE',path,headers=headers(f,'A',csrf),json={'expected_revision':0}).status_code==200
    assert client.patch(path,headers=headers(f,'A',csrf),json={'title':'재활성화','expected_revision':1}).status_code==404
    assert client.get(path+'/messages',headers=headers(f)).status_code==404
    assert not any(x['conversation_id']==id for x in client.get('/api/v1/conversations',headers=headers(f)).json()['data']['items'])
    assert client.post('/api/v1/conversations',headers=headers(f,'A',csrf),json={'agent_key':'general','client_conversation_id':str(cid)}).status_code==409
    assert client.post('/api/v1/runs',headers=headers(f,'A',csrf),json={'agent_key':'general','conversation_id':id,'client_send_id':str(uuid4()),'prompt':'삭제 우회'}).status_code==404
    with f.db.admin_connection() as conn:
        assert conn.execute('SELECT count(*) FROM portal.messages').fetchone()==before
        assert conn.execute('SELECT deleted_at IS NOT NULL FROM portal.conversations WHERE conversation_id=%s',(id,)).fetchone()==(True,)


def test_busy_delete_cancel_terminal_and_run_gate(client,ops_rows,login):
    f=ops_rows;id,csrf=create(client,f,login);path='/api/v1/conversations/'+id;send=uuid4()
    payload={'agent_key':'general','conversation_id':id,'client_send_id':str(send),'prompt':'합성 대기 질문'}
    admitted=client.post('/api/v1/runs',headers=headers(f,'A',csrf),json=payload)
    assert admitted.status_code==202;run=admitted.json()['data']['run_id']
    assert client.request('DELETE',path,headers=headers(f,'A',csrf),json={'expected_revision':0}).status_code==409
    assert client.post('/api/v1/runs/'+run+'/cancel',headers=headers(f,'A',csrf),json={'expected_revision':1}).status_code==200
    with f.db.admin_connection() as conn:
        before=conn.execute('SELECT config_snapshot FROM portal.runs WHERE run_id=%s',(run,)).fetchone()
        counts=conn.execute('SELECT (SELECT count(*) FROM ops.call_attempts),(SELECT count(*) FROM ops.usage_events),(SELECT count(*) FROM portal.messages)').fetchone()
    assert client.request('DELETE',path,headers=headers(f,'A',csrf),json={'expected_revision':0}).status_code==200
    for endpoint in ['/runs/'+run,'/runs/by-send/'+str(send),'/runs/'+run+'/evidence','/runs/'+run+'/evidence/0/source']:
        assert client.get('/api/v1'+endpoint,headers=headers(f)).status_code==404
    assert client.get('/api/v1/runs/'+run+'/events',headers={**headers(f),'Accept':'text/event-stream'}).status_code==404
    assert client.post('/api/v1/runs',headers=headers(f,'A',csrf),json=payload).status_code==404
    with f.db.admin_connection() as conn:
        assert conn.execute('SELECT config_snapshot FROM portal.runs WHERE run_id=%s',(run,)).fetchone()==before
        assert conn.execute('SELECT (SELECT count(*) FROM ops.call_attempts),(SELECT count(*) FROM ops.usage_events),(SELECT count(*) FROM portal.messages)').fetchone()==counts
    ctx=f.run(f.context('A-U1','A'))
    async def direct():
        from app.db import tenant_transaction
        async with tenant_transaction(f.pool,ctx) as conn:
            assert await (await conn.execute('SELECT run_id FROM portal.runs WHERE run_id=%s',(run,))).fetchone() is None
            assert await (await conn.execute('SELECT message_id FROM portal.messages WHERE conversation_id=%s',(id,))).fetchone() is None
    f.run(direct())


def test_deleted_rag_hides_sealed_evidence_and_keeps_settled_ledger(client,ops_rows,login,tmp_path):
    from uuid import UUID
    from app.documents.repository import DocumentRepository
    from app.documents.storage import SourceStorage
    from app.conversations.repository import ConversationRepository
    from app.db import tenant_transaction
    from test_document_sharing import publish
    from test_rag_execution import execute
    f=ops_rows
    async def build():
        admin=await f.context('A-ADM','A');ctx=await f.context('A-U1','A')
        documents=DocumentRepository(f.pool,SourceStorage(tmp_path/'rag-sources'),'x'*40)
        await publish(f,documents,admin)
        intake,result,ticket=await execute(f,documents,ctx)
        async with tenant_transaction(f.pool,ctx) as conn:
            assert (await (await conn.execute('SELECT security.can_read_rag_answer_payload(%s,%s) AS ok',(ctx.tenant_id,ticket.run.run_id))).fetchone())['ok']
        return intake,ticket
    intake,ticket=f.run(build());run=intake['run_id'];id=intake['conversation_id']
    csrf=login(client,'A-U1')['csrf_token']
    assert client.get('/api/v1/runs/'+run+'/evidence',headers=headers(f)).status_code==200
    with f.db.admin_connection() as conn:
        ledger=conn.execute('SELECT call_id,state,usage_snapshot,price_snapshot FROM ops.call_attempts WHERE run_id=%s ORDER BY call_id',(run,)).fetchall()
        payload=conn.execute('SELECT provenance_sealed,source_count,config_snapshot FROM portal.runs WHERE run_id=%s',(run,)).fetchone()
        evidence=conn.execute('SELECT quote_snapshot,location_snapshot FROM portal.answer_evidence WHERE run_id=%s ORDER BY ordinal',(run,)).fetchall()
    assert client.request('DELETE','/api/v1/conversations/'+id,headers=headers(f,'A',csrf),json={'expected_revision':0}).status_code==200
    for path in ['/runs/'+run,'/runs/'+run+'/evidence','/runs/'+run+'/evidence/0/source']:
        assert client.get('/api/v1'+path,headers=headers(f)).status_code==404
    async def gate():
        ctx=await f.context('A-U1','A')
        async with tenant_transaction(f.pool,ctx) as conn:
            assert not (await (await conn.execute('SELECT security.can_read_rag_answer_payload(%s,%s) AS ok',(ctx.tenant_id,UUID(run)))).fetchone())['ok']
    f.run(gate())
    with f.db.admin_connection() as conn:
        assert conn.execute('SELECT call_id,state,usage_snapshot,price_snapshot FROM ops.call_attempts WHERE run_id=%s ORDER BY call_id',(run,)).fetchall()==ledger
        assert conn.execute('SELECT provenance_sealed,source_count,config_snapshot FROM portal.runs WHERE run_id=%s',(run,)).fetchone()==payload
        assert conn.execute('SELECT quote_snapshot,location_snapshot FROM portal.answer_evidence WHERE run_id=%s ORDER BY ordinal',(run,)).fetchall()==evidence


def test_metadata_bigint_revision_does_not_overflow(client,ops_rows,login):
    f=ops_rows;id,csrf=create(client,f,login)
    reply=client.patch('/api/v1/conversations/'+id,headers=headers(f,'A',csrf),json={'title':'stale','expected_revision':9223372036854775807})
    assert reply.status_code==409


def test_two_sessions_race_delete_and_admit_without_orphan_or_duplicate(client,ops_rows,login):
    from concurrent.futures import ThreadPoolExecutor
    from dataclasses import replace
    from datetime import date
    from threading import Barrier
    from psycopg.types.json import Jsonb
    import psycopg
    f=ops_rows;id,csrf=create(client,f,login)
    ctx=f.run(f.context('A-U1','A'));second_session=uuid4()
    with f.db.admin_connection() as conn:
        conn.execute('INSERT INTO security.sessions(session_id,token_hash,user_id,auth_revision,csrf_secret,issued_at,last_activity_at,expires_at) SELECT %s,%s,user_id,auth_revision,csrf_secret,issued_at,last_activity_at,expires_at FROM security.sessions WHERE session_id=%s',(second_session,uuid4().bytes+uuid4().bytes,ctx.session_id))
    other=replace(ctx,session_id=second_session);barrier=Barrier(2)
    def invoke(which,c):
        with f.role_connection('ai_web') as conn:
            try:
                with conn.transaction():
                    for key,value in [('app.session_id',c.session_id),('app.user_id',c.user_id),('app.tenant_id',c.tenant_id)]:conn.execute('SELECT set_config(%s,%s,true)',(key,str(value)))
                    barrier.wait(timeout=5)
                    if which=='delete':
                        row=conn.execute('SELECT security.conversation_mutate(%s,%s,%s,%s,0,true,%s)',(c.session_id,c.tenant_id,id,Jsonb({}),uuid4())).fetchone()[0]
                        return 'delete','deleted' if row['deleted'] else 'invalid'
                    row=conn.execute('SELECT security.run_admit(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s::uuid[],%s,%s,%s)',(c.session_id,c.tenant_id,'general',id,uuid4(),b'z'*32,'race question',date(2026,10,1),'mock',1,[],5,b'y'*32,uuid4())).fetchone()[0]
                    assert row['conversation_id']==id
                    return 'run','admitted'
            except psycopg.Error as e:return which,e.sqlstate
    with ThreadPoolExecutor(max_workers=2) as pool:
        a=pool.submit(invoke,'delete',ctx);b=pool.submit(invoke,'run',other);out={a.result(),b.result()}
    assert out in ({('delete','deleted'),('run','A0404')},{('delete','B0312'),('run','admitted')})
    with f.db.admin_connection() as conn:
        deleted,count=conn.execute('SELECT c.deleted_at IS NOT NULL,(SELECT count(*) FROM portal.runs r WHERE r.tenant_id=c.tenant_id AND r.conversation_id=c.conversation_id) FROM portal.conversations c WHERE c.conversation_id=%s',(id,)).fetchone()
        assert (deleted,count) in [(True,0),(False,1)]


def test_concurrent_titles_have_one_revision_and_audit(client,ops_rows,login):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier
    from psycopg.types.json import Jsonb
    import psycopg
    f=ops_rows;id,csrf=create(client,f,login);ctx=f.run(f.context('A-U1','A'));barrier=Barrier(2)
    def rename(title):
        with f.role_connection('ai_web') as conn:
            try:
                with conn.transaction():
                    for key,value in [('app.session_id',ctx.session_id),('app.user_id',ctx.user_id),('app.tenant_id',ctx.tenant_id)]:conn.execute('SELECT set_config(%s,%s,true)',(key,str(value)))
                    barrier.wait(timeout=5)
                    row=conn.execute('SELECT security.conversation_mutate(%s,%s,%s,%s,0,false,%s)',(ctx.session_id,ctx.tenant_id,id,Jsonb({'title':title}),uuid4())).fetchone()[0]
                    assert row['metadata_revision']==1
                    return 'updated'
            except psycopg.Error as error:return error.sqlstate
    with ThreadPoolExecutor(max_workers=2) as pool:
        a=pool.submit(rename,'첫 제목');b=pool.submit(rename,'다른 제목');assert sorted([a.result(),b.result()])==['B0311','updated']
    with f.db.admin_connection() as conn:
        assert conn.execute('SELECT metadata_revision FROM portal.conversations WHERE conversation_id=%s',(id,)).fetchone()==(1,)
        assert conn.execute("SELECT count(*) FROM ops.audit_events WHERE action='conversation_updated' AND opaque_target_id=%s",(id,)).fetchone()==(1,)


def test_audit_failure_rolls_back_metadata(client,ops_rows,login):
    f=ops_rows;id,csrf=create(client,f,login)
    with f.db.admin_connection() as conn:conn.execute("ALTER TABLE ops.audit_events ADD CONSTRAINT dp03_fault CHECK(action<>'conversation_updated')")
    reply=client.patch('/api/v1/conversations/'+id,headers=headers(f,'A',csrf),json={'title':'기록할 수 없는 수정','expected_revision':0})
    assert reply.status_code==503
    with f.db.admin_connection() as conn:
        assert conn.execute('SELECT title,metadata_revision FROM portal.conversations WHERE conversation_id=%s',(id,)).fetchone()==('제목 없는 대화',0)


def test_long_korean_query_cursor_is_usable_without_raw_query(client,ops_rows,login):
    f=ops_rows;query='가'*120
    for _ in range(2):
        id,csrf=create(client,f,login)
        assert client.patch('/api/v1/conversations/'+id,headers=headers(f,'A',csrf),json={'title':query,'expected_revision':0}).status_code==200
    first=client.get('/api/v1/conversations',headers=headers(f),params={'q':query,'limit':1}).json()['data']
    assert first['next_cursor'] and len(first['next_cursor'])<=1024
    second=client.get('/api/v1/conversations',headers=headers(f),params={'q':query,'limit':1,'cursor':first['next_cursor']}).json()['data']
    assert len(second['items'])==1 and second['items'][0]['conversation_id']!=first['items'][0]['conversation_id']
