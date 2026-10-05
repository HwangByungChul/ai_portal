from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal
import asyncio
import time
from uuid import uuid4,UUID
import psycopg
from psycopg.types.json import Jsonb
import pytest
from app.ai.pricing import PRICE
from app.db import open_web_pool,tenant_transaction


@pytest.fixture
def ops_rows(db_fixture):
    f=db_fixture
    with f.db.admin_connection() as conn:
        for tenant in ['A','B']:
            for bid, in conn.execute('SELECT budget_id FROM ops.project_budget').fetchall():
                conn.execute('INSERT INTO ops.tenant_budgets(tenant_id,budget_id,allocated_cap_krw,local_cap_krw) VALUES(%s,%s,12500,12500)',(f.tenant_ids[tenant],bid))
            conn.execute('UPDATE portal.agent_configs SET settings=%s,enabled=true WHERE tenant_id=%s',
                (Jsonb({'name':'공통 Agent','description':'합성 설명','instructions':'private-instruction-marker'}),f.tenant_ids[tenant]))
    return f


def headers(f,tenant='A',csrf=None):
    h={'X-Tenant-ID':str(f.tenant_ids[tenant])}
    if csrf:h.update({'Origin':'http://127.0.0.1:5173','X-Requested-With':'ai-portal','X-CSRF-Token':csrf})
    return h


def change_agent(client,f,csrf,revision=1,tenant='A',agent='general',**kwargs):
    return client.patch('/api/v1/admin/agents/'+agent,headers=headers(f,tenant,csrf),
        json={'expected_revision':revision,**(kwargs or {'name':'변경 Agent','description':'새 설명','instructions':'새 지침'})})


def stored_agent(f,tenant='A',agent='general'):
    with f.db.admin_connection() as conn:
        return conn.execute('SELECT enabled,config_version,settings FROM portal.agent_configs WHERE tenant_id=%s AND agent_key=%s',(f.tenant_ids[tenant],agent)).fetchone()


def stored_budget(f,tenant='A',mode='mock'):
    with f.db.admin_connection() as conn:
        return conn.execute('SELECT t.allocated_cap_krw,t.local_cap_krw,t.accounted_krw,t.reserved_krw,t.revision FROM ops.tenant_budgets t JOIN ops.project_budget p USING(budget_id) WHERE tenant_id=%s AND p.mode=%s',(f.tenant_ids[tenant],mode)).fetchone()


@pytest.mark.parametrize('path',['/admin/agents/general','/admin/usage','/admin/budget'])
@pytest.mark.parametrize('actor,tenant,status',[('A-U1','A',403),('A-ADM','A',200),('P-A','A',200),('DUAL-ADM','B',200),('P_READ_ONLY','A',403),('P-A','B',403)])
def test_admin_scope_read(client,login,ops_rows,path,actor,tenant,status):
    login(client,actor)
    reply=client.get('/api/v1'+path,headers=headers(ops_rows,tenant))
    assert reply.status_code==status
    assert reply.headers['cache-control']=='no-store'
    if status==200:assert reply.json()['meta']['tenant_id']==str(ops_rows.tenant_ids[tenant])


@pytest.mark.parametrize('actor,read,write',[('A-U1',403,403),('A-ADM',403,403),('P-A',200,200),('P_READ_ONLY',200,403),('P_WRITE_ONLY',403,200),('P_NONE',403,403)])
def test_independent_global_capabilities(client,login,ops_rows,actor,read,write):
    csrf=login(client,actor)['csrf_token']
    reply=client.get('/api/v1/platform/summary')
    assert reply.status_code==read and reply.json()['meta']['tenant_id'] is None
    reply=client.put('/api/v1/platform/availability',headers={k:v for k,v in headers(ops_rows,csrf=csrf).items() if k!='X-Tenant-ID'},json={'enabled':False,'expected_revision':1})
    assert reply.status_code==write


