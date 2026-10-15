import asyncio
from uuid import uuid4
import pytest
from app.errors import AppError
from app.tools.repository import ToolRepository
from app.tools.execution import ToolExecutionService
from app.tools.registry import ToolRegistry
from app.tools.adapters import FixtureToolAdapter
from app.guardrails.service import GuardrailService

class CountingAdapter(FixtureToolAdapter):
    def __init__(self): self.calls=0
    def handle_data_view_reader(self,args):
        self.calls+=1
        return super().handle_data_view_reader(args)

async def setup(f,audience="all",members=None):
    adapter=CountingAdapter(); registry=ToolRegistry(adapter=adapter)
    repo=ToolRepository(f.pool)
    service=ToolExecutionService(repo,registry,"mock",GuardrailService(f.pool))
    author=await f.context("A-ADM","A");approver=await f.context("P-A","A")
    user=await f.context("A-U1","A")
    descriptor=service.descriptor("data_view_reader")
    body={"client_request_id":str(uuid4()),"descriptor":descriptor,"audience":audience,"member_ids":members or [],"expected_head_revision":0}
    proposal=await repo.approval(author,"submit",None,body)
    await repo.approval(approver,"approve",proposal["request_id"],{"comment":"fixture review", "expected_revision":1})
    return adapter,repo,service,user,author,approver,proposal

@pytest.mark.anyio
async def test_saved_result_survives_new_service_and_body_conflicts(db_fixture):
    adapter,repo,service,user,*_=await setup(db_fixture)
    cid=uuid4();args={"view_name":"branch_daily_stats"}
    first=await service.invoke(user,"data_view_reader",args,cid)
    restarted=ToolExecutionService(ToolRepository(db_fixture.pool),service.registry,"mock",GuardrailService(db_fixture.pool))
    second=await restarted.invoke(user,"data_view_reader",args,cid)
    assert first["state"]==second["state"]=="succeeded"
    assert first["result"]==second["result"] and adapter.calls==1
    with pytest.raises(AppError) as err:await service.invoke(user,"data_view_reader",{"view_name":"other"},cid)
    assert err.value.status==409 and adapter.calls==1

@pytest.mark.anyio
async def test_concurrent_calls_claim_one_handler(db_fixture):
    import time
    adapter,repo,service,user,*_=await setup(db_fixture)
    original=service.registry.get('data_view_reader').handler
    def slow(args):time.sleep(.1);return original(args)
    service.registry.get('data_view_reader').handler=slow
    cid=uuid4();args={'view_name':'branch_daily_stats'}
    restarted=ToolExecutionService(repo,service.registry,'mock',GuardrailService(db_fixture.pool))
    replies=await asyncio.gather(service.invoke(user,'data_view_reader',args,cid),restarted.invoke(user,'data_view_reader',args,cid))
    assert any(r['state']=='succeeded' for r in replies)
    assert adapter.calls==1
    assert (await restarted.read(user,'data_view_reader',cid))['state']=='succeeded'

@pytest.mark.anyio
async def test_self_approval_denied_and_restricted_audience(db_fixture):
    member=str(db_fixture.actor_ids['A-U2'])
    adapter,repo,service,user,author,approver,proposal=await setup(db_fixture,'restricted',[member])
    with pytest.raises(AppError) as denied:await repo.approval(author,'approve',proposal['request_id'],{'comment':'fixture review', 'expected_revision':1})
    assert denied.value.status==403
    with pytest.raises(AppError) as denied:await service.invoke(user,'data_view_reader',{'view_name':'branch_daily_stats'},uuid4())
    assert denied.value.status==403 and adapter.calls==0
    assert (await service.ready(user))[2]['execution_ready'] is False
    allowed=await db_fixture.context('A-U2','A')
    assert (await service.invoke(allowed,'data_view_reader',{'view_name':'branch_daily_stats'},uuid4()))['state']=='succeeded'

