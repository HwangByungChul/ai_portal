from datetime import date
from uuid import uuid4,UUID
from app.types import AuthContext
from app.documents.repository import DocumentRepository
from test_operations import ops_rows,headers
from test_document_api import multipart
from test_document_ingest import RAW

def test_retry_audit_failure_rolls_back_new_job_and_receipt(client,ops_rows,login,monkeypatch):
 seen=[];original=DocumentRepository.error
 def report(error):
  seen.append((type(error).__name__,getattr(error,'sqlstate',None)));return original(error)
 monkeypatch.setattr(DocumentRepository,'error',staticmethod(report))
 f=ops_rows;csrf=login(client,'A-ADM')['csrf_token'];h=headers(f,csrf=csrf)
 uploaded=client.post('/api/v1/admin/documents',headers=h,files=multipart({'client_upload_id':str(uuid4()),'title':'합성 추적 rollback','media_type':'text/plain'},RAW));assert uploaded.status_code==202
 ids=uploaded.json()['data'];job=UUID(ids['job_id'])
 with f.db.admin_connection() as c:origin=c.execute('SELECT origin_session_id FROM rag.jobs WHERE job_id=%s',(job,)).fetchone()[0]
 ctx=AuthContext(origin,f.actor_ids['A-ADM'],f.tenant_ids['A'],'TADMIN','');repo=client.app.state.documents;claim=b'r'*32
 owned=f.run(repo.job(ctx,job,'claim',claim=claim));f.run(repo.job(ctx,job,'fail',owned['epoch'],claim,{'code':'INDEX_INTERRUPTED'}))
 view=client.get('/api/v1/admin/jobs/'+str(job),headers=headers(f)).json()['data'];body={'expected_revision':view['revision'],'client_retry_id':str(uuid4())}
 with f.db.admin_connection() as c:
  c.execute("CREATE FUNCTION ops.test_trace_fault() RETURNS trigger LANGUAGE plpgsql AS $$BEGIN IF NEW.action='document.request.accepted' THEN RAISE EXCEPTION 'T286-private-trace-fault'; END IF; RETURN NEW; END;$$")
  c.execute('CREATE TRIGGER test_trace_fault BEFORE INSERT ON ops.audit_events FOR EACH ROW EXECUTE FUNCTION ops.test_trace_fault()')
 result=client.post('/api/v1/admin/jobs/'+str(job)+'/retry',headers=h,json=body);assert result.status_code==503 and 'T286-private-trace-fault' not in result.text
 with f.db.admin_connection() as c:
  assert c.execute('SELECT count(*) FROM rag.jobs').fetchone()[0]==1
  assert c.execute("SELECT count(*) FROM security.operation_receipts WHERE operation_kind='retry'").fetchone()[0]==0
  assert c.execute('SELECT count(*) FROM ops.call_attempts').fetchone()[0]==0
  c.execute('DROP TRIGGER test_trace_fault ON ops.audit_events')
 again=client.post('/api/v1/admin/jobs/'+str(job)+'/retry',headers=h,json=body);assert again.status_code==202,seen
 with f.db.admin_connection() as c:
  assert c.execute('SELECT count(*) FROM rag.jobs').fetchone()[0]==2
  assert c.execute('SELECT revisions FROM ops.audit_events WHERE event_id=%s',(again.headers['x-request-id'],)).fetchone()[0]=={'job_ids':[again.json()['data']['job_id']]}
