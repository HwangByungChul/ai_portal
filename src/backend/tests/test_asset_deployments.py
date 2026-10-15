from uuid import UUID,uuid4
from datetime import date
import pytest,psycopg
from app.ai.repository import CallRepository
from app.db import open_meter_pool
from app.errors import AppError
from app.assets.deployments import DeploymentRepository
from test_operations import ops_rows
from test_builder_shares import setup,share

async def request(f,ctx,repo,share_id,**changes):
    value={'client_request_id':str(uuid4()),'share_id':share_id,'expected_publication_revision':0,'reason':'검증된 초안 게시','audience':'all','member_ids':[],**changes}
    return await repo.call(ctx,'submit',None,value,'mock'),value
async def decide(f,repo,rid,actor='P-A',decision='approve',**changes):
    ctx=await f.context(actor,'A');body={'expected_revision':1,'decision':decision,'comment':'업무 품질과 보안 별도 확인','quality_reviewed':True,'security_reviewed':True,**changes}
    return await repo.call(ctx,'decide',UUID(rid),body,'mock')

def test_dynamic_approval_atomic_snapshot_replay_self_denial_retire(ops_rows):
    f=ops_rows
    async def check():
        async with open_meter_pool(f.db.runtime_dsn('ai_meter')) as meter:
            ctx,saved,t,b,e=await setup(f,CallRepository(f.pool,meter,date(2026,10,1)));s=await share(t,ctx,body=b);repo=DeploymentRepository(f.pool)
            req,body=await request(f,ctx,repo,s['share_id']);rid=req['request_id']
            assert (await repo.call(ctx,'submit',None,body,'mock'))['replayed']
            with pytest.raises(AppError) as conflict:await repo.call(ctx,'submit',None,body|{'reason':'변경'},'mock')
            assert conflict.value.status==409
            with pytest.raises(AppError) as denied:await decide(f,repo,rid,'A-ADM')
            assert denied.value.status==403
            with pytest.raises(AppError) as denied:await decide(f,repo,rid,quality_reviewed=False)
            assert denied.value.status==422
            approved=await decide(f,repo,rid);assert approved['status']=='approved' and approved['publication_revision']==1
            assert (await decide(f,repo,rid))['replayed']
            with pytest.raises(AppError) as conflict:await decide(f,repo,rid,decision='reject')
            assert conflict.value.status==409
            with f.db.admin_connection() as c:
                row=c.execute('SELECT version_id,asset_revision,status FROM portal.asset_publications').fetchone();assert str(row[0])==saved['version_id'] and row[1]==1 and row[2]=='published'
                assert c.execute('SELECT count(*) FROM ops.audit_events WHERE action=%s',('asset.deployment_approved',)).fetchone()[0]==1
                for sql in ["UPDATE portal.asset_deployments SET snapshot='{}'","UPDATE portal.asset_publications SET config='{}'",'DELETE FROM portal.asset_deployments','DELETE FROM portal.asset_publications']:
                    with pytest.raises(psycopg.errors.CheckViolation):
                        with c.transaction():c.execute(sql)
            admin=await f.context('P-A','A');retired=await repo.call(admin,'retire',UUID(saved['asset_id']),{'expected_revision':1},'mock');assert retired['publication_revision']==2
            assert (await repo.call(admin,'retire',UUID(saved['asset_id']),{'expected_revision':1},'mock'))['replayed']
            assert (await decide(f,repo,rid))['publication_revision']==1
            assert (await repo.call(ctx,'publication',UUID(saved['asset_id']),{},'mock'))['status']=='retired'
    f.run(check())

@pytest.mark.parametrize('changed',['withdraw','policy','mode','failed'])
def test_stale_evidence_never_publishes_and_rejection_remains_possible(ops_rows,changed):
    f=ops_rows
    async def check():
        async with open_meter_pool(f.db.runtime_dsn('ai_meter')) as meter:
            ctx,saved,t,b,e=await setup(f,CallRepository(f.pool,meter,date(2026,10,1)),['없음'] if changed=='failed' else None);s=await share(t,ctx,body=b);repo=DeploymentRepository(f.pool);req,_=await request(f,ctx,repo,s['share_id'])
            if changed=='withdraw':await share(t,ctx,'withdraw',s['share_id'],{'expected_revision':1})
            if changed=='policy':
                with f.db.admin_connection() as c:c.execute("UPDATE portal.agent_configs SET config_version=config_version+1 WHERE tenant_id=%s AND agent_key='general'",(ctx.tenant_id,))
            with pytest.raises(AppError) as blocked:
                if changed=='mode':await repo.call(await f.context('P-A','A'),'decide',UUID(req['request_id']),{'decision':'approve','expected_revision':1,'comment':'검토','quality_reviewed':True,'security_reviewed':True},'real')
                else:await decide(f,repo,req['request_id'])
            assert blocked.value.status in (404,409)
            assert (await decide(f,repo,req['request_id'],decision='reject'))['status']=='rejected'
            with f.db.admin_connection() as c:assert c.execute('SELECT count(*) FROM portal.asset_publications').fetchone()[0]==0
    f.run(check())