@pytest.mark.anyio
async def test_approval_revoke_hides_replay_and_prevents_dispatch(db_fixture):
    adapter,repo,service,user,author,approver,_=await setup(db_fixture)
    cid=uuid4();args={'view_name':'branch_daily_stats'}
    assert (await service.invoke(user,'data_view_reader',args,cid))['state']=='succeeded'
    await repo.approval(approver,'revoke',None,{'tool_id':'data_view_reader','comment':'fixture review', 'expected_revision':1})
    for request_id in (cid,uuid4()):
        with pytest.raises(AppError) as denied:await service.invoke(user,'data_view_reader',args,request_id)
        assert denied.value.status==403
    assert adapter.calls==1

@pytest.mark.anyio
async def test_expired_dispatch_is_unknown_without_reexecution(db_fixture):
    adapter,repo,service,user,*_=await setup(db_fixture)
    cid=uuid4();args={'view_name':'branch_daily_stats'};digest=service.descriptor('data_view_reader')['digest']
    await repo.execution(user,'admit','data_view_reader',digest,'mock',cid,args)
    dispatch=await repo.execution(user,'dispatch','data_view_reader',digest,'mock',cid,token=uuid4())
    assert dispatch['claimed']
    with db_fixture.db.admin_connection() as c:c.execute("UPDATE portal.tool_receipts SET lease_until=clock_timestamp()-interval '1 second'")
    for _ in range(2):assert (await service.invoke(user,'data_view_reader',args,cid))['state']=='unknown'
    assert adapter.calls==0

@pytest.mark.anyio
async def test_handler_timeout_never_reexecutes(db_fixture):
    import time
    adapter,repo,service,user,*_=await setup(db_fixture)
    original=service.registry.get('data_view_reader').handler
    def slow(args):time.sleep(.15);return original(args)
    # Runtime timeout may shorten an approved upper limit; it cannot extend it.
    service.registry.get('data_view_reader').handler=slow
    from unittest.mock import patch
    real_wait=asyncio.wait_for
    async def short_wait(coro,timeout):return await real_wait(coro,.02)
    cid=uuid4();args={'view_name':'branch_daily_stats'}
    with patch('app.tools.execution.asyncio.wait_for',short_wait):result=await service.invoke(user,'data_view_reader',args,cid)
    assert result['state']=='unknown' and result['result'] is None
    await asyncio.sleep(.2)
    assert (await service.invoke(user,'data_view_reader',args,cid))['state']=='unknown' and adapter.calls==1

@pytest.mark.anyio
async def test_output_policy_masks_or_blocks_before_receipt(db_fixture):
    from app.guardrails.repository import GuardrailRepository
    adapter,repo,service,user,author,approver,_=await setup(db_fixture)
    service.registry.get('data_view_reader').handler=lambda _: {'contact':'010-1234-5678'}
    first=await service.invoke(user,'data_view_reader',{'view_name':'branch_daily_stats'},uuid4())
    assert first['state']=='succeeded' and '010-1234-5678' not in str(first)
    policy=GuardrailRepository(db_fixture.pool);head=await policy.get_policy(approver)
    await policy.update_policy(approver,uuid4(),head['revision'],{'output_pii_action':'block'})
    second=await service.invoke(user,'data_view_reader',{'view_name':'branch_daily_stats'},uuid4())
    assert second['state']=='failed' and second['result'] is None
    with db_fixture.db.admin_connection() as c:
        assert '010-1234-5678' not in str(c.execute('SELECT result FROM portal.tool_receipts').fetchall())

@pytest.mark.parametrize('args',[{'view_name':['branch_daily_stats']},{'view_name':True},{'view_name':100},{'view_name':'x'*101},{'view_name':{'url':'http://example.invalid'}},{'view_name':'../private'},{'view_name':'DROP TABLE a'},{'view_name':'branch_daily_stats','extra':'x'}])
def test_strict_schema_blocks_type_length_and_nested_input(args):
    registry=ToolRegistry(adapter=FixtureToolAdapter())
    with pytest.raises(AppError) as invalid:registry.validate('data_view_reader',args)
    assert invalid.value.status==422

