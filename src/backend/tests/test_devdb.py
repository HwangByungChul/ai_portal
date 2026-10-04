import json
import os
import socket
import tempfile
from pathlib import Path

import pytest

from scripts.devdb import DevCluster, DevDBError, TEST_PARENT


@pytest.fixture
def cluster():
    TEST_PARENT.mkdir(mode=0o700, parents=True, exist_ok=True)
    TEST_PARENT.chmod(0o700)
    with tempfile.TemporaryDirectory(prefix='a01-', dir=TEST_PARENT) as directory:
        instance = DevCluster(Path(directory) / '.runtime', port=55433)
        try:
            yield instance
        finally:
            if instance.marker_path.exists():
                instance.stop()
                socket_marker = instance.socket_dir / 'ownership.json'
                if socket_marker.exists() and json.loads(socket_marker.read_text()) == instance._marker():
                    socket_marker.unlink()
                    instance.socket_dir.rmdir()


def test_arbitrary_runtime_is_rejected(tmp_path):
    with pytest.raises(DevDBError, match='UNOWNED_ROOT'):
        DevCluster(tmp_path / 'someone-elses-cluster', port=55433)
    assert list(tmp_path.iterdir()) == []


def test_foreign_existing_files_are_preserved(cluster):
    cluster.runtime.mkdir()
    foreign = cluster.runtime / 'foreign-data.txt'
    foreign.write_text('preserve me')
    with pytest.raises(DevDBError, match='UNOWNED_RUNTIME'):
        cluster.prepare()
    assert foreign.read_text() == 'preserve me'


def test_socket_directory_fits_unix_path_limit(cluster):
    assert len(os.fsencode(str(cluster.socket_dir / '.s.PGSQL.55433'))) < 104


@pytest.mark.integration
def test_native_cluster_lifecycle_and_private_files(cluster):
    assert cluster.status()['state'] == 'unprepared'
    assert cluster.prepare()['state'] == 'prepared'
    before = cluster.password_path.read_bytes()
    assert cluster.prepare()['state'] == 'prepared'
    unchanged = cluster.password_path.read_bytes() == before
    assert unchanged is True
    for path in (cluster.password_path, cluster.passfile_path, cluster.admin_env_path):
        assert path.stat().st_mode & 0o777 == 0o600
    assert cluster.runtime.stat().st_mode & 0o777 == 0o700
    running = cluster.start()
    assert running['state'] == 'running'
    assert running['runtime_role'] == 'mvp_bootstrap'
    assert (cluster.runtime / 'postgres.log').stat().st_mode & 0o777 == 0o600
    assert running['server_version'].startswith('15.')
    with cluster.connect() as conn:
        row = conn.execute('SELECT current_database(), current_user').fetchone()
        assert row == ('postgres', 'mvp_bootstrap')
    leaked = cluster.password_path.read_text().strip() in json.dumps(running)
    assert leaked is False
    assert cluster.stop()['state'] == 'stopped'
    assert cluster.start()['state'] == 'running'
    assert cluster.stop()['state'] == 'stopped'
    assert cluster.stop()['state'] == 'stopped'


@pytest.mark.integration
def test_occupied_port_is_not_replaced(cluster):
    cluster.prepare()
    with socket.socket() as listener:
        listener.bind(('127.0.0.1', 55433))
        listener.listen()
        with pytest.raises(DevDBError, match='PORT_IN_USE'):
            cluster.start()
        assert listener.getsockname()[1] == 55433
    assert cluster.status()['state'] == 'stopped'


@pytest.mark.integration
def test_tampered_owner_and_pid_are_rejected(cluster):
    cluster.prepare()
    marker = cluster.marker_path.read_text()
    payload = json.loads(marker)
    payload['project_id'] = 'different-project'
    cluster.marker_path.write_text(json.dumps(payload))
    try:
        with pytest.raises(DevDBError, match='UNOWNED_RUNTIME'):
            cluster.stop()
    finally:
        cluster.marker_path.write_text(marker)
    pidfile = cluster.data_dir / 'postmaster.pid'
    pidfile.write_text(f'{os.getpid()}\n/foreign/data\n0\n55433\n')
    try:
        with pytest.raises(DevDBError, match='UNOWNED_PID'):
            cluster.stop()
    finally:
        pidfile.unlink()


def test_symlink_runtime_is_rejected(cluster, tmp_path):
    link = tmp_path / '.runtime'
    link.symlink_to(cluster.runtime, target_is_directory=True)
    with pytest.raises(DevDBError, match='UNOWNED_ROOT'):
        DevCluster(link, port=55433)


@pytest.mark.integration
def test_foreign_socket_directory_is_preserved(cluster):
    cluster.prepare()
    marker_path = cluster.socket_dir / 'ownership.json'
    original = marker_path.read_text()
    marker_path.write_text('{"project_id":"foreign"}')
    try:
        with pytest.raises(DevDBError, match='UNOWNED_SOCKET_DIRECTORY'):
            cluster.start()
        assert marker_path.read_text() == '{"project_id":"foreign"}'
    finally:
        marker_path.write_text(original)


@pytest.mark.integration
def test_closed_tcp_connection_does_not_block_restart(cluster):
    cluster.prepare()
    with socket.socket() as listener:
        listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        listener.bind(('127.0.0.1', 55433))
        listener.listen()
        with socket.create_connection(('127.0.0.1', 55433), timeout=1) as client:
            accepted, _ = listener.accept()
            accepted.shutdown(socket.SHUT_RDWR)
            accepted.close()
            assert client.recv(1) == b''
    assert cluster.start()['state'] == 'running'
