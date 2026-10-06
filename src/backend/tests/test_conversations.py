from concurrent.futures import ThreadPoolExecutor
from uuid import uuid4
import pytest
from test_operations import ops_rows,headers


def submit(client,f,csrf,**delta):
    return client.post('/api/v1/runs',headers=headers(f,csrf=csrf),json={
        'client_send_id':str(uuid4()),'conversation_id':None,'agent_key':'general','prompt':'합성 질문',**delta})


def test_atomic_admission_replay_and_conflict(client,login,ops_rows):
    f=ops_rows;csrf=login(client,'A-U1')['csrf_token'];send=str(uuid4())
    first=submit(client,f,csrf,client_send_id=send);assert first.status_code==202
    data=first.json()['data'];assert data['state']=='accepted' and data['result'] is None
    assert data['execution_mode']=='mock' and data['content_status']=='pending' and data['usage_status']=='none'
    same=submit(client,f,csrf,client_send_id=send);assert same.status_code==202 and same.json()['data']['replayed']
    assert same.json()['data']['run_id']==data['run_id']
    assert submit(client,f,csrf,client_send_id=send,prompt='다른 합성 질문').status_code==409
    with f.db.admin_connection() as conn:
        assert conn.execute('SELECT count(*) FROM portal.runs').fetchone()[0]==1
        assert conn.execute('SELECT count(*) FROM portal.messages').fetchone()[0]==1
        assert conn.execute('SELECT count(*) FROM ops.call_attempts').fetchone()[0]==0


def test_concurrent_same_send_one_run(client,login,ops_rows):
    f=ops_rows;csrf=login(client,'A-U1')['csrf_token'];send=str(uuid4())
    with ThreadPoolExecutor(max_workers=2) as ex:responses=list(ex.map(lambda _:submit(client,f,csrf,client_send_id=send),range(2)))
    assert [r.status_code for r in responses]==[202,202]
    assert len({r.json()['data']['run_id'] for r in responses})==1
    with f.db.admin_connection() as conn:
        assert conn.execute('SELECT count(*) FROM portal.runs').fetchone()[0]==1
        assert conn.execute('SELECT count(*) FROM portal.messages').fetchone()[0]==1


def test_cancel_and_new_send(client,login,ops_rows):
    f=ops_rows;csrf=login(client,'A-U1')['csrf_token'];first=submit(client,f,csrf);assert first.status_code==202
    data=first.json()['data'];cancel=client.post('/api/v1/runs/'+data['run_id']+'/cancel',headers=headers(f,csrf=csrf),json={'expected_revision':1})
    assert cancel.status_code==200 and cancel.json()['data']['state']=='cancelled'
    assert submit(client,f,csrf).status_code==202

import asyncio
import hashlib
import json
import time
from decimal import Decimal
from unittest.mock import patch
from uuid import UUID
import psycopg
from psycopg.types.json import Jsonb
from app.db import open_web_pool,tenant_transaction
from app.conversations.repository import ConversationRepository
from app.errors import AppError


def cancel_run(client,f,csrf,run,revision=1):
    return client.post('/api/v1/runs/'+run+'/cancel',headers=headers(f,csrf=csrf),json={'expected_revision':revision})


def assert_empty(f):
    with f.db.admin_connection() as conn:
        assert conn.execute('SELECT count(*) FROM portal.runs').fetchone()[0]==0
        assert conn.execute('SELECT count(*) FROM portal.messages').fetchone()[0]==0
        assert conn.execute('SELECT count(*) FROM ops.call_attempts').fetchone()[0]==0
        assert conn.execute('SELECT count(*) FROM ops.usage_events').fetchone()[0]==0


def test_conversation_create_idempotent_agent_binding_and_owner_scope(client,login,ops_rows):
    f=ops_rows;csrf=login(client,'A-U1')['csrf_token'];key=str(uuid4());h=headers(f,csrf=csrf)
    body={'agent_key':'general','client_conversation_id':key}
    first=client.post('/api/v1/conversations',headers=h,json=body);assert first.status_code==201
    replay=client.post('/api/v1/conversations',headers=h,json=body);assert replay.status_code==200
    assert replay.json()['data']['conversation_id']==first.json()['data']['conversation_id']
    assert client.post('/api/v1/conversations',headers=h,json={**body,'agent_key':'rules_rag'}).status_code==409
    with f.db.admin_connection() as conn:conn.execute("UPDATE portal.agent_configs SET enabled=false WHERE tenant_id=%s AND agent_key='general'",(f.tenant_ids['A'],))
    assert client.post('/api/v1/conversations',headers=h,json=body).status_code==200
    assert client.post('/api/v1/conversations',headers=h,json={'agent_key':'general'}).status_code==409
    login(client,'A-U2');own=client.get('/api/v1/conversations',headers=headers(f)).json()['data']['items']
    assert first.json()['data']['conversation_id'] not in {x['conversation_id'] for x in own}