@pytest.mark.anyio
async def test_owner_isolation_and_membership_revocation(db_fixture):
    adapter,repo,service,user,*_=await setup(db_fixture)
    cid=uuid4();args={'view_name':'branch_daily_stats'}
    await service.invoke(user,'data_view_reader',args,cid)
    other=await db_fixture.context('A-U2','A')
    with pytest.raises(AppError) as missing:await service.read(other,'data_view_reader',cid)
    assert missing.value.status==404
    assert (await service.invoke(other,'data_view_reader',args,cid))['state']=='succeeded' and adapter.calls==2
    with db_fixture.db.admin_connection() as c:c.execute('UPDATE security.memberships SET active=false WHERE tenant_id=%s AND user_id=%s',(user.tenant_id,user.user_id))
    with pytest.raises(AppError):await service.read(user,'data_view_reader',cid)
    assert adapter.calls==2

@pytest.mark.anyio
async def test_cross_tenant_same_request_is_independent(db_fixture):
    adapter,repo,service,user,*_=await setup(db_fixture)
    # Extend only this disposable fixture platform manager's explicit managed scope.
    with db_fixture.db.admin_connection() as c:
        c.execute('INSERT INTO security.memberships(tenant_id,user_id,membership_id,role,active) VALUES(%s,%s,%s,%s,true)',(db_fixture.tenant_ids['B'],db_fixture.actor_ids['P-A'],uuid4(),'USER'))
        c.execute('INSERT INTO security.managed_tenants(user_id,tenant_id) VALUES(%s,%s)',(db_fixture.actor_ids['P-A'],db_fixture.tenant_ids['B']))
    author=await db_fixture.context('B-ADM','B');approver=await db_fixture.context('P-A','B');other=await db_fixture.context('B-U1','B')
    proposal=await repo.approval(author,'submit',None,{'client_request_id':str(uuid4()),'descriptor':service.descriptor('data_view_reader'),'audience':'all','member_ids':[],'expected_head_revision':0})
    await repo.approval(approver,'approve',proposal['request_id'],{'comment':'fixture review', 'expected_revision':1})
    cid=uuid4();args={'view_name':'branch_daily_stats'}
    first=await service.invoke(await db_fixture.context('DUAL','A'),'data_view_reader',args,cid);second=await service.invoke(await db_fixture.context('DUAL','B'),'data_view_reader',args,cid)
    assert first['receipt_id']!=second['receipt_id'] and adapter.calls==2
    assert first['approval_id']!=second['approval_id']

@pytest.mark.anyio
async def test_real_mode_is_not_fixture_fallback(db_fixture):
    adapter,repo,service,user,*_=await setup(db_fixture)
    real=ToolExecutionService(repo,service.registry,'real',GuardrailService(db_fixture.pool))
    with pytest.raises(AppError) as blocked:await real.invoke(user,'data_view_reader',{'view_name':'branch_daily_stats'},uuid4())
    assert blocked.value.status==409 and adapter.calls==0

@pytest.mark.anyio
async def test_save_failure_never_returns_handler_result(db_fixture):
    adapter,repo,service,user,*_=await setup(db_fixture)
    original=repo.execution
    async def broken(ctx,action,*args,**kwargs):
        if action=='finish':raise AppError('STORAGE_UNAVAILABLE',503)
        return await original(ctx,action,*args,**kwargs)
    repo.execution=broken
    cid=uuid4();args={'view_name':'branch_daily_stats'}
    with pytest.raises(AppError) as error:await service.invoke(user,'data_view_reader',args,cid)
    assert error.value.status==503 and adapter.calls==1
    repo.execution=original
    replay=await service.invoke(user,'data_view_reader',args,cid)
    assert replay['state']=='dispatched' and replay['result'] is None and adapter.calls==1

