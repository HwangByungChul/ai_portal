import os
import json
from pathlib import Path
import subprocess
import time
from uuid import uuid4
import httpx
from fastapi.testclient import TestClient
from app.main import create_app
from test_operations import ops_rows,headers


def test_enabled_http_intake_stream_terminal_usage_and_owner_isolation(ops_rows,auth_settings,login):
    f=ops_rows
    from pydantic import SecretStr
    settings=auth_settings.model_copy(update={'execution_enabled':True,'meter_dsn':SecretStr(f.db.runtime_dsn('ai_meter'))})
    with TestClient(create_app(settings),base_url='http://127.0.0.1:8000',client=('127.0.0.1',50000)) as client:
        csrf=login(client,'A-U1')['csrf_token']
        h=headers(f,'A',csrf);agent=client.get('/api/v1/agents',headers=headers(f)).json()['data']['items']
        assert [x['available'] for x in agent]==[True,False]
        send=uuid4();payload={'agent_key':'general','client_send_id':str(send),'prompt':'합성 HTTP 질문'}
        reply=client.post('/api/v1/runs',headers=h,json=payload);assert reply.status_code==202;run=reply.json()['data']['run_id']
        for _ in range(200):
            data=client.get('/api/v1/runs/'+run,headers=headers(f)).json()['data']
            if data['is_terminal']:break
            time.sleep(.02)
        assert data['state']=='completed' and data['content_status']=='final' and data['usage_status']=='final'
        assert client.post('/api/v1/runs',headers=h,json=payload).json()['data']['replayed']
        for _ in range(2):
            stream=client.get('/api/v1/runs/'+run+'/events',headers={**headers(f),'Accept':'text/event-stream'})
            assert stream.status_code==200 and stream.headers['cache-control']=='no-store'
            assert stream.text.count('event: snapshot')==1 and stream.text.count('event: terminal')==1
            assert '모의 AI 응답' in stream.text and 'worker_claim' not in stream.text and 'instructions' not in stream.text
        assert client.get('/api/v1/runs/'+run+'/events',headers=headers(f)).status_code==422
        assert client.get('/api/v1/runs/'+run+'/events',headers={**headers(f),'Accept':'text/event-stream','Last-Event-ID':'synthetic'}).status_code==200
        assert client.get('/api/v1/usage/me',headers=headers(f)).status_code==200
        login(client,'A-U2')
        assert client.get('/api/v1/runs/'+run+'/events',headers={**headers(f),'Accept':'text/event-stream'}).status_code==404
        assert client.get('/api/v1/runs/'+run+'/events',headers={**headers(f,'B'),'Accept':'text/event-stream'}).status_code in (403,404)
        with f.db.admin_connection() as conn:
            assert conn.execute('SELECT count(*) FROM ops.call_attempts').fetchone()[0]==1
            assert conn.execute("SELECT count(*) FROM ops.usage_events WHERE event_kind='settle'").fetchone()[0]==1
        client.app.state.execution.gateway.stop_latch=True
        login(client,'A-U1');csrf=client.get('/api/v1/auth/me').json()['data']['csrf_token']
        assert client.post('/api/v1/runs',headers=headers(f,'A',csrf),json={**payload,'client_send_id':str(uuid4())}).status_code==503


