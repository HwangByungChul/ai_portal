from uuid import uuid4
from datetime import datetime, timezone
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
import pytest
import psycopg
from psycopg.types.json import Jsonb
from test_operations import headers,ops_rows


def completed(client,f,login,actor='A-U1',tenant='A'):
    csrf=login(client,actor)['csrf_token']
    reply=client.post('/api/v1/runs',headers=headers(f,tenant,csrf),json={'agent_key':'general','client_send_id':str(uuid4()),'prompt':'합성 평가 질문'})
    assert reply.status_code==202
    run=reply.json()['data']
    with f.db.admin_connection() as conn:
        conn.execute("UPDATE portal.runs SET state='completed',stage='terminal',answer_kind='answer',ended_at=clock_timestamp() WHERE run_id=%s",(run['run_id'],))
        conn.execute("INSERT INTO portal.messages(tenant_id,message_id,conversation_id,owner_user_id,agent_key,sequence_no,role,body,run_id,payload_kind) VALUES(%s,%s,%s,%s,'general',2,'assistant','합성 완료 답변',%s,'general_assistant')",(f.tenant_ids[tenant],uuid4(),run['conversation_id'],f.actor_ids[actor],run['run_id']))
    return run,csrf


def test_owner_feedback_change_replay_withdraw_recreate_preserves_ledger(client,ops_rows,login):
    f=ops_rows;run,csrf=completed(client,f,login);path='/api/v1/runs/'+run['run_id']+'/feedback';h=headers(f,csrf=csrf)
    with f.db.admin_connection() as conn:
        before=conn.execute('SELECT (SELECT count(*) FROM ops.call_attempts),(SELECT count(*) FROM ops.usage_events),(SELECT count(*) FROM portal.messages)').fetchone()
    initial=client.get(path,headers=h);assert initial.status_code==200 and initial.json()['data']['revision']==0
    body={'rating':'positive','comment':'  비공개 합성 의견  ','expected_revision':0}
    saved=client.put(path,headers=h,json=body);assert saved.status_code==200
    assert saved.json()['data']['comment']=='비공개 합성 의견' and saved.json()['data']['revision']==1
    assert client.put(path,headers=h,json=body).json()['data']['replayed']
    conflict=client.put(path,headers=h,json={**body,'rating':'negative'});assert conflict.status_code==409 and conflict.json()['error']['code']=='FEEDBACK_CONFLICT'
    assert client.put(path,headers=h,json={'rating':'negative','expected_revision':1}).json()['data']['revision']==2
    assert client.get(path,headers=h).json()['data']['comment']==''
    assert client.request('DELETE',path,headers=h,json={'expected_revision':2}).json()['data']['revision']==3
    assert client.request('DELETE',path,headers=h,json={'expected_revision':2}).json()['data']['replayed']
    assert client.get(path,headers=h).json()['data']['rating'] is None
    assert client.put(path,headers=h,json={'rating':'positive','expected_revision':3}).json()['data']['revision']==4
    with f.db.admin_connection() as conn:
        assert conn.execute('SELECT count(*) FROM portal.response_feedback').fetchone()==(1,)
        assert conn.execute('SELECT (SELECT count(*) FROM ops.call_attempts),(SELECT count(*) FROM ops.usage_events),(SELECT count(*) FROM portal.messages)').fetchone()==before
        audit=conn.execute("SELECT revisions FROM ops.audit_events WHERE action IN ('feedback_updated','feedback_withdrawn')").fetchall()
        assert len(audit)==4 and '비공개' not in repr(audit)


@pytest.mark.parametrize('delta',[{'rating':'invalid'},{'rating':True},{'comment':'a'*1001},{'comment':None},{'comment':13},{'comment':'\x00'},{'expected_revision':True},{'expected_revision':-1},{'expected_revision':9223372036854775808},{'owner_user_id':str(uuid4())}])
def test_feedback_strict_inputs_do_not_store_or_echo_comment(client,ops_rows,login,delta):
    run,csrf=completed(client,ops_rows,login)
    response=client.put('/api/v1/runs/'+run['run_id']+'/feedback',headers=headers(ops_rows,csrf=csrf),json={'rating':'positive','comment':'private-marker','expected_revision':0,**delta})
    assert response.status_code==422 and 'private-marker' not in response.text
    with ops_rows.db.admin_connection() as conn: assert conn.execute('SELECT count(*) FROM portal.response_feedback').fetchone()==(0,)


