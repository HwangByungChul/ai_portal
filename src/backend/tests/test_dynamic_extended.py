from uuid import UUID,uuid4
from datetime import date
import asyncio,time,shutil
import pytest
from psycopg.types.json import Jsonb
from pydantic import SecretStr
from fastapi.testclient import TestClient
from app.main import create_app
from app.ai.repository import CallRepository,ExecutionError
from app.ai.gateway import AiGateway
from app.ai.providers import MockProvider
from app.ai.rag_provider import RagMockProvider
from app.builder.trials import TrialRepository
from app.builder.execution import TrialExecutor
from app.assets.published import PublishedRepository
from app.assets.deployments import DeploymentRepository
from app.documents.repository import DocumentRepository
from app.documents.storage import SourceStorage
from app.documents.embedding import MockEmbeddingProvider
from app.execution.rag import RagExecutor
from app.db import open_meter_pool,open_web_pool
from app.errors import AppError
from test_operations import ops_rows,headers
from test_published_agents import publish as publish_agent,start
from test_asset_deployments import request,decide
from test_builder_shares import share,setup
from test_builder_trials import admit
from test_builder_evaluations import spec,save
from test_document_sharing import publish
from test_document_ingest import metadata

@pytest.mark.parametrize('case',['org','empty','private','withdrawn'])
def test_dynamic_rag_exact_user_source_guard_and_zero_empty_dispatch(ops_rows,tmp_path,case):
 f=ops_rows
 async def check():
  async with open_meter_pool(f.db.runtime_dsn('ai_meter')) as meter:
   repo=CallRepository(f.pool,meter,date(2026,10,1));docs=DocumentRepository(f.pool,SourceStorage(tmp_path/'sources'),'x'*40);owner=await f.context('A-ADM','A');reviewer=await f.context('P-A','A');refs=[]
   if case!='empty':
    ids=await publish(f,docs,owner,metadata(visibility='private',owner_user_id=owner.user_id,reader_ids=[reviewer.user_id]) if case=='private' else None);refs=[{k:ids[k] for k in ('document_id','version_id')}]
   ctx,saved,payload,data=await admit(f,repo,'rules_rag',refs,'generate');t=TrialRepository(f.pool);engine=TrialExecutor(repo,AiGateway(repo,MockProvider()),RagExecutor(repo,docs,MockEmbeddingProvider(),RagMockProvider()));ticket=await repo.claim(ctx,UUID(data['run_id']),'mock');await engine.finish(ticket,await engine.execute(ticket))
   c=await save(t,ctx,saved,spec(payload,expected='insufficient_evidence' if case=='empty' else 'answer',sources=refs));e=await t.rpc(ctx,'builder_case_evaluate',(ctx.session_id,ctx.tenant_id,UUID(c['case_id']),UUID(data['run_id'])));assert e['passed']
   s=await share(t,ctx,body={'client_request_id':str(uuid4()),'run_id':data['run_id'],'evaluation_id':e['evaluation_id'],'consent':True});d=DeploymentRepository(f.pool);req,_=await request(f,ctx,d,s['share_id']);await decide(f,d,req['request_id']);user=await f.context('A-U1','A')
   if case=='private':
    with pytest.raises(AppError) as denied:await start(f,user,saved,payload['values'])
    assert denied.value.status==404;return
   run=await start(f,user,saved,payload['values']);ticket=await repo.claim(user,UUID(run['run_id']),'mock')
   if case=='withdrawn':
    await docs.delete(owner,UUID(ids['document_id']),1)
    with pytest.raises(ExecutionError):await repo.heartbeat(ticket)
    with pytest.raises(AppError):await PublishedRepository(f.pool).read(user,UUID(run['run_id']))
    await repo.fail(ticket,'EXECUTION_BLOCKED');return
   result=await engine.execute(ticket);await engine.finish(ticket,result);view=await PublishedRepository(f.pool).read(user,UUID(run['run_id']));assert view['content_status']=='final'
   with f.db.admin_connection() as c:assert c.execute('SELECT count(*) FROM ops.call_attempts WHERE run_id=%s',(UUID(run['run_id']),)).fetchone()[0]==(0 if case=='empty' else 2)
   if case=='empty':assert result['answer_kind']=='insufficient_evidence'
   else:assert result['evidence'] and all(str(x['version_id'])==ids['version_id'] for x in result['evidence'])
 f.run(check())

