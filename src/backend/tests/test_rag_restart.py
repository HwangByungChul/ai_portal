import time
from uuid import UUID,uuid4
import httpx
from app.documents.repository import DocumentRepository
from app.documents.storage import SourceStorage
from test_document_sharing import publish
from test_operations import ops_rows
from test_auth_restart import LiveServer,BASE_URL,WRITE

def test_native_completed_rag_restart_does_not_dispatch_again(ops_rows,auth_settings):
    f=ops_rows;repo=DocumentRepository(f.pool,SourceStorage(auth_settings.source_root),'x'*40);f.run(publish(f,repo,f.run(f.context('A-ADM','A'))))
    server=LiveServer(f,auth_settings);server.env.update(AI_EXECUTION_ENABLED='true',AI_METER_DSN=f.db.runtime_dsn('ai_meter'),AI_SOURCE_ROOT=str(auth_settings.source_root));server.secrets.append(server.env['AI_METER_DSN'])
    try:
        server.start()
        with httpx.Client(base_url=BASE_URL,timeout=5,trust_env=False) as client:
            login=client.post('/api/v1/auth/login',headers=WRITE,json={'login_id':'a-u1','password':f.passwords['A-U1']});assert login.status_code==200
            write={**WRITE,'X-CSRF-Token':login.json()['data']['csrf_token'],'X-Tenant-ID':str(f.tenant_ids['A'])};read={'X-Tenant-ID':str(f.tenant_ids['A'])}
            body={'client_send_id':str(uuid4()),'agent_key':'rules_rag','prompt':'여신심사 담당 부서는?'}
            reply=client.post('/api/v1/runs',headers=write,json=body);assert reply.status_code==202;run=reply.json()['data']['run_id']
            for _ in range(100):
                view=client.get('/api/v1/runs/'+run,headers=read).json()['data']
                if view['is_terminal']:break
                time.sleep(.03)
            assert view['state']=='completed';stored=view['result']['text'];server.restart()
            after=client.get('/api/v1/runs/'+run,headers=read).json()['data'];assert after['state']=='completed' and after['result']['text']==stored
            assert client.post('/api/v1/runs',headers=write,json=body).json()['data']['run_id']==run
            with f.db.admin_connection() as c:assert c.execute('SELECT count(*) FROM ops.call_attempts').fetchone()[0]==3
    finally:server.stop();server.log.close()
