from dataclasses import dataclass,field
from datetime import datetime,timedelta,timezone
from uuid import UUID
import psycopg
from psycopg.conninfo import make_conninfo
from app.db import make_web_pool
from app.types import AuthContext

@dataclass
class FixtureState:
    db: object
    state: object = field(repr=False)
    loop: object = field(repr=False)
    pool: object = field(repr=False)
    admin_dsn: str = field(repr=False)
    passwords: dict = field(repr=False)

    @property
    def actor_ids(self): return self.state.actor_ids
    @property
    def tenant_ids(self): return self.state.tenant_ids
    @property
    def conversation_ids(self): return self.state.conversation_ids

    def run(self,coroutine): return self.loop.run_until_complete(coroutine)

    async def context(self,actor,tenant):
        async with self.pool.connection() as conn:
            session=await (await conn.execute('SELECT * FROM security.session_validate(%s)',
                (self.state.token_hashes[actor],))).fetchone()
            if not session:
                raise ValueError('CONTEXT_UNAVAILABLE')
            member=await (await conn.execute('SELECT * FROM security.current_membership(%s,%s)',
                (session['session_id'],self.tenant_ids[tenant]))).fetchone()
            if not member:
                raise ValueError('CONTEXT_UNAVAILABLE')
            return AuthContext(session['session_id'],session['user_id'],self.tenant_ids[tenant],
                               member['effective_role'],session['csrf_secret'])

    def role_connection(self,role):
        return psycopg.connect(self.db.runtime_dsn(role),autocommit=True)

    def mutate_access(self,ctx,mutation):
        with self.db.admin_connection() as conn:
            if mutation=='account': conn.execute('UPDATE security.accounts SET active=false WHERE user_id=%s',(ctx.user_id,))
            elif mutation=='tenant': conn.execute('UPDATE security.tenants SET active=false WHERE tenant_id=%s',(ctx.tenant_id,))
            elif mutation=='membership': conn.execute('UPDATE security.memberships SET active=false WHERE tenant_id=%s AND user_id=%s',(ctx.tenant_id,ctx.user_id))
            elif mutation=='revision': conn.execute('UPDATE security.accounts SET auth_revision=auth_revision+1 WHERE user_id=%s',(ctx.user_id,))
            elif mutation=='revoked': conn.execute('UPDATE security.sessions SET revoked_at=clock_timestamp() WHERE session_id=%s',(ctx.session_id,))
            else:
                issued=datetime.now(timezone.utc)-timedelta(hours=9 if mutation=='expired' else 1)
                conn.execute('UPDATE security.sessions SET issued_at=%s,last_activity_at=%s,expires_at=%s WHERE session_id=%s',
                    (issued,issued,issued+timedelta(hours=8),ctx.session_id))

    def verify_catalog(self):
        with self.db.admin_connection() as conn:
            assert conn.execute("SELECT count(*) FROM pg_tables WHERE schemaname IN ('security','portal','ops','rag')").fetchone()[0]==32
            assert conn.execute("SELECT count(*) FROM infra.schema_migrations").fetchone()[0]==23
            rows=conn.execute("SELECT n.nspname,c.relname,c.relrowsecurity,c.relforcerowsecurity,r.rolname "
                "FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace JOIN pg_roles r ON r.oid=c.relowner "
                "WHERE n.nspname IN ('portal','ops') AND c.relname IN ('conversations','agent_configs','audit_events','messages','runs','tenant_budgets','call_attempts','usage_events')").fetchall()
            assert len(rows)==8 and all(r[2] and r[3] and r[4]=='ai_owner' for r in rows)
            assert conn.execute("SELECT has_table_privilege('ai_policy_executor','portal.conversations','SELECT')").fetchone()[0]
            assert conn.execute("SELECT has_column_privilege('ai_policy_executor','ops.project_budget','accounted_krw','SELECT')").fetchone()[0]
            assert conn.execute("SELECT has_column_privilege('ai_policy_executor','portal.messages','body','SELECT')").fetchone()[0]
            assert conn.execute("SELECT has_column_privilege('ai_policy_executor','portal.runs','config_snapshot','SELECT')").fetchone()[0]
            assert conn.execute("SELECT has_column_privilege('ai_policy_executor','ops.call_attempts','dispatch_claim_hash','SELECT')").fetchone()[0]
            funcs=conn.execute("SELECT p.prosecdef,p.proconfig,r.rolname, "
                "EXISTS(SELECT 1 FROM aclexplode(p.proacl) a WHERE a.grantee=0 AND a.privilege_type='EXECUTE') "
                "FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace JOIN pg_roles r ON r.oid=p.proowner "
                "WHERE n.nspname='security'").fetchall()
            assert len(funcs)==87 and all(r[0] and r[1]==['search_path=pg_catalog, security, pg_temp'] and r[2]=='ai_policy_executor' and not r[3] for r in funcs)
            assert conn.execute('SELECT count(*) FROM security.managed_tenants').fetchone()[0]==1


def login(client,actor,passwords):
    reply=client.post('/api/v1/auth/login',headers={
        'Origin':'http://127.0.0.1:5173','X-Requested-With':'ai-portal'},
        json={'login_id':actor.lower(),'password':passwords[actor]})
    assert reply.status_code==200
    return {'csrf_token':reply.json()['data']['csrf_token']}