def test_agent_public_no_instructions_and_pipeline_not_ready(client,login,ops_rows):
    login(client,'A-U1')
    reply=client.get('/api/v1/agents',headers=headers(ops_rows));assert reply.status_code==200
    rows=reply.json()['data']['items'];assert {x['agent_key'] for x in rows}=={'general','rules_rag'}
    assert all(not x['available'] and x['safe_block_reason']=='FEATURE_NOT_READY' for x in rows)
    assert 'instructions' not in reply.text and 'private-instruction-marker' not in reply.text
    assert 'model' not in reply.text and 'settings' not in reply.text


def test_agent_changes_cas_audit_and_idle(client,login,ops_rows):
    f=ops_rows;csrf=login(client,'A-ADM')['csrf_token']
    assert change_agent(client,f,csrf).status_code==200
    enabled,revision,settings=stored_agent(f);assert enabled and revision==2 and settings['name']=='변경 Agent'
    assert change_agent(client,f,csrf).status_code==409
    reply=client.put('/api/v1/admin/agents/general/availability',headers=headers(f,csrf=csrf),json={'enabled':False,'expected_revision':2});assert reply.status_code==200
    assert stored_agent(f)[:2]==(False,3)
    with f.db.admin_connection() as conn:
        assert conn.execute("SELECT count(*) FROM ops.audit_events WHERE action LIKE 'operations_agent%%'").fetchone()[0]==2
    assert stored_agent(f,'B')[1]==1


@pytest.mark.parametrize('kwargs',[{'model':'costly'},{'key':'never-log-marker'},{'tool':'tool'},{'url':'https://example.invalid'},
    {'role':'PADMIN'},{'name':''},{'name':' '*3},{'name':'n'*81},{'description':'d'*501},{'instructions':'i'*2001},
    {'instructions':None},{'expected_revision':True},{'expected_revision':'1'},{'name':13}])
def test_agent_strict_input_safe_errors(client,login,ops_rows,kwargs):
    csrf=login(client,'A-ADM')['csrf_token']
    body={'name':'ok','description':'ok','instructions':'ok','expected_revision':1};body.update(kwargs)
    reply=client.patch('/api/v1/admin/agents/general',headers=headers(ops_rows,csrf=csrf),json=body)
    assert reply.status_code==422 and 'never-log-marker' not in reply.text and 'costly' not in reply.text
    assert stored_agent(ops_rows)[1]==1


@pytest.mark.parametrize('body',[{'enabled':'false','expected_revision':1},{'enabled':0,'expected_revision':1},{'enabled':False,'expected_revision':1,'mode':'real'}])
def test_availability_strict_input(client,login,ops_rows,body):
    csrf=login(client,'A-ADM')['csrf_token']
    assert client.put('/api/v1/admin/agents/general/availability',headers=headers(ops_rows,csrf=csrf),json=body).status_code==422


def test_csrf_and_forged_authority_denied(client,login,ops_rows):
    csrf=login(client,'A-U1')['csrf_token']
    h=headers(ops_rows,csrf=csrf);h.update({'X-Role':'PADMIN','X-User-ID':str(ops_rows.actor_ids['P-A'])})
    assert client.patch('/api/v1/admin/agents/general',headers=h,json={'name':'forged','expected_revision':1}).status_code==403
    login(client,'A-ADM')
    assert client.put('/api/v1/admin/budget',headers=headers(ops_rows),json={'local_cap_krw':'100','expected_revision':1}).status_code==403


@pytest.mark.parametrize('amount',[-1,True,123,'-1','NaN','Infinity','1e3','1.234','25001',' 100','+1'])
def test_money_strict_decimal_string(client,login,ops_rows,amount):
    csrf=login(client,'A-ADM')['csrf_token']
    reply=client.put('/api/v1/admin/budget',headers=headers(ops_rows,csrf=csrf),json={'local_cap_krw':amount,'expected_revision':1})
    assert reply.status_code==422 and stored_budget(ops_rows)[1]==Decimal('12500')