@pytest.mark.parametrize('actor,tenant',[('A-U2','A'),('A-ADM','A'),('P-A','A'),('B-U1','B')])
def test_foreign_conversation_run_send_hidden_from_current_actor(client,login,ops_rows,actor,tenant):
    f=ops_rows;csrf=login(client,'A-U1')['csrf_token'];send=str(uuid4());data=submit(client,f,csrf,client_send_id=send).json()['data']
    csrf=login(client,actor)['csrf_token'];h=headers(f,tenant,csrf)
    for path in ['/runs/'+data['run_id'],'/runs/by-send/'+send,'/conversations/'+data['conversation_id']+'/messages']:
        reply=client.get('/api/v1'+path,headers=h);assert reply.status_code==404
        assert '합성 질문' not in reply.text and data['run_id'] not in reply.text
    reply=client.post('/api/v1/runs/'+data['run_id']+'/cancel',headers=h,json={'expected_revision':1});assert reply.status_code==404
    reply=client.post('/api/v1/runs',headers=h,json={'client_send_id':str(uuid4()),'conversation_id':data['conversation_id'],'agent_key':'general','prompt':'다른 주체 질문'});assert reply.status_code==404


def test_header_claims_do_not_grant_owner_or_tenant(client,login,ops_rows):
    f=ops_rows;csrf=login(client,'A-U1')['csrf_token'];data=submit(client,f,csrf).json()['data']
    h={**headers(f,'B',csrf),'X-User-ID':str(f.actor_ids['B-U1']),'X-Role':'PADMIN'}
    assert client.get('/api/v1/runs/'+data['run_id'],headers=h).status_code==403
    assert client.post('/api/v1/runs/'+data['run_id']+'/cancel',headers=h,json={'expected_revision':1}).status_code==403
    assert client.get('/api/v1/conversations').status_code==422


@pytest.mark.parametrize('delta',[
    {'prompt':''},{'prompt':' \n\t '},{'prompt':None},{'prompt':True},{'prompt':123},
    {'prompt':'x'*4001},{'prompt':'\ud800'},{'prompt':'x\x00y'},
    {'agent_key':'other'},{'client_send_id':'wrong'},{'client_send_id':None},
    {'conversation_id':'wrong'},{'execution_mode':'real'},{'model':'other'},
    {'owner_user_id':str(uuid4())},{'role':'PADMIN'},{'api_key':'synthetic-key-marker'}])
def test_strict_run_request_rejected_without_storage(client,login,ops_rows,delta):
    f=ops_rows;csrf=login(client,'A-U1')['csrf_token']
    # ensure_ascii allows even an invalid surrogate to reach server validation as JSON data.
    body={'client_send_id':str(uuid4()),'conversation_id':None,'agent_key':'general','prompt':'합성 질문',**delta}
    reply=client.post('/api/v1/runs',headers={**headers(f,csrf=csrf),'Content-Type':'application/json'},content=json.dumps(body,ensure_ascii=True))
    assert reply.status_code==422
    assert reply.json()['error']['code']=='REQUEST_INVALID'
    assert 'synthetic-key-marker' not in reply.text and 'owner_user_id' not in reply.text
    assert_empty(f)


@pytest.mark.parametrize('delta',[{'document_refs':[]},{'document_refs':None},
    {'document_refs':[{'document_id':str(uuid4()),'version_id':str(uuid4())}]}])
def test_general_document_refs_rejected_no_provider_or_storage(client,login,ops_rows,delta):
    f=ops_rows;csrf=login(client,'A-U1')['csrf_token'];reply=submit(client,f,csrf,**delta)
    assert reply.status_code==422 and reply.json()['error']['code']=='REQUEST_INVALID'
    assert_empty(f)


def test_payload_limit_before_json_parser_including_stream_without_length(client,login,ops_rows):
    f=ops_rows;csrf=login(client,'A-U1')['csrf_token'];h={**headers(f,csrf=csrf),'Content-Type':'application/json'}
    for content in [' '*32769,iter([b' '*16000,b' '*16000,b' '*1000])]:
        reply=client.post('/api/v1/runs',headers=h,content=content)
        assert reply.status_code==413 and reply.json()['error']['code']=='PAYLOAD_TOO_LARGE'
    assert_empty(f)


def test_input_codepoint_utf8_boundary_and_original_whitespace(client,login,ops_rows):
    f=ops_rows;csrf=login(client,'A-U1')['csrf_token'];prompt=' a'+'b'*3997+' '
    assert len(prompt)==4000
    send=str(uuid4());reply=submit(client,f,csrf,prompt=prompt,client_send_id=send);assert reply.status_code==202
    cid=reply.json()['data']['conversation_id']
    rows=client.get('/api/v1/conversations/'+cid+'/messages',headers=headers(f)).json()['data']['items']
    assert rows[0]['text']==prompt
    assert submit(client,f,csrf,prompt=prompt.strip(),client_send_id=send).status_code==409


def test_offline_mandatory_token_limit_rolls_back(client,login,ops_rows):
    f=ops_rows;csrf=login(client,'A-U1')['csrf_token']
    with f.db.admin_connection() as conn:conn.execute("UPDATE portal.agent_configs SET settings=settings||%s WHERE tenant_id=%s AND agent_key='general'",(Jsonb({'instructions':'🤖'*2000}),f.tenant_ids['A']))
    body={'client_send_id':str(uuid4()),'agent_key':'general','prompt':'🤖'*4000}
    reply=client.post('/api/v1/runs',headers={**headers(f,csrf=csrf),'Content-Type':'application/json'},content=json.dumps(body,ensure_ascii=False))
    assert reply.status_code==422 and reply.json()['error']['code']=='TOKEN_LIMIT_EXCEEDED'
    assert_empty(f)


