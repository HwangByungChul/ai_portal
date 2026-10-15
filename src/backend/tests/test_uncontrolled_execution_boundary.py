import pytest

@pytest.mark.parametrize("path,payload",[
 ("/api/v1/tools/data_view_reader/invoke",{"arguments":{"view_name":"branch_daily_stats"},"client_request_id":"e76a5438-667a-48e8-ace1-dbc23bcddaff"}),
 ("/api/v1/use-cases/AGENT_01/execute",{"prompt":"규정","client_request_id":"30000000-0000-4000-8000-000000000001"}),
 ("/api/v1/workflows/run",{"workflow":{"workflow_id":"review","name":"review","nodes":[{"node_id":"a","node_type":"input","title":"a"},{"node_id":"b","node_type":"output","title":"b"}],"edges":[{"source_node":"a","target_node":"b"}]},"inputs":{"query":"test"}})
])
def test_authenticated_execution_enabled_does_not_bypass_controlled_admission(client,login,db_fixture,path,payload):
    session=login(client,"A-U1")
    client.app.state.settings.execution_enabled=True
    reply=client.post(path,json=payload,headers={"X-Tenant-ID":str(db_fixture.tenant_ids["A"]),"X-CSRF-Token":session["csrf_token"],"Origin":"http://127.0.0.1:5173","X-Requested-With":"ai-portal"})
    assert reply.status_code==409
    assert reply.json()["error"]["code"]=="EXECUTION_NOT_READY"