def test_local_reduction_preserves_committed_cost_and_mode(client,login,ops_rows):
    f=ops_rows
    with f.db.admin_connection() as conn:
        conn.execute("UPDATE ops.tenant_budgets t SET accounted_krw=20,reserved_krw=3.64 FROM ops.project_budget p WHERE t.budget_id=p.budget_id AND t.tenant_id=%s AND p.mode='mock'",(f.tenant_ids['A'],))
    csrf=login(client,'A-ADM')['csrf_token']
    reply=client.put('/api/v1/admin/budget',headers=headers(f,csrf=csrf),json={'local_cap_krw':'10.00','expected_revision':1});assert reply.status_code==200
    data=reply.json()['data'];assert data['blocked'] and data['safe_block_reason']=='QUOTA_EXCEEDED'
    assert stored_budget(f)==(Decimal('12500'),Decimal('10'),Decimal('20'),Decimal('3.64'),2)
    assert stored_budget(f,mode='real')[:4]==(Decimal('12500'),Decimal('12500'),Decimal(0),Decimal(0))
    assert client.put('/api/v1/admin/budget',headers=headers(f,csrf=csrf),json={'local_cap_krw':'12501','expected_revision':2}).status_code==409


def test_allocation_scope_total_and_clamp(client,login,ops_rows):
    f=ops_rows;csrf=login(client,'P-A')['csrf_token']
    path='/api/v1/platform/tenant-budgets/'+str(f.tenant_ids['A'])
    assert client.put(path,headers=headers(f,csrf=csrf),json={'allocated_cap_krw':'13000','expected_revision':1}).status_code==409
    reply=client.put(path,headers=headers(f,csrf=csrf),json={'allocated_cap_krw':'12000','expected_revision':1});assert reply.status_code==200
    assert stored_budget(f)[:2]==(Decimal('12000'),Decimal('12000'))
    assert client.put('/api/v1/platform/tenant-budgets/'+str(f.tenant_ids['B']),headers=headers(f,csrf=csrf),json={'allocated_cap_krw':'12000','expected_revision':1}).status_code==422
    assert client.put('/api/v1/platform/tenant-budgets/'+str(f.tenant_ids['B']),headers=headers(f,'B',csrf),json={'allocated_cap_krw':'12000','expected_revision':1}).status_code==403
    csrf=login(client,'A-ADM')['csrf_token']
    assert client.put(path,headers=headers(f,csrf=csrf),json={'allocated_cap_krw':'10000','expected_revision':2}).status_code==403


def test_zero_usage_is_actual_empty_db_and_no_body(client,login,ops_rows):
    login(client,'A-U1');reply=client.get('/api/v1/usage/me',headers=headers(ops_rows));assert reply.status_code==200
    data=reply.json()['data'];assert data['call_count']==0 and data['items']==[] and data['unknown_count']==0
    assert Decimal(data['estimated_accounted_krw'])==0 and Decimal(data['reserved_krw'])==0
    for text in ['private-instruction-marker','body','conversation_id','config_snapshot','allocated_cap_krw','tenant_remaining_krw']:
        assert text not in reply.text
    login(client,'A-ADM');reply=client.get('/api/v1/admin/usage',headers=headers(ops_rows));assert reply.status_code==200 and reply.json()['data']['items']==[]


@pytest.mark.parametrize('mutation',['account','tenant','membership','revision','revoked','expired','idle','demote','managed','global'])
def test_current_authority_recomputed(client,login,ops_rows,mutation):
    f=ops_rows;csrf=login(client,'P-A')['csrf_token']
    with f.db.admin_connection() as conn:
        sid=conn.execute('SELECT session_id FROM security.sessions WHERE user_id=%s AND revoked_at IS NULL ORDER BY issued_at DESC LIMIT 1',(f.actor_ids['P-A'],)).fetchone()[0]
    if mutation in ['demote','managed','global']:
        with f.db.admin_connection() as conn:
            if mutation=='managed':conn.execute('UPDATE security.managed_tenants SET active=false WHERE user_id=%s',(f.actor_ids['P-A'],))
            elif mutation=='global':conn.execute('UPDATE security.platform_access SET active=false WHERE user_id=%s',(f.actor_ids['P-A'],))
            else:conn.execute('UPDATE security.platform_access SET is_padmin=false WHERE user_id=%s',(f.actor_ids['P-A'],))
    else:
        from app.types import AuthContext
        f.mutate_access(AuthContext(sid,f.actor_ids['P-A'],f.tenant_ids['A'],'PADMIN',''),mutation)
    reply=change_agent(client,f,csrf)
    assert reply.status_code in [401,403] and stored_agent(f)[1]==1