@pytest.mark.anyio
async def test_input_policy_blocks_before_any_admission(db_fixture):
    adapter,repo,service,user,*_=await setup(db_fixture)
    with pytest.raises(AppError) as blocked:await service.invoke(user,'data_view_reader',{'view_name':'010-1234-5678'},uuid4())
    assert blocked.value.code=='TOOL_INPUT_BLOCKED' and adapter.calls==0
    with db_fixture.db.admin_connection() as c:assert c.execute('SELECT count(*) FROM portal.tool_receipts').fetchone()[0]==0

@pytest.mark.anyio
async def test_stale_approval_and_wrong_dispatch_token(db_fixture):
    adapter,repo,service,user,author,approver,_=await setup(db_fixture)
    with pytest.raises(AppError) as stale:await repo.approval(author,'submit',None,{'client_request_id':str(uuid4()),'descriptor':service.descriptor('data_view_reader'),'audience':'all','member_ids':[],'expected_head_revision':0})
    assert stale.value.status==409
    cid=uuid4();digest=service.descriptor('data_view_reader')['digest']
    await repo.execution(user,'admit','data_view_reader',digest,'mock',cid,{'view_name':'branch_daily_stats'})
    await repo.execution(user,'dispatch','data_view_reader',digest,'mock',cid,token=uuid4())
    with pytest.raises(AppError) as wrong:await repo.execution(user,'finish','data_view_reader',digest,'mock',cid,token=uuid4(),result={'safe':'value'})
    assert wrong.value.status==422 and adapter.calls==0
    with db_fixture.db.admin_connection() as c:assert c.execute('SELECT result FROM portal.tool_receipts').fetchone()[0] is None

@pytest.mark.anyio
async def test_version_change_cannot_reuse_old_approval(db_fixture):
    adapter,repo,service,user,*_=await setup(db_fixture)
    service.registry.get('data_view_reader').timeout_seconds=9
    with pytest.raises(AppError) as denied:await service.invoke(user,'data_view_reader',{'view_name':'branch_daily_stats'},uuid4())
    assert denied.value.status==403 and adapter.calls==0

@pytest.mark.anyio
async def test_revocation_between_handler_and_save_publishes_nothing(db_fixture):
    adapter,repo,service,user,author,approver,_=await setup(db_fixture)
    original=repo.execution
    async def revoke_first(ctx,action,*args,**kwargs):
        if action=='finish':await repo.approval(approver,'revoke',None,{'tool_id':'data_view_reader','comment':'fixture review', 'expected_revision':1})
        return await original(ctx,action,*args,**kwargs)
    repo.execution=revoke_first
    with pytest.raises(AppError) as denied:await service.invoke(user,'data_view_reader',{'view_name':'branch_daily_stats'},uuid4())
    assert denied.value.status==403 and adapter.calls==1
    with db_fixture.db.admin_connection() as c:assert c.execute('SELECT result FROM portal.tool_receipts').fetchone()[0] is None


