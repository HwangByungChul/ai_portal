import asyncio
from datetime import date
from uuid import UUID,uuid4
from concurrent.futures import ThreadPoolExecutor
import pytest
import psycopg
from app.db import tenant_transaction,open_meter_pool
from app.conversations.repository import ConversationRepository
from app.ai.repository import CallRepository,ExecutionError
from test_operations import ops_rows,headers
from test_auth_restart import running_server
from test_conversations import submit

PERIOD=date(2026,10,1)
def listing(client,f,query=''):return client.get('/api/v1/catalog/assets'+query,headers=headers(f))
def favorite(client,f,csrf,asset,active=True,expected=0,key=None):
    return client.put('/api/v1/catalog/assets/'+asset+'/favorite',headers=headers(f,csrf=csrf),json={'client_request_id':key or str(uuid4()),'active':active,'expected_revision':expected})
def policy(client,f,csrf,agent='general',mode='restricted',users=None,expected=0,key=None,tenant='A'):
    return client.put('/api/v1/admin/agent-access/'+agent,headers=headers(f,tenant,csrf),json={'client_request_id':key or str(uuid4()),'mode':mode,'member_ids':users or [],'expected_revision':expected})


def test_catalog_search_detail_pagination_and_no_prompt(client,login,ops_rows):
    f=ops_rows;login(client,'A-U1');reply=listing(client,f);assert reply.status_code==200
    data=reply.json()['data'];assert len(data['items'])==2
    assert 'instructions' not in reply.text and 'private-instruction-marker' not in reply.text
    assert len(listing(client,f,'?category=general').json()['data']['items'])==1
    assert listing(client,f,'?q=no-matching-query').json()['data']['items']==[]
    assert listing(client,f,'?q=%25').json()['data']['items']==[]
    page=listing(client,f,'?limit=1').json()['data'];assert len(page['items'])==1 and page['next_cursor']
    second=listing(client,f,'?limit=1&cursor='+page['next_cursor']).json()['data'];assert len(second['items'])==1 and second['items'][0]['asset_id']!=page['items'][0]['asset_id']
    id=data['items'][0]['asset_id'];detail=client.get('/api/v1/catalog/assets/'+id,headers=headers(f));assert detail.status_code==200 and detail.json()['data']['asset_id']==id
    assert client.get('/api/v1/catalog/assets/'+str(uuid4()),headers=headers(f)).status_code==404


def test_favorite_cas_idempotency_private_and_persistent(client,login,ops_rows):
    f=ops_rows;csrf=login(client,'A-U1')['csrf_token'];id=listing(client,f).json()['data']['items'][0]['asset_id'];key=str(uuid4())
    first=favorite(client,f,csrf,id,key=key);assert first.status_code==200 and first.json()['data']['revision']==1
    same=favorite(client,f,csrf,id,key=key);assert same.status_code==200 and same.json()['data']['replayed']
    assert favorite(client,f,csrf,id,False,0,key).status_code==409
    assert favorite(client,f,csrf,id,False,0).status_code==409
    assert len(listing(client,f,'?mine=true').json()['data']['items'])==1
    assert favorite(client,f,csrf,id,False,1).json()['data']['revision']==2
    old=favorite(client,f,csrf,id,key=key);assert old.json()['data']['revision']==1
    assert listing(client,f,'?mine=true').json()['data']['items']==[]
    assert favorite(client,f,csrf,id,True,2).json()['data']['revision']==3
    login(client,'A-U2');assert listing(client,f,'?mine=true').json()['data']['items']==[]
    login(client,'A-U1');assert len(listing(client,f,'?mine=true').json()['data']['items'])==1