def test_audit_failure_rolls_back_setting_budget_and_session(client,login,ops_rows):
    f=ops_rows;csrf=login(client,'P-A')['csrf_token']
    with f.db.admin_connection() as conn:
        before=conn.execute('SELECT last_activity_at FROM security.sessions WHERE user_id=%s ORDER BY issued_at DESC LIMIT 1',(f.actor_ids['P-A'],)).fetchone()[0]
        conn.execute("ALTER TABLE ops.audit_events ADD CONSTRAINT fail_operations CHECK(action NOT LIKE 'operations_%') NOT VALID")
    assert change_agent(client,f,csrf).status_code==503
    assert client.put('/api/v1/admin/budget',headers=headers(f,csrf=csrf),json={'local_cap_krw':'10000','expected_revision':1}).status_code==503
    assert client.put('/api/v1/platform/availability',headers=headers(f,csrf=csrf),json={'enabled':False,'expected_revision':1}).status_code==503
    assert stored_agent(f)[1]==1 and stored_budget(f)[4]==1
    with f.db.admin_connection() as conn:
        assert conn.execute("SELECT stopped,revision FROM ops.project_budget WHERE mode='mock'").fetchone()==(False,1)
        assert conn.execute('SELECT last_activity_at FROM security.sessions WHERE user_id=%s ORDER BY issued_at DESC LIMIT 1',(f.actor_ids['P-A'],)).fetchone()[0]==before


def test_agent_unknown_and_duplicate_query_denied(client,login,ops_rows):
    login(client,'A-ADM')
    assert client.get('/api/v1/admin/agents/other',headers=headers(ops_rows)).status_code==404
    assert client.get('/api/v1/admin/usage?limit=1&limit=2',headers=headers(ops_rows)).status_code==422
    assert client.get('/api/v1/usage/me?mode=real',headers=headers(ops_rows)).status_code==422
    assert client.get('/api/v1/admin/usage?limit=51',headers=headers(ops_rows)).status_code==422


@pytest.fixture
def usage_rows(ops_rows):
    f=ops_rows;calls={}
    with f.db.admin_connection() as conn:
        budget=conn.execute("SELECT budget_id FROM ops.project_budget WHERE mode='mock'").fetchone()[0]
        for actor,tenant,state in [('A-U1','A','usage_unknown'),('A-U2','A','settled'),('B-U1','B','usage_unknown')]:
            run=uuid4();call=uuid4();calls[actor]=call
            conn.execute('INSERT INTO portal.runs(tenant_id,run_id,conversation_id,owner_user_id,client_send_id,request_hash,agent_key,config_snapshot,origin_session_id,execution_mode) '
                "VALUES(%s,%s,%s,%s,%s,%s,'general','{}',%s,'mock')",
                (f.tenant_ids[tenant],run,f.conversation_ids[tenant+':'+actor],f.actor_ids[actor],uuid4(),bytes(32),f.state.session_ids[actor]))
            conn.execute('INSERT INTO ops.call_attempts(tenant_id,call_id,run_id,initiator_user_id,operation,budget_id,mode,agent_key,config_revision,step_key,input_fingerprint,permit_revision,permit_expires_at,reserved_krw,price_snapshot,state,dispatched_at,dispatch_claim_hash,provider_end_status,slot_held) '
                "VALUES(%s,%s,%s,%s,'generate_general',%s,'mock','general',1,'generation',%s,1,clock_timestamp()+interval '10 seconds',3.64,%s,%s,clock_timestamp(),%s,'observed',false)",
                (f.tenant_ids[tenant],call,run,f.actor_ids[actor],budget,bytes(32),Jsonb(PRICE.as_dict()),state,bytes(32)))
            for event,dr,da,tokens in [('reserve','3.64','0',None),*([('settle','-3.64','0.51',{'input_tokens':1000,'output_tokens':100,'total_tokens':1100})] if state=='settled' else [('mark_unknown','0','0',None)])]:
                conn.execute('INSERT INTO ops.usage_events(tenant_id,event_id,call_id,event_kind,delta_reserved_krw,delta_accounted_krw,token_counts,price_snapshot) VALUES(%s,%s,%s,%s,%s,%s,%s,%s)',
                    (f.tenant_ids[tenant],uuid4(),call,event,Decimal(dr),Decimal(da),Jsonb(tokens) if tokens is not None else None,Jsonb(PRICE.as_dict())))
        conn.execute('UPDATE ops.tenant_budgets SET reserved_krw=3.64,accounted_krw=CASE WHEN tenant_id=%s THEN 0.51 ELSE 0 END WHERE budget_id=%s',(f.tenant_ids['A'],budget))
        conn.execute('UPDATE ops.project_budget SET reserved_krw=7.28,accounted_krw=0.51 WHERE budget_id=%s',(budget,))
    return f,calls


