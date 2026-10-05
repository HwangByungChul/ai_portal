from decimal import Decimal
from pathlib import Path
import hashlib,os
import pytest
from scripts.prepare_mock import initialize_missing_mock_budgets,merge_private_environment
from scripts.migrate import FixtureDatabase,MigrationError
from scripts.devdb import DevDBError,_write_private

def snapshot(f):
    with f.db.admin_connection() as conn:
        return {table:conn.execute('SELECT row_to_json(t)::text FROM '+table+' t ORDER BY row_to_json(t)::text').fetchall() for table in ['ops.project_budget','ops.tenant_budgets','ops.audit_events','portal.conversations']}

def test_missing_mock_budgets_only_and_repeat_preserves_rows(db_fixture):
    f=db_fixture;before=snapshot(f);assert initialize_missing_mock_budgets(f.db)==['A','B'];after=snapshot(f)
    assert before['ops.project_budget']==after['ops.project_budget'] and before['portal.conversations']==after['portal.conversations']
    with f.db.admin_connection() as conn:
        assert conn.execute('SELECT sum(allocated_cap_krw) FROM ops.tenant_budgets').fetchone()[0]==Decimal(25000)
        assert conn.execute("SELECT count(*) FROM ops.tenant_budgets b JOIN ops.project_budget p USING(budget_id) WHERE p.mode='real'").fetchone()[0]==0
    assert initialize_missing_mock_budgets(f.db)==[];assert snapshot(f)==after

@pytest.mark.parametrize('allocated,expected',[(10000,12500),(24000,1000),(25000,0)])
def test_existing_allocated_accounted_reserved_never_reset(db_fixture,allocated,expected):
    f=db_fixture
    with f.db.admin_connection() as conn:
        bid=conn.execute("SELECT budget_id FROM ops.project_budget WHERE mode='mock'").fetchone()[0]
        conn.execute('INSERT INTO ops.tenant_budgets(tenant_id,budget_id,allocated_cap_krw,local_cap_krw,accounted_krw,reserved_krw,active_slot) VALUES(%s,%s,%s,9000,11,3,1)',(f.tenant_ids['A'],bid,allocated))
        before=conn.execute('SELECT row_to_json(t)::text FROM ops.tenant_budgets t WHERE tenant_id=%s',(f.tenant_ids['A'],)).fetchall()
    assert initialize_missing_mock_budgets(f.db)==['B']
    with f.db.admin_connection() as conn:
        assert conn.execute('SELECT row_to_json(t)::text FROM ops.tenant_budgets t WHERE tenant_id=%s',(f.tenant_ids['A'],)).fetchall()==before
        assert conn.execute('SELECT allocated_cap_krw FROM ops.tenant_budgets WHERE tenant_id=%s',(f.tenant_ids['B'],)).fetchone()[0]==Decimal(expected)

def test_unowned_database_rejected_without_mutation(owned_cluster):
    with pytest.raises(MigrationError):initialize_missing_mock_budgets(FixtureDatabase('unowned',owned_cluster))

def private_env(tmp_path,extra=''):
    directory=tmp_path/'runtime';directory.mkdir(mode=0o700);path=directory/'app.env'
    original="AI_WEB_DSN='synthetic-web-dsn'\nAI_LOGIN_HMAC_SECRET=synthetic-hmac-secret-32-characters\nAI_OPENAI_API_KEY=synthetic-registration-marker-not-real-key\n"+extra
    _write_private(path,original);return path,original

def test_private_key_auth_lines_permissions_and_repeat_preserved(tmp_path):
    path,original=private_env(tmp_path);assert merge_private_environment(path,'synthetic-meter-dsn')
    value=path.read_text();assert value.startswith(original);assert os.stat(path).st_mode&0o777==0o600
    assert 'AI_MODE=mock' in value and 'AI_EXECUTION_ENABLED=true' in value
    assert not merge_private_environment(path,'synthetic-meter-dsn');assert path.read_text()==value
    assert list(path.parent.glob('mock-config-*.tmp'))==[]

@pytest.mark.parametrize('extra', ['AI_MODE=real\n','AI_METER_DSN=another-database\n','AI_MODE=mock\nAI_MODE=mock\n'])
def test_existing_private_configuration_conflict_preserved(tmp_path,extra):
    path,original=private_env(tmp_path,extra)
    with pytest.raises(ValueError):merge_private_environment(path,'synthetic-meter-dsn')
    assert path.read_text()==original

def test_private_environment_unsafe_permissions_rejected(tmp_path):
    path,original=private_env(tmp_path);path.chmod(0o644)
    with pytest.raises(DevDBError):merge_private_environment(path,'synthetic-meter-dsn')
    assert path.read_text()==original
