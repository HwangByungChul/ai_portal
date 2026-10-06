import json
from uuid import uuid4
import pytest
from test_operations import headers
from app.documents.upload import parse_upload
from app.errors import AppError


def multipart(meta,raw=b'body'):
    return [('metadata',(None,json.dumps(meta), 'application/json')),('file',('ignored.md',raw,'text/markdown'))]

def test_upload_job_query_duplicate_and_delete(client,db_fixture,login):
    f=db_fixture;s=login(client,'A-ADM');h=headers(f,csrf=s['csrf_token'])
    meta={'client_upload_id':str(uuid4()),'title':'합성 문서','media_type':'text/markdown'}
    raw='여신심사의 담당 부서는 가상 심사팀이다.'.encode()
    response=client.post('/api/v1/admin/documents',headers=h,files=multipart(meta,raw));assert response.status_code==202
    ids=response.json()['data'];
    with f.db.admin_connection() as c:
        trace=c.execute('SELECT opaque_target_id,revisions FROM ops.audit_events WHERE event_id=%s',(response.headers['x-request-id'],)).fetchone()
        assert str(trace[0])==ids['document_id'] and trace[1]=={'job_ids':[ids['job_id']]}
    assert client.post('/api/v1/admin/documents',headers=h,files=multipart(meta,raw)).json()['data']['job_id']==ids['job_id']
    view=client.get('/api/v1/admin/jobs/'+ids['job_id'],headers=headers(f));assert view.status_code==200 and view.json()['data']['state']=='queued'
    assert client.get('/api/v1/admin/documents',headers=headers(f)).status_code==200
    assert client.get('/api/v1/admin/jobs',headers=headers(f)).status_code==200
    data=client.request('DELETE','/api/v1/admin/documents/'+ids['document_id'],headers=h,json={'expected_revision':1});assert data.status_code==200
    assert data.json()['data']['access_state']=='deleted'
    with f.db.admin_connection() as c:
        trace=c.execute('SELECT revisions FROM ops.audit_events WHERE event_id=%s',(data.headers['x-request-id'],)).fetchone()[0]
        assert trace['job_ids']==[str(c.execute("SELECT job_id FROM rag.jobs WHERE job_kind='internal_cleanup'").fetchone()[0])]
    with f.db.admin_connection() as c:
        assert c.execute("SELECT count(*) FROM rag.jobs WHERE job_kind='internal_cleanup'").fetchone()[0]==1
        assert c.execute('SELECT count(*) FROM ops.call_attempts').fetchone()[0]==0

@pytest.mark.parametrize('case',['csrf','origin','unknown','too_big','wrong_media','duplicate_metadata'])
def test_upload_boundary_failure_without_job(client,db_fixture,login,case):
    f=db_fixture;s=login(client,'A-ADM');h=headers(f,csrf=s['csrf_token']);meta={'client_upload_id':str(uuid4()),'title':'합성 문서','media_type':'text/markdown'}
    if case=='csrf':h.pop('X-CSRF-Token')
    if case=='origin':h['Origin']='http://evil.invalid'
    if case=='unknown':meta['tenant_id']=str(f.tenant_ids['B'])
    if case=='wrong_media':meta['media_type']='text/html'
    parts=multipart(meta,b'x'*150000 if case=='too_big' else b'body')
    if case=='duplicate_metadata':parts.append(('metadata',(None,json.dumps(meta),'application/json')))
    response=client.post('/api/v1/admin/documents',headers=h,files=parts);assert response.status_code in (403,413,422)
    assert response.headers['cache-control']=='no-store'
    with f.db.admin_connection() as c:assert c.execute('SELECT count(*) FROM rag.jobs').fetchone()[0]==0

def test_foreign_job_and_nonadministrator_are_rejected(client,db_fixture,login):
    f=db_fixture;s=login(client,'A-ADM');h=headers(f,csrf=s['csrf_token']);meta={'client_upload_id':str(uuid4()),'title':'합성 문서','media_type':'text/plain'}
    response=client.post('/api/v1/admin/documents',headers=h,files=multipart(meta));job=response.json()['data']['job_id']
    login(client,'B-ADM');assert client.get('/api/v1/admin/jobs/'+job,headers=headers(f,'B')).status_code==404
    login(client,'A-U1');assert client.get('/api/v1/admin/jobs/'+job,headers=headers(f)).status_code==403

def test_opaque_cursor_is_bound_to_principal_and_tenant(client,db_fixture,login):
    f=db_fixture;s=login(client,'A-ADM');h=headers(f,csrf=s['csrf_token'])
    for _ in range(2):
        meta={'client_upload_id':str(uuid4()),'title':'합성 문서','media_type':'text/plain'}
        assert client.post('/api/v1/admin/documents',headers=h,files=multipart(meta)).status_code==202
    page=client.get('/api/v1/admin/documents?limit=1',headers=headers(f)).json()['data'];cursor=page['next_cursor'];assert cursor
    assert 'processing_state' in page['items'][0] and page['items'][0]['can_read_content'] is False
    login(client,'B-ADM');assert client.get('/api/v1/admin/documents',headers=headers(f,'B'),params={'cursor':cursor}).status_code==422