def test_usage_real_rows_owner_tenant_unknown_pagination_and_global(client,login,usage_rows):
    f,calls=usage_rows;login(client,'A-U1')
    data=client.get('/api/v1/usage/me',headers=headers(f)).json()['data']
    assert data['call_count']==1 and data['unknown_count']==1 and data['known_tokens'] is None
    assert Decimal(data['reserved_krw'])==Decimal('3.64') and Decimal(data['estimated_accounted_krw'])==0
    login(client,'A-U2');data=client.get('/api/v1/usage/me',headers=headers(f)).json()['data']
    assert data['call_count']==1 and data['unknown_count']==0 and data['known_tokens']['total_tokens']==1100
    assert Decimal(data['estimated_accounted_krw'])==Decimal('0.51')
    login(client,'A-ADM');reply=client.get('/api/v1/admin/usage?limit=1',headers=headers(f));assert reply.status_code==200
    data=reply.json()['data'];assert data['call_count']==2 and data['unknown_count']==1 and data['known_tokens']['total_tokens']==1100
    assert len(data['items'])==1 and data['next_cursor']
    more=client.get('/api/v1/admin/usage?limit=1&cursor='+data['next_cursor'],headers=headers(f)).json()['data']
    assert len(more['items'])==1 and more['items'][0]['call_id']!=data['items'][0]['call_id'] and more['next_cursor'] is None
    assert str(calls['B-U1']) not in reply.text
    assert all(k not in reply.text for k in ['instructions','body','conversation_id','initiator_user_id','dispatch_claim','provider_request_id'])
    login(client,'P_READ_ONLY');data=client.get('/api/v1/platform/summary').json()['data']
    assert data['unknown_count']==2 and Decimal(data['reserved_krw'])==Decimal('7.28') and Decimal(data['estimated_accounted_krw'])==Decimal('0.51')


def test_global_stop_resume_latch_and_no_run_reexecution(client,login,usage_rows):
    f,calls=usage_rows;csrf=login(client,'P_WRITE_ONLY')['csrf_token']
    with f.db.admin_connection() as conn:before=conn.execute('SELECT run_id,state,execution_epoch FROM portal.runs ORDER BY run_id').fetchall()
    path='/api/v1/platform/availability';h={k:v for k,v in headers(f,csrf=csrf).items() if k!='X-Tenant-ID'}
    reply=client.put(path,headers=h,json={'enabled':False,'expected_revision':1});assert reply.status_code==200 and not reply.json()['data']['enabled']
    assert 'accounted' not in reply.text and 'cap_krw' not in reply.text
    assert client.put(path,headers=h,json={'enabled':True,'expected_revision':1}).status_code==409
    assert client.put(path,headers=h,json={'enabled':True,'expected_revision':2}).status_code==200
    with f.db.admin_connection() as conn:
        assert conn.execute('SELECT run_id,state,execution_epoch FROM portal.runs ORDER BY run_id').fetchall()==before
        assert conn.execute("SELECT reserved_krw,accounted_krw FROM ops.project_budget WHERE mode='mock'").fetchone()==(Decimal('7.28'),Decimal('0.51'))
        conn.execute("UPDATE ops.project_budget SET stop_latch=true WHERE mode='mock'")
    reply=client.put(path,headers=h,json={'enabled':True,'expected_revision':3});assert reply.status_code==409 and reply.json()['error']['code']=='REVIEW_REQUIRED'