def test_policy_revoke_hides_favorite_and_blocks_key_alias_and_restores(client,login,ops_rows):
    f=ops_rows;csrf=login(client,'A-U1')['csrf_token'];item=listing(client,f,'?category=general').json()['data']['items'][0];id=item['asset_id']
    assert favorite(client,f,csrf,id).status_code==200
    admin=login(client,'A-ADM')['csrf_token'];key=str(uuid4());grant=policy(client,f,admin,users=[str(f.actor_ids['A-U2'])],key=key)
    assert grant.status_code==200 and grant.json()['data']['revision']==1
    assert policy(client,f,admin,users=[str(f.actor_ids['A-U2'])],key=key).json()['data']['replayed']
    assert policy(client,f,admin,users=[],key=key).status_code==409
    csrf=login(client,'A-U1')['csrf_token']
    assert len(listing(client,f).json()['data']['items'])==1
    assert listing(client,f,'?mine=true').json()['data']['items']==[]
    assert client.get('/api/v1/catalog/assets/'+id,headers=headers(f)).status_code==404
    assert client.get('/api/v1/agents',headers=headers(f)).json()['data']['items'][0]['agent_key']=='rules_rag'
    for delta in [{},{'asset_id':id}]:assert submit(client,f,csrf,**delta).status_code==403
    with f.db.admin_connection() as conn:assert conn.execute('SELECT count(*) FROM portal.runs').fetchone()[0]==0
    assert favorite(client,f,csrf,id,False,1).status_code==200
    admin=login(client,'A-ADM')['csrf_token'];assert policy(client,f,admin,mode='all',expected=1).status_code==200
    login(client,'A-U1');assert len(listing(client,f).json()['data']['items'])==2


@pytest.mark.parametrize('delta',[{'category':'bad'},{'limit':'0'},{'mine':'bad'},{'q':'x'*81},{'cursor':str(uuid4())}])
def test_catalog_invalid_filter(client,login,ops_rows,delta):
    f=ops_rows;login(client,'A-U1');from urllib.parse import urlencode
    assert listing(client,f,'?'+urlencode(delta)).status_code in (404,422)
    assert listing(client,f,'?limit=1&limit=2').status_code==422


@pytest.mark.parametrize('actor,tenant,expected',[('A-U1','A',403),('B-ADM','B',200),('P_READ_ONLY','A',403),('P-A','B',403)])
def test_access_management_scope(client,login,ops_rows,actor,tenant,expected):
    f=ops_rows;csrf=login(client,actor)['csrf_token'];reply=policy(client,f,csrf,tenant=tenant)
    assert reply.status_code==expected


def test_cross_tenant_inactive_duplicate_and_draft_rejected(client,login,ops_rows):
    f=ops_rows;admin=login(client,'A-ADM')['csrf_token']
    for ids in [[str(f.actor_ids['B-U1'])],[str(f.actor_ids['A-U1'])]*2]:assert policy(client,f,admin,users=ids).status_code==422
    assert policy(client,f,admin,mode='all',users=[str(f.actor_ids['A-U1'])]).status_code==422
    created=client.post('/api/v1/admin/assets',headers=headers(f,csrf=admin),json={'client_request_id':str(uuid4()),'config':{'name':'private draft catalog','description':'','instructions':'private draft','execution_kind':'general'}});assert created.status_code==201
    id=created.json()['data']['asset_id'];csrf=login(client,'A-U1')['csrf_token']
    assert client.get('/api/v1/catalog/assets/'+id,headers=headers(f)).status_code==404
    assert favorite(client,f,csrf,id).status_code==404
    assert 'private draft' not in listing(client,f).text
    item=listing(client,f).json()['data']['items'][0]
    login(client,'B-U1');assert client.get('/api/v1/catalog/assets/'+item['asset_id'],headers=headers(f,'B')).status_code==404


def test_concurrent_favorite_cas_one_winner(client,login,ops_rows):
    f=ops_rows;csrf=login(client,'A-U1')['csrf_token'];id=listing(client,f).json()['data']['items'][0]['asset_id']
    with ThreadPoolExecutor(max_workers=2) as ex:replies=list(ex.map(lambda _:favorite(client,f,csrf,id),range(2)))
    assert sorted(r.status_code for r in replies)==[200,409]


