"""Protected document markers must not escape administrative or foreign views."""
from uuid import uuid4
import pytest
from test_operations import headers
from test_document_api import multipart

@pytest.mark.parametrize('actor,tenant',[('A-ADM','A'),('B-ADM','B'),('A-U2','A')])
def test_private_source_title_and_body_are_not_public_metadata(client,db_fixture,login,caplog,actor,tenant):
 f=db_fixture;csrf=login(client,'A-ADM')['csrf_token'];marker='T286-PRIVATE-SOURCE-7531';title=marker+'-TITLE'
 meta={'client_upload_id':str(uuid4()),'title':title,'media_type':'text/plain','visibility':'private','owner_user_id':str(f.actor_ids['A-U1']),'reader_ids':[]}
 upload=client.post('/api/v1/admin/documents',headers=headers(f,csrf=csrf),files=multipart(meta,(marker+'-BODY').encode()));assert upload.status_code==202
 ids=upload.json()['data'];login(client,actor);h=headers(f,tenant)
 for path in ['/api/v1/admin/documents','/api/v1/admin/jobs','/api/v1/admin/jobs/'+ids['job_id'],'/api/v1/admin/usage','/api/v1/usage/me']:
  result=client.get(path,headers=h);assert marker not in result.text and 'source_object_key' not in result.text
 assert marker not in caplog.text
 with f.db.admin_connection() as c:assert c.execute('SELECT count(*) FROM ops.call_attempts').fetchone()[0]==0
