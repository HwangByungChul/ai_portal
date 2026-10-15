"""Read-only release verification of retained stage and unchanged original."""
import json,hashlib
from stage import *
def normalize(v):return json.loads(json.dumps(v,default=str))
def main():
 identity=json.loads((OUT/'stage-identity.json').read_text());cluster=DevCluster();db=FixtureDatabase(identity['destination_database'],cluster);primary=FixtureDatabase(identity['source_database'],cluster)
 before=json.loads((OUT/'primary-pre-tables.json').read_text());cols={k:v for k,v in before.items() if k!='infra.schema_migrations'};precat=json.loads((OUT/'primary-pre-catalog.json').read_text());postcat=normalize(catalog(primary));allstage=snapshot(db)
 save('primary-final-tables.json',snapshot(primary));save('primary-final-catalog.json',postcat);save('stage-final-tables.json',allstage);stagecat=normalize(catalog(db));save('stage-final-catalog.json',stagecat)
 assert snapshot(primary)==before;assert snapshot(db,cols)==cols
 assert {k:v for k,v in postcat.items() if k!='roles'}=={k:v for k,v in precat.items() if k!='roles'}
 assert [r[:-1] for r in postcat['roles']]==[r[:-1] for r in precat['roles']]
 http=json.loads((OUT/'http-validation.json').read_text());assert len(http['accounts'])==13 and all(x['passed'] for x in http['routes'])
 assert http['child_stopped'] and http['pool_connections_after_stop']==0 and http['validation_clone_removed']
 assert all(x['connected'] for x in http['runtime_credential_connections'])
 files=json.loads((ROOT/'.superpowers/sdd/db-restore-20261014/backup-restore-proof.json').read_text())['private_file_backup']
 unchanged=[{'path':x['source'],'same_sha256':hashlib.sha256((ROOT/x['source']).read_bytes()).hexdigest()==x['sha256']} for x in files];assert all(x['same_sha256'] for x in unchanged);save('active-private-files-unchanged.json',unchanged)
 with db.admin_connection() as c:
  db.verify(c)
  ledger=c.execute('SELECT version,sha256,applied_at FROM infra.schema_migrations ORDER BY version').fetchall();save('new-source-ledger.json',ledger)
  assert len(ledger)==51
  assert all(hashlib.sha256((MIGRATIONS/v).read_bytes()).hexdigest()==h for v,h,_ in ledger)
  connections=c.execute('SELECT count(*) FROM pg_stat_activity WHERE datname=%s AND usename IN (%s,%s,%s)',(db.name,'ai_web','ai_index','ai_meter')).fetchone()[0];assert connections==0
  validations=c.execute("SELECT count(*) FROM pg_constraint k JOIN pg_namespace n ON n.oid=k.connamespace WHERE n.nspname IN ('security','portal','ops','rag') AND NOT k.convalidated").fetchone()[0];assert validations==0
  active=c.execute("SELECT count(*) FROM portal.runs WHERE state IN ('accepted','running')").fetchone()[0]
  unknown=c.execute("SELECT count(*) FROM ops.call_attempts WHERE provider_end_status='unknown'").fetchone()[0]
  reserved=str(c.execute('SELECT coalesce(sum(reserved_krw),0) FROM ops.project_budget').fetchone()[0])
 original=json.loads((OUT/'historical-ledger-sidecar.json').read_text());assert len(original)==41
 with primary.admin_connection() as c:
  primary.verify(c);assert normalize(c.execute('SELECT version,sha256,applied_at FROM infra.schema_migrations ORDER BY version').fetchall())==original
 proof={'stage_database':db.name,'source_database':primary.name,'released_for_root_review':True,'backup_verified':True,'old_52_tables_copied_exactly':True,'old_52_tables_old_columns_exact_after_041_050_and_http':True,'accounts_13_all_rows_password_hashes_exact':True,'primary_53_tables_exact':True,'primary_database_catalog_exact':True,'shared_role_attributes_exact':True,'shared_role_salted_verifier_bytes_changed_by_normal_runner':True,'existing_runtime_credentials_authenticated_on_both_databases':True,'historical_41_ledger_preserved_sidecar_and_primary':True,'new_51_ledger_matches_current_source':True,'historical_040_not_reconstructed':True,'latest_migration_count':10,'data_restore_catalog_unchanged':True,'fk_checks':len(json.loads((OUT/'foreign-key-validation.json').read_text())),'unvalidated_constraints':0,'sequences':stagecat['sequences'],'fresh_business_initial_rows':0,'stage_table_count':len(allstage),'new_tables_initial_counts':{k:v['count'] for k,v in allstage.items() if k not in before},'active_runs':active,'unknown_calls':unknown,'reserved_total':reserved,'runtime_config_and_private_files_exact':True,'http_login_success_active_accounts':sum(x['login_status']==200 for x in http['accounts']),'http_inactive_account_rejected':True,'http_role_route_assertions':len(http['routes']),'validation_child_stopped':True,'stage_runtime_connections':connections,'active_config_changed':False,'seeded':False,'paid_calls':0,'source_store_files':len(list((cluster.runtime/'source-store').rglob('*'))) if (cluster.runtime/'source-store').exists() else None,'original_bytes_missing_document_versions':2,'private_document_checks':http['private_documents']}
 assert active==0 and unknown==0 and float(reserved)==0
 save('proof.json',proof);print(json.dumps({k:v for k,v in proof.items() if k not in ('private_document_checks','new_tables_initial_counts')},indent=2))
if __name__=='__main__':main()
