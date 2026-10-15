from pathlib import Path
import json,hashlib,difflib,re,os
from scripts.devdb import DevCluster
from scripts.migrate import FixtureDatabase,MIGRATIONS
root=Path.cwd(); out=root/'.superpowers/sdd/db-restore-20261014';out.mkdir(parents=True,exist_ok=True)
source=MIGRATIONS/'040_dynamic_agent_favorites.sql';(out/'040-current-before.sql').write_bytes(source.read_bytes())
cluster=DevCluster();cluster.status();active=json.loads((cluster.runtime/'active-fixture.json').read_text());db=FixtureDatabase(active['database'],cluster)
with db.admin_connection() as c:
 db.verify(c)
 with c.transaction():
  c.execute('SET TRANSACTION READ ONLY')
  applied=dict(c.execute('SELECT version,sha256 FROM infra.schema_migrations').fetchall())
  report={'cluster_status':cluster.status(),'applied_count':len(applied),'source_hashes':{p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in MIGRATIONS.glob('*.sql')},'applied':applied}
  report['mismatches']=[k for k,v in applied.items() if report['source_hashes'].get(k)!=v]
  for fn in ('dynamic_favorite_mutate','published_agent_read'):
   body=c.execute('SELECT prosrc FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace WHERE n.nspname=%s AND proname=%s',('security',fn)).fetchone()[0]
   (out/(fn+'-primary-body.sql')).write_text(body)
   filebody=re.search(r'CREATE OR REPLACE FUNCTION security\.'+fn+r'.*?AS \$body\$(.*?)\$body\$',source.read_text(),re.S).group(1)
   (out/(fn+'-diff.txt')).write_text(''.join(difflib.unified_diff(filebody.splitlines(True),body.splitlines(True),fromfile='current',tofile='primary')))
  tables=c.execute("SELECT schemaname,tablename FROM pg_tables WHERE schemaname NOT IN ('pg_catalog','information_schema') ORDER BY 1,2").fetchall()
  report['table_counts']={s+'.'+t:c.execute('SELECT count(*) FROM "'+s+'"."'+t+'"').fetchone()[0] for s,t in tables}
  (out/'audit.json').write_text(json.dumps(report,indent=2))
print(json.dumps({'applied_count':len(applied),'mismatches':report['mismatches'],'tables':len(tables),'proof':str(out)}))
