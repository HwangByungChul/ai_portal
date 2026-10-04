from datetime import datetime
from uuid import UUID

from fastapi.testclient import TestClient
from app.main import create_app


def test_health_has_only_safe_status():
    with TestClient(create_app(health_only=True)) as client:
        response = client.get('/api/v1/health')
    assert response.status_code == 200
    assert response.json()['data'] == {'status': 'ok'}
    meta = response.json()['meta']
    assert set(meta) == {'request_id', 'tenant_id', 'server_time'}
    UUID(meta['request_id'])
    assert meta['tenant_id'] is None
    assert datetime.fromisoformat(meta['server_time']).utcoffset().total_seconds() == 0
    assert response.headers['cache-control'] == 'no-store'
    assert response.headers['x-request-id'] == meta['request_id']


def test_health_needs_no_database_and_does_not_publish_login():
    with TestClient(create_app(health_only=True)) as client:
        assert client.get('/api/v1/health').status_code == 200
        assert client.post('/api/v1/auth/login', json={}).status_code == 404
