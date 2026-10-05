from decimal import Decimal
import json
import pytest
from scripts.real_general_check import (CheckError,validate_limits,initialize_real_budget,budget_snapshot,check_budget,create_journal,save_private,latency_summary,TENANT)

@pytest.mark.parametrize('count,amount',[(0,'10.92'),(2,'10.92'),(4,'10.92'),(3,'NaN'),(3,'Infinity'),(3,'-1'),(3,'10.91'),(3,'11'),(3,'invalid')])
def test_unapproved_or_nonfinite_batch_limit_rejected(count,amount):
    with pytest.raises(CheckError,match='CHECK_LIMIT_REJECTED'):validate_limits(count,amount)

def test_exact_approved_three_request_bound():
    assert validate_limits(3,'10.92')==Decimal('10.92')

def rows(db):
    with db.admin_connection() as conn:
        return {table:conn.execute('SELECT row_to_json(t)::text FROM '+table+' t ORDER BY row_to_json(t)::text').fetchall() for table in ('ops.project_budget','ops.tenant_budgets','ops.audit_events')}

def test_real_representative_budget_only_missing_managed_a_and_repeat_preserves_ledger(db_fixture):
    f=db_fixture;before=rows(f.db)
    assert initialize_real_budget(f.db)
    after=rows(f.db);assert after['ops.project_budget']==before['ops.project_budget']
    value=budget_snapshot(f.db);assert value['allocated_cap_krw']=='500.000000';check_budget(value)
    assert not initialize_real_budget(f.db);assert rows(f.db)==after
    with f.db.admin_connection() as conn:
        assert conn.execute("SELECT count(*) FROM ops.tenant_budgets b JOIN ops.project_budget p USING(budget_id) WHERE p.mode='real'").fetchone()[0]==1
        conn.execute("UPDATE ops.tenant_budgets SET accounted_krw=20,reserved_krw=3.64,active_slot=1,stopped=true WHERE tenant_id=%s",(TENANT,))
    changed=rows(f.db);assert not initialize_real_budget(f.db);assert rows(f.db)==changed
    with pytest.raises(CheckError,match='REAL_EXECUTION_NOT_READY'):check_budget(budget_snapshot(f.db))

@pytest.mark.parametrize('mutation', ['manager_revoked','project_stopped','project_latch','allocated_full'])
def test_bootstrap_rejects_lost_authority_stop_or_exhausted_allocation(db_fixture,mutation):
    f=db_fixture
    with f.db.admin_connection() as conn:
        if mutation=='manager_revoked':conn.execute('UPDATE security.managed_tenants SET active=false')
        elif mutation=='project_stopped':conn.execute("UPDATE ops.project_budget SET stopped=true WHERE mode='real'")
        elif mutation=='project_latch':conn.execute("UPDATE ops.project_budget SET stop_latch=true WHERE mode='real'")
        else:conn.execute("INSERT INTO ops.tenant_budgets(tenant_id,budget_id,allocated_cap_krw,local_cap_krw) SELECT %s,budget_id,25000,25000 FROM ops.project_budget WHERE mode='real'",(f.tenant_ids['B'],))
    before=rows(f.db)
    with pytest.raises(CheckError):initialize_real_budget(f.db)
    assert rows(f.db)==before

def test_existing_spend_and_reservation_count_toward_representative_limit(db_fixture):
    f=db_fixture;initialize_real_budget(f.db)
    with f.db.admin_connection() as conn:
        conn.execute("UPDATE ops.project_budget SET accounted_krw=490,reserved_krw=1 WHERE mode='real'")
    with pytest.raises(CheckError,match='REPRESENTATIVE_BUDGET_UNAVAILABLE'):check_budget(budget_snapshot(f.db))
    with pytest.raises(CheckError,match='REPRESENTATIVE_BUDGET_UNAVAILABLE'):check_budget(budget_snapshot(f.db),Decimal('10'))

def test_durable_started_or_unknown_journal_blocks_all_new_paid_batches(tmp_path):
    path=tmp_path/'batch.json';journal=create_journal(path)
    journal['requests']=[{'input_id':'B06-G1','status':'admitting'}];save_private(path,journal)
    saved=path.read_bytes()
    with pytest.raises(CheckError,match='REAL_BATCH_ALREADY_RECORDED'):create_journal(path)
    assert path.read_bytes()==saved and path.stat().st_mode&0o777==0o600

def test_latency_twenty_nearest_rank_and_target_not_manufactured():
    value=latency_summary(list(range(1,21)));assert value['p95_ms']==19 and value['target_met']
    assert not latency_summary([400]*20)['target_met']
    with pytest.raises(CheckError):latency_summary([1,2,3])

@pytest.mark.parametrize('status,provider_code',[(200,None),(401,'invalid_api_key'),(429,'insufficient_quota')])
def test_provider_observations_do_not_capture_body_credentials_headers_or_error_message(tmp_path,monkeypatch,status,provider_code):
    import asyncio,httpx2
    import scripts.real_general_check as module
    import app.main as main
    from app.ai.providers import OpenAIProvider
    from app.ai.types import DispatchClaim
    from uuid import uuid4
    from test_ai_provider import chunk
    runtime=tmp_path/'.runtime';runtime.mkdir(mode=0o700)
    monkeypatch.setattr(module,'BACKEND',tmp_path)
    monkeypatch.setattr(module,'DevCluster',lambda:type('Cluster',(),{'runtime':runtime})())
    monkeypatch.setattr(module,'FixtureDatabase',lambda *a:object())
    monkeypatch.setattr(module,'_read_private',lambda path:json.dumps({'database':'synthetic-owned-db'}))
    monkeypatch.setattr(module,'private_settings',lambda *a:object())
    monkeypatch.setattr(main,'OpenAIProvider',OpenAIProvider)
    monkeypatch.setattr(main,'create_app',lambda settings:main.OpenAIProvider('synthetic-secret-provider-key'))
    original=httpx2.AsyncClient
    def transport(request):
        if status!=200:return httpx2.Response(status,json={'error':{'code':provider_code,'message':'private-error-body-never-recorded'}},request=request)
        body=''.join('data: '+json.dumps(v)+'\n\n' for v in [chunk('private-answer-never-recorded'),chunk(finish='stop'),chunk(usage={'prompt_tokens':4,'completion_tokens':3,'total_tokens':7})])+'data: [DONE]\n\n'
        return httpx2.Response(200,content=body.encode(),headers={'content-type':'text/event-stream'},request=request)
    class SyntheticClient(original):
        def __init__(self,**kwargs):super().__init__(**kwargs,transport=httpx2.MockTransport(transport))
    monkeypatch.setattr(httpx2,'AsyncClient',SyntheticClient)
    async def run():
        provider=module.create_real_app()
        async def delta(text):pass
        try:return await provider.generate(DispatchClaim(uuid4(),1,'synthetic-proof'),[{'role':'user','content':'private-prompt-never-recorded'}],delta)
        finally:await provider.close()
    outcome=asyncio.run(run());assert (outcome.safe_error_code is None)==(status==200)
    text=(runtime/'B06-provider-metadata.json').read_text();value=json.loads(text)['requests']
    assert len(value)==1 and value[0]['http_status']==status
    assert set(value[0])<=set(('model','service_tier','max_completion_tokens','stream','stream_options','n','store','http_status','provider_error_code'))
    assert all(secret not in text for secret in ('private-prompt-never-recorded','private-answer-never-recorded','private-error-body-never-recorded','synthetic-secret-provider-key','Authorization'))
