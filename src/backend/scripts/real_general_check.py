"""One bounded, owned synthetic real batch through the protected portal HTTP API.

Default is a paid-call-free preflight. Never delete its durable journal to retry.
No key, prompt, response or raw exception is written to public output.
"""
import argparse
from datetime import date
from decimal import Decimal
import hashlib,json,math,os,shlex,socket,subprocess,time
from pathlib import Path
from statistics import median
from uuid import UUID,uuid4,uuid5
import httpx
from pydantic import SecretStr
from psycopg.types.json import Jsonb
from app.config import Settings
from app.db import DB_MARKER
from app.ai.pricing import reservation_krw
from app.ai.token_limits import validate_general_input
from scripts.devdb import DevCluster,_read_private,_write_private
from scripts.migrate import FixtureDatabase
from scripts.seed import NAMESPACE

BACKEND=Path(__file__).resolve().parents[1]
PERIOD=date(2026,10,1)
TENANT=UUID('10000000-0000-4000-8000-00000000000a')
MAX_RESERVATION=Decimal('10.92')
REPRESENTATIVE_CAP=Decimal('500')
INPUTS=tuple((input_id,'AI 포털 학습의 목표를 한 문장으로 설명해 주세요.') for input_id in ('B06-G1','B06-G2','B06-G3'))
JOURNAL=BACKEND/'.runtime/B06-real-batch.json'
RESULT=BACKEND/'.runtime/B06-real-result.json'

class CheckError(RuntimeError):
    pass

def validate_limits(count,maximum):
    try:amount=Decimal(maximum)
    except Exception:raise CheckError('CHECK_LIMIT_REJECTED') from None
    if count!=3 or not amount.is_finite() or amount!=MAX_RESERVATION or reservation_krw('generate_general')*count>amount:
        raise CheckError('CHECK_LIMIT_REJECTED')
    return amount

def initialize_real_budget(db):
    """Only a missing A representative row; existing state is never reset."""
    with db.admin_connection() as conn:
        db.verify(conn)
        with conn.transaction():
            conn.execute('SELECT pg_advisory_xact_lock(250002)')
            project=conn.execute("SELECT budget_id,operational_cap_krw,stopped,stop_latch FROM ops.project_budget WHERE mode='real' AND period=%s FOR UPDATE",(PERIOD,)).fetchone()
            if not project or project[2] or project[3]:raise CheckError('PROJECT_NOT_READY')
            actor=conn.execute("SELECT a.user_id FROM security.accounts a JOIN security.platform_access p USING(user_id) JOIN security.managed_tenants m USING(user_id) JOIN security.memberships s ON s.user_id=m.user_id AND s.tenant_id=m.tenant_id JOIN security.tenants t ON t.tenant_id=m.tenant_id WHERE a.login_id='p-a' AND a.active AND p.active AND p.is_padmin AND m.active AND s.active AND t.active AND m.tenant_id=%s",(TENANT,)).fetchone()
            if not actor or actor[0]!=uuid5(NAMESPACE,'P-A'):raise CheckError('MANAGED_SYNTHETIC_SCOPE_REQUIRED')
            if conn.execute('SELECT 1 FROM ops.tenant_budgets WHERE tenant_id=%s AND budget_id=%s',(TENANT,project[0])).fetchone():return False
            allocated=conn.execute('SELECT coalesce(sum(allocated_cap_krw),0) FROM ops.tenant_budgets WHERE budget_id=%s',(project[0],)).fetchone()[0]
            if project[1]-allocated<REPRESENTATIVE_CAP:raise CheckError('REPRESENTATIVE_BUDGET_UNAVAILABLE')
            conn.execute('INSERT INTO ops.tenant_budgets(tenant_id,budget_id,allocated_cap_krw,local_cap_krw) VALUES(%s,%s,%s,%s)',(TENANT,project[0],REPRESENTATIVE_CAP,REPRESENTATIVE_CAP))
            conn.execute("INSERT INTO ops.audit_events(event_id,scope_kind,tenant_id,actor_id,action,result,revisions) VALUES(%s,'tenant',%s,%s,'real_representative_budget_initialized','ok',%s)",(uuid4(),TENANT,actor[0],Jsonb({'execution_mode':'real','allocated_cap_krw':'500','bootstrap':'owned_synthetic_fixture'})))
            return True

