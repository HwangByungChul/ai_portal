"""Reviewed-only staging: never writes primary/config; private restore limited to new owned DB."""
from pathlib import Path
import os,json,hashlib,subprocess,shutil
from psycopg import sql
from scripts.devdb import DevCluster,_read_private
from scripts.migrate import FixtureDatabase,create_fixture_database,apply_migrations,MIGRATIONS
from app.db import DB_MARKER
ROOT=Path.cwd();OUT=ROOT/'.superpowers/sdd/db-data-migrate-20261014';PRIVATE=ROOT/'src/backend/.runtime/backups/db-restore-20261014'
def save(name,value): (OUT/name).write_text(json.dumps(value,indent=2,default=str))
def snapshot(db,columns=None):
 with db.admin_connection() as c:
  db.verify(c)
  with c.transaction():
   c.execute('SET TRANSACTION READ ONLY')
   tables=c.execute("SELECT schemaname,tablename FROM pg_tables WHERE schemaname NOT IN ('pg_catalog','information_schema') ORDER BY 1,2").fetchall()
   result={}
   for s,t in tables:
    key=s+'.'+t
    if columns is not None and key not in columns: continue
    cols=columns[key]['columns'] if columns else [r[0] for r in c.execute('SELECT column_name FROM information_schema.columns WHERE table_schema=%s AND table_name=%s ORDER BY ordinal_position',(s,t))]
    rows=c.execute(sql.SQL('SELECT to_jsonb(x)::text FROM (SELECT {} FROM {}.{}) x').format(sql.SQL(',').join(map(sql.Identifier,cols)),sql.Identifier(s),sql.Identifier(t))).fetchall()
    hashes=sorted(hashlib.sha256(r[0].encode()).hexdigest() for r in rows)
    result[key]={'count':len(rows),'columns':cols,'digest':hashlib.sha256('\n'.join(hashes).encode()).hexdigest()}
   return result
CAT_QUERIES={
 'tables':"SELECT n.nspname,c.relname,pg_get_userbyid(c.relowner),c.relrowsecurity,c.relforcerowsecurity,c.relacl::text FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace WHERE n.nspname IN ('infra','security','portal','ops','rag') AND c.relkind IN ('r','S') ORDER BY 1,2",
 'constraints':"SELECT n.nspname,c.relname,k.conname,k.contype,k.convalidated,k.condeferrable,k.condeferred,pg_get_constraintdef(k.oid) FROM pg_constraint k JOIN pg_class c ON c.oid=k.conrelid JOIN pg_namespace n ON n.oid=c.relnamespace WHERE n.nspname IN ('infra','security','portal','ops','rag') ORDER BY 1,2,3",
 'policies':"SELECT schemaname,tablename,policyname,permissive,roles::text,cmd,qual,with_check FROM pg_policies WHERE schemaname IN ('infra','security','portal','ops','rag') ORDER BY 1,2,3",
 'triggers':"SELECT n.nspname,c.relname,t.tgname,t.tgenabled,pg_get_triggerdef(t.oid) FROM pg_trigger t JOIN pg_class c ON c.oid=t.tgrelid JOIN pg_namespace n ON n.oid=c.relnamespace WHERE NOT t.tgisinternal AND n.nspname IN ('security','portal','ops','rag') ORDER BY 1,2,3",
 'functions':"SELECT n.nspname,p.proname,pg_get_function_identity_arguments(p.oid),pg_get_userbyid(p.proowner),p.prosecdef,p.proacl::text,p.proconfig::text,md5(pg_get_functiondef(p.oid)) FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace WHERE p.prokind='f' AND n.nspname IN ('security','portal','ops','rag') ORDER BY 1,2,3",
 'column_grants':"SELECT table_schema,table_name,column_name,grantee,privilege_type,is_grantable FROM information_schema.column_privileges WHERE table_schema IN ('security','portal','ops','rag') ORDER BY 1,2,3,4,5",
 'roles':"SELECT rolname,rolcanlogin,rolsuper,rolbypassrls,rolinherit,rolcreatedb,rolcreaterole,rolreplication,md5(coalesce(rolpassword,'')) FROM pg_authid WHERE rolname IN ('ai_owner','ai_policy_executor','ai_web','ai_index','ai_meter') ORDER BY 1",
 'sequences':"SELECT schemaname,sequencename,sequenceowner,data_type,start_value,min_value,max_value,increment_by,cycle,cache_size,last_value FROM pg_sequences WHERE schemaname IN ('security','portal','ops','rag') ORDER BY 1,2"}
