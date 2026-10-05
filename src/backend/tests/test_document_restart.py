import json,time
from uuid import uuid4
import httpx
from test_auth_restart import LiveServer,BASE_URL,WRITE
from test_operations import ops_rows
from test_document_api import multipart

def test_native_queued_restart_publishes_once_and_cleanup(ops_rows,auth_settings,tmp_path):
    f=ops_rows;server=LiveServer(f,auth_settings)
    server.env.update(AI_SOURCE_ROOT=str(tmp_path/'native-sources'),AI_INDEX_ENABLED='false',AI_INDEX_DSN=f.db.runtime_dsn('ai_index'),AI_METER_DSN=f.db.runtime_dsn('ai_meter'))
    server.secrets += [server.env['AI_INDEX_DSN'],server.env['AI_METER_DSN']]
    try:
        server.start()
        with httpx.Client(base_url=BASE_URL,timeout=5,trust_env=False) as client:
            reply=client.post('/api/v1/auth/login',headers=WRITE,json={'login_id':'a-adm','password':f.passwords['A-ADM']});assert reply.status_code==200
            h={**WRITE,'X-CSRF-Token':reply.json()['data']['csrf_token'],'X-Tenant-ID':str(f.tenant_ids['A'])}
            meta={'client_upload_id':str(uuid4()),'title':'합성 문서','media_type':'text/markdown'}
            reply=client.post('/api/v1/admin/documents',headers=h,files=multipart(meta,'업무의 담당 부서는 팀이다.'.encode()));assert reply.status_code==202
            ids=reply.json()['data'];job=ids['job_id'];doc=ids['document_id'];read={'X-Tenant-ID':str(f.tenant_ids['A'])}
            assert client.get('/api/v1/admin/jobs/'+job,headers=read).json()['data']['state']=='queued'
            server.env['AI_INDEX_ENABLED']='true';server.restart()
            deadline=time.monotonic()+10
            while time.monotonic()<deadline:
                view=client.get('/api/v1/admin/jobs/'+job,headers=read).json()['data']
                if view['state']=='completed':break
                time.sleep(.05)
            assert view['state']=='completed'
            server.restart();assert client.get('/api/v1/admin/jobs/'+job,headers=read).json()['data']['state']=='completed'
            assert client.post('/api/v1/admin/documents',headers=h,files=multipart(meta,'업무의 담당 부서는 팀이다.'.encode())).json()['data']['job_id']==job
            reply=client.request('DELETE','/api/v1/admin/documents/'+doc,headers=h,json={'expected_revision':1});assert reply.status_code==200
            deadline=time.monotonic()+10
            while time.monotonic()<deadline:
                with f.db.admin_connection() as c:
                    done=c.execute("SELECT count(*) FROM rag.jobs WHERE job_kind='internal_cleanup' AND state='completed'").fetchone()[0]
                if done:break
                time.sleep(.05)
            assert done==1
            with f.db.admin_connection() as c:
                assert c.execute('SELECT count(*) FROM ops.call_attempts').fetchone()[0]==1
                assert c.execute('SELECT count(*) FROM rag.document_versions WHERE payload_purged AND title IS NULL AND source_object_key IS NULL').fetchone()[0]==1
                assert c.execute('SELECT count(*) FROM rag.chunks WHERE payload_purged AND embedding IS NULL AND text IS NULL').fetchone()[0]==1
                assert c.execute('SELECT count(*) FROM security.document_publications WHERE active').fetchone()[0]==0
            assert not list((tmp_path/'native-sources').rglob('source'))
    finally:
        server.stop();server.log.close()
