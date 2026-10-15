from uuid import UUID,uuid4
from datetime import date
import pytest
from psycopg.types.json import Jsonb
from app.ai.repository import CallRepository
from app.db import open_meter_pool
from app.errors import AppError
from app.conversations.repository import ConversationRepository
from app.assets.published import PublishedRepository
from app.builder.execution import TrialExecutor
from app.ai.gateway import AiGateway
from app.ai.providers import MockProvider
from test_operations import ops_rows,headers
from test_published_agents import publish,start

async def history(f,ctx,action='list',id=None,body=None):
 return await PublishedRepository(f.pool).rpc(ctx,'published_run_history',(ctx.session_id,ctx.tenant_id,action,id,Jsonb(body or {}),'mock'))

@pytest.mark.parametrize('case',['retired','publication','fixed_access','sources','audience','membership'])
def test_own_minimum_record_current_guard_and_no_private_payload(ops_rows,case):
 f=ops_rows
 async def check():
  async with open_meter_pool(f.db.runtime_dsn('ai_meter')) as meter:
   calls=CallRepository(f.pool,meter,date(2026,10,1));owner,saved,b,d=await publish(f,calls);u=await f.context('A-U1','A');run=await start(f,u,saved,{'audience':'사용자','rule':'기준','question':'비공개 질문'});id=UUID(run['run_id'])
   ticket=await calls.claim(u,id,'mock');engine=TrialExecutor(calls,AiGateway(calls,MockProvider()),None);await engine.finish(ticket,await engine.execute(ticket))
   record=await history(f,u,'record',id);assert record['available'] and record['display_name'] and record['is_terminal'];assert record['publication_revision']==1
   assert set(record)=={'run_id','asset_id','asset_revision','asset_version_id','publication_revision','state','revision','is_terminal','execution_mode','created_at','available','display_name'}
   for actor,tenant in [('A-U2','A'),('P-A','A'),('B-U1','B')]:
    other=await f.context(actor,tenant);assert not (await history(f,other))['items']
    with pytest.raises(AppError) as e:await history(f,other,'record',id)
    assert e.value.status==404
    with pytest.raises(AppError) as e:await history(f,other,body={'cursor':str(id)})
    assert e.value.status==404
   if case=='retired':await d.call(await f.context('P-A','A'),'retire',UUID(saved['asset_id']),{'expected_revision':1},'mock')
   elif case=='membership':
    f.mutate_access(u,'membership')
    with pytest.raises(AppError):await history(f,u)
    return
   else:
    with f.db.admin_connection() as c:
     if case=='fixed_access':c.execute("INSERT INTO portal.agent_access(tenant_id,agent_key,mode,member_ids,revision) VALUES(%s,'general','restricted','{}',1)",(u.tenant_id,))
     elif case=='audience':
      c.execute('ALTER TABLE portal.asset_publications DISABLE TRIGGER USER');c.execute("UPDATE portal.asset_publications SET audience='restricted',member_ids='{}' WHERE tenant_id=%s",(u.tenant_id,));c.execute('ALTER TABLE portal.asset_publications ENABLE TRIGGER USER')
     elif case=='publication':
      # Fixture-only state perturbation of the immutable binding, never used on primary data.
      c.execute('ALTER TABLE portal.asset_publications DISABLE TRIGGER USER');c.execute('UPDATE portal.asset_publications SET publication_revision=2 WHERE tenant_id=%s',(u.tenant_id,));c.execute('ALTER TABLE portal.asset_publications ENABLE TRIGGER USER')
     else:
      # A sealed source ref absent from the current document scope exercises the source guard.
      c.execute('ALTER TABLE portal.published_agent_runs DISABLE TRIGGER USER');c.execute('UPDATE portal.published_agent_runs SET sources=%s WHERE run_id=%s',(Jsonb([{'source_tenant_id':str(u.tenant_id),'document_id':str(uuid4()),'version_id':str(uuid4()),'index_id':str(uuid4())}]),id));c.execute('ALTER TABLE portal.published_agent_runs ENABLE TRIGGER USER')
   record=await history(f,u,'record',id);assert not record['available'] and record['display_name'] is None
   assert (await history(f,u))['items']==[record]
   with pytest.raises(AppError):await PublishedRepository(f.pool).read(u,id)
 f.run(check())

def test_history_pagination_filter_cursor_scope_and_readonly(ops_rows):
 f=ops_rows
 async def check():
  async with open_meter_pool(f.db.runtime_dsn('ai_meter')) as meter:
   calls=CallRepository(f.pool,meter,date(2026,10,1));_,saved,_,_=await publish(f,calls);u=await f.context('A-U1','A');p=PublishedRepository(f.pool);ids=[]
   for i in range(23):
    if i and i%10==0:
     with f.db.admin_connection() as c:c.execute("UPDATE security.login_windows SET window_started_at=clock_timestamp()-interval '2 minutes' WHERE purpose='run_admission'")
    run=await start(f,u,saved,{'audience':'사용자','rule':'기준','question':str(i)});id=UUID(run['run_id']);ids.append(str(id));await ConversationRepository(f.pool).cancel(u,id,run['revision'],uuid4())
   a=await history(f,u);assert len(a['items'])==20 and a['next_cursor']==a['items'][-1]['run_id'];b=await history(f,u,body={'cursor':a['next_cursor']});assert len(b['items'])==3 and b['next_cursor'] is None
   assert {x['run_id'] for x in a['items']+b['items']}==set(ids)
   assert len((await history(f,u,body={'asset_id':saved['asset_id'],'state':'cancelled'}))['items'])==20
   assert not (await history(f,u,body={'state':'completed'}))['items']
   for body in [{'cursor':a['next_cursor'],'state':'completed'},{'cursor':a['next_cursor'],'asset_id':str(uuid4())}]:
    with pytest.raises(AppError) as e:await history(f,u,body=body)
    assert e.value.status==404
   for body in [{'state':'anything'},{'state':None},{'owner_user_id':str(u.user_id)}]:
    with pytest.raises(AppError) as e:await history(f,u,body=body)
    assert e.value.status==422
   f.verify_catalog()
 f.run(check())

