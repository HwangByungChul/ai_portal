from uuid import UUID,uuid4
from datetime import date
import pytest
from psycopg.types.json import Jsonb
from app.ai.repository import CallRepository,ExecutionError
from app.db import open_meter_pool
from app.builder.execution import TrialExecutor
from app.ai.gateway import AiGateway
from app.ai.providers import MockProvider
from app.assets.published import PublishedRepository
from app.assets.deployments import DeploymentRepository
from app.errors import AppError
from test_operations import ops_rows
from test_builder_shares import setup,share
from test_asset_deployments import request,decide

async def publish(f,repo,**audience):
    ctx,saved,t,b,e=await setup(f,repo);s=await share(t,ctx,body=b);d=DeploymentRepository(f.pool);req,_=await request(f,ctx,d,s['share_id'],**audience);await decide(f,d,req['request_id'])
    return ctx,saved,b,d
async def start(f,ctx,saved,body,client=None):
    return await PublishedRepository(f.pool).admit(ctx,UUID(saved['asset_id']),{'version_id':UUID(saved['version_id']),'expected_publication_revision':1,'client_send_id':client or uuid4(),'values':body},date(2026,10,1),'mock',b'p'*32,uuid4())

def test_ordinary_user_exact_published_profile_result_and_central_meter(ops_rows):
    f=ops_rows
    async def check():
        async with open_meter_pool(f.db.runtime_dsn('ai_meter')) as meter:
            calls=CallRepository(f.pool,meter,date(2026,10,1));owner,saved,b,d=await publish(f,calls);ctx=await f.context('A-U1','A');p=PublishedRepository(f.pool);asset=UUID(saved['asset_id'])
            listing=await p.rpc(ctx,'published_agent_read',(ctx.session_id,ctx.tenant_id,'list',None,Jsonb({}),'mock'));assert listing['items'][0]['asset_id']==saved['asset_id'] and listing['items'][0]['variables']==['audience','question','rule']
            values={'audience':'사용자','rule':'통제','question':'질문값'};client=uuid4();run=await start(f,ctx,saved,values,client);assert run['asset_binding']['source']=='published_agent'
            assert (await start(f,ctx,saved,values,client))['run_id']==run['run_id']
            ticket=await calls.claim(ctx,UUID(run['run_id']),'mock');assert ticket.task_kind=='asset_chat' and ticket.asset_binding.version_id==UUID(saved['version_id'])
            assert ticket.messages==[{'role':'system','content':'시스템 사용자'},{'role':'developer','content':'검토 기준 통제'},{'role':'user','content':'질문 질문값'}]
            engine=TrialExecutor(calls,AiGateway(calls,MockProvider()),None);await engine.finish(ticket,await engine.execute(ticket))
            view=await p.read(ctx,UUID(run['run_id']));assert view['content_status']=='final' and view['usage_status']=='final' and '모의 AI 응답' in view['result']['text']
            other=await f.context('A-U2','A')
            with pytest.raises(AppError) as denied:await p.read(other,UUID(run['run_id']))
            assert denied.value.status==404
            with f.db.admin_connection() as c:
                assert c.execute('SELECT count(*) FROM ops.call_attempts WHERE run_id=%s AND state=%s',(UUID(run['run_id']),'settled')).fetchone()[0]==1
                assert c.execute("SELECT count(*) FROM ops.usage_events e JOIN ops.call_attempts c USING(tenant_id,call_id) WHERE c.run_id=%s AND e.event_kind='settle'",(UUID(run['run_id']),)).fetchone()[0]==1
            h=await p.rpc(ctx,'published_agent_read',(ctx.session_id,ctx.tenant_id,'history',asset,Jsonb({}),'mock'));assert len(h['items'])==1
    f.run(check())