def budget_snapshot(db):
    with db.admin_connection() as conn:
        db.verify(conn)
        row=conn.execute("SELECT p.approved_cap_krw,p.operational_cap_krw,p.accounted_krw,p.reserved_krw,p.active_slot,p.stopped,p.stop_latch,b.allocated_cap_krw,b.local_cap_krw,b.accounted_krw,b.reserved_krw,b.active_slot,b.stopped FROM ops.project_budget p LEFT JOIN ops.tenant_budgets b ON b.budget_id=p.budget_id AND b.tenant_id=%s WHERE p.mode='real' AND p.period=%s",(TENANT,PERIOD)).fetchone()
        if not row:raise CheckError('PROJECT_NOT_READY')
        names=('approved_cap_krw','operational_cap_krw','project_accounted_krw','project_reserved_krw','project_slots','project_stopped','stop_latch','allocated_cap_krw','local_cap_krw','tenant_accounted_krw','tenant_reserved_krw','tenant_slots','tenant_stopped')
        return {k:str(v) if isinstance(v,Decimal) else v for k,v in zip(names,row)}

def check_budget(snapshot,remaining=MAX_RESERVATION):
    if snapshot['allocated_cap_krw'] is None:raise CheckError('REAL_TENANT_BUDGET_REQUIRED')
    if snapshot['project_stopped'] or snapshot['stop_latch'] or snapshot['tenant_stopped'] or snapshot['project_slots'] or snapshot['tenant_slots']:
        raise CheckError('REAL_EXECUTION_NOT_READY')
    used=Decimal(snapshot['project_accounted_krw'])+Decimal(snapshot['project_reserved_krw'])
    local_used=Decimal(snapshot['tenant_accounted_krw'])+Decimal(snapshot['tenant_reserved_krw'])
    if used+remaining>min(REPRESENTATIVE_CAP,Decimal(snapshot['operational_cap_krw'])) or local_used+remaining>min(REPRESENTATIVE_CAP,Decimal(snapshot['local_cap_krw'])):
        raise CheckError('REPRESENTATIVE_BUDGET_UNAVAILABLE')

def private_settings(cluster,db):
    values={}
    for line in _read_private(cluster.runtime/'app.env').splitlines():
        if not line.strip() or line.lstrip().startswith('#'):continue
        key,value=line.split('=',1)
        if key in values:raise CheckError('CONFIGURATION_REJECTED')
        parsed=shlex.split(value)
        if len(parsed)!=1:raise CheckError('CONFIGURATION_REJECTED')
        values[key]=parsed[0]
    if values.get('AI_MODE')!='mock' or values.get('AI_WEB_DSN')!=db.runtime_dsn() or values.get('AI_METER_DSN')!=db.runtime_dsn('ai_meter'):
        raise CheckError('PRIVATE_CONFIGURATION_MISMATCH')
    settings=Settings(mode='real',execution_enabled=True,web_dsn=SecretStr(values['AI_WEB_DSN']),meter_dsn=SecretStr(values['AI_METER_DSN']),login_hmac_secret=SecretStr(values['AI_LOGIN_HMAC_SECRET']),openai_api_key=SecretStr(values.get('AI_OPENAI_API_KEY','')))
    settings.require_auth_configuration();settings.require_execution_configuration()
    validate_general_input('질문에 답해 주세요.',[],INPUTS[0][1])
    return settings

def save_private(path,value):
    tmp=path.with_name(path.name+'.'+uuid4().hex+'.tmp')
    try:
        _write_private(tmp,json.dumps(value,ensure_ascii=False))
        with tmp.open('rb') as handle:os.fsync(handle.fileno())
        os.replace(tmp,path)
        fd=os.open(path.parent,os.O_RDONLY)
        try:os.fsync(fd)
        finally:os.close(fd)
    finally:tmp.unlink(missing_ok=True)