def test_owner_tenant_admin_csrf_deleted_and_direct_sql_boundaries(client,ops_rows,login):
    f=ops_rows;run,csrf=completed(client,f,login);path='/api/v1/runs/'+run['run_id']+'/feedback'
    assert client.put(path,headers=headers(f),json={'rating':'positive','expected_revision':0}).status_code==403
    assert client.put(path,headers=headers(f,csrf=csrf),json={'rating':'positive','comment':'private-marker','expected_revision':0}).status_code==200
    for actor,tenant in [('A-U2','A'),('A-ADM','A'),('P-A','A'),('B-U1','B')]:
        token=login(client,actor)['csrf_token'];h=headers(f,tenant,token)
        assert client.get(path,headers=h).status_code in (403,404)
        assert client.put(path,headers=h,json={'rating':'negative','expected_revision':1}).status_code in (403,404)
        assert client.request('DELETE',path,headers=h,json={'expected_revision':1}).status_code in (403,404)
    csrf=login(client,'A-U1')['csrf_token']
    assert client.request('DELETE','/api/v1/conversations/'+run['conversation_id'],headers=headers(f,csrf=csrf),json={'expected_revision':0}).status_code==200
    assert client.get(path,headers=headers(f)).status_code==404
    assert client.put(path,headers=headers(f,csrf=csrf),json={'rating':'negative','expected_revision':1}).status_code==404
    ctx=f.run(f.context('A-U1','A'))
    with f.role_connection('ai_web') as conn:
        with conn.transaction():
            for k,value in [('app.session_id',ctx.session_id),('app.user_id',ctx.user_id),('app.tenant_id',ctx.tenant_id)]:conn.execute('SELECT set_config(%s,%s,true)',(k,str(value)))
            assert conn.execute('SELECT * FROM portal.response_feedback').fetchall()==[]
        with pytest.raises(psycopg.errors.InsufficientPrivilege):conn.execute("UPDATE portal.response_feedback SET rating='negative'")
    with f.db.admin_connection() as conn: assert conn.execute('SELECT count(*) FROM portal.response_feedback').fetchone()==(1,)


@pytest.mark.parametrize('state',['accepted','failed','cancelled','interrupted','blocked'])
def test_noncompleted_answer_cannot_be_rated(client,ops_rows,login,state):
    f=ops_rows;run,csrf=completed(client,f,login)
    with f.db.admin_connection() as conn:
        conn.execute("UPDATE portal.runs SET state=%s,stage=%s,answer_kind=NULL,ended_at=CASE WHEN %s='accepted' THEN NULL ELSE clock_timestamp() END WHERE run_id=%s",(state,'queued' if state=='accepted' else 'terminal',state,run['run_id']))
    response=client.put('/api/v1/runs/'+run['run_id']+'/feedback',headers=headers(f,csrf=csrf),json={'rating':'positive','expected_revision':0})
    assert response.status_code==409 and response.json()['error']['code']=='FEEDBACK_NOT_READY'


def test_summary_current_capability_threshold_mode_period_no_private_fields(client,ops_rows,login):
    f=ops_rows;rows=[]
    for actor in ['A-U1','A-U2','A-ADM']:
        run,csrf=completed(client,f,login,actor);rows.append(run)
        assert client.put('/api/v1/runs/'+run['run_id']+'/feedback',headers=headers(f,csrf=csrf),json={'rating':'negative' if actor=='A-U2' else 'positive','comment':'never-in-summary','expected_revision':0}).status_code==200
    path='/api/v1/admin/feedback/summary';period=datetime.now(timezone.utc).date().replace(day=1).isoformat()
    result=client.get(path,headers=headers(f),params={'period':period});assert result.status_code==200
    assert 'never-in-summary' not in result.text
    data=result.json()['data'];general=next(x for x in data['items'] if x['agent_key']=='general')
    assert general['total_count']==3 and general['positive_count']==2 and general['negative_count']==1
    for key in ['run_id','user_id','comment','title','body','prompt']:assert key not in result.text
    run,csrf=completed(client,f,login,'B-U1','B')
    assert client.put('/api/v1/runs/'+run['run_id']+'/feedback',headers=headers(f,'B',csrf),json={'rating':'positive','expected_revision':0}).status_code==200
    login(client,'A-U1');assert client.get(path,headers=headers(f),params={'period':period}).status_code==403
    csrf=login(client,'A-ADM')['csrf_token']
    assert client.get(path,headers=headers(f),params={'period':'2000-01-01'}).json()['data']['items'][0]['status']=='empty'
    assert client.get(path,headers=headers(f),params={'mode':'real'}).status_code==422
    assert client.get(path,headers=headers(f),params={'period':'2026-10-02'}).status_code==422
    # Deleting one of three participants excludes it and suppresses the small group.
    csrf=login(client,'A-U1')['csrf_token']
    assert client.request('DELETE','/api/v1/conversations/'+rows[0]['conversation_id'],headers=headers(f,csrf=csrf),json={'expected_revision':0}).status_code==200
    login(client,'A-ADM');small=client.get(path,headers=headers(f),params={'period':period}).json()['data']['items'][0]
    assert small['status']=='suppressed' and small['total_count'] is None
    with f.db.admin_connection() as conn:conn.execute("UPDATE security.memberships SET role='USER',revision=revision+1 WHERE tenant_id=%s AND user_id=%s",(f.tenant_ids['A'],f.actor_ids['A-ADM']))
    assert client.get(path,headers=headers(f),params={'period':period}).status_code==403


