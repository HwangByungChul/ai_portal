import asyncio

import pytest

from app import db


def test_runtime_pool_rejects_non_native_port_before_pool_creation(monkeypatch):
    pool_construction = []

    def unexpected_pool(*args, **kwargs):
        pool_construction.append((args, kwargs))
        raise AssertionError('pool must not be created for a rejected DSN')

    monkeypatch.setattr(db, 'AsyncConnectionPool', unexpected_pool)

    with pytest.raises(db.DatabaseBoundaryError) as exc:
        db._make_runtime_pool(
            'host=127.0.0.1 port=55433 dbname=ai_portal_mvp_test_' + 'a' * 32 + ' user=ai_web',
            'ai_web',
            1,
        )

    assert str(exc.value) == 'WEB_CONFIGURATION_REJECTED'
    assert pool_construction == []


class _Result:
    def __init__(self, row):
        self.row = row

    async def fetchone(self):
        return self.row


class _Connection:
    async def execute(self, query):
        assert 'current_database()' in query
        return _Result({
            'session_user': 'ai_web',
            'current_user': 'ai_web',
            'marker': 'foreign-database-marker',
            'port': '55432',
            'rolsuper': False,
            'rolbypassrls': False,
            'rolinherit': False,
            'rolcreatedb': False,
            'rolcreaterole': False,
            'rolreplication': False,
            'inherited': False,
            'owns_content': False,
            'owns_database': False,
        })


def test_runtime_connection_rejects_wrong_database_marker_without_details():
    with pytest.raises(db.DatabaseBoundaryError) as exc:
        asyncio.run(db._verify_runtime_connection(_Connection(), 'ai_web'))

    assert str(exc.value) == 'WEB_DATABASE_REJECTED'
    assert 'foreign-database-marker' not in str(exc.value)
    assert '127.0.0.1' not in str(exc.value)
    assert '55432' not in str(exc.value)