@pytest.mark.parametrize('phase',['claim','reserve','dispatch','finish','stream'])
def test_running_access_revoke_fails_closed_and_preserves_accounting(ops_rows,phase):
    f=ops_rows
    async def check():
        from app.catalog.repository import CatalogRepository
        ctx=await f.context('A-U1','A');admin=await f.context('A-ADM','A')
        async with open_meter_pool(f.db.runtime_dsn('ai_meter')) as meter:
            repo=CallRepository(f.pool,meter,PERIOD)
            data=await ConversationRepository(f.pool).admit(ctx,'general',None,uuid4(),'access synthetic',PERIOD,'mock',b'x'*32,uuid4());rid=UUID(data['run_id'])
            t=None;c=None
            if phase!='claim':t=await repo.claim(ctx,rid,'mock')
            if phase in ('dispatch','finish'):c=await repo.reserve(t,b'x'*32)
            if phase=='finish':
                from app.ai.types import UsageReceipt
                claim=await repo.dispatch(t,UUID(c['call_id']));await repo.settle(t,claim,UsageReceipt(120,40,160,'gpt-4o-mini','default',None),'observed')
            await CatalogRepository(f.pool).call(admin,'access_set',None,'general',{'client_request_id':str(uuid4()),'expected_revision':0,'mode':'restricted','member_ids':[]},PERIOD,'mock',uuid4(),None)
            with pytest.raises(ExecutionError):
                if phase=='claim':await repo.claim(ctx,rid,'mock')
                elif phase=='reserve':await repo.reserve(t,b'x'*32)
                elif phase=='dispatch':await repo.dispatch(t,UUID(c['call_id']))
                elif phase=='finish':await repo.finish(t,'must never be stored')
                else:await repo.stream_view(ctx,rid,'mock')
            with f.db.admin_connection() as conn:
                assert conn.execute("SELECT count(*) FROM portal.messages WHERE run_id=%s AND role='assistant'",(rid,)).fetchone()[0]==0
                if phase=='finish':assert conn.execute("SELECT count(*) FROM ops.usage_events WHERE event_kind='settle'").fetchone()[0]==1
    f.run(check())


@pytest.mark.parametrize('delta',[{'active':'true'},{'active':1},{'expected_revision':True},{'expected_revision':-1},{'extra':'x'},{'client_request_id':'invalid'}])
def test_strict_favorite_mutation_rejected_without_write(client,login,ops_rows,delta):
    f=ops_rows;csrf=login(client,'A-U1')['csrf_token'];item=listing(client,f).json()['data']['items'][0]
    body={'client_request_id':str(uuid4()),'active':True,'expected_revision':0,**delta}
    assert client.put('/api/v1/catalog/assets/'+item['asset_id']+'/favorite',headers=headers(f,csrf=csrf),json=body).status_code==422
    with f.db.admin_connection() as conn:assert conn.execute('SELECT count(*) FROM portal.agent_favorites').fetchone()[0]==0


def test_inactive_member_rejected_and_audit_atomic_private(client,login,ops_rows):
    f=ops_rows;csrf=login(client,'A-ADM')['csrf_token']
    with f.db.admin_connection() as conn:conn.execute('UPDATE security.memberships SET active=false WHERE tenant_id=%s AND user_id=%s',(f.tenant_ids['A'],f.actor_ids['A-U2']))
    assert policy(client,f,csrf,users=[str(f.actor_ids['A-U2'])]).status_code==422
    assert policy(client,f,csrf,users=[str(f.actor_ids['A-U1'])]).status_code==200
    with f.db.admin_connection() as conn:
        rows=conn.execute("SELECT revisions FROM ops.audit_events WHERE action='catalog.access'").fetchall();assert rows==[({'revision':1},)]
        assert conn.execute('SELECT count(*) FROM portal.catalog_mutations').fetchone()[0]==1