def test_competing_requests_only_one_publication_cas_winner(ops_rows):
 f=ops_rows
 async def check():
  async with open_meter_pool(f.db.runtime_dsn('ai_meter')) as meter:
   ctx,saved,t,b,e=await setup(f,CallRepository(f.pool,meter,date(2026,10,1)));s=await share(t,ctx,body=b);d=DeploymentRepository(f.pool);a,_=await request(f,ctx,d,s['share_id']);b,_=await request(f,ctx,d,s['share_id']);admin=await f.context('P-A','A')
   async def approve(row):
    async with open_web_pool(f.db.runtime_dsn('ai_web')) as pool:return await DeploymentRepository(pool).call(admin,'decide',UUID(row['request_id']),{'decision':'approve','expected_revision':1,'comment':'독립 확인','quality_reviewed':True,'security_reviewed':True},'mock')
   results=await asyncio.gather(approve(a),approve(b),return_exceptions=True);assert sum(isinstance(x,dict) for x in results)==1;assert sum(isinstance(x,AppError) and x.status==409 for x in results)==1
   with f.db.admin_connection() as c:
    assert c.execute('SELECT count(*) FROM portal.asset_publications').fetchone()[0]==1
    assert c.execute("SELECT count(*) FROM portal.asset_deployments WHERE status='approved'").fetchone()[0]==1
 f.run(check())

def test_published_http_csrf_strict_input_worker_owner_and_no_draft_execution(ops_rows,auth_settings,login):
 f=ops_rows
 async def prepare():
  async with open_meter_pool(f.db.runtime_dsn('ai_meter')) as meter:return await publish_agent(f,CallRepository(f.pool,meter,date(2026,10,1)))
 _,saved,_,_=f.run(prepare());settings=auth_settings.model_copy(update={'execution_enabled':True,'meter_dsn':SecretStr(f.db.runtime_dsn('ai_meter'))})
 with TestClient(create_app(settings),base_url='http://127.0.0.1:8000',client=('127.0.0.1',50000)) as client:
  csrf=login(client,'A-U1')['csrf_token'];path='/api/v1/published-agents/'+saved['asset_id']+'/runs';body={'client_send_id':str(uuid4()),'version_id':saved['version_id'],'expected_publication_revision':1,'values':{'audience':'이용자','rule':'기준','question':'업무 질문'}}
  assert client.post(path,headers=headers(f),json=body).status_code==403
  assert client.post(path,headers=headers(f,'A',csrf),json=body|{'owner_user_id':str(f.actor_ids['A-ADM'])}).status_code==422
  assert client.post(path,headers=headers(f,'A',csrf),json=body|{'expected_publication_revision':2}).status_code==409
  assert client.post('/api/v1/runs',headers=headers(f,'A',csrf),json={'client_send_id':str(uuid4()),'agent_key':'general','asset_id':saved['asset_id'],'prompt':'질문'}).status_code==404
  accepted=client.post(path,headers=headers(f,'A',csrf),json=body);assert accepted.status_code==202;run=accepted.json()['data']['run_id']
  for _ in range(200):
   reply=client.get('/api/v1/published-agent-runs/'+run,headers=headers(f));assert reply.status_code==200;data=reply.json()['data']
   if data['is_terminal']:break
   time.sleep(.02)
  assert data['content_status']=='final' and data['usage_status']=='final' and reply.headers['cache-control']=='no-store'
  assert client.post(path,headers=headers(f,'A',csrf),json=body).json()['data']['replayed']
  login(client,'A-U2');assert client.get('/api/v1/published-agent-runs/'+run,headers=headers(f)).status_code==404

def test_036_037_preserve_prior_rows_checksums_raw_denial_and_rerun(owned_cluster,tmp_path):
 from scripts.migrate import MIGRATIONS,create_fixture_database,apply_migrations
 from scripts.seed import seed_fixture
 from test_catalog_migration import fingerprint
 old=tmp_path/'old';old.mkdir()
 for p in MIGRATIONS.glob('[0-9][0-9][0-9]_*.sql'):
  if p.name<'036_':shutil.copy2(p,old/p.name)
 db=create_fixture_database();state=None
 try:
  apply_migrations(db,old);state=seed_fixture(db)
  with db.admin_connection() as c:before=fingerprint(c);hashes=dict(c.execute('SELECT version,sha256 FROM infra.schema_migrations').fetchall())
  through=tmp_path/'through037';through.mkdir()
  for path in MIGRATIONS.glob('[0-9][0-9][0-9]_*.sql'):
   if path.name<'038_':shutil.copy2(path,through/path.name)
  assert apply_migrations(db,through)==['036_asset_deployments.sql','037_published_agent_execution.sql']
  with db.admin_connection() as c:
   after=fingerprint(c);assert len(after)==50 and all(after[k]==v for k,v in before.items());assert dict(c.execute("SELECT version,sha256 FROM infra.schema_migrations WHERE version<'036_'").fetchall())==hashes
   for table in ('asset_deployments','asset_publications','published_agent_runs'):
    assert after['portal',table][0]==0
    assert c.execute('SELECT relrowsecurity AND relforcerowsecurity FROM pg_class WHERE oid=%s::regclass',('portal.'+table,)).fetchone()[0]
    for role in ('ai_web','ai_index','ai_meter'):assert not c.execute('SELECT has_table_privilege(%s,%s,%s)',(role,'portal.'+table,'SELECT,INSERT,UPDATE,DELETE')).fetchone()[0]
  assert apply_migrations(db,through)==[]
  with db.admin_connection() as c:assert fingerprint(c)==after
 finally:
  db.drop()
  if state:state.secret_path.unlink(missing_ok=True)

