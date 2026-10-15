from pathlib import Path
import shutil,json,hashlib,os
from scripts.devdb import DevCluster
from scripts.migrate import FixtureDatabase
root=Path.cwd();out=root/'.superpowers/sdd/db-restore-20261014';cluster=DevCluster();report=json.loads((out/'backup-restore-proof.json').read_text());private=cluster.runtime/'backups/db-restore-20261014'
for n in ('db_restore_audit.py','db_restore_backup.py','db_restore_finalize.py'):
 shutil.copyfile(Path('/private/tmp')/n,out/n)
store=cluster.runtime/'source-store';files=list(store.rglob('*')) if store.exists() else []
assert not any(p.is_symlink() for p in files)
objects=[p for p in files if p.is_file()]
report['source_store']={'configured_default':True,'exists':store.is_dir(),'file_count':len(objects),'backup_mode':'directories0700/files0600','content_sha256s':[hashlib.sha256(p.read_bytes()).hexdigest() for p in objects]}
if store.exists():
 dest=private/'source-store';shutil.copytree(store,dest,dirs_exist_ok=True)
 for p in [dest]+list(dest.rglob('*')):p.chmod(0o700 if p.is_dir() else 0o600)
primary=FixtureDatabase(json.loads((cluster.runtime/'active-fixture.json').read_text())['database'],cluster)
with primary.admin_connection() as c:
 primary.verify(c)
 report['primary_document_count']=c.execute('SELECT count(*) FROM rag.document_versions').fetchone()[0]
 report['primary_password_hash_account_count']=c.execute('SELECT count(*) FROM security.accounts').fetchone()[0]
report['source_recovery']={'exact_match_found':False,'current_sha256':'49235a34ddcdb1a3c034c6ac42303cbd3bfadaddb20d3e2bf71830521e07fff4','recorded_sha256':'ca78a8d3c17ee6c104d5703a01c500edda3efcb7c398b2f6d26e2ae64c661adb','primary_function_body_difference_count':2,'published_agent_read_body_exact':True,'two_literal_candidate_sha256':'4ccf60654f96ea92312e97e8dcd9b63bf6d5849764677f217d0c2b64053b31cb','bounded_whitespace_candidates':2856,'old_source_not_modified':True,'checksum_history_not_modified':True}
(out/'backup-restore-proof.json').write_text(json.dumps(report,indent=2,default=str))
print(json.dumps({'source_store_files':len(objects),'documents':report['primary_document_count'],'accounts':report['primary_password_hash_account_count'],'report':str(out/'backup-restore-proof.json')}))