def test_direct_sql_intake_bypass_denied_and_regrant_restores_favorite(ops_rows):
    f=ops_rows
    async def check():
        from app.catalog.repository import CatalogRepository
        ctx=await f.context('A-U1','A');admin=await f.context('A-ADM','A');repo=CatalogRepository(f.pool)
        body={'q':'','category':'general','mine':False,'limit':20,'cursor':None}
        item=(await repo.call(ctx,'list',body=body,period=PERIOD,mode='mock'))['items'][0]
        await repo.call(ctx,'favorite',UUID(item['asset_id']),body={'client_request_id':str(uuid4()),'active':True,'expected_revision':0},trace=uuid4())
        await repo.call(admin,'access_set',agent='general',body={'client_request_id':str(uuid4()),'mode':'restricted','member_ids':[],'expected_revision':0},trace=uuid4())
        with pytest.raises(psycopg.Error) as error:
            async with tenant_transaction(f.pool,ctx) as conn:
                await conn.execute('SELECT security.run_prepare(%s,%s,%s,%s,%s,%s,%s,%s)',(ctx.session_id,ctx.tenant_id,'general',None,uuid4(),b'x'*32,PERIOD,'mock'))
        assert error.value.sqlstate=='B0340'
        await repo.call(admin,'access_set',agent='general',body={'client_request_id':str(uuid4()),'mode':'all','member_ids':[],'expected_revision':1},trace=uuid4())
        body['mine']=True;assert len((await repo.call(ctx,'list',body=body,period=PERIOD,mode='mock'))['items'])==1
    f.run(check())



def test_audit_failure_rolls_back_favorite_and_receipt(ops_rows):
    f=ops_rows
    async def check():
        from app.catalog.repository import CatalogRepository
        ctx=await f.context('A-U1','A');repo=CatalogRepository(f.pool);trace=uuid4()
        items=(await repo.call(ctx,'list',body={'q':'','category':'all','mine':False,'limit':20,'cursor':None},period=PERIOD,mode='mock'))['items']
        body={'client_request_id':str(uuid4()),'active':True,'expected_revision':0}
        await repo.call(ctx,'favorite',UUID(items[0]['asset_id']),body=body,trace=trace)
        body['client_request_id']=str(uuid4())
        with pytest.raises(psycopg.errors.UniqueViolation):await repo.call(ctx,'favorite',UUID(items[1]['asset_id']),body=body,trace=trace)
        with f.db.admin_connection() as conn:
            assert conn.execute('SELECT count(*) FROM portal.agent_favorites').fetchone()[0]==1
            assert conn.execute('SELECT count(*) FROM portal.catalog_mutations').fetchone()[0]==1
    f.run(check())


def test_fresh_admin_authority_required_before_replay(client,login,ops_rows):
    f=ops_rows;csrf=login(client,'A-ADM')['csrf_token'];key=str(uuid4())
    assert policy(client,f,csrf,key=key).status_code==200
    with f.db.admin_connection() as conn:conn.execute("UPDATE security.memberships SET role='USER',revision=revision+1 WHERE tenant_id=%s AND user_id=%s",(f.tenant_ids['A'],f.actor_ids['A-ADM']))
    assert policy(client,f,csrf,key=key).status_code==403



@pytest.mark.parametrize('phase',['admit','claim','replay'])
def test_summary_admission_and_worker_obey_same_agent_access(ops_rows,tmp_path,phase):
    from test_dp07_acceptance import setup,admit,RAW
    from test_document_sharing import publish
    from test_document_ingest import metadata
    from app.errors import AppError
    f=ops_rows
    async def check():
        from app.catalog.repository import CatalogRepository
        admin=await f.context('A-ADM','A');ctx=await f.context('A-U1','A');docs=setup(f,tmp_path)
        ids=await publish(f,docs,admin,metadata(visibility='private',owner_user_id=ctx.user_id),RAW)
        send=uuid4();data=await admit(f,docs,ctx,ids,send=send) if phase!='admit' else None
        await CatalogRepository(f.pool).call(admin,'access_set',agent='rules_rag',body={'client_request_id':str(uuid4()),'mode':'restricted','member_ids':[],'expected_revision':0},trace=uuid4())
        if phase in ('admit','replay'):
            with pytest.raises(AppError) as error:await admit(f,docs,ctx,ids,send=send)
            assert error.value.code=='AGENT_ACCESS_DENIED'
        else:
            with pytest.raises(ExecutionError):await CallRepository(f.pool,None,PERIOD).claim(ctx,UUID(data['run_id']),'mock')
    f.run(check())


