"""Real loopback process restart/outage tests; disposable owned DB only.

Public observations contain counts, durations and booleans, never credentials.
"""
import hashlib
import json
import math
import os
from pathlib import Path
import socket
import subprocess
import time
from datetime import datetime, timezone

import httpx
import pytest

from app.db import tenant_transaction
from app.types import AuthContext
from scripts.devdb import _write_private

BACKEND = Path(__file__).resolve().parents[1]
BASE_URL = 'http://127.0.0.1:8000'
WRITE = {'Origin': 'http://127.0.0.1:5173', 'X-Requested-With': 'ai-portal'}


def record(test_id, started, observed):
    path = BACKEND / '.runtime' / f'{test_id}.json'
    path.unlink(missing_ok=True)
    _write_private(path, json.dumps({
        'test_id': test_id, 'status': 'pass',
        'utc_time': datetime.now(timezone.utc).isoformat(),
        'duration_ms': round((time.monotonic() - started) * 1000, 2),
        'observed': observed, 'safe_error_code': None,
    }))


class LiveServer:
    def __init__(self, fixture, settings):
        self.fixture = fixture
        self.child = None
        self.starts = 0
        self.log_path = BACKEND / '.runtime' / 'A06-api-private.log'
        fd = os.open(self.log_path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        self.log = os.fdopen(fd, 'w')
        self.env = {k: v for k, v in os.environ.items() if not k.startswith(('AI_', 'PG'))}
        self.env.update(AI_WEB_DSN=fixture.db.runtime_dsn(),
                        AI_LOGIN_HMAC_SECRET=settings.login_hmac_secret.get_secret_value(), AI_MODE='mock')
        self.secrets = list(fixture.passwords.values()) + [
            self.env['AI_WEB_DSN'], self.env['AI_LOGIN_HMAC_SECRET']]

    def start(self):
        with socket.socket() as probe:
            probe.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            probe.bind(('127.0.0.1', 8000))
        self.child = subprocess.Popen([
            str(BACKEND / '.venv/bin/python'), '-m', 'uvicorn', 'app.main:create_app', '--factory',
            '--host', '127.0.0.1', '--port', '8000', '--no-proxy-headers', '--no-access-log'],
            cwd=BACKEND, env=self.env, stdout=self.log, stderr=self.log)
        self.starts += 1
        deadline = time.monotonic() + 12
        with httpx.Client(base_url=BASE_URL, timeout=1, trust_env=False) as probe:
            while time.monotonic() < deadline:
                if self.child.poll() is not None:
                    raise RuntimeError('A06_CHILD_START_FAILED')
                try:
                    if probe.get('/api/v1/health').status_code == 200:
                        return
                except httpx.TransportError:
                    pass
                time.sleep(.05)
        raise RuntimeError('A06_CHILD_START_TIMEOUT')

    def stop(self):
        if self.child and self.child.poll() is None:
            self.child.terminate()
            try:
                self.child.wait(timeout=8)
            except subprocess.TimeoutExpired:
                self.child.kill()
                self.child.wait(timeout=3)
                raise RuntimeError('A06_CHILD_STOP_TIMEOUT')

    def restart(self):
        self.stop()
        self.start()

    def login(self, client, actor):
        reply = client.post('/api/v1/auth/login', headers=WRITE,
                            json={'login_id': actor.lower(), 'password': self.fixture.passwords[actor]})
        assert reply.status_code == 200
        csrf = reply.json()['data']['csrf_token']
        self.secrets.extend([csrf, client.cookies.get('ai_session_dev')])
        return csrf

    def session_snapshot(self, client):
        digest = hashlib.sha256(client.cookies.get('ai_session_dev').encode()).digest()
        with self.fixture.db.admin_connection() as conn:
            return conn.execute('SELECT session_id,issued_at,last_activity_at,expires_at,revoked_at '
                                'FROM security.sessions WHERE token_hash=%s', (digest,)).fetchone()

    def rows(self, client, tenant):
        digest = hashlib.sha256(client.cookies.get('ai_session_dev').encode()).digest()
        async def check():
            async with self.fixture.pool.connection() as conn:
                session = await (await conn.execute('SELECT * FROM security.session_validate(%s)', (digest,))).fetchone()
                member = await (await conn.execute('SELECT * FROM security.current_membership(%s,%s)',
                    (session['session_id'], self.fixture.tenant_ids[tenant]))).fetchone()
            if not member:
                return None
            ctx = AuthContext(session['session_id'], session['user_id'], self.fixture.tenant_ids[tenant],
                              member['effective_role'], session['csrf_secret'])
            async with tenant_transaction(self.fixture.pool, ctx) as conn:
                return (await (await conn.execute('SELECT count(*) AS n FROM portal.conversations')).fetchone())['n']
        return self.fixture.run(check())


@pytest.fixture
def running_server(db_fixture, auth_settings, request):
    live = LiveServer(db_fixture, auth_settings)
    try:
        live.start()
        yield live
    finally:
        # Restore the owned cluster before fixture pool shutdown and verified DB drop.
        if db_fixture.db.cluster.status()['state'] != 'running':
            db_fixture.db.cluster.start()
        live.stop()
        live.log.flush()
        content = live.log_path.read_text()
        live.log.close()
        assert not any(value and value in content for value in live.secrets)
        db_fixture.run(db_fixture.pool.close())
        with db_fixture.db.admin_connection() as conn:
            remaining = conn.execute("SELECT count(*) FROM pg_stat_activity WHERE datname=%s AND usename='ai_web'",
                                     (db_fixture.db.name,)).fetchone()[0]
        # The outage can discard the fixture connection; close both pools before counting.
        assert remaining == 0
        path = BACKEND / '.runtime' / ('A06-cleanup-' + request.node.name + '.json')
        path.unlink(missing_ok=True)
        _write_private(path, json.dumps({'test_id': request.node.name,
            'api_child_stopped': live.child.poll() is not None,
            'api_pool_remaining_connections': remaining,
            'private_log_secret_hits': 0,
            'fixture_id': hashlib.sha256(db_fixture.db.name.encode()).hexdigest()[:12]}))


def client():
    return httpx.Client(base_url=BASE_URL, timeout=12, trust_env=False)


def headers(live, csrf=None, tenant='A'):
    return {'X-Tenant-ID': str(live.fixture.tenant_ids[tenant]),
            **({**WRITE, 'X-CSRF-Token': csrf} if csrf else {})}


def test_session_revocation_and_rls_survive_real_api_restart(running_server):
    started = time.monotonic(); live = running_server; f = live.fixture
    with client() as dual, client() as admin, client() as user, client() as platform, client() as bad:
        live.login(dual, 'DUAL'); csrf = live.login(admin, 'A-ADM')
        live.login(user, 'A-U1'); live.login(platform, 'P-A')
        f.verify_catalog()
        before = live.session_snapshot(dual)
        expires = dual.get('/api/v1/auth/me').json()['data']['session_expires_at']
        counts = [live.rows(user, 'A'), live.rows(dual, 'B'), live.rows(platform, 'A')]
        assert counts == [1, 1, 0]
        reply = admin.patch('/api/v1/admin/memberships/' + str(f.actor_ids['DUAL']),
                            headers=headers(live, csrf), json={'active': False, 'expected_revision': 1})
        assert reply.status_code == 200
        for _ in range(5):
            reply = bad.post('/api/v1/auth/login', headers=WRITE,
                             json={'login_id': 'a-u2', 'password': 'deliberately-wrong'})
            assert reply.status_code == 401
        live.restart()
        assert dual.get('/api/v1/auth/me').status_code == 200
        assert dual.get('/api/v1/auth/me').json()['data']['session_expires_at'] == expires
        assert live.session_snapshot(dual) == before
        allowed = dual.get('/api/v1/me/tenants').json()['data']['items']
        assert [item['tenant_id'] for item in allowed] == [str(f.tenant_ids['B'])]
        assert dual.get('/api/v1/admin/memberships', headers=headers(live)).status_code == 403
        assert live.rows(dual, 'A') is None
        assert [live.rows(user, 'A'), live.rows(dual, 'B'), live.rows(platform, 'A')] == counts
        reply = bad.post('/api/v1/auth/login', headers=WRITE,
                         json={'login_id': 'a-u2', 'password': f.passwords['A-U2']})
        assert reply.status_code == 429
        with f.db.admin_connection() as conn:
            assert conn.execute('SELECT active,revision FROM security.memberships WHERE tenant_id=%s AND user_id=%s',
                (f.tenant_ids['A'], f.actor_ids['DUAL'])).fetchone() == (False, 2)
            assert conn.execute('SELECT count(*) FROM portal.conversations').fetchone()[0] == 5
        record('A06_01_restart', started, {'api_starts': live.starts, 'same_cookie_valid': True,
            'session_dates_unchanged': True, 'membership_revocation_persisted': True,
            'login_window_persisted': True, 'own_rls_counts_before_after': counts,
            'revoked_tenant_context_rejected': True, 'all_conversations_persisted': 5})


def test_absolute_idle_expiry_and_logout_survive_api_restart(running_server):
    started = time.monotonic(); live = running_server; f = live.fixture
    with client() as absolute, client() as idle, client() as revoked:
        live.login(absolute, 'A-U1'); live.login(idle, 'A-U2'); csrf = live.login(revoked, 'B-U1')
        absolute_id = live.session_snapshot(absolute)[0]; idle_id = live.session_snapshot(idle)[0]
        with f.db.admin_connection() as conn:
            conn.execute("WITH moment AS (SELECT clock_timestamp() AS n) UPDATE security.sessions "
                "SET issued_at=n-interval '9 hours',expires_at=n-interval '1 hour',last_activity_at=n "
                'FROM moment WHERE session_id=%s', (absolute_id,))
            conn.execute("WITH moment AS (SELECT clock_timestamp() AS n) UPDATE security.sessions "
                "SET issued_at=n-interval '1 hour',expires_at=n+interval '7 hours',"
                "last_activity_at=n-interval '31 minutes' FROM moment WHERE session_id=%s", (idle_id,))
        assert revoked.post('/api/v1/auth/logout', headers={**WRITE, 'X-CSRF-Token': csrf}).status_code == 200
        old_token = live.secrets[-1]
        revoked.cookies.set('ai_session_dev', old_token, domain='127.0.0.1', path='/')
        snapshots = [live.session_snapshot(absolute), live.session_snapshot(idle), live.session_snapshot(revoked)]
        live.restart()
        assert [c.get('/api/v1/auth/me').status_code for c in [absolute, idle, revoked]] == [401, 401, 401]
        assert [live.session_snapshot(absolute), live.session_snapshot(idle), live.session_snapshot(revoked)] == snapshots
        record('A06_02_expiry', started, {'api_starts': live.starts, 'absolute_expired': 401,
            'idle_expired': 401, 'logged_out_old_cookie': 401, 'session_dates_unchanged': True})


def test_real_database_outage_safe_503_then_explicit_recovery(running_server):
    started = time.monotonic(); live = running_server; f = live.fixture; cluster = f.db.cluster
    with client() as admin, client() as fresh:
        csrf = live.login(admin, 'A-ADM'); token = admin.cookies.get('ai_session_dev')
        target = '/api/v1/admin/memberships/' + str(f.actor_ids['A-U1'])
        before = live.session_snapshot(admin)
        cluster.stop()
        try:
            replies = [fresh.post('/api/v1/auth/login', headers=WRITE,
                                   json={'login_id': 'b-u1', 'password': f.passwords['B-U1']}),
                       admin.post('/api/v1/auth/logout', headers={**WRITE, 'X-CSRF-Token': csrf}),
                       admin.get('/api/v1/admin/memberships', headers=headers(live)),
                       admin.patch(target, headers=headers(live, csrf),
                                   json={'active': False, 'expected_revision': 1})]
            for reply in replies:
                assert reply.status_code == 503
                assert reply.json()['error']['code'] == 'STORAGE_UNAVAILABLE'
                assert reply.json()['error']['retryable'] is True
                assert 'set-cookie' not in reply.headers
                assert not any(value and value in reply.text for value in live.secrets)
            assert admin.cookies.get('ai_session_dev') == token
        finally:
            cluster.start()
        deadline = time.monotonic() + 20; recovered = False
        while time.monotonic() < deadline:
            reply = admin.get('/api/v1/admin/memberships', headers=headers(live))
            if reply.status_code == 200:
                recovered = True; break
            assert reply.status_code == 503
            time.sleep(.1)
        assert recovered
        assert live.session_snapshot(admin) == before
        with f.db.admin_connection() as conn:
            assert conn.execute('SELECT active,revision FROM security.memberships WHERE tenant_id=%s AND user_id=%s',
                (f.tenant_ids['A'], f.actor_ids['A-U1'])).fetchone() == (True, 1)
            assert conn.execute("SELECT count(*) FROM ops.audit_events WHERE action='membership_active'").fetchone()[0] == 0
        assert fresh.post('/api/v1/auth/login', headers=WRITE,
                          json={'login_id': 'b-u1', 'password': f.passwords['B-U1']}).status_code == 200
        live.secrets.extend([fresh.cookies.get('ai_session_dev'), fresh.get('/api/v1/auth/me').json()['data']['csrf_token']])
        assert admin.patch(target, headers=headers(live, csrf),
                           json={'active': False, 'expected_revision': 1}).status_code == 200
        assert admin.post('/api/v1/auth/logout', headers={**WRITE, 'X-CSRF-Token': csrf}).status_code == 200
        admin.cookies.set('ai_session_dev', token, domain='127.0.0.1', path='/')
        assert admin.get('/api/v1/auth/me').status_code == 401
        with f.db.admin_connection() as conn:
            assert conn.execute('SELECT active,revision FROM security.memberships WHERE tenant_id=%s AND user_id=%s',
                (f.tenant_ids['A'], f.actor_ids['A-U1'])).fetchone() == (False, 2)
            assert conn.execute("SELECT count(*) FROM ops.audit_events WHERE action='membership_active'").fetchone()[0] == 1
        record('A06_03_outage', started, {'real_owned_db_stop_start': True,
            'offline_login_logout_members_read_write': [r.status_code for r in replies],
            'offline_cookie_unchanged': True, 'failed_write_unchanged': True,
            'recovery_without_api_restart': True, 'explicit_retry_one_write_one_audit': True,
            'explicit_logout_old_cookie': 401, 'raw_secret_response_hits': 0})


def test_authenticated_get_p95_and_idle_not_extended(running_server):
    started = time.monotonic(); live = running_server; samples = []
    with client() as user:
        live.login(user, 'A-U1'); before = live.session_snapshot(user)
        assert user.get('/api/v1/me/tenants').status_code == 200  # warmup excluded
        for _ in range(20):
            tick = time.perf_counter()
            reply = user.get('/api/v1/me/tenants')
            samples.append(round((time.perf_counter() - tick) * 1000, 3))
            assert reply.status_code == 200
        assert live.session_snapshot(user) == before
        p95 = sorted(samples)[math.ceil(.95 * len(samples)) - 1]
        record('A06_04_latency', started, {'endpoint': 'GET /api/v1/me/tenants', 'samples_ms': samples,
            'sample_count': 20, 'warmup_count': 1, 'p95_nearest_rank_ms': p95,
            'mean_ms': round(sum(samples) / len(samples), 3), 'max_ms': max(samples),
            'goal_ms': 300, 'goal_met': p95 <= 300, 'idle_unchanged': True,
            'concurrency': 1, 'transport': 'real loopback HTTP, keep-alive, trust_env=False'})
        assert p95 <= 300