def test_tokenizer_not_ready_is_safe_503(client,login,ops_rows):
    from app.ai.token_limits import TokenizerNotReady
    f=ops_rows;csrf=login(client,'A-U1')['csrf_token']
    with patch('app.conversations.repository.validate_general_input',side_effect=TokenizerNotReady('TOKENIZER_NOT_READY')):
        reply=submit(client,f,csrf)
    assert reply.status_code==503 and reply.json()['error']['code']=='SERVICE_UNAVAILABLE'
    assert_empty(f)


@pytest.mark.parametrize('gate,code',[('agent','AGENT_STOPPED'),('project','PLATFORM_STOPPED'),('tenant','PLATFORM_STOPPED'),
    ('latch','REVIEW_REQUIRED'),('local','QUOTA_EXCEEDED'),('project_cap','QUOTA_EXCEEDED'),('missing','STORAGE_UNAVAILABLE')])
def test_current_policy_gate_prevents_new_admission(client,login,ops_rows,gate,code):
    f=ops_rows;csrf=login(client,'A-U1')['csrf_token']
    with f.db.admin_connection() as conn:
        if gate=='agent':conn.execute("UPDATE portal.agent_configs SET enabled=false WHERE tenant_id=%s AND agent_key='general'",(f.tenant_ids['A'],))
        elif gate=='project':conn.execute("UPDATE ops.project_budget SET stopped=true WHERE mode='mock'")
        elif gate=='latch':conn.execute("UPDATE ops.project_budget SET stop_latch=true WHERE mode='mock'")
        elif gate=='project_cap':conn.execute("UPDATE ops.project_budget SET operational_cap_krw=0 WHERE mode='mock'")
        elif gate=='missing':conn.execute('DELETE FROM ops.tenant_budgets WHERE tenant_id=%s',(f.tenant_ids['A'],))
        else:conn.execute('UPDATE ops.tenant_budgets SET '+('stopped=true' if gate=='tenant' else 'local_cap_krw=0')+' WHERE tenant_id=%s',(f.tenant_ids['A'],))
    reply=submit(client,f,csrf);assert reply.status_code==(503 if gate=='missing' else 409)
    assert reply.json()['error']['code']==code;assert_empty(f)


def test_same_request_replays_after_agent_config_budget_and_global_stop(client,login,ops_rows):
    f=ops_rows;csrf=login(client,'A-U1')['csrf_token'];send=str(uuid4());first=submit(client,f,csrf,client_send_id=send).json()['data']
    with f.db.admin_connection() as conn:
        conn.execute("UPDATE portal.agent_configs SET enabled=false,config_version=2,settings=settings||%s WHERE tenant_id=%s AND agent_key='general'",(Jsonb({'instructions':'변경된 지침'}),f.tenant_ids['A']))
        conn.execute("UPDATE ops.project_budget SET stopped=true WHERE mode='mock'")
        conn.execute('UPDATE ops.tenant_budgets SET local_cap_krw=0 WHERE tenant_id=%s',(f.tenant_ids['A'],))
    replay=submit(client,f,csrf,client_send_id=send);assert replay.status_code==202
    assert replay.json()['data']['run_id']==first['run_id'] and replay.json()['data']['config_version']==1
    assert cancel_run(client,f,csrf,first['run_id']).status_code==200
    again=submit(client,f,csrf,client_send_id=send);assert again.status_code==200 and again.json()['data']['state']=='cancelled'
    with f.db.admin_connection() as conn:assert conn.execute('SELECT count(*) FROM portal.runs').fetchone()[0]==1


def test_conversation_agent_mismatch_no_admission(client,login,ops_rows):
    f=ops_rows;csrf=login(client,'A-U1')['csrf_token']
    reply=submit(client,f,csrf,conversation_id=str(f.conversation_ids['A:A-U1']),agent_key='rules_rag')
    assert reply.status_code==409 and reply.json()['error']['code']=='CONVERSATION_AGENT_MISMATCH';assert_empty(f)


