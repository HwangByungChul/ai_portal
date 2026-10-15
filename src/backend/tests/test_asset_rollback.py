import asyncio,shutil
from uuid import UUID,uuid4
from datetime import date
import pytest,psycopg
from psycopg.types.json import Jsonb
from app.assets.deployments import DeploymentRepository
from app.assets.published import PublishedRepository
from app.builder.repository import BuilderRepository
from app.builder.trials import TrialRepository
from app.builder.execution import TrialExecutor
from app.ai.repository import CallRepository
from app.ai.gateway import AiGateway
from app.ai.providers import MockProvider
from app.db import open_meter_pool,open_web_pool
from app.errors import AppError
from test_operations import ops_rows
from test_published_agents import publish,start
from test_asset_deployments import request,decide
from test_builder_shares import share
from test_builder_profiles import body
from test_builder_evaluations import save,spec

async def rpc(repo,ctx,action,target=None,value=None,mode='mock'):
 return await repo.rpc(ctx,'asset_rollback',(ctx.session_id,ctx.tenant_id,action,UUID(str(target)) if target else None,Jsonb(value or {}),mode))
async def two_versions(f,calls):
 ctx,old,b,d=await publish(f,calls)
 with f.db.admin_connection() as c:source=str(c.execute('SELECT request_id FROM portal.asset_publications').fetchone()[0])
 value=body();value['profile']['developer_prompt']='변경한 기준 {{rule}}';value['expected_revision']=1
 newer=await BuilderRepository(f.pool).call(ctx,'append',UUID(old['asset_id']),body=value,trace=uuid4());t=TrialRepository(f.pool)
 payload={'client_send_id':str(uuid4()),'purpose':'generate','values':{'audience':'이용자','rule':'기준','question':'절차'}}
 run=await t.admit(ctx,UUID(old['asset_id']),UUID(newer['version_id']),payload,date(2026,10,1),'mock',b'y'*32,uuid4());ticket=await calls.claim(ctx,UUID(run['run_id']),'mock');engine=TrialExecutor(calls,AiGateway(calls,MockProvider()),None);await engine.finish(ticket,await engine.execute(ticket))
 case=await save(t,ctx,newer,spec(payload,terms=['모의 AI 응답']));e=await t.rpc(ctx,'builder_case_evaluate',(ctx.session_id,ctx.tenant_id,UUID(case['case_id']),UUID(run['run_id'])))
 s=await share(t,ctx,body={'client_request_id':str(uuid4()),'run_id':run['run_id'],'evaluation_id':e['evaluation_id'],'consent':True});row,_=await request(f,ctx,d,s['share_id'],expected_publication_revision=1,audience='restricted',member_ids=[str(f.actor_ids['A-U1'])]);await decide(f,d,row['request_id'])
 return ctx,old,newer,source,d
def rollback_body(source,**changes):return {'client_request_id':str(uuid4()),'source_request_id':source,'expected_publication_revision':2,'reason':'검토한 이전 버전 복원',**changes}

def test_exact_rollback_current_audience_compare_events_replay_and_execution(ops_rows):
 f=ops_rows
 async def check():
  async with open_meter_pool(f.db.runtime_dsn('ai_meter')) as meter:
   calls=CallRepository(f.pool,meter,date(2026,10,1));ctx,old,newer,source,d=await two_versions(f,calls);admin=await f.context('P-A','A');value=rollback_body(source)
   history=await rpc(d,ctx,'history',old['asset_id']);assert len(history['items'])==2 and history['history_complete']
   comparison=await rpc(d,ctx,'compare',old['asset_id'],{'left_revision':1,'right_revision':2});assert next(x for x in comparison['fields'] if x['field']=='developer_prompt')['changed']
   row=await rpc(d,ctx,'submit',value=value);assert (await rpc(d,ctx,'submit',value=value))['replayed']
   with pytest.raises(AppError) as conflict:await rpc(d,ctx,'submit',value=value|{'reason':'다른 요청'})
   assert conflict.value.status==409
   with pytest.raises(AppError) as denied:await decide(f,d,row['request_id'],'A-ADM')
   assert denied.value.status==403
   detail=await d.call(admin,'detail',UUID(row['request_id']),{},'mock');assert detail['deployment_kind']=='rollback' and detail['rollback_ready'] and detail['body']['audience']=='restricted'
   approved=await decide(f,d,row['request_id']);assert approved['publication_revision']==3 and (await decide(f,d,row['request_id']))['replayed']
   with f.db.admin_connection() as c:
    pub=c.execute('SELECT version_id,member_ids,asset_revision FROM portal.asset_publications').fetchone();assert str(pub[0])==old['version_id'] and pub[1]==[f.actor_ids['A-U1']] and pub[2]==1
    for sql in ['UPDATE portal.asset_publication_events SET event_kind=\'current_state\'','DELETE FROM portal.asset_publication_events']:
     with pytest.raises(psycopg.errors.CheckViolation):
      with c.transaction():c.execute(sql)
   user=await f.context('A-U1','A');p=PublishedRepository(f.pool);run=await p.admit(user,UUID(old['asset_id']),{'version_id':UUID(old['version_id']),'expected_publication_revision':3,'client_send_id':uuid4(),'values':{'audience':'이용자','rule':'기준','question':'절차'}},date(2026,10,1),'mock',b'p'*32,uuid4());ticket=await calls.claim(user,UUID(run['run_id']),'mock');assert ticket.messages[1]['content']=='검토 기준 기준';engine=TrialExecutor(calls,AiGateway(calls,MockProvider()),None);await engine.finish(ticket,await engine.execute(ticket));assert (await p.read(user,UUID(run['run_id'])))['content_status']=='final'
   history=await rpc(d,admin,'history',old['asset_id']);assert [x['event_kind'] for x in history['items']]==['rollback','publish','publish']
 f.run(check())

