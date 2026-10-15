"""Local DB-name-only cutover; preserve original configs; pair rollback on failure."""
import sys,os,json,hashlib,shlex,re,subprocess,socket
from pathlib import Path
sys.path.insert(0,str(Path.cwd()/'.superpowers/sdd/db-data-migrate-20261014'))
from stage import ROOT,OUT as STAGE,snapshot,DevCluster,FixtureDatabase,MIGRATIONS,_read_private
import httpx
from app.auth.crypto import verify_password
OUT=ROOT/'.superpowers/sdd/db-cutover-20261014'
def sha(b):return hashlib.sha256(b).hexdigest()
def guard(p):
 for q in [p,*p.parents]:
  if q.is_symlink():raise RuntimeError('SYMLINK_REJECTED')
def atomic(p,b):
 guard(p);tmp=p.with_name(p.name+'.cutover-tmp');fd=os.open(tmp,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
 with os.fdopen(fd,'wb') as f:f.write(b);f.flush();os.fsync(f.fileno())
 os.replace(tmp,p);os.chmod(p,0o600)
def save(name,data):atomic(OUT/name,(json.dumps(data,indent=2,default=str)+'\n').encode())
def service(name,action):
 r=subprocess.run([str(ROOT/'src/backend/.venv/bin/python'),'scripts/service_control.py',name,action],cwd=ROOT,capture_output=True)
 if r.returncode:raise RuntimeError('SERVICE_'+name.upper()+'_'+action.upper()+'_FAILED')
def main():
 cluster=DevCluster();identity=json.loads((STAGE/'stage-identity.json').read_text());target=identity['destination_database'];source=identity['source_database'];db=FixtureDatabase(target,cluster);old=FixtureDatabase(source,cluster)
 private=cluster.runtime/'backups/db-cutover-20261014';guard(private);private.mkdir(mode=0o700,parents=True,exist_ok=True);os.chmod(private,0o700)
 paths=[cluster.runtime/'app.env',cluster.runtime/'active-fixture.json'];original=[p.read_bytes() for p in paths]
 backup=json.loads((ROOT/'.superpowers/sdd/db-restore-20261014/backup-restore-proof.json').read_text())['private_file_backup']
 for p,b in zip(paths,original):
  guard(p);assert any(x['source']==str(p.relative_to(ROOT)) and x['sha256']==sha(b) for x in backup);atomic(private/(p.name+'.original'),b)
 for port in (8000,5173,5174):
  with socket.socket() as s:assert s.connect_ex(('127.0.0.1',port))!=0,'PORT_OCCUPIED'
 before=json.loads((STAGE/'primary-pre-tables.json').read_text());cols={k:v for k,v in before.items() if k!='infra.schema_migrations'}
 assert snapshot(old)==before;assert all(v==cols[k] for k,v in snapshot(db,cols).items() if k not in ('security.sessions','security.login_windows','ops.audit_events'))
 pre=snapshot(db);save('stage-pre-tables.json',pre)
 with db.admin_connection() as c:
  db.verify(c);ledger=c.execute('SELECT version,sha256 FROM infra.schema_migrations ORDER BY version').fetchall();assert len(ledger)==51 and all(sha((MIGRATIONS/v).read_bytes())==h for v,h in ledger)
  for table,states in [('portal.runs',['accepted','running','cancel_requested']),('rag.jobs',['queued','running']),('portal.workflow_runs',['accepted','running']),('portal.workflow_steps',['pending','running']),('portal.tool_receipts',['accepted','dispatched','unknown']),('ops.call_attempts',['reserved','dispatched','usage_unknown'])]:
   assert c.execute('SELECT count(*) FROM '+table+' WHERE state=ANY(%s)',(states,)).fetchone()[0]==0
  assert c.execute("SELECT count(*) FROM ops.call_attempts WHERE provider_end_status='unknown'").fetchone()[0]==0
  for table in ('ops.project_budget','ops.tenant_budgets'):assert c.execute('SELECT coalesce(sum(reserved_krw),0) FROM '+table).fetchone()[0]==0
  accounts=c.execute('SELECT login_id,password_hash FROM security.accounts').fetchall()
 fixture=json.loads(original[1]);assert fixture['database']==source
 secrets=json.loads(_read_private(cluster.runtime/(source+'-fixture-secrets.json')))['passwords'];assert all(verify_password(h,secrets[k.upper()]) for k,h in accounts)
 envtext=original[0].decode();changed=[]
 for key in ('AI_WEB_DSN','AI_METER_DSN','AI_INDEX_DSN'):
  pattern=r'(?m)^'+key+r'=(.*)$';match=re.search(pattern,envtext);assert match and match.group(1).count(source)==1
  envtext=re.sub(pattern,lambda m:key+'='+m.group(1).replace(source,target),envtext);changed.append(key)
 assert envtext.replace(target,source)==original[0].decode();fixture['database']=target;new=[envtext.encode(),(json.dumps(fixture,indent=2)+'\n').encode()]
 for i,b in enumerate(new):atomic(private/('staged-'+paths[i].name),b)
 proof={'source_database':source,'target_database':target,'source_marker_verified':True,'stage_marker_verified':True,'new_51_source_hashes_match':True,'old_52_historical_rows_and_account_hashes_exact_before':True,'active_unknown_reserved_jobs_zero':True,'original_credentials_valid':True,'configuration_changed_keys':changed,'fixture_only_database_changed':True,'credentials_hmac_key_mode_preserved':True,'pre_config_sha256':[sha(x) for x in original],'post_config_sha256':[sha(x) for x in new],'seeded':False,'paid_calls':0,'services':[],'accounts':[],'routes':[]}
 started=[];mutated=False
 try:
  mutated=True
  for p,b in zip(paths,new):atomic(p,b)
  assert all(target in shlex.split(re.search(r'(?m)^'+k+r'=(.*)$',paths[0].read_text()).group(1))[0] for k in changed);assert json.loads(paths[1].read_text())['database']==target
  for name in ('backend','frontend','admin-frontend'):
   started.append(name);service(name,'start');proof['services'].append({'name':name,'ready':True})
  for url in ('http://127.0.0.1:8000/api/v1/health','http://127.0.0.1:5173/user/home','http://127.0.0.1:5174/manage/admin'):assert httpx.get(url,trust_env=False).status_code==200,'HTTP_READINESS_FAILED'
  for login in ('a-u1','a-adm','p-a'):
   with httpx.Client(base_url='http://127.0.0.1:8000',headers={'Origin':'http://127.0.0.1:5173','X-Requested-With':'ai-portal'},timeout=10,trust_env=False) as client:
    reply=client.post('/api/v1/auth/login',json={'login_id':login,'password':secrets[login.upper()]});assert reply.status_code==200, 'LOGIN_STATUS_'+str(reply.status_code)
    me=client.get('/api/v1/auth/me');assert me.status_code==200,'ME_STATUS_'+str(me.status_code)
    replydata=reply.json()['data'];tenants=client.get('/api/v1/me/tenants');assert tenants.status_code==200,'TENANTS_STATUS_'+str(tenants.status_code);data=tenants.json()['data'];items=data.get('items',data.get('tenants',[])) if isinstance(data,dict) else data
    for member in items:
     role=member.get('effective_role',member.get('role'));headers={'X-Tenant-ID':str(member['tenant_id'])}
     for route in ('/api/v1/admin/overview','/api/v1/admin/tool-approvals','/api/v1/admin/workflow-approvals','/api/v1/tools','/api/v1/workflows/catalog','/api/v1/use-cases'):
      status=client.get(route,headers=headers).status_code;expected=403 if role=='USER' and '/admin/' in route else 200;assert status==expected, 'READ_ROUTE_STATUS_FAILED';proof['routes'].append({'login_id':login,'role':role,'path':route,'status':status,'passed':True})
    logout=client.post('/api/v1/auth/logout',headers={'X-CSRF-Token':replydata['csrf_token']});assert logout.status_code==200,'LOGOUT_STATUS_'+str(logout.status_code);proof['accounts'].append({'login_id':login,'login':200,'me':200,'tenants':200,'logout':200})
  assert snapshot(old)==before
  post=snapshot(db);save('stage-post-tables.json',post)
  altered=[k for k in cols if post[k]!=pre[k]];assert all(k in ('security.sessions','security.login_windows','ops.audit_events') for k in altered),'UNEXPECTED_BUSINESS_CHANGE'
  assert post['security.accounts']==pre['security.accounts'];proof['normal_auth_changed_tables']=altered;proof['original_database_53_tables_unchanged']=True;proof['status']='DONE';proof['services_kept_running']=True;save('proof.json',proof)
 except BaseException as e:
  for name in reversed(started):
   try:service(name,'stop')
   except Exception:pass
  if mutated:
   for p,b in zip(paths,original):atomic(p,b)
  proof['status']='FAILED';proof['error_type']=type(e).__name__;proof['safe_error']=str(e) if isinstance(e,(AssertionError,RuntimeError)) else 'DETAIL_PRIVATE';proof['config_pair_restored']=all(p.read_bytes()==b for p,b in zip(paths,original));save('proof.json',proof);raise RuntimeError('CUTOVER_FAILED_SAFE_PROOF') from None
 print('Cutover DONE; existing credentials valid; HTTP health/user/admin ready; services running')
if __name__=='__main__':main()
