from pathlib import Path
import os,json,hashlib,subprocess,shutil,datetime
from scripts.devdb import DevCluster,_read_private
from scripts.migrate import FixtureDatabase,create_fixture_database,apply_migrations,MigrationError
from psycopg import sql
root=Path.cwd();out=root/'.superpowers/sdd/db-restore-20261014';cluster=DevCluster();primary=FixtureDatabase(json.loads(_read_private(cluster.runtime/'active-fixture.json'))['database'],cluster)
private=cluster.runtime/'backups/db-restore-20261014';private.mkdir(parents=True,mode=0o700,exist_ok=True);private.chmod(0o700)
report={'primary_migrations_applied':False,'seeded':False,'paid_calls':0}
def snapshot(db):
 with db.admin_connection() as c:
  db.verify(c)
  with c.transaction():
   c.execute('SET TRANSACTION READ ONLY')
   tables=c.execute("SELECT schemaname,tablename FROM pg_tables WHERE schemaname NOT IN ('pg_catalog','information_schema') ORDER BY 1,2").fetchall()
   result={}
   for s,t in tables:
    query=sql.SQL('SELECT to_jsonb(x)::text FROM {}.{} x').format(sql.Identifier(s),sql.Identifier(t))
    rows=c.execute(query).fetchall(); hashes=sorted(hashlib.sha256(r[0].encode()).hexdigest() for r in rows)
    columns=c.execute('SELECT column_name FROM information_schema.columns WHERE table_schema=%s AND table_name=%s ORDER BY ordinal_position',(s,t)).fetchall()
    result[s+'.'+t]={'count':len(rows),'columns':[r[0] for r in columns],'digest':hashlib.sha256('\n'.join(hashes).encode()).hexdigest()}
   return result
before=snapshot(primary);(out/'primary-pre-tables.json').write_text(json.dumps(before,indent=2))
files=[cluster.runtime/'app.env',cluster.runtime/'active-fixture.json',cluster.runtime/'runtime-roles.json']+list(cluster.runtime.glob('*fixture-secrets.json'))+list((root/'docs/Obsidain/200.프로젝트실행/270.파일럿적용').glob('*계정*비공개*.md'))
proof=[]
for i,p in enumerate(files):
 if not p.is_file():continue
 dest=private/f'{i:02d}-{p.name}';shutil.copyfile(p,dest);dest.chmod(0o600)
 proof.append({'source':str(p.relative_to(root)),'sha256':hashlib.sha256(dest.read_bytes()).hexdigest(),'mode':'0600'})
report['private_file_backup']=proof
env={k:v for k,v in os.environ.items() if not k.startswith('PG')};env['PGPASSFILE']=str(cluster.passfile_path)
dump=private/'primary.pgdump'
with dump.open('wb') as f:
 dump.chmod(0o600)
 run=subprocess.run(['/usr/local/bin/pg_dump','-h','127.0.0.1','-p','55432','-U','mvp_bootstrap','-d',primary.name,'-Fc','--no-comments'],env=env,stdout=f,stderr=subprocess.PIPE,timeout=60)
 if run.returncode:raise RuntimeError('PG_DUMP_FAILED')
report['dump']={'path':str(dump.relative_to(root)),'sha256':hashlib.sha256(dump.read_bytes()).hexdigest(),'bytes':dump.stat().st_size,'mode':'0600'}
restored=create_fixture_database();report['restore_database']=restored.name
run=subprocess.run(['/usr/local/bin/pg_restore','-h','127.0.0.1','-p','55432','-U','mvp_bootstrap','-d',restored.name,'--exit-on-error','--single-transaction',str(dump)],env=env,stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=90)
(private/'pg_restore.stderr').write_bytes(run.stderr);(private/'pg_restore.stderr').chmod(0o600)
if run.returncode:raise RuntimeError('PG_RESTORE_FAILED')
after=snapshot(restored);report['restore_all_tables_exact']=before==after;report['restore_password_hash_rows_exact']=before['security.accounts']==after['security.accounts'];report['restore_table_count']=len(after)
try:report['migration_applied']=apply_migrations(restored)
except MigrationError as e:report['migration_error']=str(e)
post=snapshot(restored);report['runner_failure_atomic_no_row_or_schema_changes']=post==after
report['primary_after_exact']=snapshot(primary)==before
with primary.admin_connection() as c:
 primary.verify(c)
 report['active_runs']=c.execute("SELECT state,count(*) FROM portal.runs WHERE state IN ('accepted','running') GROUP BY state").fetchall()
 report['call_state_counts']=c.execute('SELECT state,count(*) FROM ops.call_attempts GROUP BY state').fetchall()
 report['unknown_provider_end_count']=c.execute("SELECT count(*) FROM ops.call_attempts WHERE provider_end_status='unknown'").fetchone()[0]
 report['project_budget_reserved_total']=str(c.execute('SELECT coalesce(sum(reserved_krw),0) FROM ops.project_budget').fetchone()[0])
report['restore_retained_for_review']=True
(out/'backup-restore-proof.json').write_text(json.dumps(report,indent=2,default=str))
print(json.dumps({k:v for k,v in report.items() if k not in ('private_file_backup','dump')},default=str))
