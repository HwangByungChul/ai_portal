"""Synthetic authentication fixture initialization; no reset of existing data."""
import argparse
from dataclasses import dataclass, field
from datetime import datetime,timedelta,timezone
import hashlib
import json
from pathlib import Path
import secrets
from uuid import UUID,uuid4,uuid5
from argon2 import PasswordHasher,Type
from psycopg.types.json import Jsonb
from app.db import DB_MARKER
from scripts.devdb import DevCluster,_read_private,_write_private
from scripts.migrate import FixtureDatabase,MigrationError

NAMESPACE=UUID('4c9e4258-a883-4e35-9458-6736a31a0c11')
MANIFEST=Path(__file__).resolve().parents[3] / 'data/synthetic/document_manifest.json'
HASHER=PasswordHasher(time_cost=2,memory_cost=19456,parallelism=1,type=Type.ID)

@dataclass
class SeedState:
    actor_ids: dict
    tenant_ids: dict
    conversation_ids: dict
    passwords: dict = field(repr=False)
    token_hashes: dict = field(repr=False)
    session_ids: dict = field(repr=False)
    secret_path: Path = field(repr=False)


def seed_fixture(db):
    manifest=json.loads(MANIFEST.read_text()); actors=list(manifest['actors'])
    for name,permissions in [('NO_MEMBERS',None),('P_READ_ONLY',['global_usage_read']),
                            ('P_WRITE_ONLY',['global_stop_write']),('P_NONE',[])]:
        actors.append({'actor_id':name,'account_status':'active',
            'memberships':[] if name=='NO_MEMBERS' else [{'tenant_id':'A','role':'ACT-USER','status':'active'}],
            'managed_tenant_ids':[],'platform_operations':permissions is not None,'permissions':permissions})
    ids={a['actor_id']:uuid5(NAMESPACE,a['actor_id']) for a in actors}
    tenants={n:UUID('10000000-0000-4000-8000-00000000000'+n.lower()) for n in ('A','B')}
    passwords={n:secrets.token_urlsafe(24) for n in ids}
    hashes={n:HASHER.hash(p) for n,p in passwords.items()}
    token_hashes={n:hashlib.sha256(secrets.token_bytes(32)).digest() for n in ids}
    sessions={n:uuid4() for n in ids}; conversations={}
    secret_path=db.cluster.runtime / f'{db.name}-fixture-secrets.json'
    with db.admin_connection() as conn:
        db.verify(conn)
        with conn.transaction():
            conn.execute('SELECT pg_advisory_xact_lock(250002)')
            if conn.execute('SELECT 1 FROM security.accounts LIMIT 1').fetchone():
                raise MigrationError('FIXTURE_ALREADY_SEEDED')
            if conn.execute('SELECT 1 FROM ops.project_budget LIMIT 1').fetchone():
                raise MigrationError('BUDGET_ALREADY_PRESENT')
            for tenant in manifest['tenants']:
                conn.execute('INSERT INTO security.tenants(tenant_id,fixture_label,display_name) VALUES(%s,%s,%s)',
                    (tenants[tenant['tenant_id']],tenant['tenant_id'],tenant['display_name']))
            now=datetime.now(timezone.utc)
            for actor in actors:
                n=actor['actor_id']; uid=ids[n]
                conn.execute('INSERT INTO security.accounts(user_id,login_id,display_name,password_hash,active) VALUES(%s,%s,%s,%s,%s)',
                    (uid,n.lower(),n,hashes[n],actor['account_status']=='active'))
                for membership in actor['memberships']:
                    tenant=membership['tenant_id']; role='TADMIN' if membership['role']=='ACT-TADMIN' else 'USER'
                    conn.execute('INSERT INTO security.memberships(tenant_id,user_id,membership_id,role,active) VALUES(%s,%s,%s,%s,%s)',
                        (tenants[tenant],uid,uuid5(NAMESPACE,tenant+':'+n),role,membership['status']=='active'))
                if actor['platform_operations']:
                    permissions=actor.get('permissions',['global_usage_read','global_stop_write'])
                    conn.execute('INSERT INTO security.platform_access(user_id,is_padmin,permissions) VALUES(%s,true,%s)',(uid,permissions))
                    for tenant in actor['managed_tenant_ids']:
                        conn.execute('INSERT INTO security.managed_tenants(tenant_id,user_id) VALUES(%s,%s)',(tenants[tenant],uid))
                conn.execute('INSERT INTO security.sessions(session_id,token_hash,user_id,auth_revision,csrf_secret,issued_at,last_activity_at,expires_at) '
                    'VALUES(%s,%s,%s,1,%s,%s,%s,%s)',(sessions[n],token_hashes[n],uid,secrets.token_urlsafe(32),now,now,now+timedelta(hours=8)))
            for tenant in tenants:
                for agent in ('general','rules_rag'):
                    conn.execute('INSERT INTO portal.agent_configs(tenant_id,agent_key,enabled,updated_by) VALUES(%s,%s,false,%s)',
                        (tenants[tenant],agent,ids[tenant+'-ADM']))
            for actor,tenant in [('A-U1','A'),('A-U2','A'),('B-U1','B'),('DUAL','A'),('DUAL','B')]:
                cid=uuid4(); conversations[tenant+':'+actor]=cid
                conn.execute('INSERT INTO portal.conversations(tenant_id,conversation_id,owner_user_id,agent_key) VALUES(%s,%s,%s,%s)',
                    (tenants[tenant],cid,ids[actor],'general'))
            for mode in ('mock','real'):
                conn.execute('INSERT INTO ops.project_budget(budget_id,period,mode,approved_cap_krw,operational_cap_krw) '
                    "VALUES(%s,'2026-10-01',%s,30000,25000)",(uuid4(),mode))
            for scope,tenant in [('tenant','A'),('tenant','B'),('platform',None),('auth',None)]:
                conn.execute('INSERT INTO ops.audit_events(event_id,scope_kind,tenant_id,actor_id,action,result,revisions) '
                    'VALUES(%s,%s,%s,%s,%s,%s,%s)',(uuid4(),scope,tenants[tenant] if tenant else None,ids['P-A'],'fixture_initialized','ok',Jsonb({})))
            _write_private(secret_path,json.dumps({'fixture':'A-auth','passwords':passwords}))
    return SeedState(ids,tenants,conversations,passwords,token_hashes,sessions,secret_path)


def main():
    parser=argparse.ArgumentParser(description='Seed only a verified, empty A-auth fixture database')
    parser.add_argument('--fixture',required=True,choices=['A-auth']); parser.parse_args()
    try:
        cluster=DevCluster(); registry=json.loads(_read_private(cluster.runtime/'active-fixture.json'))
        if registry.get('marker') != DB_MARKER:
            raise MigrationError('FIXTURE_MARKER_REJECTED')
        state=seed_fixture(FixtureDatabase(registry['database'],cluster))
        print(json.dumps({'fixture':'A-auth','accounts':len(state.actor_ids),'conversations':len(state.conversation_ids)}))
        return 0
    except Exception:
        print(json.dumps({'error':{'code':'FIXTURE_SEED_FAILED'}})); return 1

if __name__ == '__main__':
    raise SystemExit(main())
