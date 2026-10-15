"""Real loopback HTTP on upgraded marker clone; execution/index/provider disabled."""
from pathlib import Path
import json,os,shlex,subprocess,time,socket,re,hashlib
import httpx,psycopg
from scripts.devdb import DevCluster,_read_private
from scripts.migrate import FixtureDatabase,create_fixture_database
from app.auth.crypto import verify_password
from stage import ROOT,OUT,PRIVATE,save,snapshot,catalog

def main():
 cluster=DevCluster();identity=json.loads((OUT/'stage-identity.json').read_text());stage=FixtureDatabase(identity['destination_database'],cluster);primary=FixtureDatabase(identity['source_database'],cluster)
 env={k:v for k,v in os.environ.items() if not k.startswith(('PG','AI_'))};env['PGPASSFILE']=str(cluster.passfile_path)
 dump=PRIVATE/'upgraded-stage.pgdump'
 with dump.open('wb') as f:
  dump.chmod(0o600);subprocess.run(['/usr/local/bin/pg_dump','-h','127.0.0.1','-p','55432','-U','mvp_bootstrap','-d',stage.name,'-Fc'],env=env,stdout=f,stderr=subprocess.PIPE,check=True)
 clone=create_fixture_database();assert clone.name not in identity.values()
 res=subprocess.run(['/usr/local/bin/pg_restore','-h','127.0.0.1','-p','55432','-U','mvp_bootstrap','-d',clone.name,'--single-transaction','--exit-on-error',str(dump)],env=env,capture_output=True)
 if res.returncode:raise RuntimeError('VALIDATION_CLONE_RESTORE_FAILED')
 with clone.admin_connection() as c:
  clone.verify(c);c.execute('GRANT CONNECT ON DATABASE '+clone.name+' TO ai_web,ai_meter,ai_index');c.execute('ALTER DATABASE '+clone.name+' CONNECTION LIMIT -1')
 assert snapshot(clone)==snapshot(stage)
 with stage.admin_connection() as c:
  stage.verify(c);accounts=c.execute('SELECT login_id,password_hash,active FROM security.accounts ORDER BY login_id').fetchall()
 credentials=json.loads(_read_private(cluster.runtime/(primary.name+'-fixture-secrets.json')))['passwords'];result={'validation_database':clone.name,'stage_database':stage.name,'clone_exact_before_http':True,'accounts':[],'private_documents':[],'routes':[],'execution_enabled':False,'index_enabled':False,'paid_calls':0}
 for path in (ROOT/'docs/Obsidain/200.프로젝트실행/270.파일럿적용').glob('*계정*비공개*.md'):
  mapped={}
  for line in path.read_text().splitlines():
   if not line.startswith('|'):continue
   cells=[x.strip().strip('`') for x in line.strip('|').split('|')]
   if len(cells)>=2 and cells[0] in {a[0] for a in accounts}:mapped[cells[0]]=cells[1]
  checks=[{'login_id':login,'password_matches':verify_password(encoded,mapped[login]),'active':active} for login,encoded,active in accounts if login in mapped]
  result['private_documents'].append({'path':str(path.relative_to(ROOT)),'checked_accounts':len(checks),'matches':sum(x['password_matches'] for x in checks),'mismatches':[x['login_id'] for x in checks if not x['password_matches']]})
 # Verify runtime password values on source and stage; SCRAM verifier re-salting is allowed only by normal runner.
 role_checks=[]
 for db in (primary,stage):
  for role in ('ai_web','ai_index','ai_meter'):
   with psycopg.connect(db.runtime_dsn(role)) as c:role_checks.append({'database':db.name,'role':role,'connected':c.execute('SELECT current_database(),session_user').fetchone()==(db.name,role)})
 result['runtime_credential_connections']=role_checks
 sock=socket.socket();sock.bind(('127.0.0.1',0));port=sock.getsockname()[1];sock.close();assert port not in (8000,5173,5174)
 childenv={k:v for k,v in env.items() if not k.startswith(('PG','AI_'))};childenv['PYTHONPATH']=str(OUT)+':'+str(ROOT/'src/backend');childenv['AI_WEB_DSN']=clone.runtime_dsn()
 for line in _read_private(cluster.runtime/'app.env').splitlines():
  if line.startswith('AI_LOGIN_HMAC_SECRET='):childenv['AI_LOGIN_HMAC_SECRET']=shlex.split(line.split('=',1)[1])[0]
 factory=OUT/'validation_app.py';factory.write_text("from app.main import create_app as base\nfrom app.config import Settings\ndef create_app():\n return base(Settings(mode='mock',execution_enabled=False,index_enabled=False,openai_api_key=None))\n")
 log=PRIVATE/'validation-api.log';fd=os.open(log,os.O_WRONLY|os.O_CREAT|os.O_TRUNC,0o600);process=None
 try:
  with os.fdopen(fd,'w') as f:
   process=subprocess.Popen([str(ROOT/'src/backend/.venv/bin/python'),'-m','uvicorn','validation_app:create_app','--factory','--host','127.0.0.1','--port',str(port),'--no-access-log','--no-proxy-headers'],cwd=ROOT,env=childenv,stdout=f,stderr=f)
   url=f'http://127.0.0.1:{port}';deadline=time.monotonic()+20
   while time.monotonic()<deadline:
    try:
     response=httpx.get(url+'/api/v1/health',timeout=1)
     if response.status_code==200:break
    except httpx.HTTPError:pass
    if process.poll() is not None:raise RuntimeError('VALIDATION_API_EXITED')
    time.sleep(.1)
   else:raise RuntimeError('VALIDATION_API_TIMEOUT')
   result['health_status']=response.status_code
   headers={'Origin':'http://127.0.0.1:5173','Content-Type':'application/json','X-Requested-With':'ai-portal'}
   for login,encoded,active in accounts:
    password=credentials.get(login.upper());assert password and verify_password(encoded,password)
    with httpx.Client(base_url=url,headers=headers,timeout=10) as client:
     loginreply=client.post('/api/v1/auth/login',json={'login_id':login,'password':password});entry={'login_id':login,'active':active,'credential_hash_match':True,'login_status':loginreply.status_code};result['accounts'].append(entry)
     assert loginreply.status_code==(200 if active else 401)
     if not active:continue
     me=client.get('/api/v1/auth/me');entry['me_status']=me.status_code;assert me.status_code==200
     medata=me.json()['data'];entry['effective_capabilities']=medata.get('capabilities')
     # Obtain actual tenant IDs and effective role from current membership response.
     tenants=client.get('/api/v1/me/tenants');entry['tenants_status']=tenants.status_code;assert tenants.status_code==200
     data=tenants.json()['data'];items=data.get('items',data.get('tenants',[])) if isinstance(data,dict) else data
     entry['tenant_response_shape']=list(data) if isinstance(data,dict) else 'list'
     for member in items:
      tid=member.get('tenant_id');role=member.get('effective_role',member.get('role'));assert tid
      tenantheaders={'X-Tenant-ID':str(tid)}
      for route in ('/api/v1/catalog/assets','/api/v1/published-agents','/api/v1/published-agent-runs','/api/v1/documents','/api/v1/tools','/api/v1/workflows/catalog','/api/v1/admin/overview','/api/v1/admin/guardrails/policies','/api/v1/admin/guardrails/violations','/api/v1/admin/tool-approvals','/api/v1/admin/workflow-approvals','/api/v1/admin/data-imports'):
       reply=client.get(route,headers=tenantheaders);safe={'login_id':login,'role':role,'tenant_id':tid,'path':route,'status':reply.status_code}
       if reply.status_code>=400:safe['error_code']=reply.json().get('error',{}).get('code')
       expected=200
       if route in ('/api/v1/admin/guardrails/policies','/api/v1/admin/guardrails/violations') and role!='PADMIN':expected=403
       if route in ('/api/v1/admin/overview','/api/v1/admin/tool-approvals','/api/v1/admin/workflow-approvals') and role=='USER':expected=403
       safe['expected_status']=expected;safe['passed']=reply.status_code==expected;result['routes'].append(safe)
       assert safe['passed']
     # Logout preserves any baseline sessions; test clone is subsequently dropped.
     csrf=loginreply.json()['data']['csrf_token'];logout=client.post('/api/v1/auth/logout',headers={'X-CSRF-Token':csrf});entry['logout_status']=logout.status_code
   save('http-validation.json',result)
 finally:
  if process and process.poll() is None:
   process.terminate()
   try:process.wait(timeout=5)
   except subprocess.TimeoutExpired:process.kill();process.wait(timeout=5)
  with clone.admin_connection() as c:
   clone.verify(c);connections=c.execute('SELECT count(*) FROM pg_stat_activity WHERE datname=%s AND usename IN (%s,%s,%s)',(clone.name,'ai_web','ai_index','ai_meter')).fetchone()[0]
  result['child_stopped']=process is None or process.poll() is not None;result['pool_connections_after_stop']=connections
  result['stage_52_old_columns_still_exact']=snapshot(stage,json.loads((OUT/'upgraded-old-column-tables.json').read_text()))==json.loads((OUT/'upgraded-old-column-tables.json').read_text())
  result['primary_53_tables_still_exact']=snapshot(primary)==json.loads((OUT/'primary-pre-tables.json').read_text())
  clone.drop();result['validation_clone_removed']=True;save('http-validation.json',result)
 print('HTTP validation finished; no live settings changed; validation clone stopped/removed')
if __name__=='__main__':main()