def test_user_tenant_and_project_capacity_and_mode_separation(client,login,ops_rows):
    f=ops_rows;csrf=login(client,'A-U1')['csrf_token'];first=submit(client,f,csrf);assert first.status_code==202
    assert submit(client,f,csrf).json()['error']['code']=='EXECUTION_CAPACITY_EXCEEDED'
    csrf=login(client,'A-U2')['csrf_token'];assert submit(client,f,csrf).status_code==202
    csrf=login(client,'A-ADM')['csrf_token'];assert submit(client,f,csrf).status_code==429
    third=uuid4();f.tenant_ids['C']=third;mock_runs=[]
    with f.db.admin_connection() as conn:
        conn.execute("UPDATE portal.runs SET state='cancelled',stage='terminal',ended_at=clock_timestamp()")
        conn.execute("INSERT INTO security.tenants(tenant_id,fixture_label,display_name) VALUES(%s,'C','시험 전용 C')",(third,))
        conn.execute("INSERT INTO security.memberships(tenant_id,user_id,membership_id,role) VALUES(%s,%s,%s,'USER')",(third,f.actor_ids['A-ADM'],uuid4()))
        conn.execute("INSERT INTO portal.agent_configs(tenant_id,agent_key,enabled,updated_by,settings) VALUES(%s,'general',true,%s,%s)",(third,f.actor_ids['A-ADM'],Jsonb({'instructions':'합성 지침'})))
        conn.execute('UPDATE ops.tenant_budgets SET allocated_cap_krw=10000,local_cap_krw=10000')
        conn.execute('INSERT INTO ops.tenant_budgets(tenant_id,budget_id,allocated_cap_krw,local_cap_krw) SELECT %s,budget_id,5000,5000 FROM ops.project_budget',(third,))
        for mode in ['mock','real']:
            for actor,tenant in [('A-U1','A'),('A-U2','A'),('B-U1','B'),('DUAL','B')]:
                rid=uuid4()
                if mode=='mock':mock_runs.append(rid)
                conn.execute("INSERT INTO portal.runs(tenant_id,run_id,conversation_id,owner_user_id,client_send_id,request_hash,agent_key,config_snapshot,origin_session_id,execution_mode) VALUES(%s,%s,%s,%s,%s,%s,'general','{}',%s,%s)",
                    (f.tenant_ids[tenant],rid,f.conversation_ids[tenant+':'+actor],f.actor_ids[actor],uuid4(),bytes(32),f.state.session_ids[actor],mode))
    def new_c():
        return client.post('/api/v1/runs',headers=headers(f,'C',csrf),json={'client_send_id':str(uuid4()),'agent_key':'general','prompt':'합성 C 질문'})
    reply=new_c();assert reply.status_code==429 and reply.json()['error']['code']=='EXECUTION_CAPACITY_EXCEEDED'
    with f.db.admin_connection() as conn:conn.execute("UPDATE portal.runs SET state='cancelled',stage='terminal',ended_at=clock_timestamp() WHERE run_id=%s",(mock_runs[-1],))
    assert new_c().status_code==202  # Four real-mode runs do not occupy the mock project gate.


def test_dual_actor_user_capacity_spans_tenants_but_client_ids_scoped(client,login,ops_rows):
    f=ops_rows;csrf=login(client,'DUAL')['csrf_token'];send=str(uuid4());body={'client_send_id':send,'agent_key':'general','prompt':'조직별 합성 질문'}
    a=client.post('/api/v1/runs',headers=headers(f,'A',csrf),json=body);assert a.status_code==202
    b=client.post('/api/v1/runs',headers=headers(f,'B',csrf),json=body);assert b.status_code==429
    assert client.get('/api/v1/runs/by-send/'+send,headers=headers(f,'B')).status_code==404
    assert cancel_run(client,f,csrf,a.json()['data']['run_id']).status_code==200
    b=client.post('/api/v1/runs',headers=headers(f,'B',csrf),json=body);assert b.status_code==202
    assert b.json()['data']['run_id']!=a.json()['data']['run_id']


def test_successful_admission_window_ten_replay_and_relogin_no_reset(client,login,ops_rows):
    f=ops_rows;csrf=login(client,'A-U1')['csrf_token'];first_send=None
    for i in range(10):
        send=str(uuid4());reply=submit(client,f,csrf,client_send_id=send);assert reply.status_code==202
        assert cancel_run(client,f,csrf,reply.json()['data']['run_id']).status_code==200
        if i==0:first_send=send
    reply=submit(client,f,csrf);assert reply.status_code==429 and reply.json()['error']['code']=='RATE_LIMITED' and int(reply.headers['Retry-After'])>=1
    assert submit(client,f,csrf,client_send_id=first_send).status_code==200
    csrf=login(client,'A-U1')['csrf_token'];assert submit(client,f,csrf).status_code==429
    with f.db.admin_connection() as conn:
        conn.execute("UPDATE security.login_windows SET window_started_at=clock_timestamp()-interval '61 seconds' WHERE purpose='run_admission'")
    assert submit(client,f,csrf).status_code==202


@pytest.mark.parametrize('state,expected',[('running','cancel_requested'),('cancel_requested','cancel_requested'),('completed','completed'),('failed','failed'),('blocked','blocked'),('interrupted','interrupted'),('cancelled','cancelled')])
def test_cancel_preserves_terminal_and_pending_states(client,login,ops_rows,state,expected):
    f=ops_rows;csrf=login(client,'A-U1')['csrf_token'];data=submit(client,f,csrf).json()['data'];run=data['run_id']
    with f.db.admin_connection() as conn:
        terminal=state in ('completed','failed','blocked','interrupted','cancelled')
        conn.execute('UPDATE portal.runs SET state=%s,stage=%s,ended_at=CASE WHEN %s THEN clock_timestamp() ELSE NULL END,answer_kind=%s,cancel_requested_at=CASE WHEN %s THEN clock_timestamp() ELSE NULL END WHERE run_id=%s',
            (state,'terminal' if terminal else 'generation',terminal,'answer' if state=='completed' else None,state=='cancel_requested',UUID(run)))
    reply=cancel_run(client,f,csrf,run);assert reply.status_code==(200 if terminal else 202)
    assert reply.json()['data']['state']==expected
    again=cancel_run(client,f,csrf,run);assert again.json()['data']['revision']==reply.json()['data']['revision']