def create_journal(path=JOURNAL):
    journal={'kind':'B06-one-real-batch','mode':'real','count_limit':3,'reservation_limit_krw':'10.92','status':'started','requests':[]}
    try:_write_private(path,json.dumps(journal))
    except FileExistsError:raise CheckError('REAL_BATCH_ALREADY_RECORDED') from None
    with path.open('rb') as handle:os.fsync(handle.fileno())
    fd=os.open(path.parent,os.O_RDONLY)
    try:os.fsync(fd)
    finally:os.close(fd)
    return journal

def latency_summary(samples):
    if len(samples)!=20:raise CheckError('LATENCY_SAMPLE_COUNT_INVALID')
    ordered=sorted(samples);p95=ordered[math.ceil(.95*len(ordered))-1]
    return {'samples':len(samples),'median_ms':round(median(samples),2),'p95_ms':round(p95,2),'max_ms':round(max(samples),2),'method':'nearest_rank','target_p95_ms':300,'target_met':p95<=300}

def data(reply,allowed=(200,)):
    if reply.status_code not in allowed:raise CheckError('PORTAL_HTTP_'+str(reply.status_code))
    return reply.json()['data']

def create_real_app():
    """Native B06 child: central provider with body-free transport observations."""
    import httpx2
    import app.main as main
    from app.ai.providers import OpenAIProvider
    metadata={'requests':[]}
    path=BACKEND/'.runtime/B06-provider-metadata.json'
    async def requested(request):
        payload=json.loads(request.content)
        metadata['requests'].append({key:payload.get(key) for key in ('model','service_tier','max_completion_tokens','stream','stream_options','n','store')})
        save_private(path,metadata)
    async def responded(response):
        metadata['requests'][-1]['http_status']=response.status_code
        if response.status_code>=400:
            await response.aread()
            try:code=response.json().get('error',{}).get('code')
            except Exception:code=None
            if code in ('invalid_api_key','insufficient_quota','rate_limit_exceeded','model_not_found','unsupported_parameter'):
                metadata['requests'][-1]['provider_error_code']=code
        save_private(path,metadata)
    class ObservedProvider(OpenAIProvider):
        def __init__(self,key):
            super().__init__(key,http_client=httpx2.AsyncClient(trust_env=False,timeout=60,event_hooks={'request':[requested],'response':[responded]}))
    main.OpenAIProvider=ObservedProvider
    cluster=DevCluster();db=FixtureDatabase(json.loads(_read_private(cluster.runtime/'active-fixture.json'))['database'],cluster)
    save_private(path,metadata)
    return main.create_app(private_settings(cluster,db))

def start_server(cluster,db):
    with socket.socket() as probe:probe.bind(('127.0.0.1',8000))
    # Only the backend child reads private settings. No credential in command arguments.
    code="from scripts.real_general_check import create_real_app\nimport uvicorn\nuvicorn.run(create_real_app(),host='127.0.0.1',port=8000,access_log=False,log_level='critical')"
    env={k:v for k,v in os.environ.items() if not k.startswith(('AI_','PG','OPENAI_'))}
    log=os.fdopen(os.open(cluster.runtime/'B06-native-private.log',os.O_WRONLY|os.O_CREAT|os.O_TRUNC|os.O_NOFOLLOW,0o600),'w')
    process=subprocess.Popen([str(BACKEND/'.venv/bin/python'),'-c',code],cwd=BACKEND,env=env,stdout=log,stderr=log)
    try:
        for _ in range(150):
            if process.poll() is not None:raise CheckError('NATIVE_START_FAILED')
            try:
                if httpx.get('http://127.0.0.1:8000/api/v1/health',timeout=.2,trust_env=False).status_code==200:return process,log
            except httpx.HTTPError:pass
            time.sleep(.1)
        raise CheckError('NATIVE_START_TIMEOUT')
    except BaseException:
        stop_server(process,log);raise

def stop_server(process,log):
    if process.poll() is None:process.terminate()
    try:process.wait(timeout=10)
    except subprocess.TimeoutExpired:process.kill();process.wait(timeout=3)
    log.close()

