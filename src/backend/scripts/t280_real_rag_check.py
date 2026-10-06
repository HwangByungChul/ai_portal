"""One durable minimal real batch on the existing owned primary fixture.
No automatic paid retries; only synthetic source text. Default remains unchanged.
"""
from pathlib import Path
from uuid import UUID,uuid4,uuid5
from decimal import Decimal
import hashlib,json,os,time,subprocess,socket
import httpx
from pydantic import SecretStr
from psycopg.types.json import Jsonb
from scripts.devdb import DevCluster,_read_private
from scripts.migrate import FixtureDatabase,apply_migrations
from scripts.seed import NAMESPACE
from scripts.real_general_check import private_settings,save_private,data,stop_server,CheckError
from app.db import DB_MARKER
from app.main import create_app

BACKEND=Path(__file__).resolve().parents[1]
JOURNAL=BACKEND/'.runtime/T286-real-rag-journal.json'
RESULT=BACKEND/'.runtime/T286-real-rag-result.json'
PERIOD='2026-10-01'
TENANTS={x:UUID('10000000-0000-4000-8000-00000000000'+x.lower()) for x in ('A','B')}

def settings():
 c=DevCluster();d=FixtureDatabase(json.loads(_read_private(c.runtime/'active-fixture.json'))['database'],c)
 return private_settings(c,d).model_copy(update={'index_enabled':True,'index_dsn':SecretStr(d.runtime_dsn('ai_index')),'source_root':BACKEND/'.runtime/T286-real-sources'})

def snapshot(db):
 with db.admin_connection() as c:
  db.verify(c)
  rows=c.execute("SELECT t.fixture_label,b.allocated_cap_krw,b.local_cap_krw,b.accounted_krw,b.reserved_krw,b.active_slot FROM ops.tenant_budgets b JOIN security.tenants t USING(tenant_id) JOIN ops.project_budget p USING(budget_id) WHERE p.mode='real' AND p.period=%s ORDER BY t.fixture_label",(PERIOD,)).fetchall()
  calls=c.execute("SELECT call_id,mode,operation,state,slot_held,usage_snapshot FROM ops.call_attempts WHERE mode='real' ORDER BY call_id").fetchall()
  return {'budgets':[[str(x) for x in row] for row in rows],'calls':[{'call_id':str(row[0]),'mode':row[1],'operation':row[2],'state':row[3],'slot_held':row[4],'receipt':row[5]} for row in calls]}

def bootstrap(db):
 with db.admin_connection() as c:
  db.verify(c)
  with c.transaction():
   c.execute('SELECT pg_advisory_xact_lock(250002)')
   p=c.execute("SELECT budget_id,accounted_krw,reserved_krw,active_slot,stopped,stop_latch FROM ops.project_budget WHERE mode='real' AND period=%s FOR UPDATE",(PERIOD,)).fetchone()
   if not p or p[1]!=Decimal('.19') or p[2]!=0 or p[3]!=0 or p[4] or p[5]:raise CheckError('EXISTING_REAL_LEDGER_NOT_READY')
   a=c.execute('SELECT allocated_cap_krw,local_cap_krw,accounted_krw,reserved_krw,active_slot FROM ops.tenant_budgets WHERE budget_id=%s AND tenant_id=%s FOR UPDATE',(p[0],TENANTS['A'])).fetchone()
   if a!=(Decimal(500),Decimal(500),Decimal('.19'),Decimal(0),0):raise CheckError('EXISTING_A_ALLOCATION_NOT_READY')
   if c.execute('SELECT 1 FROM ops.tenant_budgets WHERE budget_id=%s AND tenant_id=%s',(p[0],TENANTS['B'])).fetchone():raise CheckError('B_ALREADY_ALLOCATED')
   actor=c.execute("SELECT a.user_id FROM security.accounts a JOIN security.memberships m USING(user_id) WHERE a.login_id='b-adm' AND a.active AND m.active AND m.role='TADMIN' AND m.tenant_id=%s",(TENANTS['B'],)).fetchone()
   if not actor:raise CheckError('SYNTHETIC_B_ADMIN_REQUIRED')
   c.execute('UPDATE ops.tenant_budgets SET allocated_cap_krw=300,local_cap_krw=300,revision=revision+1 WHERE budget_id=%s AND tenant_id=%s',(p[0],TENANTS['A']))
   c.execute('INSERT INTO ops.tenant_budgets(tenant_id,budget_id,allocated_cap_krw,local_cap_krw) VALUES(%s,%s,200,200)',(TENANTS['B'],p[0]))
   for tenant,amount,who in [(TENANTS['A'],'300',uuid5(NAMESPACE,'P-A')),(TENANTS['B'],'200',actor[0])]:
    c.execute("INSERT INTO ops.audit_events(event_id,scope_kind,tenant_id,actor_id,action,result,revisions) VALUES(%s,'tenant',%s,%s,'real_representative_allocation','ok',%s)",(uuid4(),tenant,who,Jsonb({'mode':'real','allocated_cap_krw':amount,'representative_total_krw':'500','reason':'authorized_owned_synthetic_AB_check'})))

