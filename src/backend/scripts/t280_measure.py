"""Native Mock integration measurement on a marked disposable DB only."""
import asyncio,hashlib,json,math,os,platform,shutil,socket,subprocess,sys,time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from uuid import UUID,uuid4
from importlib.metadata import version
from scripts.c06_evaluate import Api

ROOT=Path(__file__).resolve().parents[3]
BACKEND=ROOT/'src/backend'

def percentile(samples, fraction):
    if not samples or not 0<fraction<=1 or any(type(x) not in (int,float) or not math.isfinite(x) or x<0 for x in samples):raise ValueError('INVALID_SAMPLES')
    return sorted(samples)[math.ceil(fraction*len(samples))-1]

def summarize(rows,target_ms,expected=20):
    values=[r['duration_ms'] for r in rows];errors=sum(r['status']!=200 or not r['scope_valid'] for r in rows)
    return {'samples':rows,'count':len(rows),'expected_count':expected,'errors':errors,'error_rate':errors/len(rows) if rows else None,'p50_ms':percentile(values,.5) if values else None,'p95_ms':percentile(values,.95) if values else None,'max_ms':max(values) if values else None,'target_ms':target_ms,'verdict':'pass' if len(rows)==expected and not errors and percentile(values,.95)<=target_ms else 'fail'}