def catalog(db):
 with db.admin_connection() as c:
  db.verify(c)
  with c.transaction():
   c.execute('SET TRANSACTION READ ONLY');return {k:c.execute(q).fetchall() for k,q in CAT_QUERIES.items()}
def main():
 cluster=DevCluster();primary=FixtureDatabase(json.loads(_read_private(cluster.runtime/'active-fixture.json'))['database'],cluster)
 assert PRIVATE==cluster.runtime/'backups/db-restore-20261014'
 backup_proof=json.loads((ROOT/'.superpowers/sdd/db-restore-20261014/backup-restore-proof.json').read_text());dump=PRIVATE/'primary.pgdump'
 assert hashlib.sha256(dump.read_bytes()).hexdigest()==backup_proof['dump']['sha256']
 before=snapshot(primary);assert before==json.loads((ROOT/'.superpowers/sdd/db-restore-20261014/primary-pre-tables.json').read_text())
 pre_cat=catalog(primary);save('primary-pre-catalog.json',pre_cat);save('primary-pre-tables.json',before)
 cols={k:v for k,v in before.items() if k!='infra.schema_migrations'};assert len(cols)==52
 with primary.admin_connection() as c:
  primary.verify(c)
  ledger=c.execute('SELECT version,sha256,applied_at FROM infra.schema_migrations ORDER BY version').fetchall()
 save('historical-ledger-sidecar.json',ledger)
 base=OUT/'source-000-040';base.mkdir(exist_ok=True)
 for p in sorted(MIGRATIONS.glob('[0-9][0-9][0-9]_*.sql')):
  if int(p.name[:3])<=40:shutil.copyfile(p,base/p.name)
 assert len(list(base.glob('*.sql')))==41
 db=create_fixture_database();assert db.name not in (primary.name,backup_proof['restore_database'])
 save('stage-identity.json',{'source_database':primary.name,'destination_database':db.name,'marker':DB_MARKER,'cutover':False})
 initial=apply_migrations(db,base);assert len(initial)==41
 fresh=snapshot(db);fresh_cat=catalog(db);save('fresh-040-tables.json',fresh);save('fresh-040-catalog.json',fresh_cat)
 assert set(fresh)==set(before)
 # Filter the verified custom archive TOC, retaining data entries except historical ledger.
 env={k:v for k,v in os.environ.items() if not k.startswith('PG')};env['PGPASSFILE']=str(cluster.passfile_path)
 toc=subprocess.run(['/usr/local/bin/pg_restore','-l',str(dump)],env=env,capture_output=True,check=True).stdout.decode()
 filtered='\n'.join(line for line in toc.splitlines() if not ('TABLE DATA infra schema_migrations ' in line))+'\n'
 tocfile=PRIVATE/'migration-data.toc';tocfile.write_text(filtered);tocfile.chmod(0o600)
 data=subprocess.run(['/usr/local/bin/pg_restore','--data-only','--disable-triggers','-L',str(tocfile),'-f','-',str(dump)],env=env,capture_output=True,check=True).stdout
 # Guard destination/marker/superuser explicitly in same transaction as replacement and restore.
 with db.admin_connection() as c:
  db.verify(c)
  targets=sql.SQL(',').join(sql.Identifier(*k.split('.')) for k in cols).as_string(c)
  guard=sql.SQL("BEGIN; SELECT pg_advisory_xact_lock(250002); DO $$ BEGIN IF current_database() <> {} OR session_user <> 'mvp_bootstrap' OR shobj_description((SELECT oid FROM pg_database WHERE datname=current_database()),'pg_database') <> {} THEN RAISE EXCEPTION 'STAGE_IDENTITY_DENIED'; END IF; END $$; TRUNCATE {};").format(sql.Literal(db.name),sql.Literal(DB_MARKER),sql.SQL(targets)).as_string(c)
 script=PRIVATE/'migration-data.sql';script.write_bytes(guard.encode()+b'\n'+data+b'\nCOMMIT;\n');script.chmod(0o600)
 run=subprocess.run(['/usr/local/bin/psql','-X','-v','ON_ERROR_STOP=1','-h','127.0.0.1','-p','55432','-U','mvp_bootstrap','-d',db.name,'-f',str(script)],env=env,capture_output=True,timeout=120)
 (PRIVATE/'migration-data.stderr').write_bytes(run.stderr);(PRIVATE/'migration-data.stderr').chmod(0o600)
 if run.returncode: raise RuntimeError('DATA_RESTORE_FAILED')
 copied=snapshot(db);save('copied-040-tables.json',copied);assert all(copied[k]==v for k,v in cols.items())
 copied_cat=catalog(db);save('copied-040-catalog.json',copied_cat);assert fresh_cat==copied_cat
 with db.admin_connection() as c:
  db.verify(c)
  assert c.execute('SELECT count(*) FROM infra.schema_migrations').fetchone()[0]==41
  # Validate every FK explicitly: restore temporarily disables triggers, so existing rows need a full relation check.
  fk=c.execute("SELECT k.oid,k.conrelid::regclass::text,k.confrelid::regclass::text,k.conkey,k.confkey FROM pg_constraint k JOIN pg_namespace n ON n.oid=k.connamespace WHERE k.contype='f' AND n.nspname IN ('security','portal','ops','rag') ORDER BY k.oid").fetchall();checks=[]
  for oid,child,parent,keys,pkeys in fk:
   cn=[c.execute('SELECT attname FROM pg_attribute WHERE attrelid=%s::regclass AND attnum=%s',(child,k)).fetchone()[0] for k in keys]
   pn=[c.execute('SELECT attname FROM pg_attribute WHERE attrelid=%s::regclass AND attnum=%s',(parent,k)).fetchone()[0] for k in pkeys]
   condition=sql.SQL(' AND ').join(sql.SQL('x.{}=y.{}').format(sql.Identifier(a),sql.Identifier(b)) for a,b in zip(cn,pn))
   nonnull=sql.SQL(' AND ').join(sql.SQL('x.{} IS NOT NULL').format(sql.Identifier(a)) for a in cn)
   q=sql.SQL('SELECT count(*) FROM {} x WHERE {} AND NOT EXISTS(SELECT 1 FROM {} y WHERE {})').format(sql.Identifier(*child.split('.')),nonnull,sql.Identifier(*parent.split('.')),condition)
   violations=c.execute(q).fetchone()[0];checks.append({'child':child,'parent':parent,'columns':cn,'violations':violations});assert violations==0
 save('foreign-key-validation.json',checks)
 applied=apply_migrations(db);assert len(applied)==10
 post=snapshot(db,cols);save('upgraded-old-column-tables.json',post);assert post==cols
 save('upgraded-all-tables.json',snapshot(db));save('upgraded-catalog.json',catalog(db))
 with db.admin_connection() as c:
  db.verify(c);newledger=c.execute('SELECT version,sha256,applied_at FROM infra.schema_migrations ORDER BY version').fetchall()
 save('new-source-ledger.json',newledger);assert len(newledger)==51
 source_after=snapshot(primary);save('primary-post-tables.json',source_after);assert source_after==before
 source_cat=catalog(primary);save('primary-post-catalog.json',source_cat);assert {k:v for k,v in source_cat.items() if k!='roles'}=={k:v for k,v in pre_cat.items() if k!='roles'}
 assert [r[:-1] for r in source_cat['roles']]==[r[:-1] for r in pre_cat['roles']]
 save('proof.json',{'stage_database':db.name,'backup_sha256_verified':True,'source_52_tables_exact_after_copy':True,'source_52_old_columns_exact_after_upgrade':True,'accounts_all_rows_password_hashes_exact':post['security.accounts']==cols['security.accounts'],'primary_53_tables_exact':True,'primary_database_catalog_exact':True,'shared_role_attributes_exact':True,'shared_role_verifier_bytes_exact':False,'shared_role_verifier_reason':'normal runner reapplies existing runtime password values using salted SCRAM; actual authentication separately verified','new_ledger_count':51,'fresh_040_count':41,'latest_applied':applied,'fk_checks':len(checks),'sequences':copied_cat['sequences'],'fresh_catalog_unchanged_by_data_restore':True,'active_config_changed':False,'seeded':False,'paid_calls':0})
 print('STAGE_DATABASE='+db.name);print('52 old tables preserved; 51 legitimate source migrations; primary tables/catalog unchanged')
if __name__=='__main__':main()
