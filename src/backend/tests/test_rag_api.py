import time
from uuid import UUID
from pydantic import SecretStr
from fastapi.testclient import TestClient
from app.main import create_app
from app.documents.repository import DocumentRepository
from app.documents.storage import SourceStorage
from test_document_sharing import publish
from test_operations import ops_rows,headers

def test_full_http_rag_share_sources_revoke_and_no_unverified_stream(ops_rows,auth_settings):
    f=ops_rows;documents=DocumentRepository(f.pool,SourceStorage(auth_settings.source_root),auth_settings.login_hmac_secret.get_secret_value());a=f.run(f.context('A-ADM','A'));ids=f.run(publish(f,documents,a))
    settings=auth_settings.model_copy(update={'execution_enabled':True,'meter_dsn':SecretStr(f.db.runtime_dsn('ai_meter')),'index_enabled':True,'index_dsn':SecretStr(f.db.runtime_dsn('ai_index'))})
    with TestClient(create_app(settings),base_url='http://127.0.0.1:8000',client=('127.0.0.1',50000)) as client:
        def login(actor,tenant):
            reply=client.post('/api/v1/auth/login',headers={'Origin':settings.origin,'X-Requested-With':'ai-portal'},json={'login_id':actor.lower(),'password':f.passwords[actor]});assert reply.status_code==200
            return {'Origin':settings.origin,'X-Requested-With':'ai-portal','X-CSRF-Token':reply.json()['data']['csrf_token'],'X-Tenant-ID':str(f.tenant_ids[tenant])}
        ha=login('A-ADM','A');path=f"/api/v1/admin/documents/{ids['document_id']}/versions/{ids['version_id']}/grants"
        recipients=client.get('/api/v1/admin/share-recipients',headers=ha);assert recipients.status_code==200
        reply=client.post(path,headers=ha,json={'recipient_tenant_id':str(f.tenant_ids['B']),'expected_publication_revision':1});assert reply.status_code==201;grant=reply.json()['data']
        hb=login('B-U1','B');read={'X-Tenant-ID':str(f.tenant_ids['B'])}
        agents=client.get('/api/v1/agents',headers=read).json()['data']['items'];assert next(x for x in agents if x['agent_key']=='rules_rag')['available']
        docs=client.get('/api/v1/documents',headers=read).json()['data']['items'];assert len(docs)==1 and docs[0]['visibility']=='shared' and docs[0]['safe_version_label']=='v1'
        from uuid import uuid4
        body={'client_send_id':str(uuid4()),'agent_key':'rules_rag','prompt':'여신심사 담당 부서는?','document_refs':[{'document_id':ids['document_id'],'version_id':ids['version_id']}]}
        reply=client.post('/api/v1/runs',headers=hb,json=body);assert reply.status_code==202;run=reply.json()['data']['run_id']
        for _ in range(100):
            view=client.get('/api/v1/runs/'+run,headers=read).json()['data']
            if view['is_terminal']:break
            time.sleep(.03)
        assert view['state']=='completed' and view['answer_kind']=='answer' and '[1]' in view['result']['text']
        replay=client.post('/api/v1/runs',headers=hb,json=body);assert replay.status_code==200 and replay.json()['data']['run_id']==run
        evidence=client.get('/api/v1/runs/'+run+'/evidence',headers=read);assert evidence.status_code==200 and len(evidence.json()['data']['items'])==1
        item=evidence.json()['data']['items'][0];assert item['content_status']=='available' and 'source_object_key' not in evidence.text
        source=client.get(item['source_url'],headers=read);assert source.status_code==200 and 'attachment' in source.headers['content-disposition'] and source.content.decode().startswith('여신심사')
        stream=client.get('/api/v1/runs/'+run+'/events',headers={**read,'Accept':'text/event-stream'});assert stream.status_code==200 and 'terminal' in stream.text and 'draft_delta' not in stream.text and 'selected_fact_ids' not in stream.text
        ha=login('A-ADM','A');assert client.request('DELETE','/api/v1/admin/grants/'+grant['grant_id'],headers=ha,json={'expected_revision':grant['revision']}).status_code==200
        hb=login('B-U1','B');view=client.get('/api/v1/runs/'+run,headers=read).json()['data'];assert view['state']=='completed' and view['content_status']=='unavailable' and view['result'] is None
        evidence=client.get('/api/v1/runs/'+run+'/evidence',headers=read);assert evidence.json()['data']['items']==[{'ordinal':0,'content_status':'unavailable'}]
        assert client.get(item['source_url'],headers=read).status_code==404
        forbidden=client.post('/api/v1/runs',headers=hb,json={**body,'client_send_id':str(uuid4())});assert forbidden.status_code==404
        with f.db.admin_connection() as c:assert c.execute('SELECT count(*) FROM ops.call_attempts').fetchone()[0]==3