def test_cancel_revision_conflict_and_simultaneous_single_audit(client,login,ops_rows):
    f=ops_rows;csrf=login(client,'A-U1')['csrf_token'];run=submit(client,f,csrf).json()['data']['run_id']
    assert cancel_run(client,f,csrf,run,2).status_code==409
    with ThreadPoolExecutor(max_workers=2) as ex:replies=list(ex.map(lambda _:cancel_run(client,f,csrf,run),range(2)))
    assert [r.status_code for r in replies]==[200,200]
    assert {r.json()['data']['revision'] for r in replies}=={2}
    with f.db.admin_connection() as conn:assert conn.execute("SELECT count(*) FROM ops.audit_events WHERE action='run_cancelled'").fetchone()[0]==1


def test_accepted_with_existing_call_requires_review_and_preserves_cost(client,login,ops_rows):
    from app.ai.pricing import PRICE
    f=ops_rows;csrf=login(client,'A-U1')['csrf_token'];run=submit(client,f,csrf).json()['data']['run_id']
    with f.db.admin_connection() as conn:
        bid=conn.execute("SELECT budget_id FROM ops.project_budget WHERE mode='mock'").fetchone()[0]
        conn.execute("INSERT INTO ops.call_attempts(tenant_id,call_id,run_id,initiator_user_id,operation,budget_id,mode,agent_key,config_revision,step_key,input_fingerprint,permit_revision,permit_expires_at,reserved_krw,price_snapshot) VALUES(%s,%s,%s,%s,'generate_general',%s,'mock','general',1,'generation',%s,1,clock_timestamp()+interval '10 seconds',3.64,%s)",
            (f.tenant_ids['A'],uuid4(),UUID(run),f.actor_ids['A-U1'],bid,bytes(32),Jsonb(PRICE.as_dict())))
        conn.execute('UPDATE ops.tenant_budgets SET reserved_krw=3.64 WHERE tenant_id=%s AND budget_id=%s',(f.tenant_ids['A'],bid))
        conn.execute('UPDATE ops.project_budget SET reserved_krw=3.64 WHERE budget_id=%s',(bid,))
    reply=cancel_run(client,f,csrf,run);assert reply.status_code==409 and reply.json()['error']['code']=='REVIEW_REQUIRED'
    view=client.get('/api/v1/runs/'+run,headers=headers(f)).json()['data'];assert view['state']=='accepted' and view['usage_status']=='estimated'
    with f.db.admin_connection() as conn:assert conn.execute('SELECT reserved_krw FROM ops.tenant_budgets WHERE tenant_id=%s AND budget_id=%s',(f.tenant_ids['A'],bid)).fetchone()[0]==Decimal('3.64')


def test_audit_failure_rolls_back_admission_conversation_window_and_idle(client,login,ops_rows):
    f=ops_rows;csrf=login(client,'A-U1')['csrf_token']
    with f.db.admin_connection() as conn:
        before=conn.execute('SELECT count(*) FROM portal.conversations').fetchone()[0]
        idle=conn.execute('SELECT last_activity_at FROM security.sessions WHERE user_id=%s ORDER BY issued_at DESC LIMIT 1',(f.actor_ids['A-U1'],)).fetchone()[0]
        conn.execute("ALTER TABLE ops.audit_events ADD CONSTRAINT fail_run_audit CHECK(action NOT IN ('run_admitted','conversation_created')) NOT VALID")
    assert submit(client,f,csrf).status_code==503
    assert client.post('/api/v1/conversations',headers=headers(f,csrf=csrf),json={'agent_key':'general'}).status_code==503
    assert_empty(f)
    with f.db.admin_connection() as conn:
        assert conn.execute('SELECT count(*) FROM portal.conversations').fetchone()[0]==before
        assert conn.execute("SELECT count(*) FROM security.login_windows WHERE purpose='run_admission'").fetchone()[0]==0
        assert conn.execute('SELECT last_activity_at FROM security.sessions WHERE user_id=%s ORDER BY issued_at DESC LIMIT 1',(f.actor_ids['A-U1'],)).fetchone()[0]==idle


def test_cancel_audit_failure_rolls_back_state_revision(client,login,ops_rows):
    f=ops_rows;csrf=login(client,'A-U1')['csrf_token'];run=submit(client,f,csrf).json()['data']['run_id']
    with f.db.admin_connection() as conn:conn.execute("ALTER TABLE ops.audit_events ADD CONSTRAINT fail_cancel_audit CHECK(action NOT IN ('run_cancelled','run_cancel_requested')) NOT VALID")
    assert cancel_run(client,f,csrf,run).status_code==503
    data=client.get('/api/v1/runs/'+run,headers=headers(f)).json()['data'];assert data['state']=='accepted' and data['revision']==1