def test_feedback_audit_failure_rollback(client,ops_rows,login):
    f=ops_rows;run,csrf=completed(client,f,login)
    with f.db.admin_connection() as conn:conn.execute("ALTER TABLE ops.audit_events ADD CONSTRAINT dp04_fault CHECK(action<>'feedback_updated')")
    response=client.put('/api/v1/runs/'+run['run_id']+'/feedback',headers=headers(f,csrf=csrf),json={'rating':'positive','expected_revision':0})
    assert response.status_code==503
    with f.db.admin_connection() as conn:assert conn.execute('SELECT count(*) FROM portal.response_feedback').fetchone()==(0,)


def test_concurrent_feedback_unique_row_and_revision(client,ops_rows,login):
    f=ops_rows;run,_=completed(client,f,login);ctx=f.run(f.context('A-U1','A'));barrier=Barrier(2)
    def save(rating):
        with f.role_connection('ai_web') as conn:
            try:
                with conn.transaction():
                    for k,value in [('app.session_id',ctx.session_id),('app.user_id',ctx.user_id),('app.tenant_id',ctx.tenant_id)]:conn.execute('SELECT set_config(%s,%s,true)',(k,str(value)))
                    barrier.wait(timeout=5)
                    return conn.execute("SELECT security.feedback_mutate(%s,%s,%s,%s,0,false,%s)",(ctx.session_id,ctx.tenant_id,run['run_id'],Jsonb({'rating':rating,'comment':''}),uuid4())).fetchone()[0]['revision']
            except psycopg.Error as error:return error.sqlstate
    with ThreadPoolExecutor(max_workers=2) as pool:
        a=pool.submit(save,'positive');b=pool.submit(save,'negative');values=[a.result(),b.result()]
    assert values.count(1)==1 and values.count('B0411')==1
    with f.db.admin_connection() as conn:assert conn.execute('SELECT count(*) FROM portal.response_feedback').fetchone()==(1,)


def test_rag_feedback_is_private_and_revoked_source_hides_it(ops_rows,tmp_path):
    from uuid import UUID
    from app.feedback.repository import FeedbackRepository
    from app.documents.repository import DocumentRepository
    from app.documents.storage import SourceStorage
    from app.documents.sharing import SharingRepository
    from app.db import tenant_transaction
    from app.errors import AppError
    from test_document_sharing import publish
    from test_rag_execution import execute
    f=ops_rows
    async def check():
        a=await f.context('A-ADM','A');b=await f.context('B-U1','B');documents=DocumentRepository(f.pool,SourceStorage(tmp_path/'sources'),'x'*40)
        ids=await publish(f,documents,a);sharing=SharingRepository(documents)
        grant=await sharing.control(a,UUID(ids['document_id']),UUID(ids['version_id']),'issue',f.tenant_ids['B'],expected=1,request=uuid4())
        intake,result,ticket=await execute(f,documents,b);repo=FeedbackRepository(f.pool)
        with f.db.admin_connection() as conn:before=conn.execute('SELECT call_id,state,usage_snapshot,price_snapshot FROM ops.call_attempts ORDER BY call_id').fetchall()
        saved=await repo.mutate(b,ticket.run.run_id,{'rating':'positive','comment':'비공개 RAG 의견'},0,False,uuid4());assert saved['revision']==1
        assert (await repo.read(b,ticket.run.run_id,b'x'*32))['comment']=='비공개 RAG 의견'
        await sharing.control(a,action='revoke',grant=UUID(grant['grant_id']),expected=1,request=uuid4())
        for action in ['read','write']:
            with pytest.raises(AppError) as error:
                if action=='read':await repo.read(b,ticket.run.run_id,b'x'*32)
                else:await repo.mutate(b,ticket.run.run_id,{'rating':'negative','comment':''},1,False,uuid4())
            assert error.value.code=='FEEDBACK_NOT_READY'
        async with tenant_transaction(f.pool,b) as conn:assert await (await conn.execute('SELECT * FROM portal.response_feedback')).fetchall()==[]
        with f.db.admin_connection() as conn:assert conn.execute('SELECT call_id,state,usage_snapshot,price_snapshot FROM ops.call_attempts ORDER BY call_id').fetchall()==before
    f.run(check())


