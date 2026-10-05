"""First preparation of owned synthetic mock demo; never reset ledger/real data."""
from datetime import date
from decimal import Decimal,ROUND_DOWN
import json,os,shlex,stat
from pathlib import Path
from uuid import uuid4
from fastapi.testclient import TestClient
from pydantic import SecretStr
from psycopg.types.json import Jsonb
from app.config import Settings
from app.db import DB_MARKER
from app.main import create_app
from scripts.devdb import DevCluster,_read_private,_write_private
from scripts.migrate import FixtureDatabase,apply_migrations
from scripts.seed import NAMESPACE
from uuid import uuid5
PERIOD=date(2026,10,1)

def initialize_missing_mock_budgets(db):
    with db.admin_connection() as conn:
        db.verify(conn)
        with conn.transaction():
            conn.execute('SELECT pg_advisory_xact_lock(250002)')
            project=conn.execute("SELECT budget_id,operational_cap_krw FROM ops.project_budget WHERE period=%s AND mode='mock' FOR UPDATE",(PERIOD,)).fetchone()
            if not project:raise ValueError('MOCK_BUDGET_REQUIRED')
            organizations=conn.execute("SELECT tenant_id,fixture_label FROM security.tenants ORDER BY fixture_label").fetchall()
            if len(organizations)!=2 or [x[1] for x in organizations]!=['A','B']:raise ValueError('SYNTHETIC_SCOPE_REQUIRED')
            expected={'A':'10000000-0000-4000-8000-00000000000a','B':'10000000-0000-4000-8000-00000000000b'}
            if any(str(org)!=expected[label] for org,label in organizations):raise ValueError('SYNTHETIC_SCOPE_REQUIRED')
            actor=conn.execute("SELECT user_id FROM security.accounts WHERE login_id='p-a'").fetchone()
            if not actor or actor[0]!=uuid5(NAMESPACE,'P-A'):raise ValueError('SYNTHETIC_SCOPE_REQUIRED')
            existing=conn.execute('SELECT tenant_id,allocated_cap_krw FROM ops.tenant_budgets WHERE budget_id=%s',(project[0],)).fetchall()
            ids={row[0] for row in existing};missing=[(org,label) for org,label in organizations if org not in ids]
            if not missing:return []
            remaining=max(Decimal(0),project[1]-sum((x[1] for x in existing),Decimal(0)))
            cap=min(Decimal('12500'),(remaining/len(missing)).quantize(Decimal('.01'),rounding=ROUND_DOWN))
            created=[]
            for org,label in missing:
                inserted=conn.execute('INSERT INTO ops.tenant_budgets(tenant_id,budget_id,allocated_cap_krw,local_cap_krw) VALUES(%s,%s,%s,%s) ON CONFLICT DO NOTHING RETURNING tenant_id',
                    (org,project[0],cap,cap)).fetchone()
                if inserted:
                    conn.execute("INSERT INTO ops.audit_events(event_id,scope_kind,tenant_id,actor_id,action,result,revisions) VALUES(%s,'tenant',%s,%s,'mock_budget_initialized','ok',%s)",
                        (uuid4(),org,actor[0],Jsonb({'execution_mode':'mock','allocated_cap_krw':str(cap),'bootstrap':'owned_synthetic_fixture'})))
                    created.append(label)
            return created

def merge_private_environment(path,meter_dsn):
    original=_read_private(path)
    parent=path.parent.stat()
    if path.parent.is_symlink() or parent.st_uid!=os.getuid() or stat.S_IMODE(parent.st_mode)!=0o700:raise ValueError('UNOWNED_RUNTIME')
    lines=original.splitlines();mapping={}
    for line in lines:
        if not line.strip() or line.lstrip().startswith('#'):continue
        key,value=line.split('=',1)
        if key in mapping:raise ValueError('DUPLICATE_CONFIGURATION')
        mapping[key]=shlex.split(value)[0] if shlex.split(value) else ''
    if mapping.get('AI_MODE','mock')!='mock':raise ValueError('REAL_CONFIGURATION_PRESERVED')
    if 'AI_METER_DSN' in mapping and mapping['AI_METER_DSN']!=meter_dsn:raise ValueError('METER_CONFIGURATION_MISMATCH')
    updates={'AI_MODE':'mock','AI_EXECUTION_ENABLED':'true','AI_METER_DSN':meter_dsn}
    changed=False;result=[];seen=set()
    for line in lines:
        key=line.split('=',1)[0]
        if key in updates:
            seen.add(key)
            if mapping[key]!=updates[key]:line=key+'='+shlex.quote(updates[key]);changed=True
        result.append(line)
    for key,value in updates.items():
        if key not in seen:result.append(key+'='+shlex.quote(value));changed=True
    if not changed:return False
    target=path.with_name('mock-config-'+uuid4().hex+'.tmp')
    try:
        _write_private(target,'\n'.join(result)+'\n')
        with target.open('rb') as handle:os.fsync(handle.fileno())
        os.replace(target,path)
        fd=os.open(path.parent,os.O_RDONLY)
        try:os.fsync(fd)
        finally:os.close(fd)
    finally:target.unlink(missing_ok=True)
    # Existing credential lines are preserved literally, not merely as equivalent parsed values.
    after=path.read_text().splitlines()
    if any(line not in after for line in lines if line.split('=',1)[0] not in updates):raise ValueError('CONFIGURATION_PRESERVATION_FAILED')
    return True