def test_history_http_strict_no_store_and_record_owner(ops_rows,client,login):
 f=ops_rows
 async def prepare():
  async with open_meter_pool(f.db.runtime_dsn('ai_meter')) as meter:
   _,saved,_,_=await publish(f,CallRepository(f.pool,meter,date(2026,10,1)));u=await f.context('A-U1','A');return await start(f,u,saved,{'audience':'사용자','rule':'기준','question':'개인 질문'})
 run=f.run(prepare());login(client,'A-U1');path='/api/v1/published-agent-runs'
 reply=client.get(path,headers=headers(f));assert reply.status_code==200 and reply.headers['cache-control']=='no-store';assert len(reply.json()['data']['items'])==1
 for q in ['?state=no','?state=queued','?state=queued&state=running','?owner_user_id=x','?cursor=no','?asset_id=no']:
  assert client.get(path+q,headers=headers(f)).status_code==422
 record=path+'/'+run['run_id']+'/record';assert client.get(record,headers=headers(f)).status_code==200
 assert client.get(record+'?cursor='+run['run_id'],headers=headers(f)).status_code==422
 login(client,'A-U2');assert client.get(record,headers=headers(f)).status_code==404
 assert client.get(path+'?cursor='+run['run_id'],headers=headers(f)).status_code==404


def test_039_additive_preserves_every_table_and_frozen_checksums(owned_cluster,tmp_path):
 from scripts.migrate import MIGRATIONS,create_fixture_database,apply_migrations
 from scripts.seed import seed_fixture
 from test_catalog_migration import fingerprint
 import shutil
 prior=tmp_path/'through038';prior.mkdir()
 for path in MIGRATIONS.glob('*.sql'):
  if path.name<'039_':shutil.copy2(path,prior/path.name)
 db=create_fixture_database();seed=None
 try:
  apply_migrations(db,prior);seed=seed_fixture(db)
  with db.admin_connection() as c:
   before=fingerprint(c);hashes=dict(c.execute('SELECT version,sha256 FROM infra.schema_migrations').fetchall());assert len(before)==51 and len(hashes)==39
  through=tmp_path/'through039';through.mkdir()
  for path in MIGRATIONS.glob('*.sql'):
   if path.name<'040_':shutil.copy2(path,through/path.name)
  assert apply_migrations(db,through)==['039_published_run_history.sql']
  with db.admin_connection() as c:
   assert fingerprint(c)==before
   assert dict(c.execute("SELECT version,sha256 FROM infra.schema_migrations WHERE version<'039_'").fetchall())==hashes
   assert c.execute("SELECT count(*) FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace WHERE n.nspname='security'").fetchone()[0]==141
   assert c.execute("SELECT has_function_privilege('ai_web','security.published_run_history(uuid,uuid,text,uuid,jsonb,text)','EXECUTE')").fetchone()[0]
   for role in ['ai_web','ai_index','ai_meter']:
    assert not c.execute("SELECT has_table_privilege(%s,'portal.published_agent_runs','SELECT')",(role,)).fetchone()[0]
   for role in ['ai_index','ai_meter']:
    assert not c.execute("SELECT has_function_privilege(%s,'security.published_run_history(uuid,uuid,text,uuid,jsonb,text)','EXECUTE')",(role,)).fetchone()[0]
  assert apply_migrations(db,through)==[]
  with db.admin_connection() as c:assert fingerprint(c)==before
 finally:
  db.drop()
  if seed:seed.secret_path.unlink(missing_ok=True)


def test_retired_queued_record_can_cancel_without_answer_or_dispatch(ops_rows,client,login):
 f=ops_rows
 async def prepare():
  async with open_meter_pool(f.db.runtime_dsn('ai_meter')) as meter:
   _,saved,_,d=await publish(f,CallRepository(f.pool,meter,date(2026,10,1)));u=await f.context('A-U1','A');run=await start(f,u,saved,{'audience':'사용자','rule':'기준','question':'미발사 질문'})
   await d.call(await f.context('P-A','A'),'retire',UUID(saved['asset_id']),{'expected_revision':1},'mock');return run
 run=f.run(prepare());csrf=login(client,'A-U1')['csrf_token'];path='/api/v1/published-agent-runs/'+run['run_id']
 assert len(client.get('/api/v1/published-agent-runs?state=accepted',headers=headers(f)).json()['data']['items'])==1
 record=client.get(path+'/record',headers=headers(f)).json()['data'];assert not record['available'] and not record['is_terminal']
 assert client.get(path,headers=headers(f)).status_code==404
 assert client.post(path+'/cancel',headers=headers(f),json={'expected_revision':record['revision']}).status_code==403
 reply=client.post(path+'/cancel',headers=headers(f,'A',csrf),json={'expected_revision':record['revision']});assert reply.status_code==200 and reply.json()['data']['is_terminal']
 record=client.get(path+'/record',headers=headers(f)).json()['data'];assert record['state']=='cancelled' and record['is_terminal'] and not record['available']
 with f.db.admin_connection() as c:assert c.execute('SELECT count(*) FROM ops.call_attempts WHERE run_id=%s',(UUID(run['run_id']),)).fetchone()[0]==0