def test_allocation_cannot_reassign_encumbered_funds(client,login,usage_rows):
    f,_=usage_rows;csrf=login(client,'P-A')['csrf_token']
    reply=client.put('/api/v1/platform/tenant-budgets/'+str(f.tenant_ids['A']),headers=headers(f,csrf=csrf),json={'allocated_cap_krw':'1','expected_revision':1})
    assert reply.status_code==409 and stored_budget(f)[0]==Decimal('12500')


def test_two_tenant_concurrent_allocation_last_capacity_one_success(client,login,ops_rows):
    f=ops_rows
    with f.db.admin_connection() as conn:
        conn.execute("INSERT INTO security.memberships(tenant_id,user_id,membership_id,role) VALUES(%s,%s,%s,'USER')",(f.tenant_ids['B'],f.actor_ids['P-A'],uuid4()))
        conn.execute('INSERT INTO security.managed_tenants(tenant_id,user_id) VALUES(%s,%s)',(f.tenant_ids['B'],f.actor_ids['P-A']))
        conn.execute("UPDATE ops.tenant_budgets t SET allocated_cap_krw=12000,local_cap_krw=12000 FROM ops.project_budget p WHERE t.budget_id=p.budget_id AND p.mode='mock'")
    csrf=login(client,'P-A')['csrf_token']
    def allocate(tenant):return client.put('/api/v1/platform/tenant-budgets/'+str(f.tenant_ids[tenant]),headers=headers(f,tenant,csrf),json={'allocated_cap_krw':'13000','expected_revision':1})
    with ThreadPoolExecutor(max_workers=2) as executor:replies=list(executor.map(allocate,['A','B']))
    assert sorted(x.status_code for x in replies)==[200,409]
    assert stored_budget(f,'A')[0]+stored_budget(f,'B')[0]==Decimal('25000')
    with f.db.admin_connection() as conn:assert conn.execute("SELECT count(*) FROM ops.audit_events WHERE action='operations_allocated_budget'").fetchone()[0]==1


def test_simultaneous_same_revision_agent_update_one_success(client,login,ops_rows):
    f=ops_rows;csrf=login(client,'A-ADM')['csrf_token']
    with ThreadPoolExecutor(max_workers=2) as executor:replies=list(executor.map(lambda _:change_agent(client,f,csrf),range(2)))
    assert sorted(x.status_code for x in replies)==[200,409] and stored_agent(f)[1]==2
    with f.db.admin_connection() as conn:assert conn.execute("SELECT count(*) FROM ops.audit_events WHERE action='operations_agent_settings'").fetchone()[0]==1


def test_waiting_agent_change_rechecks_committed_demotion(client,login,ops_rows):
    f=ops_rows;csrf=login(client,'A-ADM')['csrf_token']
    with ThreadPoolExecutor(max_workers=1) as executor:
        with f.db.admin_connection() as conn:
            with conn.transaction():
                conn.execute("UPDATE security.memberships SET role='USER' WHERE tenant_id=%s AND user_id=%s",(f.tenant_ids['A'],f.actor_ids['A-ADM']))
                future=executor.submit(change_agent,client,f,csrf)
                deadline=time.monotonic()+1.5;waiting=False
                while time.monotonic()<deadline:
                    with f.db.admin_connection() as observe:
                        waiting=observe.execute("SELECT EXISTS(SELECT 1 FROM pg_stat_activity WHERE datname=%s AND usename='ai_web' AND wait_event_type='Lock' AND query LIKE 'SELECT security.operations_mutate%%')",(f.db.name,)).fetchone()[0]
                    if waiting:break
                    time.sleep(.01)
                assert waiting
        assert future.result(timeout=4).status_code==403
    assert stored_agent(f)[1]==1