@pytest.mark.parametrize('case',['restricted','retired','policy','fixed_access','other_tenant'])
def test_dynamic_publication_and_current_policy_gate(ops_rows,case):
    f=ops_rows
    async def check():
        async with open_meter_pool(f.db.runtime_dsn('ai_meter')) as meter:
            calls=CallRepository(f.pool,meter,date(2026,10,1));owner,saved,b,d=await publish(f,calls,**({'audience':'restricted','member_ids':[str(f.actor_ids['A-U2'])]} if case=='restricted' else {}));ctx=await f.context('A-U1','B' if case=='other_tenant' else 'A') if case!='other_tenant' else await f.context('B-U1','B')
            if case in ('restricted','other_tenant'):
                with pytest.raises(AppError) as denied:await start(f,ctx,saved,b['values'] if 'values' in b else {'audience':'담당','rule':'기준','question':'질문'})
                assert denied.value.status==404;return
            data=await start(f,ctx,saved,{'audience':'담당','rule':'기준','question':'질문'});ticket=await calls.claim(ctx,UUID(data['run_id']),'mock')
            if case=='retired':await d.call(await f.context('P-A','A'),'retire',UUID(saved['asset_id']),{'expected_revision':1},'mock')
            else:
                with f.db.admin_connection() as c:
                    if case=='policy':c.execute("UPDATE portal.agent_configs SET config_version=config_version+1 WHERE tenant_id=%s AND agent_key='general'",(ctx.tenant_id,))
                    else:c.execute("INSERT INTO portal.agent_access(tenant_id,agent_key,mode,member_ids,revision) VALUES(%s,'general','restricted','{}',1)",(ctx.tenant_id,))
            with pytest.raises(ExecutionError):
                if case=='policy':await calls.reserve(ticket,b'x'*32)
                else:await calls.heartbeat(ticket)
            await calls.fail(ticket,'EXECUTION_BLOCKED')
            if case=='retired':
                with pytest.raises(AppError):await PublishedRepository(f.pool).read(ctx,UUID(data['run_id']))
                history=await PublishedRepository(f.pool).rpc(ctx,'published_agent_read',(ctx.session_id,ctx.tenant_id,'history',UUID(saved['asset_id']),Jsonb({}),'mock'));assert len(history['items'])==1
    f.run(check())

def test_dynamic_agent_favorite_toggle_and_filter(ops_rows):
    f=ops_rows
    async def check():
        async with open_meter_pool(f.db.runtime_dsn('ai_meter')) as meter:
            calls=CallRepository(f.pool,meter,date(2026,10,1));owner,saved,b,d=await publish(f,calls);ctx1=await f.context('A-U1','A');ctx2=await f.context('A-U2','A')
            p=PublishedRepository(f.pool);asset_id=UUID(saved['asset_id'])
            # 1. 초기 상태: 둘 다 즐겨찾기 아님
            listing1=await p.rpc(ctx1,'published_agent_read',(ctx1.session_id,ctx1.tenant_id,'list',None,Jsonb({}),'mock'))
            item1=listing1['items'][0];assert item1['favorite'] is False and item1['favorite_revision']==0
            # 2. U1 즐겨찾기 등록 (expected_revision 0 -> 1)
            fav_res=await p.favorite(ctx1,asset_id,True,0,uuid4())
            assert fav_res['active'] is True and fav_res['revision']==1
            # 3. U1 목록 조회: 즐겨찾기 반영 확인
            listing1=await p.rpc(ctx1,'published_agent_read',(ctx1.session_id,ctx1.tenant_id,'list',None,Jsonb({}),'mock'))
            assert listing1['items'][0]['favorite'] is True and listing1['items'][0]['favorite_revision']==1
            # 4. mine=true 필터링 확인
            mine1=await p.rpc(ctx1,'published_agent_read',(ctx1.session_id,ctx1.tenant_id,'list',None,Jsonb({'mine':True}),'mock'))
            assert len(mine1['items'])==1 and mine1['items'][0]['asset_id']==saved['asset_id']
            # 5. U2는 즐겨찾기 안 되어 있음
            listing2=await p.rpc(ctx2,'published_agent_read',(ctx2.session_id,ctx2.tenant_id,'list',None,Jsonb({}),'mock'))
            assert listing2['items'][0]['favorite'] is False and listing2['items'][0]['favorite_revision']==0
            mine2=await p.rpc(ctx2,'published_agent_read',(ctx2.session_id,ctx2.tenant_id,'list',None,Jsonb({'mine':True}),'mock'))
            assert len(mine2['items'])==0
            # 6. CAS 충돌 테스트 (expected_revision 0 재시도 시 409)
            with pytest.raises(AppError) as conflict:
                await p.favorite(ctx1,asset_id,False,0,uuid4())
            assert conflict.value.status==409
            # 7. U1 즐겨찾기 해제 (expected_revision 1 -> 2)
            unfav_res=await p.favorite(ctx1,asset_id,False,1,uuid4())
            assert unfav_res['active'] is False and unfav_res['revision']==2
            mine1_after=await p.rpc(ctx1,'published_agent_read',(ctx1.session_id,ctx1.tenant_id,'list',None,Jsonb({'mine':True}),'mock'))
            assert len(mine1_after['items'])==0
            # 8. 감사 로그 확인
            with f.db.admin_connection() as c:
                events=c.execute("SELECT count(*) FROM ops.audit_events WHERE action='catalog.dynamic_favorite' AND tenant_id=%s",(ctx1.tenant_id,)).fetchone()[0]
                assert events>=2
    f.run(check())