def check_one(client,headers,input_id,prompt,db,journal):
    record={'input_id':input_id,'client_send_id':str(uuid4()),'status':'admitting'}
    journal['requests'].append(record);save_private(JOURNAL,journal)
    start=time.monotonic();first=None
    try:
        view=data(client.post('/api/v1/runs',headers=headers,json={'agent_key':'general','client_send_id':record['client_send_id'],'prompt':prompt}),allowed=(200,202))
    except httpx.HTTPError:
        # Lost acceptance is reconciled by the same ID; no POST or provider retry.
        view=data(client.get('/api/v1/runs/by-send/'+record['client_send_id'],headers=headers))
    record['run_id']=view['run_id'];save_private(JOURNAL,journal)
    try:
        with client.stream('GET','/api/v1/runs/'+view['run_id']+'/events',headers={**headers,'Accept':'text/event-stream'},timeout=190) as stream:
            if stream.status_code!=200:raise CheckError('STREAM_HTTP_'+str(stream.status_code))
            event='';lines=[]
            for line in stream.iter_lines():
                if line.startswith('event: '):event=line[7:]
                elif line.startswith('data: '):lines.append(line[6:])
                elif not line and lines:
                    payload=json.loads('\n'.join(lines));lines=[]
                    if payload['run_id']!=view['run_id'] or payload['tenant_id']!=str(TENANT):raise CheckError('STREAM_SCOPE_INVALID')
                    d=payload['data']
                    if first is None and ((event=='draft_delta' and d.get('text')) or (d.get('result') or {}).get('text')):first=time.monotonic()-start
                    if event in ('terminal','delivery_error'):break
    except httpx.HTTPError:
        record['stream_delivery_lost']=True
    # A stored canonical GET is required even after a terminal frame or EOF.
    end=time.monotonic()+185
    while True:
        view=data(client.get('/api/v1/runs/'+record['run_id'],headers=headers))
        if view['is_terminal']:break
        if time.monotonic()>end:raise CheckError('CANONICAL_TERMINAL_UNCONFIRMED')
        time.sleep(2)
    elapsed=time.monotonic()-start
    if first is None and (view.get('result') or {}).get('text'):first=elapsed
    record.update(status=view['state'],execution_mode=view['execution_mode'],usage_status=view['usage_status'],content_status=view['content_status'],error_code=view['error_code'],first_body_seconds=None if first is None else round(first,3),terminal_seconds=round(elapsed,3),first_body_target_met=first is not None and first<=10,terminal_target_met=elapsed<=30)
    with db.admin_connection() as conn:
        rows=conn.execute('SELECT call_id,state,provider_end_status,slot_held,usage_snapshot FROM ops.call_attempts WHERE run_id=%s',(record['run_id'],)).fetchall()
        if len(rows)!=1:raise CheckError('CALL_CARDINALITY_INVALID')
        call,state,end_status,held,receipt=rows[0]
        settlements=conn.execute("SELECT count(*),coalesce(sum(delta_accounted_krw),0) FROM ops.usage_events WHERE call_id=%s AND event_kind='settle'",(call,)).fetchone()
        record.update(call_id=str(call),call_state=state,provider_end_status=end_status,slot_held=held,settle_count=settlements[0],estimated_cost_krw=str(settlements[1]),tokens=None if receipt is None else {k:receipt[k] for k in ('input_tokens','output_tokens','total_tokens')},observed_model=None if receipt is None else receipt['observed_model'],observed_tier=None if receipt is None else receipt['observed_tier'])
    save_private(JOURNAL,journal)
    return record