@pytest.mark.parametrize('case',['withdraw','policy','stale','mode','inactive_member','other_tenant','same_version'])
def test_rollback_current_guards_and_rejection(ops_rows,case):
 f=ops_rows
 async def check():
  async with open_meter_pool(f.db.runtime_dsn('ai_meter')) as meter:
   ctx,old,newer,source,d=await two_versions(f,CallRepository(f.pool,meter,date(2026,10,1)));value=rollback_body(source)
   if case=='same_version':
    with f.db.admin_connection() as c:value['source_request_id']=str(c.execute('SELECT request_id FROM portal.asset_publications').fetchone()[0])
   if case in ('same_version','other_tenant'):
    with pytest.raises(AppError) as blocked:await rpc(d,await f.context('B-ADM','B') if case=='other_tenant' else ctx,'submit',value=value)
    assert blocked.value.status==(404 if case=='other_tenant' else 409);return
   row=await rpc(d,ctx,'submit',value=value)
   if case=='withdraw':
    with f.db.admin_connection() as c:sid=str(c.execute('SELECT share_id FROM portal.asset_deployments WHERE request_id=%s',(UUID(source),)).fetchone()[0])
    await share(TrialRepository(f.pool),ctx,'withdraw',sid,{'expected_revision':1})
   elif case=='policy':
    with f.db.admin_connection() as c:c.execute("UPDATE portal.agent_configs SET config_version=config_version+1 WHERE tenant_id=%s AND agent_key='general'",(ctx.tenant_id,))
   elif case=='inactive_member':
    with f.db.admin_connection() as c:c.execute('UPDATE security.memberships SET active=false WHERE tenant_id=%s AND user_id=%s',(ctx.tenant_id,f.actor_ids['A-U1']))
   elif case=='stale':await d.call(await f.context('P-A','A'),'retire',UUID(old['asset_id']),{'expected_revision':2},'mock')
   with pytest.raises(AppError) as blocked:
    if case=='mode':await d.call(await f.context('P-A','A'),'decide',UUID(row['request_id']),{'expected_revision':1,'decision':'approve','comment':'검토','quality_reviewed':True,'security_reviewed':True},'real')
    else:await decide(f,d,row['request_id'])
   assert blocked.value.status in (404,409)
   assert (await decide(f,d,row['request_id'],decision='reject'))['status']=='rejected'
 f.run(check())

def test_concurrent_rollback_same_receipt_and_old_decision_cannot_bypass(ops_rows):
 f=ops_rows
 async def check():
  async with open_meter_pool(f.db.runtime_dsn('ai_meter')) as meter:
   ctx,old,newer,source,d=await two_versions(f,CallRepository(f.pool,meter,date(2026,10,1)));row=await rpc(d,ctx,'submit',value=rollback_body(source));admin=await f.context('P-A','A')
   async def approve():
    async with open_web_pool(f.db.runtime_dsn('ai_web')) as pool:return await DeploymentRepository(pool).call(admin,'decide',UUID(row['request_id']),{'expected_revision':1,'decision':'approve','comment':'별도 검토','quality_reviewed':True,'security_reviewed':True},'mock')
   result=await asyncio.gather(approve(),approve());assert sum(x['replayed'] for x in result)==1
   with f.db.admin_connection() as c:
    assert not c.execute("SELECT has_function_privilege('ai_web','security.asset_deployment_v1(uuid,uuid,text,uuid,jsonb,text)','EXECUTE')").fetchone()[0]
    assert c.execute("SELECT count(*) FROM ops.audit_events WHERE action='asset.rollback_approved'").fetchone()[0]==1
 f.run(check())

