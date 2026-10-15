from datetime import date, timedelta


def test_admin_overview_catalog_and_api(client, login, db_fixture):
    # Verify migration 043 and security function 150
    db_fixture.verify_catalog()

    tenant_id = str(db_fixture.tenant_ids["A"])
    base_headers = {
        "X-Tenant-ID": tenant_id,
        "Origin": "http://127.0.0.1:5174",
        "X-Requested-With": "ai-portal",
    }

    # 1. Unauthenticated request -> 401
    res = client.get("/api/v1/admin/overview", headers=base_headers)
    assert res.status_code == 401

    # 2. Regular user (A-U1) -> 403 MANAGEMENT_DENIED
    u1_session = login(client, "A-U1")
    u_headers = {
        **base_headers,
        "X-CSRF-Token": u1_session["csrf_token"],
    }
    res_u = client.get("/api/v1/admin/overview", headers=u_headers)
    assert res_u.status_code == 403
    assert res_u.json()["error"]["code"] == "MANAGEMENT_DENIED"

    # 3. PADMIN (P-A) -> 200 OK
    p_session = login(client, "P-A")
    p_headers = {
        **base_headers,
        "X-CSRF-Token": p_session["csrf_token"],
    }
    res_p = client.get("/api/v1/admin/overview", headers=p_headers)
    assert res_p.status_code == 200
    body = res_p.json()["data"]
    assert "as_of" in body
    assert "period" in body
    assert body["timezone"] == "Asia/Seoul"
    assert "metrics" in body
    assert isinstance(body["metrics"]["calls"], int)
    assert isinstance(body["daily_calls"], list)
    assert "pending" in body
    assert body["pending"]["total"] >= 0
    assert isinstance(body["pending"]["items"], list)
    assert "services" in body
    assert len(body["services"]) >= 3
    for svc in body["services"]:
        assert svc["status"] == "unknown"
        assert svc["observed_at"] is None
        assert svc["scope"] == "tenant"

    # 4. Custom date range within 31 days
    today = date.today()
    d_from = (today - timedelta(days=10)).isoformat()
    d_to = today.isoformat()
    res_custom = client.get(
        f"/api/v1/admin/overview?date_from={d_from}&date_to={d_to}",
        headers=p_headers
    )
    assert res_custom.status_code == 200
    custom_body = res_custom.json()["data"]
    assert custom_body["period"]["from"] == d_from
    assert custom_body["period"]["to"] == d_to
    assert len(custom_body["daily_calls"]) == 11

    # 5. Invalid query parameters
    # Invalid date format
    res_bad_fmt = client.get(
        "/api/v1/admin/overview?date_from=2026/10/01&date_to=2026/10/05",
        headers=p_headers
    )
    assert res_bad_fmt.status_code == 422

    # Inverted dates (from > to)
    res_inverted = client.get(
        f"/api/v1/admin/overview?date_from={d_to}&date_to={d_from}",
        headers=p_headers
    )
    assert res_inverted.status_code == 422

    # Exceeding 31 days
    d_far_from = (today - timedelta(days=35)).isoformat()
    res_too_long = client.get(
        f"/api/v1/admin/overview?date_from={d_far_from}&date_to={d_to}",
        headers=p_headers
    )
    assert res_too_long.status_code == 422

    # Unexpected query parameter
    res_extra = client.get(
        f"/api/v1/admin/overview?date_from={d_from}&date_to={d_to}&hack=1",
        headers=p_headers
    )
    assert res_extra.status_code == 422