def test_owner_read_window_is_shared_and_get_does_not_touch_idle(client,login,ops_rows):
    f=ops_rows;csrf=login(client,'A-U1')['csrf_token'];send=str(uuid4());data=submit(client,f,csrf,client_send_id=send).json()['data']
    with f.db.admin_connection() as conn:idle=conn.execute('SELECT last_activity_at FROM security.sessions WHERE user_id=%s ORDER BY issued_at DESC LIMIT 1',(f.actor_ids['A-U1'],)).fetchone()[0]
    paths=['/agents','/conversations','/runs/'+data['run_id'],'/runs/by-send/'+send,'/conversations/'+data['conversation_id']+'/messages']
    for i in range(120):assert client.get('/api/v1'+paths[i%5],headers=headers(f)).status_code==200
    assert client.get('/api/v1/runs/'+data['run_id'],headers=headers(f)).status_code==429
    with f.db.admin_connection() as conn:assert conn.execute('SELECT last_activity_at FROM security.sessions WHERE user_id=%s ORDER BY issued_at DESC LIMIT 1',(f.actor_ids['A-U1'],)).fetchone()[0]==idle


@pytest.mark.parametrize('mutation',['account','tenant','membership','revision','revoked','expired','idle'])
def test_repository_rechecks_current_authority_before_mutation(db_fixture,ops_rows,mutation):
    f=ops_rows
    async def check():
        ctx=await f.context('A-U1','A');f.mutate_access(ctx,mutation)
        with pytest.raises(AppError):await ConversationRepository(f.pool).create(ctx,'general',uuid4(),uuid4())
    f.run(check());assert_empty(f)


def test_csrf_query_and_revision_inputs_are_strict(client,login,ops_rows):
    f=ops_rows;csrf=login(client,'A-U1')['csrf_token'];run=submit(client,f,csrf).json()['data']['run_id']
    assert client.post('/api/v1/runs/'+run+'/cancel',headers=headers(f),json={'expected_revision':1}).status_code==403
    for revision in [True,0,'1',None]:assert cancel_run(client,f,csrf,run,revision).status_code==422
    assert client.get('/api/v1/conversations?limit=1&limit=2',headers=headers(f)).status_code==422
    assert client.get('/api/v1/runs/'+run+'?mode=real',headers=headers(f)).status_code==422
    assert client.get('/api/v1/conversations?limit=51',headers=headers(f)).status_code==422


def test_pagination_signatures_context_binding_and_empty_private_fields(client,login,ops_rows):
    f=ops_rows;csrf=login(client,'A-U1')['csrf_token']
    for _ in range(3):assert client.post('/api/v1/conversations',headers=headers(f,csrf=csrf),json={'agent_key':'general'}).status_code==201
    first=client.get('/api/v1/conversations?limit=1',headers=headers(f)).json()['data'];cursor=first['next_cursor'];assert cursor
    second=client.get('/api/v1/conversations?limit=1&cursor='+cursor,headers=headers(f));assert second.status_code==200
    assert second.json()['data']['items'][0]['conversation_id']!=first['items'][0]['conversation_id']
    assert client.get('/api/v1/conversations?cursor='+cursor+'x',headers=headers(f)).status_code==422
    target=str(f.conversation_ids['A:A-U1'])
    assert client.get('/api/v1/conversations/'+target+'/messages?cursor='+cursor,headers=headers(f)).status_code==422
    login(client,'A-U2');assert client.get('/api/v1/conversations?cursor='+cursor,headers=headers(f)).status_code==422
    assert all(k not in second.text for k in ['config_snapshot','instructions','request_hash','owner_user_id','prompt'])


def test_message_pages_hidden_drafts_and_purged_sequence_no_collision(client,login,ops_rows):
    f=ops_rows;csrf=login(client,'A-U1')['csrf_token'];cid=str(f.conversation_ids['A:A-U1'])
    for i in range(3):
        data=submit(client,f,csrf,conversation_id=cid,prompt='합성 질문 '+str(i)).json()['data']
        assert cancel_run(client,f,csrf,data['run_id']).status_code==200
    with f.db.admin_connection() as conn:conn.execute('UPDATE portal.messages SET body=NULL,payload_purged=true WHERE conversation_id=%s AND sequence_no=3',(UUID(cid),))
    data=submit(client,f,csrf,conversation_id=cid).json()['data'];assert data['state']=='accepted'
    first=client.get('/api/v1/conversations/'+cid+'/messages?limit=1',headers=headers(f)).json()['data'];assert first['items'][0]['sequence_no']==1
    more=client.get('/api/v1/conversations/'+cid+'/messages?limit=1&cursor='+first['next_cursor'],headers=headers(f)).json()['data'];assert more['items'][0]['sequence_no']==2
    more=client.get('/api/v1/conversations/'+cid+'/messages?limit=1&cursor='+more['next_cursor'],headers=headers(f)).json()['data'];assert more['items'][0]['sequence_no']==4 and more['next_cursor'] is None