def test_favorite_and_access_survive_http_restart(running_server):
    import httpx
    live=running_server;f=live.fixture
    with httpx.Client(base_url='http://127.0.0.1:8000',timeout=12,trust_env=False) as client:
        csrf=live.login(client,'A-U1');item=listing(client,f).json()['data']['items'][0];aid=item['asset_id'];key=str(uuid4())
        assert favorite(client,f,csrf,aid,key=key).status_code==200
        live.restart();assert len(listing(client,f,'?mine=true').json()['data']['items'])==1
        assert favorite(client,f,csrf,aid,key=key).json()['data']['replayed']
        admin=live.login(client,'A-ADM');assert policy(client,f,admin,agent=item['agent_key']).status_code==200
        live.restart();assert client.get('/api/v1/admin/agent-access/'+item['agent_key'],headers=headers(f)).json()['data']['revision']==1
        live.login(client,'A-U1');assert listing(client,f,'?mine=true').json()['data']['items']==[]



def test_rules_rag_direct_admission_revoke_before_feature_processing(ops_rows):
    from app.errors import AppError
    f=ops_rows
    async def check():
        from app.catalog.repository import CatalogRepository
        admin=await f.context('A-ADM','A');ctx=await f.context('A-U1','A')
        await CatalogRepository(f.pool).call(admin,'access_set',agent='rules_rag',body={'client_request_id':str(uuid4()),'mode':'restricted','member_ids':[],'expected_revision':0},trace=uuid4())
        with pytest.raises(AppError) as error:await ConversationRepository(f.pool).admit(ctx,'rules_rag',None,uuid4(),'blocked rag synthetic',PERIOD,'mock',b'x'*32,uuid4())
        assert error.value.code=='AGENT_ACCESS_DENIED'
        with f.db.admin_connection() as conn:assert conn.execute('SELECT count(*) FROM portal.runs').fetchone()[0]==0
    f.run(check())


@pytest.mark.parametrize('path',['/api/v1/admin/agent-access/general','/api/v1/catalog/assets/'+str(uuid4())+'/favorite'])
def test_catalog_write_stream_size_bound(client,path):
    assert client.put(path,content=b'x'*32769,headers={'Content-Type':'application/json'}).status_code==413



def test_eligible_member_picker_excludes_inactive_accounts_and_memberships(client,login,ops_rows):
    f=ops_rows;login(client,'A-ADM');path='/api/v1/admin/agent-access/general/members'
    with f.db.admin_connection() as conn:conn.execute('UPDATE security.memberships SET active=false WHERE tenant_id=%s AND user_id=%s',(f.tenant_ids['A'],f.actor_ids['A-U2']))
    reply=client.get(path,headers=headers(f));assert reply.status_code==200
    ids={x['user_id'] for x in reply.json()['data']['items']};assert str(f.actor_ids['A-U2']) not in ids and str(f.actor_ids['INACTIVE']) not in ids and str(f.actor_ids['B-U1']) not in ids
    page=client.get(path+'?limit=1',headers=headers(f)).json()['data'];assert len(page['items'])==1 and page['next_cursor']
    second=client.get(path+'?limit=1&cursor='+page['next_cursor'],headers=headers(f)).json()['data'];assert second['items'][0]['user_id']!=page['items'][0]['user_id']
    assert client.get(path+'?limit=1&limit=2',headers=headers(f)).status_code==422
    login(client,'A-U1');assert client.get(path,headers=headers(f)).status_code==403