def prepare_primary():
    cluster=DevCluster();prior=cluster.status()['state']
    if prior!='running':cluster.start()
    try:
        registry=json.loads(_read_private(cluster.runtime/'active-fixture.json'))
        if registry.get('marker')!=DB_MARKER:raise ValueError('PRIMARY_MARKER_REQUIRED')
        db=FixtureDatabase(registry['database'],cluster)
        if apply_migrations(db):raise ValueError('MIGRATIONS_MUST_ALREADY_BE_APPLIED')
        created=initialize_missing_mock_budgets(db)
        with db.admin_connection() as conn:
            db.verify(conn)
            eligible=conn.execute("SELECT t.fixture_label,a.config_version FROM portal.agent_configs a JOIN security.tenants t USING(tenant_id) JOIN ops.tenant_budgets b USING(tenant_id) JOIN ops.project_budget p USING(budget_id) WHERE a.agent_key='general' AND NOT a.enabled AND a.config_version=1 AND a.settings='{}'::jsonb AND p.mode='mock' AND p.period=%s AND b.local_cap_krw>b.accounted_krw+b.reserved_krw ORDER BY t.fixture_label",(PERIOD,)).fetchall()
        # Do not change existing edited/stopped Agents or replay any existing run.
        enabled=[]
        if eligible:
            credentials=json.loads(_read_private(cluster.runtime/(db.name+'-fixture-secrets.json')))['passwords']
            hmac=None
            for line in _read_private(cluster.runtime/'app.env').splitlines():
                if line.startswith('AI_LOGIN_HMAC_SECRET='):hmac=shlex.split(line.split('=',1)[1])[0]
            settings=Settings(web_dsn=SecretStr(db.runtime_dsn()),login_hmac_secret=SecretStr(hmac),openai_api_key=None,mode='mock',execution_enabled=False)
            with TestClient(create_app(settings),base_url='http://127.0.0.1:8000',client=('127.0.0.1',50000)) as client:
                for label,revision in eligible:
                    actor=label+'-ADM';transport={'Origin':settings.origin,'X-Requested-With':'ai-portal'}
                    reply=client.post('/api/v1/auth/login',headers=transport,json={'login_id':actor.lower(),'password':credentials[actor]})
                    if reply.status_code!=200:raise ValueError('DEMO_ADMIN_LOGIN_REJECTED')
                    csrf=reply.json()['data']['csrf_token'];transport['X-CSRF-Token']=csrf
                    org='10000000-0000-4000-8000-00000000000'+label.lower()
                    reply=client.put('/api/v1/admin/agents/general/availability',headers={**transport,'X-Tenant-ID':org},json={'enabled':True,'expected_revision':revision})
                    if reply.status_code!=200:raise ValueError('DEMO_AGENT_PREPARATION_REJECTED')
                    if client.post('/api/v1/auth/logout',headers=transport).status_code!=200:raise ValueError('DEMO_ADMIN_LOGOUT_UNCONFIRMED')
                    enabled.append(label)
        changed=merge_private_environment(cluster.runtime/'app.env',db.runtime_dsn('ai_meter'))
        return {'kind':'B05-owned-mock-preparation','budget_rows_created':len(created),'agents_enabled':len(enabled),'private_execution_configuration_changed':changed,'execution_mode':'mock','existing_usage_reset':False,'real_calls':0}
    finally:
        if prior!='running':cluster.stop()

if __name__=='__main__':
    try:print(json.dumps(prepare_primary()))
    except Exception:print(json.dumps({'error':'MOCK_PREPARATION_FAILED'}));raise SystemExit(1)