def test_shared_120_read_window_relogin_and_tenant_independence(client,login,ops_rows):
    f=ops_rows;login(client,'DUAL-ADM')
    for i in range(120):assert client.get('/api/v1/agents' if i%2 else '/api/v1/admin/memberships',headers=headers(f)).status_code==200
    reply=client.get('/api/v1/usage/me',headers=headers(f));assert reply.status_code==429 and int(reply.headers['retry-after'])>=1
    login(client,'DUAL-ADM');assert client.get('/api/v1/admin/budget',headers=headers(f)).status_code==429
    assert client.get('/api/v1/admin/budget',headers=headers(f,'B')).status_code==200


def test_read_idle_unchanged_write_touched(client,login,ops_rows):
    f=ops_rows;csrf=login(client,'A-ADM')['csrf_token']
    def idle():
        with f.db.admin_connection() as conn:return conn.execute('SELECT last_activity_at FROM security.sessions WHERE user_id=%s ORDER BY issued_at DESC LIMIT 1',(f.actor_ids['A-ADM'],)).fetchone()[0]
    before=idle()
    for path in ['/agents','/usage/me','/admin/agents/general','/admin/budget','/admin/usage']:
        assert client.get('/api/v1'+path,headers=headers(f)).status_code==200
    assert idle()==before
    assert change_agent(client,f,csrf).status_code==200 and idle()>before


def test_fixed_functions_and_content_permissions_no_escalation(db_fixture,ops_rows):
    f=ops_rows
    for role in ['ai_index','ai_meter']:
        with f.role_connection(role) as conn:
            with pytest.raises(psycopg.errors.InsufficientPrivilege):
                conn.execute("SELECT security.operations_read(%s,%s,'usage_me','2026-10-01','mock',NULL,NULL,20)",(f.state.session_ids['A-U1'],f.tenant_ids['A']))
    async def check():
        async with f.pool.connection() as conn:
            with pytest.raises(psycopg.errors.InsufficientPrivilege):await conn.execute('SELECT settings FROM portal.agent_configs')
            with pytest.raises(psycopg.errors.InsufficientPrivilege):await conn.execute('UPDATE ops.tenant_budgets SET accounted_krw=0')
            with pytest.raises(psycopg.Error) as err:
                await conn.execute("SELECT security.operations_read(%s,%s,'usage_me','2026-10-01','mock',NULL,NULL,20)",(f.state.session_ids['A-U1'],f.tenant_ids['A']))
            assert err.value.sqlstate=='A0403'
        ctx=await f.context('A-U1','A')
        from app.operations.repository import OperationsRepository
        data=await OperationsRepository(f.pool).read(ctx,'usage_me',__import__('datetime').date(2026,10,1),'mock',bytes(32))
        assert data['call_count']==0
        async with f.pool.connection() as conn:
            assert (await (await conn.execute("SELECT NULLIF(current_setting('app.operations_scope',true),'') AS value")).fetchone())['value'] is None
    f.run(check())
    f.verify_catalog()


def test_unconfigured_tenant_budget_does_not_fabricate_usage(client,login,db_fixture):
    login(client,'A-U1')
    assert client.get('/api/v1/usage/me',headers=headers(db_fixture)).status_code==503



def test_managed_padmin_without_global_capabilities_can_allocate_only_own(client,login,ops_rows):
    f=ops_rows
    with f.db.admin_connection() as conn:conn.execute("UPDATE security.platform_access SET permissions='{}' WHERE user_id=%s",(f.actor_ids['P-A'],))
    csrf=login(client,'P-A')['csrf_token']
    assert client.get('/api/v1/platform/summary').status_code==403
    assert client.put('/api/v1/platform/tenant-budgets/'+str(f.tenant_ids['A']),headers=headers(f,csrf=csrf),json={'allocated_cap_krw':'12000','expected_revision':1}).status_code==200
    assert client.get('/api/v1/admin/budget',headers=headers(f,'B')).status_code==403