def test_history_http_strict_scope_csrf_and_comparison_owner_boundary(ops_rows,auth_settings,login):
 from fastapi.testclient import TestClient
 from app.main import create_app
 from test_operations import headers
 f=ops_rows
 async def prepare():
  async with open_meter_pool(f.db.runtime_dsn('ai_meter')) as meter:return await two_versions(f,CallRepository(f.pool,meter,date(2026,10,1)))
 ctx,old,newer,source,d=f.run(prepare());path='/api/v1/admin/asset-deployments'
 with TestClient(create_app(auth_settings),base_url='http://127.0.0.1:8000',client=('127.0.0.1',50000)) as c:
  csrf=login(c,'A-ADM')['csrf_token'];h=headers(f,'A',csrf);value=rollback_body(source)
  assert c.post(path+'/rollbacks',headers=headers(f),json=value).status_code==403
  assert c.post(path+'/rollbacks',headers=h,json=value|{'audience':'all'}).status_code==422
  reply=c.post(path+'/rollbacks',headers=h,json=value);assert reply.status_code==201
  assert c.post(path+'/rollbacks',headers=h,json=value).json()['data']['replayed']
  history=path+'/publications/'+old['asset_id']+'/history';compare=path+'/publications/'+old['asset_id']+'/compare'
  assert c.get(history+'?cursor=1&cursor=1',headers=headers(f)).status_code==422
  assert c.get(history+'?cursor=0',headers=headers(f)).status_code==422
  assert c.get(compare+'?left_revision=1&right_revision=2',headers=headers(f)).headers['cache-control']=='no-store'
  login(c,'A-U1');assert c.get(history,headers=headers(f)).status_code==403
  assert c.get(compare+'?left_revision=1&right_revision=2',headers=headers(f)).status_code==403
  login(c,'B-ADM');assert c.get(history,headers=headers(f,'B')).status_code==404

def test_migration_038_preserves_rows_and_raw_event_privileges(owned_cluster,tmp_path):
 from scripts.migrate import MIGRATIONS,create_fixture_database,apply_migrations
 from scripts.seed import seed_fixture
 from test_catalog_migration import fingerprint
 prior=tmp_path/'through037';prior.mkdir();current=tmp_path/'through038';current.mkdir()
 for path in MIGRATIONS.glob('[0-9][0-9][0-9]_*.sql'):
  if path.name<'038_':shutil.copy2(path,prior/path.name)
  if path.name<'039_':shutil.copy2(path,current/path.name)
 db=create_fixture_database();state=None
 try:
  apply_migrations(db,prior);state=seed_fixture(db)
  with db.admin_connection() as c:before=fingerprint(c);hashes=dict(c.execute('SELECT version,sha256 FROM infra.schema_migrations').fetchall())
  assert apply_migrations(db,current)==['038_asset_rollback_history.sql']
  with db.admin_connection() as c:
   after=fingerprint(c);assert len(after)==51 and all(after[k]==v for k,v in before.items());assert dict(c.execute("SELECT version,sha256 FROM infra.schema_migrations WHERE version<'038_'").fetchall())==hashes
   assert c.execute('SELECT count(*) FROM portal.asset_publication_events').fetchone()[0]==0
   for role in ('ai_web','ai_index','ai_meter'):assert not c.execute("SELECT has_table_privilege(%s,'portal.asset_publication_events','SELECT,INSERT,UPDATE,DELETE')",(role,)).fetchone()[0]
   assert c.execute("SELECT relrowsecurity AND relforcerowsecurity FROM pg_class WHERE oid='portal.asset_publication_events'::regclass").fetchone()[0]
  assert apply_migrations(db,current)==[]
  with db.admin_connection() as c:assert fingerprint(c)==after
 finally:
  db.drop()
  if state:state.secret_path.unlink(missing_ok=True)