def test_actual_last_six_history_selected_and_snapshot_private(client,login,ops_rows):
    f=ops_rows;csrf=login(client,'A-U1')['csrf_token'];cid=f.conversation_ids['A:A-U1'];ids=[]
    with f.db.admin_connection() as conn:
        rid=uuid4();conn.execute("INSERT INTO portal.runs(tenant_id,run_id,conversation_id,owner_user_id,client_send_id,request_hash,agent_key,config_snapshot,origin_session_id,execution_mode,state,stage,answer_kind,ended_at) VALUES(%s,%s,%s,%s,%s,%s,'general','{}',%s,'mock','completed','terminal','answer',clock_timestamp())",
            (f.tenant_ids['A'],rid,cid,f.actor_ids['A-U1'],uuid4(),bytes(32),f.state.session_ids['A-U1']))
        for i in range(8):
            mid=uuid4();ids.append(str(mid));role='user' if i%2==0 else 'assistant'
            conn.execute('INSERT INTO portal.messages(tenant_id,message_id,conversation_id,owner_user_id,agent_key,sequence_no,role,body,run_id,payload_kind) VALUES(%s,%s,%s,%s,\'general\',%s,%s,%s,%s,%s)',
                (f.tenant_ids['A'],mid,cid,f.actor_ids['A-U1'],i+1,role,'합성 이력 '+str(i),rid,'user' if role=='user' else 'general_assistant'))
    data=submit(client,f,csrf,conversation_id=str(cid)).json()['data'];run=UUID(data['run_id'])
    with f.db.admin_connection() as conn:
        snapshot=conn.execute('SELECT config_snapshot FROM portal.runs WHERE run_id=%s',(run,)).fetchone()[0]
        assert snapshot['selected_history_ids']==ids[-6:] and 0<snapshot['estimated_input_tokens']<=6000
    reply=client.get('/api/v1/runs/'+str(run),headers=headers(f));assert 'private-instruction-marker' not in reply.text and 'selected_history_ids' not in reply.text


def test_fixed_functions_nonowner_roles_and_pool_scope_cleanup(db_fixture,ops_rows):
    f=ops_rows
    for role in ['ai_index','ai_meter']:
        with f.role_connection(role) as conn:
            with pytest.raises(psycopg.errors.InsufficientPrivilege):conn.execute("SELECT security.run_read(%s,%s,'conversations',NULL,NULL,20)",(f.state.session_ids['A-U1'],f.tenant_ids['A']))
    async def check():
        ctx=await f.context('A-U1','A');await ConversationRepository(f.pool).create(ctx,'general',uuid4(),uuid4())
        async with f.pool.connection() as conn:
            assert (await (await conn.execute("SELECT NULLIF(current_setting('app.run_scope',true),'') AS scope")).fetchone())['scope'] is None
            for query in ['SELECT config_snapshot FROM portal.runs','SELECT request_hash FROM portal.runs','UPDATE portal.runs SET state=state','INSERT INTO portal.messages DEFAULT VALUES','SELECT security.run_view(NULL,NULL)']:
                with pytest.raises(psycopg.errors.InsufficientPrivilege):await conn.execute(query)
    f.run(check());f.verify_catalog()


from test_auth_restart import running_server


def test_seven_api_routes_real_http_restart_no_provider(running_server,ops_rows):
    import httpx
    from test_auth_restart import record
    live=running_server;f=ops_rows;started=time.monotonic();send=str(uuid4())
    with httpx.Client(base_url='http://127.0.0.1:8000',timeout=12,trust_env=False) as client:
        csrf=live.login(client,'A-U1');h=headers(f,csrf=csrf)
        conversation=client.post('/api/v1/conversations',headers=h,json={'agent_key':'general'});assert conversation.status_code==201
        cid=conversation.json()['data']['conversation_id']
        assert client.get('/api/v1/conversations',headers=headers(f)).status_code==200
        body={'client_send_id':send,'conversation_id':cid,'agent_key':'general','prompt':'네트워크 합성 질문'}
        reply=client.post('/api/v1/runs',headers=h,json=body);assert reply.status_code==202;run=reply.json()['data']['run_id']
        assert client.get('/api/v1/conversations/'+cid+'/messages',headers=headers(f)).json()['data']['items'][0]['text']=='네트워크 합성 질문'
        assert client.get('/api/v1/runs/by-send/'+send,headers=headers(f)).json()['data']['run_id']==run
        live.restart()
        assert client.get('/api/v1/runs/'+run,headers=headers(f)).json()['data']['state']=='accepted'
        assert client.post('/api/v1/runs',headers=h,json=body).json()['data']['run_id']==run
        assert client.post('/api/v1/runs/'+run+'/cancel',headers=h,json={'expected_revision':1}).json()['data']['state']=='cancelled'
        live.restart()
        canonical=client.get('/api/v1/runs/'+run,headers=headers(f)).json()['data'];assert canonical['state']=='cancelled' and canonical['revision']==2
        assert canonical['result'] is None and canonical['usage_status']=='none'
    record('B03-live-conversations',started,{'native_api_routes_checked':7,'restart_preserved_accepted':True,'restart_preserved_cancelled_revision':2,'provider_calls':0})


def test_same_actor_concurrent_new_ids_only_one_admitted(client,login,ops_rows):
    f=ops_rows;csrf=login(client,'A-U1')['csrf_token']
    with ThreadPoolExecutor(max_workers=2) as ex:replies=list(ex.map(lambda _:submit(client,f,csrf),range(2)))
    assert sorted(r.status_code for r in replies)==[202,429]
    with f.db.admin_connection() as conn:
        assert conn.execute('SELECT count(*) FROM portal.runs').fetchone()[0]==1
        assert conn.execute('SELECT count(*) FROM portal.messages').fetchone()[0]==1
        assert conn.execute("SELECT count FROM security.login_windows WHERE purpose='run_admission'").fetchone()[0]==1


