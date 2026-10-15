import pytest

def test_guardrail_routes_rbac(client, login, db_fixture):
    """Guardrail policies and violations require PADMIN effective role, X-Tenant-ID, and valid CSRF."""
    tenant_id = str(db_fixture.tenant_ids["A"])

    # 1. Unauthenticated -> 401 or 403
    unauth_headers = {
        "X-Tenant-ID": tenant_id,
        "Origin": "http://127.0.0.1:5173",
        "X-Requested-With": "ai-portal"
    }
    res_unauth = client.get("/api/v1/admin/guardrails/policies", headers=unauth_headers)
    assert res_unauth.status_code in (401, 403)

    # 2. Regular USER (A-U1) -> 403 MANAGEMENT_DENIED
    u1_session = login(client, "A-U1")
    u1_headers = {
        "X-Tenant-ID": tenant_id,
        "X-CSRF-Token": u1_session["csrf_token"],
        "Origin": "http://127.0.0.1:5173",
        "X-Requested-With": "ai-portal"
    }
    res_user = client.get("/api/v1/admin/guardrails/policies", headers=u1_headers)
    assert res_user.status_code == 403
    assert res_user.json()["error"]["code"] == "MANAGEMENT_DENIED"

    # 3. PADMIN (P-A) -> 200 OK without AttributeError
    padmin_session = login(client, "P-A")
    padmin_headers = {
        "X-Tenant-ID": tenant_id,
        "X-CSRF-Token": padmin_session["csrf_token"],
        "Origin": "http://127.0.0.1:5173",
        "X-Requested-With": "ai-portal"
    }
    res_padmin = client.get("/api/v1/admin/guardrails/policies", headers=padmin_headers)
    assert res_padmin.status_code == 200
    data = res_padmin.json()["data"]
    assert "revision" in data
    assert "input_rules" in data
    assert "output_rules" in data

    # 4. Violations endpoint with PADMIN -> 200 OK
    res_viol = client.get("/api/v1/admin/guardrails/violations", headers=padmin_headers)
    assert res_viol.status_code == 200
    assert "items" in res_viol.json()["data"]