def test_native_process_crash_recovery_never_repeats_dispatch(ops_rows):
    f=ops_rows;b=Path(__file__).resolve().parents[1];process=None
    # The child only serves this disposable fixture and deterministic local provider.
    code="""import asyncio,os
from pydantic import SecretStr
import app.main as main
from app.ai.providers import MockProvider
from app.config import Settings
import uvicorn
class PausedProvider(MockProvider):
 async def generate(self,claim,messages,on_delta):
  await on_delta('합성 임시 초안');await asyncio.sleep(600)
if os.environ.get('TASK_B04_BLOCK')=='1':main.MockProvider=PausedProvider
settings=Settings(web_dsn=SecretStr(os.environ['TASK_B04_WEB']),meter_dsn=SecretStr(os.environ['TASK_B04_METER']),
 login_hmac_secret=SecretStr(os.environ['TASK_B04_HMAC']),execution_enabled=True,mode='mock',openai_api_key=None)
uvicorn.run(main.create_app(settings),host='127.0.0.1',port=8000,access_log=False,log_level='critical')
"""
    env={k:v for k,v in os.environ.items() if not k.startswith('AI_')}
    env.update(TASK_B04_WEB=f.db.runtime_dsn(),TASK_B04_METER=f.db.runtime_dsn('ai_meter'),TASK_B04_HMAC='synthetic-native-hmac-32-characters')
    from app.auth.crypto import new_secret
    env['TASK_B04_HMAC']=new_secret()
    logpath=b/'.runtime/B04-native-http-private.log'
    log=os.fdopen(os.open(logpath,os.O_WRONLY|os.O_CREAT|os.O_TRUNC,0o600),'w')
    def start(block):
        nonlocal process
        env['TASK_B04_BLOCK']='1' if block else '0'
        process=subprocess.Popen([str(b/'.venv/bin/python'),'-c',code],cwd=b,env=env,stdout=log,stderr=log)
        for _ in range(100):
            if process.poll() is not None:raise AssertionError('PRIVATE_NATIVE_SERVER_START_FAILED')
            try:
                if httpx.get('http://127.0.0.1:8000/api/v1/health',timeout=.2).status_code==200:return
            except httpx.HTTPError:pass
            time.sleep(.1)
        raise AssertionError('NATIVE_SERVER_NOT_READY')
    def login(client):
        reply=client.post('/api/v1/auth/login',headers={'Origin':'http://127.0.0.1:5173','X-Requested-With':'ai-portal'},
            json={'login_id':'a-u1','password':f.passwords['A-U1']});assert reply.status_code==200
        return reply.json()['data']['csrf_token']
    try:
        start(True)
        with httpx.Client(base_url='http://127.0.0.1:8000',timeout=5) as client:
            csrf=login(client);reply=client.post('/api/v1/runs',headers=headers(f,'A',csrf),
                json={'agent_key':'general','client_send_id':str(uuid4()),'prompt':'합성 재시작 질문'})
            assert reply.status_code==202;run=reply.json()['data']['run_id']
            for _ in range(100):
                with f.db.admin_connection() as conn:row=conn.execute('SELECT state FROM ops.call_attempts WHERE run_id=%s',(run,)).fetchone()
                if row==('dispatched',):break
                time.sleep(.05)
            assert row==('dispatched',)
            process.kill();process.wait(timeout=5);process=None
        start(False)
        with httpx.Client(base_url='http://127.0.0.1:8000',timeout=5) as client:
            login(client);data=client.get('/api/v1/runs/'+run,headers=headers(f)).json()['data']
            assert data['state']=='interrupted' and data['usage_status']=='unknown' and data['result'] is None
            reply=client.get('/api/v1/runs/'+run+'/events',headers={**headers(f),'Accept':'text/event-stream'})
            assert reply.status_code==200 and 'terminal' in reply.text and '합성 임시 초안' not in reply.text
        with f.db.admin_connection() as conn:
            assert conn.execute('SELECT count(*),min(state) FROM ops.call_attempts').fetchone()==(1,'usage_unknown')
            assert conn.execute("SELECT reserved_krw,active_slot FROM ops.project_budget WHERE mode='mock'").fetchone()==(__import__('decimal').Decimal('3.64'),1)
            assert conn.execute("SELECT count(*) FROM portal.messages WHERE role='assistant'").fetchone()[0]==0
    finally:
        if process is not None:
            process.terminate()
            try:process.wait(timeout=5)
            except subprocess.TimeoutExpired:process.kill();process.wait(timeout=5)
        log.close()


def test_real_execution_requires_explicit_meter_and_key_before_startup(auth_settings):
    from pydantic import SecretStr
    import pytest
    from app.main import create_app
    missing_meter=auth_settings.model_copy(update={'execution_enabled':True,'mode':'real','openai_api_key':None})
    with pytest.raises(ValueError,match='METER_CONFIGURATION_REQUIRED'):create_app(missing_meter)
    missing_key=missing_meter.model_copy(update={'meter_dsn':SecretStr('synthetic-not-a-dsn')})
    with pytest.raises(ValueError,match='PROVIDER_CONFIGURATION_REQUIRED'):create_app(missing_key)
