import pytest

VALID_WF = {
    "workflow_id": "WF_TEST",
    "name": "Test DAG",
    "description": "Validation test",
    "nodes": [
        {"node_id": "N1", "node_type": "input", "title": "Start", "config": {}},
        {"node_id": "N2", "node_type": "output", "title": "Finish", "config": {}}
    ],
    "edges": [
        {"source_node": "N1", "target_node": "N2"}
    ]
}

@pytest.mark.parametrize("path,method,payload", [
    ("/api/v1/tools", "GET", None),
    ("/api/v1/tools/data_view_reader/invoke", "POST", {"arguments": {"view_name": "branch_daily_stats"}}),
    ("/api/v1/workflows/validate", "POST", VALID_WF),
    ("/api/v1/workflows/run", "POST", {"workflow": VALID_WF, "inputs": {}}),
    ("/api/v1/use-cases", "GET", None),
    ("/api/v1/use-cases/AGENT_01", "GET", None),
    ("/api/v1/use-cases/AGENT_01/execute", "POST", {"prompt": "규정 안내 테스트"}),
])
def test_missing_session_rejected(client, db_fixture, path, method, payload):
    """Unauthenticated requests must be rejected (401 or 403) and never return 200."""
    headers = {
        "X-Tenant-ID": str(db_fixture.tenant_ids["A"]),
        "Origin": "http://127.0.0.1:5173",
        "X-Requested-With": "ai-portal"
    }
    if method == "GET":
        res = client.get(path, headers=headers)
    else:
        res = client.post(path, json=payload, headers=headers)
    assert res.status_code in (401, 403), f"Expected 401 or 403 but got {res.status_code} for {path}"


def test_authenticated_user_access_control(client, login, db_fixture):
    """Authenticated USER should access catalog, but cannot invoke without execution readiness."""
    user_session = login(client, "A-U1")
    tenant_id = str(db_fixture.tenant_ids["A"])
    headers = {
        "X-Tenant-ID": tenant_id,
        "X-CSRF-Token": user_session["csrf_token"],
        "Origin": "http://127.0.0.1:5173",
        "X-Requested-With": "ai-portal"
    }

    # 1. Tools list requires authentication
    res = client.get("/api/v1/tools", headers=headers)
    assert res.status_code == 200
    assert "items" in res.json()["data"]

    # 2. Use cases list requires authentication
    res = client.get("/api/v1/use-cases", headers=headers)
    assert res.status_code == 200
    assert "items" in res.json()["data"]

    # 3. Workflows validate requires admin role (TADMIN or PADMIN)
    res = client.post("/api/v1/workflows/validate", json=VALID_WF, headers=headers)
    assert res.status_code == 403
    assert res.json()["error"]["code"] == "MANAGEMENT_DENIED"

    # 4. Invoke requires execution_enabled readiness (409)
    res_tool = client.post("/api/v1/tools/data_view_reader/invoke", json={
        "arguments": {"view_name": "branch_daily_stats"}
    }, headers=headers)
    assert res_tool.status_code == 409
    assert res_tool.json()["error"]["code"] == "EXECUTION_NOT_READY"

    res_uc = client.post("/api/v1/use-cases/AGENT_01/execute", json={
        "prompt": "규정 안내 테스트"
    }, headers=headers)
    assert res_uc.status_code == 409
    assert res_uc.json()["error"]["code"] == "EXECUTION_NOT_READY"