def test_main_auth_http_tool_approval_and_execution(db_fixture,auth_settings):
    from pydantic import SecretStr
    from fastapi.testclient import TestClient
    from app.main import create_app
    from support import login as sign_in
    settings=auth_settings.model_copy(update={'execution_enabled':True,'meter_dsn':SecretStr(db_fixture.db.runtime_dsn('ai_meter'))})
    with TestClient(create_app(settings),base_url='http://127.0.0.1:8000',client=('127.0.0.1',50000)) as client:
        def headers(session):return {'X-Tenant-ID':str(db_fixture.tenant_ids['A']),'X-CSRF-Token':session['csrf_token'],'Origin':'http://127.0.0.1:5173','X-Requested-With':'ai-portal'}
        user=sign_in(client,'A-U1',db_fixture.passwords)
        before=client.get('/api/v1/tools',headers=headers(user));assert before.status_code==200
        assert not any(t['execution_ready'] for t in before.json()['data']['items'])
        forbidden=client.post('/api/v1/admin/tool-approvals',headers=headers(user),json={'tool_id':'data_view_reader','client_request_id':str(uuid4()),'expected_head_revision':0})
        assert forbidden.status_code==403
        author=sign_in(client,'A-ADM',db_fixture.passwords)
        proposal=client.post('/api/v1/admin/tool-approvals',headers=headers(author),json={'tool_id':'data_view_reader','client_request_id':str(uuid4()),'expected_head_revision':0,'audience':'all'})
        assert proposal.status_code==200;rid=proposal.json()['data']['request_id']
        self_approval=client.post(f'/api/v1/admin/tool-approvals/{rid}/decision',headers=headers(author),json={'decision':'approve','comment':'fixture review', 'expected_revision':1})
        assert self_approval.status_code==403
        approver=sign_in(client,'P-A',db_fixture.passwords)
        approved=client.post(f'/api/v1/admin/tool-approvals/{rid}/decision',headers=headers(approver),json={'decision':'approve','comment':'fixture review', 'expected_revision':1});assert approved.status_code==200
        user=sign_in(client,'A-U1',db_fixture.passwords);cid=str(uuid4());payload={'client_request_id':cid,'arguments':{'view_name':'branch_daily_stats'}}
        invoked=client.post('/api/v1/tools/data_view_reader/invoke',headers=headers(user),json=payload)
        assert invoked.status_code==200 and invoked.json()['data']['state']=='succeeded'
        again=client.post('/api/v1/tools/data_view_reader/invoke',headers=headers(user),json=payload)
        assert again.json()['data']['receipt_id']==invoked.json()['data']['receipt_id']
        saved=client.get(f'/api/v1/tools/data_view_reader/receipts/{cid}',headers=headers(user));assert saved.json()['data']['result']['source']=='fixture'
        invalid=client.post('/api/v1/tools/data_view_reader/invoke',headers=headers(user),json={'client_request_id':'invalid','arguments':{}});assert invalid.status_code==422
        bad_csrf=client.post('/api/v1/tools/data_view_reader/invoke',headers=headers(user)|{'X-CSRF-Token':'wrong'},json=payload);assert bad_csrf.status_code==403
        oversized=client.post('/api/v1/tools/data_view_reader/invoke',headers=headers(user),json={'client_request_id':str(uuid4()),'arguments':{'view_name':'x'*33000}});assert oversized.status_code==413
        with db_fixture.db.admin_connection() as c:
            assert c.execute("SELECT count(*) FROM ops.audit_events WHERE action='tool.dispatched'").fetchone()[0]==1

@pytest.mark.anyio
async def test_admission_audit_failure_rolls_back_receipt(db_fixture):
    adapter,repo,service,user,*_=await setup(db_fixture)
    with db_fixture.db.admin_connection() as c:c.execute('DROP POLICY audit_tool_runtime ON ops.audit_events')
    with pytest.raises(AppError) as unavailable:await service.invoke(user,'data_view_reader',{'view_name':'branch_daily_stats'},uuid4())
    assert unavailable.value.status==503 and adapter.calls==0
    with db_fixture.db.admin_connection() as c:assert c.execute('SELECT count(*) FROM portal.tool_receipts').fetchone()[0]==0

@pytest.mark.anyio
async def test_bounded_owner_queue_preserves_existing_retry(db_fixture):
    adapter,repo,service,user,*_=await setup(db_fixture)
    digest=service.descriptor('data_view_reader')['digest'];ids=[uuid4() for _ in range(20)];args={'view_name':'branch_daily_stats'}
    for cid in ids:await repo.execution(user,'admit','data_view_reader',digest,'mock',cid,args)
    with pytest.raises(AppError) as full:await service.invoke(user,'data_view_reader',args,uuid4())
    assert full.value.status==429 and adapter.calls==0
    assert (await service.invoke(user,'data_view_reader',args,ids[0]))['state']=='succeeded' and adapter.calls==1


