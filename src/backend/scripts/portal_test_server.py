"""A05/B05 browser-test harness: own marked disposable DB, loopback children only."""
from pathlib import Path
import json,os,shlex,signal,socket,subprocess,time,shutil
from uuid import uuid4
from scripts.devdb import DevCluster,_read_private,_write_private
from scripts.migrate import create_fixture_database,apply_migrations
from scripts.seed import seed_fixture
from app.db import DB_MARKER

BACKEND=Path(__file__).resolve().parents[1]
FRONTEND=BACKEND.parent/'frontend'
CONFIG=BACKEND/'.runtime/A05-fixture.json'
STOP=False

def stop(signum,frame):
    global STOP
    STOP=True

def main():
    cluster=DevCluster();prior=cluster.status()['state'];db=None;state=None;children=[];logs=[];configured=False;source_root=BACKEND/'.runtime'/("C05-source-"+uuid4().hex)
    try:
        for port in (8000,5173):
            with socket.socket() as probe:
                probe.setsockopt(socket.SOL_SOCKET,socket.SO_REUSEADDR,1);probe.bind(('127.0.0.1',port))
        if CONFIG.exists(): raise RuntimeError('TEST_RUNTIME_ALREADY_EXISTS')
        signal.signal(signal.SIGTERM,stop);signal.signal(signal.SIGINT,stop)
        if prior!='running': cluster.start()
        db=create_fixture_database();apply_migrations(db);state=seed_fixture(db)
        with db.admin_connection() as conn:
            for org in state.tenant_ids.values():
                conn.execute("INSERT INTO ops.tenant_budgets(tenant_id,budget_id,allocated_cap_krw,local_cap_krw) SELECT %s,budget_id,12500,12500 FROM ops.project_budget WHERE mode='mock'",(org,))
                conn.execute("UPDATE portal.agent_configs SET enabled=true WHERE tenant_id=%s AND agent_key='general'",(org,))
        _write_private(BACKEND/'.runtime/B05-provider-control.json',json.dumps({'behavior':'normal'}))
        with db.admin_connection() as conn:
            members=[{'tenant':str(t),'user':str(u),'role':role,'active':active,'revision':rev}
                for t,u,role,active,rev in conn.execute('SELECT tenant_id,user_id,role,active,revision FROM security.memberships').fetchall()]
        config={'kind':'A05-disposable-browser','pid':os.getpid(),'database':db.name,'marker':DB_MARKER,
                'secret_path':str(state.secret_path),'actors':{k:str(v) for k,v in state.actor_ids.items()},
                'tenants':{k:str(v) for k,v in state.tenant_ids.items()},'members':members,'conversations':[str(v) for v in state.conversation_ids.values()]}
        _write_private(CONFIG,json.dumps(config));configured=True
        env=os.environ.copy()
        for key in list(env):
            if key.startswith(('AI_','PG')): env.pop(key)
        api_env=env.copy()
        for line in _read_private(cluster.runtime/'app.env').splitlines():
            key,value=line.split('=',1)
            if key=='AI_LOGIN_HMAC_SECRET':api_env[key]=shlex.split(value)[0]
        api_env['AI_WEB_DSN']=db.runtime_dsn();api_env['AI_MODE']='mock';api_env['AI_EXECUTION_ENABLED']='true';api_env['AI_METER_DSN']=db.runtime_dsn('ai_meter');api_env['AI_INDEX_DSN']=db.runtime_dsn('ai_index');api_env['AI_INDEX_ENABLED']='true';api_env['AI_SOURCE_ROOT']=str(source_root)
        commands=[([str(BACKEND/'.venv/bin/python'),'-m','uvicorn','scripts.portal_test_app:create_app','--factory',
            '--host','127.0.0.1','--port','8000','--no-proxy-headers','--no-access-log'],BACKEND,api_env,'api'),
            ([str(Path.home()/'.nvm/versions/node/v22.23.1/bin/node'),str(FRONTEND/'node_modules/vite/bin/vite.js')],FRONTEND,env,'vite')]
        for command,cwd,child_env,name in commands:
            fd=os.open(BACKEND/'.runtime'/f'A05-{name}.log',os.O_WRONLY|os.O_CREAT|os.O_TRUNC,0o600)
            log=os.fdopen(fd,'w');logs.append(log)
            children.append(subprocess.Popen(command,cwd=cwd,env=child_env,stdout=log,stderr=log))
        while not STOP:
            request=BACKEND/'.runtime/C05-restart-request.json'
            if request.exists():
                assert json.loads(_read_private(request))['kind']=='C05-owned-child-restart'
                old=children[0];old.terminate();old.wait(timeout=5)
                command,cwd,child_env,name=commands[0]
                children[0]=subprocess.Popen(command,cwd=cwd,env=child_env,stdout=logs[0],stderr=logs[0])
                proof=BACKEND/'.runtime/C05-restart-done.json';proof.unlink(missing_ok=True)
                _write_private(proof,json.dumps({'restarted':True,'old_child_exited':old.poll() is not None,'new_pid_differs':children[0].pid!=old.pid}))
                request.unlink()
            if any(c.poll() is not None for c in children): raise RuntimeError('TEST_CHILD_FAILED')
            time.sleep(.1)
    except Exception:
        print(json.dumps({'error':'BROWSER_TEST_RUNTIME_FAILED'}));return 1
    finally:
        for child in children:
            if child.poll() is None: child.terminate()
        for child in children:
            try: child.wait(timeout=3)
            except subprocess.TimeoutExpired: child.kill();child.wait(timeout=3)
        for log in logs: log.close()
        proof={'kind':'A05-runtime-cleanup','api_pool_connections':None,'fixture_removed':False,'private_credentials_removed':False}
        if db:
            with db.admin_connection() as conn:
                proof['api_pool_connections']=conn.execute("SELECT count(*) FROM pg_stat_activity WHERE datname=%s AND usename IN ('ai_web','ai_meter','ai_index')",(db.name,)).fetchone()[0]
            db.drop();proof['fixture_removed']=True
        if state: state.secret_path.unlink(missing_ok=True);proof['private_credentials_removed']=True
        if source_root.exists():
            assert source_root.parent==BACKEND/'.runtime' and source_root.name.startswith('C05-source-');shutil.rmtree(source_root)
        proof['owned_source_store_removed']=not source_root.exists()
        if configured: CONFIG.unlink()
        for name in ['B05-provider-control.json','B05-provider-count.txt','C05-restart-request.json','C05-restart-done.json']:(BACKEND/'.runtime'/name).unlink(missing_ok=True)
        if prior!='running': cluster.stop()
        proof['database_state_after']=cluster.status()['state']
        path=BACKEND/'.runtime/A05-cleanup.json'
        if path.exists(): path.unlink()
        _write_private(path,json.dumps(proof))
    return 0

if __name__=='__main__': raise SystemExit(main())