def test_feedback_bigint_overflow_empty_withdraw_and_raw_roles(client,ops_rows,login):
    f=ops_rows;run,csrf=completed(client,f,login);path='/api/v1/runs/'+run['run_id']+'/feedback';h=headers(f,csrf=csrf)
    assert client.request('DELETE',path,headers=h,json={'expected_revision':0}).json()['data']['replayed']
    assert client.put(path,headers=h,json={'rating':'positive','expected_revision':0}).status_code==200
    with f.db.admin_connection() as conn:conn.execute('UPDATE portal.response_feedback SET revision=9223372036854775807')
    assert client.put(path,headers=h,json={'rating':'negative','expected_revision':9223372036854775807}).status_code==409
    assert client.put(path,headers=h,json={'rating':'positive','expected_revision':9223372036854775807}).status_code==200
    for role in ['ai_meter','ai_index']:
        with f.role_connection(role) as conn:
            with pytest.raises(psycopg.errors.InsufficientPrivilege):conn.execute('SELECT * FROM portal.response_feedback')
    ctx=f.run(f.context('A-ADM','A'))
    with f.role_connection('ai_web') as conn:
        with conn.transaction():
            for k,value in [('app.session_id',ctx.session_id),('app.user_id',ctx.user_id),('app.tenant_id',ctx.tenant_id),('app.feedback_scope','summary'),('app.run_scope','owner')]:conn.execute('SELECT set_config(%s,%s,true)',(k,str(value)))
            assert conn.execute('SELECT * FROM portal.response_feedback').fetchall()==[]
            assert conn.execute('SELECT * FROM portal.conversations WHERE conversation_id=%s',(run['conversation_id'],)).fetchall()==[]
            with pytest.raises(psycopg.errors.InsufficientPrivilege):conn.execute('SELECT security.feedback_target(%s,%s,%s,false)',(ctx.session_id,ctx.tenant_id,run['run_id']))


@pytest.mark.parametrize('mutation',['account','membership','revoked'])
def test_feedback_current_authority_revoked(client,ops_rows,login,mutation):
    from app.feedback.repository import FeedbackRepository
    from app.errors import AppError
    f=ops_rows;run,_=completed(client,f,login);ctx=f.run(f.context('A-U1','A'))
    f.run(FeedbackRepository(f.pool).mutate(ctx,run['run_id'],{'rating':'positive','comment':'owner only'},0,False,uuid4()))
    f.mutate_access(ctx,mutation)
    with pytest.raises(AppError):f.run(FeedbackRepository(f.pool).read(ctx,run['run_id'],b'x'*32))


def test_different_sessions_delete_and_feedback_are_serialized(client,ops_rows,login):
    from dataclasses import replace
    f=ops_rows;run,_=completed(client,f,login);ctx=f.run(f.context('A-U1','A'));second=uuid4()
    with f.db.admin_connection() as conn:
        conn.execute('INSERT INTO security.sessions(session_id,token_hash,user_id,auth_revision,csrf_secret,issued_at,last_activity_at,expires_at) SELECT %s,%s,user_id,auth_revision,csrf_secret,issued_at,last_activity_at,expires_at FROM security.sessions WHERE session_id=%s',(second,uuid4().bytes+uuid4().bytes,ctx.session_id))
    other=replace(ctx,session_id=second);barrier=Barrier(2)
    def invoke(which,c):
        with f.role_connection('ai_web') as conn:
            try:
                with conn.transaction():
                    for k,value in [('app.session_id',c.session_id),('app.user_id',c.user_id),('app.tenant_id',c.tenant_id)]:conn.execute('SELECT set_config(%s,%s,true)',(k,str(value)))
                    barrier.wait(timeout=5)
                    if which=='delete':conn.execute('SELECT security.conversation_mutate(%s,%s,%s,%s,0,true,%s)',(c.session_id,c.tenant_id,run['conversation_id'],Jsonb({}),uuid4()))
                    else:conn.execute('SELECT security.feedback_mutate(%s,%s,%s,%s,0,false,%s)',(c.session_id,c.tenant_id,run['run_id'],Jsonb({'rating':'positive','comment':''}),uuid4()))
                    return 'ok'
            except psycopg.Error as error:return error.sqlstate
    with ThreadPoolExecutor(max_workers=2) as pool:
        a=pool.submit(invoke,'delete',ctx);b=pool.submit(invoke,'feedback',other);assert a.result()=='ok';assert b.result() in ('ok','A0404')
    with f.db.admin_connection() as conn:assert conn.execute('SELECT deleted_at IS NOT NULL FROM portal.conversations WHERE conversation_id=%s',(run['conversation_id'],)).fetchone()==(True,)
    token=login(client,'A-U1')['csrf_token']
    assert client.get('/api/v1/runs/'+run['run_id']+'/feedback',headers=headers(f,csrf=token)).status_code==404
