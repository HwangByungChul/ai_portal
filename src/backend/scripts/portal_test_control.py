"""Private A05 fault controls: never an HTTP route or a general reset command."""
from pathlib import Path
import json,os,sys
from uuid import UUID,uuid5
from scripts.devdb import DevCluster,_read_private,_write_private
from scripts.migrate import FixtureDatabase
from app.db import DB_MARKER
BACKEND=Path(__file__).resolve().parents[1]

def main():
    config=json.loads(_read_private(BACKEND/'.runtime/A05-fixture.json'))
    if config.get('kind')!='A05-disposable-browser' or config.get('marker')!=DB_MARKER: raise ValueError('TEST_SCOPE_REJECTED')
    os.kill(config['pid'],0)
    primary=json.loads(_read_private(BACKEND/'.runtime/active-fixture.json'))
    if config['database']==primary['database']: raise ValueError('PRIMARY_FIXTURE_REJECTED')
    db=FixtureDatabase(config['database'],DevCluster())
    action=sys.argv[1];actor=sys.argv[2] if len(sys.argv)>2 else 'A-U1';tenant=sys.argv[3] if len(sys.argv)>3 else 'A'
    if actor not in config['actors'] or tenant not in config['tenants']: raise ValueError('UNKNOWN_SYNTHETIC_ACTOR')
    user=UUID(config['actors'][actor]);org=UUID(config['tenants'][tenant])
    with db.admin_connection() as conn:
        db.verify(conn)
        if action=='case-start':
            with conn.transaction():
                conn.execute('ALTER TABLE ops.audit_events DROP CONSTRAINT IF EXISTS a05_fail_logout')
                conn.execute('GRANT EXECUTE ON FUNCTION security.list_memberships(uuid,uuid,uuid,integer) TO ai_web')
                conn.execute("DELETE FROM security.memberships WHERE user_id IN (SELECT user_id FROM security.accounts WHERE login_id LIKE 'a05page_%%')")
                conn.execute("DELETE FROM security.accounts WHERE login_id LIKE 'a05page_%%'")
                conn.execute('DELETE FROM security.login_windows')
                conn.execute("DELETE FROM ops.audit_events WHERE action IN ('membership_active','membership_role','login','logout')")
                conn.execute("UPDATE security.accounts SET active=(login_id<>'inactive'),auth_revision=1")
                conn.execute('UPDATE security.sessions SET revoked_at=clock_timestamp()')
                conn.execute('UPDATE security.platform_access SET active=true')
                conn.execute('UPDATE security.managed_tenants SET active=true')
                # Only this marked disposable browser DB is reset; primary is rejected above.
                conn.execute('TRUNCATE ops.usage_events,ops.call_attempts,portal.messages,portal.runs')
                conn.execute('DELETE FROM portal.conversations WHERE NOT(conversation_id=ANY(%s))',([UUID(v) for v in config['conversations']],))
                conn.execute('UPDATE ops.project_budget SET stopped=false,stop_latch=false,revision=1,accounted_krw=0,reserved_krw=0,active_slot=0')
                conn.execute('UPDATE ops.tenant_budgets SET allocated_cap_krw=12500,local_cap_krw=12500,accounted_krw=0,reserved_krw=0,active_slot=0,stopped=false,revision=1')
                conn.execute("UPDATE portal.agent_configs SET settings='{}'::jsonb,enabled=(agent_key='general'),config_version=1")
                for name in ['B05-provider-control.json','B05-provider-count.txt']:(BACKEND/'.runtime'/name).unlink(missing_ok=True)
                _write_private(BACKEND/'.runtime/B05-provider-control.json',json.dumps({'behavior':'normal'}))
                for row in config['members']:
                    conn.execute('UPDATE security.memberships SET role=%s,active=%s,revision=%s WHERE tenant_id=%s AND user_id=%s',
                        (row['role'],row['active'],row['revision'],row['tenant'],row['user']))
        elif action in ('slow-provider','release-provider','unknown-provider'):
            path=BACKEND/'.runtime/B05-provider-control.json';path.unlink()
            _write_private(path,json.dumps({'behavior':{'slow-provider':'slow','release-provider':'normal','unknown-provider':'unknown'}[action]}))
        elif action=='b05-counts':
            count_path=BACKEND/'.runtime/B05-provider-count.txt'
            print(json.dumps({'provider_calls':len(_read_private(count_path).splitlines()) if count_path.exists() else 0,
                'runs':conn.execute('SELECT count(*) FROM portal.runs').fetchone()[0],
                'active':conn.execute("SELECT count(*) FROM portal.runs WHERE state IN ('queued','running','cancel_requested')").fetchone()[0],
                'messages':conn.execute('SELECT count(*) FROM portal.messages').fetchone()[0],
                'unknown':conn.execute("SELECT count(*) FROM ops.call_attempts WHERE state='usage_unknown'").fetchone()[0]}));return 0
        elif action=='revoke-platform':conn.execute('UPDATE security.platform_access SET active=false WHERE user_id=%s',(user,))
        elif action=='demote':
            conn.execute("UPDATE security.memberships SET role='USER',revision=revision+1 WHERE tenant_id=%s AND user_id=%s",(org,user))
        elif action=='revoke':
            conn.execute('UPDATE security.memberships SET active=false,revision=revision+1 WHERE tenant_id=%s AND user_id=%s',(org,user))
        elif action=='expire':
            conn.execute("WITH moment AS (SELECT clock_timestamp() AS now) UPDATE security.sessions SET issued_at=moment.now-interval '9 hours',last_activity_at=moment.now-interval '9 hours',expires_at=moment.now-interval '1 hour' FROM moment WHERE user_id=%s",(user,))
        elif action=='fail-logout':
            conn.execute("ALTER TABLE ops.audit_events ADD CONSTRAINT a05_fail_logout CHECK(action<>'logout') NOT VALID")
        elif action=='restore-logout': conn.execute('ALTER TABLE ops.audit_events DROP CONSTRAINT a05_fail_logout')
        elif action=='fail-read': conn.execute('REVOKE EXECUTE ON FUNCTION security.list_memberships(uuid,uuid,uuid,integer) FROM ai_web')
        elif action=='restore-read': conn.execute('GRANT EXECUTE ON FUNCTION security.list_memberships(uuid,uuid,uuid,integer) TO ai_web')
        elif action=='counts':
            row=conn.execute('SELECT role,active,revision FROM security.memberships WHERE tenant_id=%s AND user_id=%s',(org,user)).fetchone()
            audits=conn.execute("SELECT count(*) FROM ops.audit_events WHERE action LIKE 'membership_%%'").fetchone()[0]
            print(json.dumps({'role':row[0],'active':row[1],'revision':row[2],'audits':audits}));return 0
        elif action=='pagination':
            with conn.transaction():
                encoded=conn.execute('SELECT password_hash FROM security.accounts WHERE user_id=%s',(user,)).fetchone()[0]
                namespace=UUID('af54d850-d897-4f1c-8a72-14326bb36655')
                for i in range(24):
                    actor_id=uuid5(namespace,'a05page_'+str(i));member_id=uuid5(namespace,'membership_'+str(i))
                    conn.execute('INSERT INTO security.accounts(user_id,login_id,display_name,password_hash,active) VALUES(%s,%s,%s,%s,true)',
                        (actor_id,'a05page_'+str(i),'시연 추가 사용자 '+str(i+1).zfill(2),encoded))
                    conn.execute("INSERT INTO security.memberships(tenant_id,user_id,membership_id,role) VALUES(%s,%s,%s,'USER')",(org,actor_id,member_id))
            count=conn.execute('SELECT count(*) FROM security.memberships WHERE tenant_id=%s',(org,)).fetchone()[0]
            print(json.dumps({'members':count}));return 0
        else: raise ValueError('ACTION_REJECTED')
    print(json.dumps({'ok':True}));return 0

if __name__=='__main__':
    try: raise SystemExit(main())
    except Exception: print(json.dumps({'error':'PRIVATE_TEST_CONTROL_FAILED'}));raise SystemExit(2)