def test_retired_republication_and_history_pagination(ops_rows):
 f=ops_rows
 async def check():
  async with open_meter_pool(f.db.runtime_dsn('ai_meter')) as meter:
   ctx,old,newer,source,d=await two_versions(f,CallRepository(f.pool,meter,date(2026,10,1)));admin=await f.context('P-A','A');revision=2
   for _ in range(10):
    await d.call(admin,'retire',UUID(old['asset_id']),{'expected_revision':revision},'mock');revision+=1
    row=await rpc(d,ctx,'submit',value=rollback_body(source,expected_publication_revision=revision));await decide(f,d,row['request_id']);revision+=1
   page=await rpc(d,ctx,'history',old['asset_id']);assert len(page['items'])==20 and page['next_cursor'] and page['history_complete']
   rest=await rpc(d,ctx,'history',old['asset_id'],{'cursor':page['next_cursor']});assert len(rest['items'])==2 and rest['next_cursor'] is None
 f.run(check())

def test_legacy_real_approvals_backfill_without_invented_retirement(owned_cluster,tmp_path):
 from scripts.migrate import MIGRATIONS,create_fixture_database,apply_migrations
 from scripts.seed import seed_fixture
 from support import FixtureState
 from app.db import make_web_pool
 from test_catalog_migration import fingerprint
 from psycopg.conninfo import make_conninfo
 prior=tmp_path/'through037';prior.mkdir();current=tmp_path/'through038';current.mkdir()
 for path in MIGRATIONS.glob('[0-9][0-9][0-9]_*.sql'):
  if path.name<'038_':shutil.copy2(path,prior/path.name)
  if path.name<'039_':shutil.copy2(path,current/path.name)
 db=create_fixture_database();state=None;pool=None;loop=asyncio.new_event_loop()
 try:
  apply_migrations(db,prior);state=seed_fixture(db)
  with db.admin_connection() as c:
   bid=c.execute('SELECT budget_id FROM ops.project_budget').fetchone()[0]
   for tenant in state.tenant_ids.values():
    c.execute('INSERT INTO ops.tenant_budgets(tenant_id,budget_id,allocated_cap_krw,local_cap_krw) VALUES(%s,%s,12500,12500)',(tenant,bid))
    c.execute('UPDATE portal.agent_configs SET settings=%s,enabled=true WHERE tenant_id=%s',(Jsonb({'name':'공통 Agent','description':'합성 설명','instructions':'지시문'}),tenant))
  pool=make_web_pool(db.runtime_dsn(),size=1);loop.run_until_complete(pool.open());loop.run_until_complete(pool.wait(timeout=5));f=FixtureState(db,state,loop,pool,make_conninfo(host='127.0.0.1',port=55432,dbname=db.name,user='mvp_bootstrap',passfile=str(db.cluster.passfile_path)),state.passwords)
  async def prepare():
   async with open_meter_pool(db.runtime_dsn('ai_meter')) as meter:
    ctx,old,newer,source,d=await two_versions(f,CallRepository(pool,meter,date(2026,10,1)));admin=await f.context('P-A','A');await d.call(admin,'retire',UUID(old['asset_id']),{'expected_revision':2},'mock')
    with db.admin_connection() as c:sid=str(c.execute('SELECT share_id FROM portal.asset_deployments WHERE publication_revision=2').fetchone()[0])
    row,_=await request(f,ctx,d,sid,expected_publication_revision=3);await decide(f,d,row['request_id']);await d.call(admin,'retire',UUID(old['asset_id']),{'expected_revision':4},'mock');return ctx,old,d
  ctx,old,d=f.run(prepare())
  with db.admin_connection() as c:before=fingerprint(c)
  assert apply_migrations(db,current)==['038_asset_rollback_history.sql']
  with db.admin_connection() as c:
   after=fingerprint(c);assert all(after[k]==val for k,val in before.items() if k!=('portal','asset_deployments'))
   projected=c.execute("SELECT count(*),md5(coalesce(string_agg((to_jsonb(t)-ARRAY['deployment_kind','source_request_id'])::text,'' ORDER BY (to_jsonb(t)-ARRAY['deployment_kind','source_request_id'])::text),'')) FROM portal.asset_deployments t").fetchone();assert projected==before['portal','asset_deployments']
  history=f.run(rpc(d,ctx,'history',old['asset_id']));assert [x['publication_revision'] for x in history['items']]==[5,4,2,1] and not history['history_complete']
  assert history['items'][0]['event_kind']=='current_state' and history['items'][0]['actor_id'] is None
  assert all(x['event_kind']=='approval_record' for x in history['items'][1:])
 finally:
  if pool:loop.run_until_complete(pool.close())
  loop.close();db.drop()
  if state:state.secret_path.unlink(missing_ok=True)