def run():
 if JOURNAL.exists():raise CheckError('REAL_BATCH_ALREADY_RECORDED')
 c=DevCluster();prior=c.status()['state'];process=log=None;original=[];journal=None;result={'status':'preflight','paid_retry_count':0,'paid_call_limit':8,'representative_cap_krw':'500','reservation_bound_krw':'15.36'}
 config_hash=hashlib.sha256((c.runtime/'app.env').read_bytes()).hexdigest()
 if prior!='running':c.start()
 d=FixtureDatabase(json.loads(_read_private(c.runtime/'active-fixture.json'))['database'],c)
 try:
  with d.admin_connection() as conn:d.verify(conn)
  apply_migrations(d);s=settings();result['before']=snapshot(d)
  # Read-only access checks; no completion or embedding is sent here.
  with httpx.Client(timeout=10,trust_env=False,headers={'Authorization':'Bearer '+s.openai_api_key.get_secret_value()}) as key_client:
   result['model_access']={model:key_client.get('https://api.openai.com/v1/models/'+model).status_code for model in ('gpt-4o-mini','text-embedding-3-small')}
  if set(result['model_access'].values())!={200}:raise CheckError('MODEL_ACCESS_NOT_READY')
  journal={'kind':'T286-one-primary-real-rag-batch','database':d.name,'marker':DB_MARKER,'status':'started','requests':[]}
  from scripts.devdb import _write_private
  _write_private(JOURNAL,json.dumps(journal));save_private(JOURNAL,journal)
  bootstrap(d)
  with socket.socket() as probe:probe.bind(('127.0.0.1',8000))
  env={k:v for k,v in os.environ.items() if not k.startswith(('AI_','PG','OPENAI_'))}
  log=os.fdopen(os.open(c.runtime/'T286-real-native-private.log',os.O_WRONLY|os.O_CREAT|os.O_TRUNC,0o600),'w')
  code="from scripts.t280_real_rag_check import settings\nfrom app.main import create_app\nimport uvicorn\nuvicorn.run(create_app(settings()),host='127.0.0.1',port=8000,access_log=False,log_level='critical')"
  process=subprocess.Popen([str(BACKEND/'.venv/bin/python'),'-c',code],cwd=BACKEND,env=env,stdout=log,stderr=log)
  deadline=time.monotonic()+20
  while time.monotonic()<deadline:
   if process.poll() is not None:raise CheckError('NATIVE_START_FAILED')
   try:
    if httpx.get('http://127.0.0.1:8000/api/v1/health',trust_env=False,timeout=.2).status_code==200:break
   except httpx.HTTPError:pass
   time.sleep(.1)
  else:raise CheckError('NATIVE_START_TIMEOUT')
  passwords=json.loads(_read_private(c.runtime/(d.name+'-fixture-secrets.json')))['passwords']
  transport={'Origin':'http://127.0.0.1:5173','X-Requested-With':'ai-portal'}
  def login(client,actor,tenant):
   auth=data(client.post('/api/v1/auth/login',headers=transport,json={'login_id':actor.lower(),'password':passwords[actor]}));return transport|{'X-CSRF-Token':auth['csrf_token'],'X-Tenant-ID':str(TENANTS[tenant])}
  def terminal(client,h,path):
   end=time.monotonic()+185
   while time.monotonic()<end:
    v=data(client.get('/api/v1'+path,headers=h))
    if v.get('is_terminal') or v.get('terminal') or v.get('state') in ('completed','failed','needs_review','cancelled','interrupted','blocked'):return v
    time.sleep(1)
   raise CheckError('TERMINAL_UNCONFIRMED')
  for tenant,team in [('A','심사1팀'),('B','심사2팀')]:
   with httpx.Client(base_url='http://127.0.0.1:8000',timeout=10,trust_env=False) as client:
    h=login(client,tenant+'-ADM',tenant)
    agent=data(client.get('/api/v1/admin/agents/rules_rag',headers=h));original.append((tenant,agent['enabled']))
    if not agent['enabled']:data(client.put('/api/v1/admin/agents/rules_rag/availability',headers=h,json={'enabled':True,'expected_revision':agent['config_version']}))
    record={'operation':'upload','tenant':tenant,'client_id':str(uuid4()),'status':'admitting'};journal['requests'].append(record);save_private(JOURNAL,journal)
    meta={'client_upload_id':record['client_id'],'title':'T286 합성 '+tenant+' 규정','visibility':'org','reader_ids':[],'media_type':'text/plain'}
    raw=('여신심사의 담당 부서는 '+team+'이다.\n').encode()
    ids=data(client.post('/api/v1/admin/documents',headers=h,files={'metadata':(None,json.dumps(meta),'application/json'),'file':('synthetic.txt',raw,'text/plain')}),allowed=(202,));record.update(ids);save_private(JOURNAL,journal)
    job=terminal(client,h,'/admin/jobs/'+ids['job_id']);record['status']=job['state'];save_private(JOURNAL,journal)
    if job['state']!='completed':raise CheckError('REAL_DOCUMENT_NOT_PUBLISHED')
    h=login(client,tenant+'-U1',tenant)
    for agent_key,prompt in [('general','AI 포털의 용도를 한 문장으로 설명해 주세요.'),('rules_rag','여신심사 담당 부서는?')]:
     record={'operation':agent_key,'tenant':tenant,'client_send_id':str(uuid4()),'status':'admitting'};journal['requests'].append(record);save_private(JOURNAL,journal)
     body={'agent_key':agent_key,'client_send_id':record['client_send_id'],'prompt':prompt}
     if agent_key=='rules_rag':body['document_refs']=[{k:ids[k] for k in ('document_id','version_id')}]
     view=data(client.post('/api/v1/runs',headers=h,json=body),allowed=(200,202));record['run_id']=view['run_id'];save_private(JOURNAL,journal)
     view=terminal(client,h,'/runs/'+view['run_id']);record.update(state=view['state'],usage_status=view['usage_status'],error_code=view['error_code']);save_private(JOURNAL,journal)
     if view['state']!='completed' or view['usage_status']!='final':raise CheckError('REAL_RUN_NOT_COMPLETED')
     if agent_key=='rules_rag':
      record['answer_has_expected_team']=team in (view.get('result') or {}).get('text','');save_private(JOURNAL,journal)
      if not record['answer_has_expected_team']:raise CheckError('REAL_PROOF_ANSWER_MISMATCH')
  result['status']='pass'
 except Exception as e:
  result['status']='blocked';result['safe_error_code']=str(e) if isinstance(e,CheckError) else type(e).__name__
 finally:
  # Restore current administrative availability through the authenticated API.
  if process and process.poll() is None:
   try:
    for tenant,enabled in original:
     with httpx.Client(base_url='http://127.0.0.1:8000',timeout=10,trust_env=False) as client:
      h=login(client,tenant+'-ADM',tenant);agent=data(client.get('/api/v1/admin/agents/rules_rag',headers=h))
      if agent['enabled']!=enabled:data(client.put('/api/v1/admin/agents/rules_rag/availability',headers=h,json={'enabled':enabled,'expected_revision':agent['config_version']}))
    result['rag_availability_restored']=True
   except Exception:result['rag_availability_restored']=False
   stop_server(process,log)
  result['after']=snapshot(d);result['default_configuration_unchanged']=hashlib.sha256((c.runtime/'app.env').read_bytes()).hexdigest()==config_hash
  if journal:journal['status']=result['status'];save_private(JOURNAL,journal);result['requests']=journal['requests']
  save_private(RESULT,result)
  if prior!='running':c.stop()
 return result

if __name__=='__main__':
 try:
  v=run();print(json.dumps({k:v[k] for k in ('status','paid_retry_count','paid_call_limit','default_configuration_unchanged') if k in v}|{'safe_error_code':v.get('safe_error_code')}));raise SystemExit(0 if v['status']=='pass' else 1)
 except CheckError as e:print(json.dumps({'status':'blocked','safe_error_code':str(e)}));raise SystemExit(1)