def run_check(count=3,maximum='10.92',execute=False):
    validate_limits(count,maximum)
    cluster=DevCluster();prior=cluster.status()['state'];process=log=None;db=None;journal=None
    config_hash=hashlib.sha256((cluster.runtime/'app.env').read_bytes()).hexdigest()
    result={'kind':'B06-real-general-check','mode':'real','status':'preflight','paid_retry_count':0,'count_limit':3,'reservation_limit_krw':'10.92','requests':[]}
    if execute and JOURNAL.exists():raise CheckError('REAL_BATCH_ALREADY_RECORDED')
    if prior!='running':cluster.start()
    try:
        registry=json.loads(_read_private(cluster.runtime/'active-fixture.json'))
        if registry.get('marker')!=DB_MARKER:raise CheckError('PRIMARY_MARKER_REQUIRED')
        db=FixtureDatabase(registry['database'],cluster);private_settings(cluster,db)
        if not execute:
            snapshot=budget_snapshot(db);result['budget_before']=snapshot
            result['status']='ready' if snapshot['allocated_cap_krw'] is not None else 'real_budget_first_preparation_required'
            return result
        journal=create_journal()
        result['budget_row_created']=initialize_real_budget(db);result['budget_before']=budget_snapshot(db);check_budget(result['budget_before'])
        process,log=start_server(cluster,db)
        passwords=json.loads(_read_private(cluster.runtime/(db.name+'-fixture-secrets.json')))['passwords']
        with httpx.Client(base_url='http://127.0.0.1:8000',timeout=5,trust_env=False) as client:
            transport={'Origin':'http://127.0.0.1:5173','X-Requested-With':'ai-portal'}
            auth=data(client.post('/api/v1/auth/login',headers=transport,json={'login_id':'a-u1','password':passwords['A-U1']}))
            headers={**transport,'X-Tenant-ID':str(TENANT),'X-CSRF-Token':auth['csrf_token']}
            samples=[]
            for _ in range(20):
                begin=time.monotonic();data(client.get('/api/v1/conversations',headers=headers));samples.append((time.monotonic()-begin)*1000)
            result['get_latency']=latency_summary(samples)
            for index,(input_id,prompt) in enumerate(INPUTS):
                check_budget(budget_snapshot(db),reservation_krw('generate_general')*(3-index))
                agents=data(client.get('/api/v1/agents',headers=headers))['items']
                if not any(a['agent_key']=='general' and a.get('available') for a in agents):raise CheckError('GENERAL_AGENT_NOT_READY')
                record=check_one(client,headers,input_id,prompt,db,journal)
                result['requests']=journal['requests']
                if record['status']!='completed' or record['usage_status']!='final' or record['call_state']!='settled' or record['settle_count']!=1 or record['slot_held']:
                    result['status']='blocked';break
            else:result['status']='pass'
            data(client.post('/api/v1/auth/logout',headers=transport|{'X-CSRF-Token':auth['csrf_token']}))
    except Exception as error:
        result['status']='blocked';result['safe_error_code']=str(error) if isinstance(error,CheckError) else 'REAL_CHECK_FAILED'
        if journal:result['requests']=journal['requests']
    finally:
        if process:stop_server(process,log)
        metadata_path=cluster.runtime/'B06-provider-metadata.json'
        if process and metadata_path.exists():result['provider_transport']=json.loads(_read_private(metadata_path))
        if db:
            result['budget_after']=budget_snapshot(db)
            with db.admin_connection() as conn:result['runtime_pool_connections_after']=conn.execute("SELECT count(*) FROM pg_stat_activity WHERE datname=%s AND usename IN ('ai_web','ai_meter','ai_index')",(db.name,)).fetchone()[0]
        if prior!='running':cluster.stop()
        result['cluster_state_after']=cluster.status()['state'];result['private_mock_configuration_identical']=hashlib.sha256((cluster.runtime/'app.env').read_bytes()).hexdigest()==config_hash
        if journal:
            journal['status']=result['status'];save_private(JOURNAL,journal);save_private(RESULT,result)
    return result

def main():
    parser=argparse.ArgumentParser(description='Owned synthetic B06 check; paid execution limited to one recorded batch')
    parser.add_argument('--count',type=int,default=3);parser.add_argument('--max-reservation-krw',default='10.92');parser.add_argument('--execute',action='store_true')
    args=parser.parse_args()
    try:result=run_check(args.count,args.max_reservation_krw,args.execute)
    except Exception as error:result={'status':'blocked','safe_error_code':str(error) if isinstance(error,CheckError) else 'REAL_CHECK_FAILED'}
    print(json.dumps(result,ensure_ascii=False));return 0 if result['status'] in ('pass','ready','real_budget_first_preparation_required') else 1

if __name__=='__main__':raise SystemExit(main())