def test_046_addition_preserves_rows_checksums_and_privilege_boundary(owned_cluster,tmp_path):
    import hashlib,shutil
    import psycopg
    from scripts.migrate import MIGRATIONS,create_fixture_database,apply_migrations
    from scripts.seed import seed_fixture
    from test_catalog_migration import fingerprint
    old=tmp_path/'through045';old.mkdir()
    for path in MIGRATIONS.glob('[0-9][0-9][0-9]_*.sql'):
        if path.name<'046_':shutil.copy2(path,old/path.name)
    hashes={path.name:hashlib.sha256(path.read_bytes()).hexdigest() for path in old.iterdir()}
    db=create_fixture_database();state=None
    try:
        apply_migrations(db,old);state=seed_fixture(db)
        with db.admin_connection() as c:before=fingerprint(c);assert len(before)==56
        stage=tmp_path/'046through049';stage.mkdir()
        for migration in MIGRATIONS.glob('[0-9][0-9][0-9]_*.sql'):
            if migration.name<'050_':shutil.copy2(migration,stage/migration.name)
        assert apply_migrations(db,stage)==['046_tool_approvals_and_receipts.sql','047_approved_workflow_versions.sql','048_workflow_execution_ledger.sql','049_meeting_workflow_binding.sql']
        with db.admin_connection() as c:
            after=fingerprint(c);assert len(after)==65
            assert all(after[name]==value for name,value in before.items())
            assert dict(c.execute("SELECT version,sha256 FROM infra.schema_migrations WHERE version<'046_'").fetchall())==hashes
            for table in ['tool_approvals','tool_heads','tool_receipts','workflows','workflow_versions','workflow_heads','workflow_runs','workflow_steps']:
                assert c.execute('SELECT relrowsecurity AND relforcerowsecurity FROM pg_class WHERE oid=%s::regclass',('portal.'+table,)).fetchone()[0]
                for role in ['ai_web','ai_index','ai_meter']:
                    for privilege in ['SELECT','INSERT','UPDATE','DELETE']:
                        assert not c.execute('SELECT has_table_privilege(%s,%s,%s)',(role,'portal.'+table,privilege)).fetchone()[0]
            assert c.execute("SELECT count(*) FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace WHERE n.nspname='security'").fetchone()[0]==169
        with psycopg.connect(db.runtime_dsn(),autocommit=True) as c:
            with pytest.raises(psycopg.errors.InsufficientPrivilege):c.execute('SELECT * FROM portal.tool_receipts')
            with pytest.raises(psycopg.errors.InsufficientPrivilege):c.execute('SELECT * FROM portal.workflow_versions')
        assert apply_migrations(db,stage)==[]
    finally:
        db.drop()
        if state:state.secret_path.unlink(missing_ok=True)

@pytest.mark.anyio
async def test_global_stop_blocks_new_calls_and_saved_result(db_fixture):
    adapter,repo,service,user,*_=await setup(db_fixture)
    cid=uuid4();args={'view_name':'branch_daily_stats'}
    await service.invoke(user,'data_view_reader',args,cid)
    with db_fixture.db.admin_connection() as c:c.execute("UPDATE ops.project_budget SET stopped=true WHERE mode='mock'")
    assert not any(t['execution_ready'] for t in await service.ready(user))
    for request_id in (cid,uuid4()):
        with pytest.raises(AppError) as denied:await service.invoke(user,'data_view_reader',args,request_id)
        assert denied.value.status==403
    assert adapter.calls==1

@pytest.mark.anyio
async def test_replay_checks_revocation_after_output_audit(db_fixture):
    adapter,repo,service,user,author,approver,_=await setup(db_fixture)
    cid=uuid4();args={'view_name':'branch_daily_stats'}
    await service.invoke(user,'data_view_reader',args,cid)
    inspect=service.guardrails.inspect
    async def inspect_and_revoke(ctx,text,**kwargs):
        result=await inspect(ctx,text,**kwargs)
        if kwargs.get('direction')=='output':await repo.approval(approver,'revoke',None,{'tool_id':'data_view_reader','comment':'fixture review', 'expected_revision':1})
        return result
    service.guardrails.inspect=inspect_and_revoke
    with pytest.raises(AppError) as denied:await service.read(user,'data_view_reader',cid)
    assert denied.value.status==403 and adapter.calls==1