def test_missing_optional_settings_snapshot_keeps_server_default(client,login,ops_rows):
    f=ops_rows;csrf=login(client,'A-U1')['csrf_token']
    with f.db.admin_connection() as conn:conn.execute("UPDATE portal.agent_configs SET settings='{}' WHERE tenant_id=%s AND agent_key='general'",(f.tenant_ids['A'],))
    reply=submit(client,f,csrf);assert reply.status_code==202
    with f.db.admin_connection() as conn:
        snapshot=conn.execute('SELECT config_snapshot FROM portal.runs WHERE run_id=%s',(UUID(reply.json()['data']['run_id']),)).fetchone()[0]
        assert snapshot['instructions']=='사용자 질문에 간결하고 정확하게 답변하세요.'
        assert snapshot['generation_model']=='gpt-4o-mini'


def test_admission_lock_timeout_has_no_partial_storage(client,login,ops_rows):
    f=ops_rows;csrf=login(client,'A-U1')['csrf_token']
    with ThreadPoolExecutor(max_workers=1) as ex:
        with f.db.admin_connection() as conn:
            with conn.transaction():
                conn.execute("SELECT budget_id FROM ops.project_budget WHERE mode='mock' FOR UPDATE")
                reply=ex.submit(submit,client,f,csrf).result(timeout=4)
                assert reply.status_code==503 and reply.json()['error']['retryable']
    assert_empty(f)
    assert submit(client,f,csrf).status_code==202


def test_waiting_admission_observes_membership_revocation_commit(client,login,ops_rows):
    f=ops_rows;csrf=login(client,'A-U1')['csrf_token']
    with ThreadPoolExecutor(max_workers=1) as ex:
        with f.db.admin_connection() as conn:
            with conn.transaction():
                conn.execute('UPDATE security.memberships SET active=false WHERE tenant_id=%s AND user_id=%s',(f.tenant_ids['A'],f.actor_ids['A-U1']))
                future=ex.submit(submit,client,f,csrf)
                deadline=time.monotonic()+1.5;waiting=False
                while time.monotonic()<deadline:
                    with f.db.admin_connection() as observe:
                        waiting=observe.execute("SELECT EXISTS(SELECT 1 FROM pg_stat_activity WHERE datname=%s AND usename='ai_web' AND wait_event_type='Lock' AND query LIKE 'SELECT security.run_prepare%%')",(f.db.name,)).fetchone()[0]
                    if waiting:break
                    time.sleep(.01)
                assert waiting
        assert future.result(timeout=4).status_code in (401,403)
    assert_empty(f)


def test_rollback_context_and_next_tenant_reuse_on_same_connection(db_fixture,ops_rows):
    f=ops_rows
    with f.db.admin_connection() as conn:conn.execute("ALTER TABLE ops.audit_events ADD CONSTRAINT fail_conversation CHECK(action<>'conversation_created') NOT VALID")
    async def check():
        ctx=await f.context('A-U1','A');repo=ConversationRepository(f.pool)
        with pytest.raises(psycopg.errors.CheckViolation):await repo.create(ctx,'general',uuid4(),uuid4())
        async with f.pool.connection() as conn:
            assert (await (await conn.execute("SELECT NULLIF(current_setting('app.run_scope',true),'') AS scope")).fetchone())['scope'] is None
        with f.db.admin_connection() as conn:conn.execute('ALTER TABLE ops.audit_events DROP CONSTRAINT fail_conversation')
        ctx=await f.context('B-U1','B');data=await repo.create(ctx,'general',uuid4(),uuid4())
        assert data['tenant_id']==str(f.tenant_ids['B'])
        async with tenant_transaction(f.pool,ctx) as conn:
            rows=await (await conn.execute('SELECT tenant_id,owner_user_id FROM portal.conversations')).fetchall()
            assert rows and all(x['tenant_id']==ctx.tenant_id and x['owner_user_id']==ctx.user_id for x in rows)
    f.run(check())


def test_released_without_dispatch_has_no_confirmed_usage(client,login,ops_rows):
    from app.ai.pricing import PRICE
    f=ops_rows;csrf=login(client,'A-U1')['csrf_token'];run=UUID(submit(client,f,csrf).json()['data']['run_id'])
    with f.db.admin_connection() as conn:
        bid=conn.execute("SELECT budget_id FROM ops.project_budget WHERE mode='mock'").fetchone()[0]
        conn.execute("INSERT INTO ops.call_attempts(tenant_id,call_id,run_id,initiator_user_id,operation,budget_id,mode,agent_key,config_revision,step_key,input_fingerprint,permit_revision,permit_expires_at,reserved_krw,price_snapshot,state,slot_held) VALUES(%s,%s,%s,%s,'generate_general',%s,'mock','general',1,'generation',%s,1,clock_timestamp()+interval '10 seconds',3.64,%s,'released_no_dispatch',false)",
            (f.tenant_ids['A'],uuid4(),run,f.actor_ids['A-U1'],bid,bytes(32),Jsonb(PRICE.as_dict())))
    data=client.get('/api/v1/runs/'+str(run),headers=headers(f)).json()['data']
    assert data['usage_status']=='none' and data['result'] is None