def main():
    import httpx
    from scripts.devdb import DevCluster,_write_private,_read_private
    from scripts.migrate import create_fixture_database,apply_migrations
    from scripts.seed import seed_fixture
    from psycopg.types.json import Jsonb
    from app.db import open_web_pool
    from app.types import AuthContext
    from app.documents.repository import DocumentRepository
    from app.documents.search import SearchRepository
    from app.documents.storage import SourceStorage
    cluster=DevCluster();prior=cluster.status()['state'];db=None;state=None;api=None;proc=None;log=None;store=BACKEND/'.runtime'/('T280-source-'+uuid4().hex);start=time.monotonic();result={'stage':'T280','mode':'mock','paid_dispatches':0,'metrics':{},'concurrent':{},'execution_status':'running'}
    def save(path,obj):
        if path.exists():_read_private(path);path.unlink()
        _write_private(path,json.dumps(obj,ensure_ascii=False,indent=2))
    try:
        with socket.socket() as s:s.setsockopt(socket.SOL_SOCKET,socket.SO_REUSEADDR,1);s.bind(('127.0.0.1',8000))
        if prior!='running':cluster.start()
        db=create_fixture_database();apply_migrations(db);state=seed_fixture(db)
        with db.admin_connection() as conn:
            db.verify(conn)
            for tenant in state.tenant_ids.values():
                conn.execute("INSERT INTO ops.tenant_budgets(tenant_id,budget_id,allocated_cap_krw,local_cap_krw) SELECT %s,budget_id,12500,12500 FROM ops.project_budget WHERE mode='mock'",(tenant,))
                conn.execute("UPDATE portal.agent_configs SET enabled=true,settings=%s WHERE tenant_id=%s",(Jsonb({'name':'합성 검증','description':'모의 측정','instructions':'허용 근거만 선택한다.'}),tenant))
        env={k:v for k,v in os.environ.items() if not k.startswith(('AI_','PG'))};secret=__import__('secrets').token_urlsafe(32);env.update(AI_WEB_DSN=db.runtime_dsn(),AI_METER_DSN=db.runtime_dsn('ai_meter'),AI_INDEX_DSN=db.runtime_dsn('ai_index'),AI_LOGIN_HMAC_SECRET=secret,AI_MODE='mock',AI_EXECUTION_ENABLED='true',AI_INDEX_ENABLED='true',AI_SOURCE_ROOT=str(store))
        log=os.fdopen(os.open(BACKEND/'.runtime/T280-native-private.log',os.O_WRONLY|os.O_CREAT|os.O_TRUNC,0o600),'w');proc=subprocess.Popen([sys.executable,'-m','uvicorn','app.main:create_app','--factory','--host','127.0.0.1','--port','8000','--no-proxy-headers','--no-access-log'],cwd=BACKEND,env=env,stdout=log,stderr=log)
        deadline=time.monotonic()+20
        while time.monotonic()<deadline:
            if proc.poll() is not None:raise RuntimeError('NATIVE_START_FAILED')
            try:
                if httpx.get('http://127.0.0.1:8000/api/v1/health',timeout=.3,trust_env=False).status_code==200:break
            except httpx.HTTPError:pass
            time.sleep(.1)
        else:raise RuntimeError('NATIVE_NOT_READY')
        api=Api(state);mapping={};manifest=json.loads((ROOT/'data/synthetic/document_manifest.json').read_text());index_samples=[]
        for doc in manifest['documents']:
            raw=(ROOT/doc['source_path']).read_bytes();assert hashlib.sha256(raw).hexdigest()==doc['sha256'];tenant=doc['owner_tenant_id'];actor=tenant+'-ADM';meta={'client_upload_id':str(uuid4()),'title':doc['title'],'media_type':'text/markdown'}
            if doc['version']=='v2':
                old=mapping[(doc['document_id'],'v1')];listing=api.data(actor,tenant,'GET','/admin/documents')['items'];meta['expected_revision']=next(x['revision'] for x in listing if x['document_id']==old['document_id']);path='/admin/documents/'+old['document_id']+'/versions'
            else:
                meta.update(visibility='private' if doc['scope']=='private' else 'org',reader_ids=[])
                if doc['owner_actor_id']:meta['owner_user_id']=str(state.actor_ids[doc['owner_actor_id']])
                path='/admin/documents'
            tick=time.monotonic();receipt=api.data(actor,tenant,'POST',path,files={'metadata':(None,json.dumps(meta),'application/json'),'file':('document.md',raw,'text/markdown')});job=api.terminal(actor,tenant,'/admin/jobs/'+receipt['job_id'],'terminal');assert job['state']=='completed';mapping[(doc['document_id'],doc['version'])]=receipt
            index_samples.append({'document_alias':doc['document_id'],'version_alias':doc['version'],'bytes':len(raw),'upload_to_observed_publication_ms':round((time.monotonic()-tick)*1000,3),'mode':'mock','real_index_latency':'not_run'})
            if (doc['document_id'],doc['version'])==('D-S','v1'):api.data('A-ADM','A','POST','/admin/documents/'+receipt['document_id']+'/versions/'+receipt['version_id']+'/grants',json={'recipient_tenant_id':str(state.tenant_ids['B']),'expected_publication_revision':1})
        run_payload={'client_send_id':str(uuid4()),'agent_key':'rules_rag','prompt':'가상 여신심사의 담당 부서는?'};run=api.data('A-U1','A','POST','/runs',json=run_payload)['run_id'];view=api.terminal('A-U1','A','/runs/'+run,'is_terminal');assert view['state']=='completed' and view['answer_kind']=='answer';proof=api.data('A-U1','A','GET','/runs/'+run+'/evidence');source=proof['items'][0]['source_url'].removeprefix('/api/v1');expected_sha=next(d['sha256'] for d in manifest['documents'] if mapping[(d['document_id'],d['version'])]['version_id']==proof['items'][0]['version_id'])
        def request_sample(actor,tenant,path,validator):
            tick=time.monotonic();reply=api.request(actor,tenant,'GET',path);duration=round((time.monotonic()-tick)*1000,3)
            valid=validator(reply) if reply.status_code==200 else False
            return {'duration_ms':duration,'status':reply.status_code,'scope_valid':bool(valid)}
        specifications=[('agent_list','A-U2','A','/agents',lambda q:all(x['agent_key'] in ('general','rules_rag') for x in q.json()['data']['items']),300),('document_list','A-U2','A','/documents',lambda q:all(x['visibility']=='org' for x in q.json()['data']['items']),300),('conversation_list','A-U2','A','/conversations',lambda q:all(x['tenant_id']==str(state.tenant_ids['A']) for x in q.json()['data']['items']),300),('personal_usage','A-U2','A','/usage/me',lambda q:q.json()['data']['execution_mode']=='mock',300),('organization_usage','A-ADM','A','/admin/usage',lambda q:q.json()['data']['execution_mode']=='mock',300),('run_state','A-U1','A','/runs/'+run,lambda q:q.json()['data']['run_id']==run and q.json()['data']['state']=='completed',300),('evidence','A-U1','A','/runs/'+run+'/evidence',lambda q:q.json()['data']['items'][0]['quote']==proof['items'][0]['quote'],500),('source','A-U1','A',source,lambda q:hashlib.sha256(q.content).hexdigest()==expected_sha and q.headers.get('cache-control')=='no-store',300)]
        for name,actor,tenant,path,validator,target in specifications:
            api.client(actor)
            for _ in range(3):assert request_sample(actor,tenant,path,validator)['scope_valid']
            result['metrics'][name]=summarize([request_sample(actor,tenant,path,validator) for _ in range(20)],target)
        # Each pair uses a separate authenticated HTTP connection and organization.
        api.client('DUAL');api.client('B-U1');parallel=[]
        def scoped_conversations(actor,tenant):return request_sample(actor,tenant,'/conversations',lambda q:all(x['tenant_id']==str(state.tenant_ids[tenant]) for x in q.json()['data']['items']))
        with ThreadPoolExecutor(max_workers=2) as executor:
            for _ in range(10):
                futures=[executor.submit(scoped_conversations,'DUAL','A'),executor.submit(scoped_conversations,'B-U1','B')];parallel.extend(f.result() for f in futures)
        result['concurrent']=summarize(parallel,500);result['concurrent']['pairs']=10;result['concurrent']['connections']=2
        # Pre-computed fixed query vector: measures real RLS/search/provenance without an embedding/generation request.
        with db.admin_connection() as conn:
            sid,csrf=conn.execute('SELECT session_id,csrf_secret FROM security.sessions WHERE user_id=%s AND revoked_at IS NULL ORDER BY issued_at DESC LIMIT 1',(state.actor_ids['A-U1'],)).fetchone()
        ctx=AuthContext(sid,state.actor_ids['A-U1'],state.tenant_ids['A'],'USER',csrf)
        async def search_measure():
            async with open_web_pool(db.runtime_dsn(),size=1) as pool:
                repository=SearchRepository(DocumentRepository(pool,SourceStorage(store),secret));vector=[1/math.sqrt(1536)]*1536;rows=[]
                for index in range(23):
                    tick=time.monotonic();allowed=await repository.allowed(ctx,None,'mock');packets,required=await repository.packets(ctx,'가상 여신심사의 담당 부서는?','mock',allowed,vector);elapsed=round((time.monotonic()-tick)*1000,3);valid=bool(packets and '담당부서' in required and all(x.evidence['index_id'] in {s['index_id'] for s in allowed} for x in packets))
                    if index<3:assert valid
                    else:rows.append({'duration_ms':elapsed,'status':200,'scope_valid':valid})
                return summarize(rows,500)
        result['metrics']['fixed_vector_acl_search']=asyncio.run(search_measure());result['index_observations']=index_samples
        def hw(key):
            try:return subprocess.check_output(['sysctl','-n',key],text=True).strip()
            except subprocess.CalledProcessError:return 'unavailable'
        with db.admin_connection() as conn:
            result['corpus']={k:n for k,n in zip(('versions','chunks','entities','relations','evidence'),conn.execute('SELECT (SELECT count(*) FROM rag.document_versions),(SELECT count(*) FROM rag.chunks),(SELECT count(*) FROM rag.entities),(SELECT count(*) FROM rag.relations),(SELECT count(*) FROM rag.evidence)').fetchone())};pg=conn.execute('SHOW server_version').fetchone()[0];vector_version=conn.execute("SELECT extversion FROM pg_extension WHERE extname='vector'").fetchone()[0];result['calls']=[{'operation':o,'state':s,'count':n} for o,s,n in conn.execute('SELECT operation,state,count(*) FROM ops.call_attempts GROUP BY operation,state ORDER BY operation,state').fetchall()]
        result['environment']={'os':platform.system(),'os_version':platform.mac_ver()[0],'architecture':platform.machine(),'cpu':hw('machdep.cpu.brand_string'),'memory_bytes':hw('hw.memsize'),'python':platform.python_version(),'node':subprocess.check_output([str(Path.home()/'.nvm/versions/node/v22.23.1/bin/node'),'--version'],text=True).strip(),'postgresql':pg,'pgvector':vector_version,'sdk_openai':version('openai'),'workers':1,'provider':'Mock','external_network_calls':0,'free_disk_bytes':shutil.disk_usage(BACKEND).free,'source_hashes':{d['source_path']:d['sha256'] for d in manifest['documents']},'lock_hashes':{f:hashlib.sha256((ROOT/f).read_bytes()).hexdigest() for f in ['src/frontend/package-lock.json','src/backend/requirements.lock']}}
        # Stop only the owned native app, restart the owned cluster, then reconnect
        # to the same marked DB. No seed/reset/recovery shortcut is used.
        with db.admin_connection() as conn:
            before=conn.execute('SELECT (SELECT count(*) FROM ops.call_attempts),(SELECT count(*) FROM rag.evidence),(SELECT accounted_krw FROM ops.project_budget WHERE mode=\'mock\'),(SELECT reserved_krw FROM ops.project_budget WHERE mode=\'mock\')').fetchone()
        old_pid=proc.pid;proc.terminate();proc.wait(timeout=10);proc=None;cluster.stop();cluster.start()
        proc=subprocess.Popen([sys.executable,'-m','uvicorn','app.main:create_app','--factory','--host','127.0.0.1','--port','8000','--no-proxy-headers','--no-access-log'],cwd=BACKEND,env=env,stdout=log,stderr=log)
        deadline=time.monotonic()+20
        while time.monotonic()<deadline:
            try:
                if httpx.get('http://127.0.0.1:8000/api/v1/health',timeout=.3,trust_env=False).status_code==200:break
            except httpx.HTTPError:pass
            if proc.poll() is not None:raise RuntimeError('RESTART_FAILED')
            time.sleep(.1)
        else:raise RuntimeError('RESTART_NOT_READY')
        restored=api.data('A-U1','A','GET','/runs/'+run);replayed=api.data('A-U1','A','POST','/runs',json=run_payload);download=api.request('A-U1','A','GET',source)
        assert restored['result']==view['result'] and replayed['run_id']==run and download.status_code==200 and hashlib.sha256(download.content).hexdigest()==expected_sha
        with db.admin_connection() as conn:
            after=conn.execute('SELECT (SELECT count(*) FROM ops.call_attempts),(SELECT count(*) FROM rag.evidence),(SELECT accounted_krw FROM ops.project_budget WHERE mode=\'mock\'),(SELECT reserved_krw FROM ops.project_budget WHERE mode=\'mock\')').fetchone()
        assert before==after
        result['restart']={'native_app_pid_changed':old_pid!=proc.pid,'database_restarted':True,'same_marked_database':True,'saved_result_and_source_preserved':True,'same_send_same_run':True,'calls_evidence_accounted_reserved_unchanged':True,'additional_provider_calls':0}
        result['execution_status']='completed';result['verdict']='pass' if all(m['verdict']=='pass' for m in result['metrics'].values()) and result['concurrent']['verdict']=='pass' else 'fail'
        return 0 if result['verdict']=='pass' else 1
    finally:
        if api:api.close()
        if proc:
            proc.terminate()
            try:proc.wait(timeout=10)
            except subprocess.TimeoutExpired:proc.kill();proc.wait(timeout=5)
        if log:log.close()
        if db:
            with db.admin_connection() as conn:result['runtime_connections_after']=conn.execute('SELECT count(*) FROM pg_stat_activity WHERE datname=current_database() AND pid<>pg_backend_pid()').fetchone()[0]
            db.drop();result['fixture_removed']=True
        if state:state.secret_path.unlink(missing_ok=True)
        if store.exists():assert store.name.startswith('T280-source-') and store.parent==BACKEND/'.runtime';shutil.rmtree(store)
        result['source_store_removed']=not store.exists()
        if prior!='running':cluster.stop()
        result['cluster_after']=cluster.status()['state'];result['duration_seconds']=round(time.monotonic()-start,2);save(BACKEND/'.runtime/T280-performance-safe.json',result)

if __name__=='__main__':
    try:raise SystemExit(main())
    except Exception as error:
        import traceback
        from scripts.devdb import _write_private,_read_private
        p=BACKEND/'.runtime/T280-measure-error-private.txt'
        if p.exists():_read_private(p);p.unlink()
        _write_private(p,traceback.format_exc());print(json.dumps({'error':type(error).__name__,'private_diagnostic_saved':True}));raise SystemExit(1)
