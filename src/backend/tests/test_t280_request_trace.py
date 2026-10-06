from uuid import uuid4
from test_operations import ops_rows,headers

def test_http_request_identity_is_server_owned_and_links_to_run(client,ops_rows,login):
 f=ops_rows;csrf=login(client,'A-U1')['csrf_token'];forged=str(uuid4())
 response=client.post('/api/v1/runs',headers=headers(f,csrf=csrf)|{'X-Request-ID':forged},json={'agent_key':'general','client_send_id':str(uuid4()),'prompt':'합성 요청 추적'})
 assert response.status_code==202 and response.headers['x-request-id']!=forged
 with f.db.admin_connection() as c:
  row=c.execute('SELECT action,opaque_target_id FROM ops.audit_events WHERE event_id=%s',(response.headers['x-request-id'],)).fetchone()
  assert row[0]=='run_admitted' and str(row[1])==response.json()['data']['run_id']
  assert c.execute('SELECT count(*) FROM ops.call_attempts').fetchone()[0]==0