@pytest.mark.parametrize('case',['cancel','retire','retire_before_read'])
def test_dynamic_manager_cancel_unknown_cost_and_retired_late_result(ops_rows,case):
 from app.execution.manager import ExecutionManager
 from app.execution.stream import StreamHub
 from app.conversations.repository import ConversationRepository
 from app.ai.types import ProviderOutcome,UsageReceipt
 f=ops_rows
 async def check():
  async with open_web_pool(f.db.runtime_dsn(),size=4) as web,open_meter_pool(f.db.runtime_dsn('ai_meter')) as meter:
   repo=CallRepository(web,meter,date(2026,10,1));owner,saved,b,d=await publish_agent(f,repo);ctx=await f.context('A-U1','A')
   if case=='retire_before_read':
    data=await start(f,ctx,saved,{'audience':'담당','rule':'규정','question':'절차'});run=UUID(data['run_id'])
    ticket=await repo.claim(ctx,run,'mock');await d.call(await f.context('P-A','A'),'retire',UUID(saved['asset_id']),{'expected_revision':1},'mock')
    with pytest.raises(ExecutionError) as blocked:await TrialExecutor(repo,AiGateway(repo,MockProvider()),None).execute(ticket)
    assert blocked.value.code=='EXECUTION_BLOCKED';assert await repo.fail(ticket,blocked.value.code);return
   class Controlled(MockProvider):
    def __init__(self):self.entered=asyncio.Event();self.release=asyncio.Event();self.calls=0
    async def generate(self,claim,messages,on_delta):
     self.calls+=1;self.entered.set();await self.release.wait();return ProviderOutcome('합성 최종 답변',UsageReceipt(120,40,160,'gpt-4o-mini','default',None),'observed',None)
   provider=Controlled();manager=ExecutionManager(repo,provider,'mock',StreamHub());await manager.start()
   try:
    data=await start(f,ctx,saved,{'audience':'담당','rule':'규정','question':'절차'});run=UUID(data['run_id'])
    manager.notify(ctx,run);await asyncio.wait_for(provider.entered.wait(),3)
    if case=='cancel':
     state=await PublishedRepository(web).read(ctx,run);await ConversationRepository(web).cancel(ctx,run,state['revision'],uuid4());manager.cancel(ctx,run)
    else:await d.call(await f.context('P-A','A'),'retire',UUID(saved['asset_id']),{'expected_revision':1},'mock');provider.release.set()
    await asyncio.wait_for(asyncio.gather(*list(manager.tasks.values())),5)
    with f.db.admin_connection() as c:
     assert c.execute('SELECT state FROM portal.runs WHERE run_id=%s',(run,)).fetchone()[0]==('cancelled' if case=='cancel' else 'failed')
     assert c.execute('SELECT result FROM portal.published_agent_runs WHERE run_id=%s',(run,)).fetchone()[0] is None
     assert c.execute('SELECT state FROM ops.call_attempts WHERE run_id=%s',(run,)).fetchone()[0]==('usage_unknown' if case=='cancel' else 'settled')
     assert provider.calls==1
   finally:await manager.close()
 f.run(check())

def test_same_request_concurrent_decisions_share_one_receipt(ops_rows):
 f=ops_rows
 async def check():
  async with open_meter_pool(f.db.runtime_dsn('ai_meter')) as meter:
   ctx,saved,t,b,e=await setup(f,CallRepository(f.pool,meter,date(2026,10,1)));s=await share(t,ctx,body=b);d=DeploymentRepository(f.pool);row,_=await request(f,ctx,d,s['share_id']);admin=await f.context('P-A','A')
   async def approve():
    async with open_web_pool(f.db.runtime_dsn('ai_web')) as pool:return await DeploymentRepository(pool).call(admin,'decide',UUID(row['request_id']),{'decision':'approve','expected_revision':1,'comment':'별도 검토','quality_reviewed':True,'security_reviewed':True},'mock')
   results=await asyncio.gather(approve(),approve());assert sum(x['replayed'] for x in results)==1 and all(x['publication_revision']==1 for x in results)
 f.run(check())