def test_agent_partial_settings_and_explicit_rag_enable_remain_unavailable(client,login,ops_rows):
    f=ops_rows;csrf=login(client,'A-ADM')['csrf_token']
    reply=change_agent(client,f,csrf,name='이름만 변경');assert reply.status_code==200
    assert stored_agent(f)[2]['instructions']=='private-instruction-marker'
    reply=client.put('/api/v1/admin/agents/rules_rag/availability',headers=headers(f,csrf=csrf),json={'enabled':True,'expected_revision':1});assert reply.status_code==200
    public=client.get('/api/v1/agents',headers=headers(f)).json()['data']['items']
    assert next(x for x in public if x['agent_key']=='rules_rag')['safe_block_reason']=='FEATURE_NOT_READY'
    assert 'instructions' not in client.get('/api/v1/agents',headers=headers(f)).text


def test_operations_lock_timeout_leaves_no_partial_save(client,login,ops_rows):
    f=ops_rows;csrf=login(client,'A-ADM')['csrf_token']
    with ThreadPoolExecutor(max_workers=1) as executor:
        with f.db.admin_connection() as conn:
            with conn.transaction():
                conn.execute("SELECT tenant_id FROM portal.agent_configs WHERE tenant_id=%s AND agent_key='general' FOR UPDATE",(f.tenant_ids['A'],))
                reply=executor.submit(change_agent,client,f,csrf).result(timeout=4)
                assert reply.status_code==503 and reply.json()['error']['retryable']
    assert stored_agent(f)[1]==1



from test_auth_restart import running_server


def test_all_operations_over_real_http_and_restart(running_server,ops_rows):
    import httpx
    from test_auth_restart import record
    f=ops_rows;live=running_server;started=time.monotonic()
    with httpx.Client(base_url='http://127.0.0.1:8000',timeout=12,trust_env=False) as admin, httpx.Client(base_url='http://127.0.0.1:8000',timeout=12,trust_env=False) as user:
        csrf=live.login(admin,'P-A');live.login(user,'A-U1')
        h=headers(f,csrf=csrf)
        assert admin.get('/api/v1/agents',headers=headers(f)).status_code==200
        assert admin.get('/api/v1/admin/agents/general',headers=headers(f)).status_code==200
        assert admin.patch('/api/v1/admin/agents/general',headers=h,json={'name':'네트워크 시험','expected_revision':1}).status_code==200
        assert admin.put('/api/v1/admin/agents/general/availability',headers=h,json={'enabled':False,'expected_revision':2}).status_code==200
        assert admin.get('/api/v1/usage/me',headers=headers(f)).json()['data']['call_count']==0
        assert admin.get('/api/v1/admin/usage',headers=headers(f)).json()['data']['call_count']==0
        assert admin.get('/api/v1/admin/budget',headers=headers(f)).status_code==200
        assert admin.put('/api/v1/admin/budget',headers=h,json={'local_cap_krw':'10000','expected_revision':1}).status_code==200
        assert admin.get('/api/v1/platform/summary').status_code==200
        assert admin.put('/api/v1/platform/availability',headers=h,json={'enabled':False,'expected_revision':1}).status_code==200
        assert admin.put('/api/v1/platform/tenant-budgets/'+str(f.tenant_ids['A']),headers=h,json={'allocated_cap_krw':'12000','expected_revision':2}).status_code==200
        assert user.get('/api/v1/admin/usage',headers=headers(f)).status_code==403
        live.restart()
        assert admin.get('/api/v1/admin/agents/general',headers=headers(f)).json()['data']['config_version']==3
        budget=admin.get('/api/v1/admin/budget',headers=headers(f)).json()['data']
        assert budget['revision']==3 and Decimal(budget['local_cap_krw'])==Decimal('10000') and Decimal(budget['allocated_cap_krw'])==Decimal('12000')
        assert not admin.get('/api/v1/platform/summary').json()['data']['enabled']
        assert admin.get('/api/v1/admin/usage',headers=headers(f)).json()['data']['call_count']==0
    record('B02-live-operations',started,{'native_api_routes_checked':11,'user_admin_denied':True,
        'restart_preserved_agent_revision':3,'restart_preserved_budget_revision':3,
        'restart_preserved_global_stop':True,'provider_calls':0})
