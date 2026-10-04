"""Manage only this project's native PostgreSQL development cluster."""

import argparse
import hashlib
import json
import os
from pathlib import Path
import secrets
import shlex
import socket
import stat
import subprocess

import psycopg

PROJECT_ID = "202610-ai-platform"
DEFAULT_RUNTIME = Path(__file__).resolve().parents[1] / ".runtime"
TEST_PARENT = Path("/private/tmp") / f"ai-platform-devdb-tests-{os.getuid()}"
PG_BIN = Path("/usr/local/bin")


class DevDBError(RuntimeError):
    """Expose only fixed error codes, never subprocess/connection details."""


def _write_private(path: Path, content: str) -> None:
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW
    fd = os.open(path, flags, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as handle:
        handle.write(content)


def _read_private(path: Path) -> str:
    if path.is_symlink():
        raise DevDBError("UNOWNED_RUNTIME")
    try:
        details = path.stat()
        if (details.st_uid != os.getuid() or not stat.S_ISREG(details.st_mode)
                or stat.S_IMODE(details.st_mode) != 0o600):
            raise DevDBError("UNOWNED_RUNTIME")
        return path.read_text(encoding="utf-8")
    except OSError:
        raise DevDBError("UNOWNED_RUNTIME") from None


class DevCluster:
    def __init__(self, runtime: Path = DEFAULT_RUNTIME, port: int = 55432):
        if runtime.is_symlink():
            raise DevDBError("UNOWNED_ROOT")
        if TEST_PARENT.is_symlink():
            raise DevDBError("UNOWNED_ROOT")
        self.runtime = runtime.resolve()
        normal = self.runtime == DEFAULT_RUNTIME.resolve() and port == 55432
        test = (self.runtime.parent.parent == TEST_PARENT.resolve()
                and self.runtime.parent.name.startswith("a01-")
                and self.runtime.name == ".runtime" and port == 55433)
        if not (normal or test):
            raise DevDBError("UNOWNED_ROOT")
        self.port = port
        self.cluster_key = hashlib.sha256(str(self.runtime).encode()).hexdigest()[:12]
        # macOS sockaddr_un cannot fit the long Korean project path.
        self.socket_dir = Path("/private/tmp") / f"ai-portal-pg-{os.getuid()}-{self.cluster_key}"
        self.data_dir = self.runtime / "pgdata"
        self.marker_path = self.runtime / "ownership.json"
        self.password_path = self.runtime / "bootstrap.password"
        self.passfile_path = self.runtime / "pgpass"
        self.admin_env_path = self.runtime / "admin.env"

    def _marker(self) -> dict:
        return {"project_id": PROJECT_ID, "runtime": str(self.runtime),
                "port": self.port, "uid": os.getuid(), "cluster_key": self.cluster_key}

    def _validate(self, prepared: bool = True) -> None:
        if self.runtime.is_symlink():
            raise DevDBError("UNOWNED_RUNTIME")
        try:
            details = self.runtime.stat()
            if (details.st_uid != os.getuid() or not stat.S_ISDIR(details.st_mode)
                    or stat.S_IMODE(details.st_mode) != 0o700):
                raise DevDBError("UNOWNED_RUNTIME")
            if json.loads(_read_private(self.marker_path)) != self._marker():
                raise DevDBError("UNOWNED_RUNTIME")
        except (OSError, ValueError):
            raise DevDBError("UNOWNED_RUNTIME") from None
        if prepared:
            if self.data_dir.is_symlink():
                raise DevDBError("UNOWNED_RUNTIME")
            try:
                version = (self.data_dir / "PG_VERSION").read_text().strip()
            except OSError:
                raise DevDBError("PREPARATION_INCOMPLETE") from None
            if version != "15":
                raise DevDBError("PG_VERSION_MISMATCH")
            for path in (self.password_path, self.passfile_path, self.admin_env_path):
                _read_private(path)

    def _socket_directory(self) -> None:
        if self.socket_dir.is_symlink():
            raise DevDBError("UNOWNED_SOCKET_DIRECTORY")
        if self.socket_dir.exists():
            details = self.socket_dir.stat()
            if (details.st_uid != os.getuid() or not stat.S_ISDIR(details.st_mode)
                    or stat.S_IMODE(details.st_mode) != 0o700):
                raise DevDBError("UNOWNED_SOCKET_DIRECTORY")
            try:
                if json.loads(_read_private(self.socket_dir / "ownership.json")) != self._marker():
                    raise DevDBError("UNOWNED_SOCKET_DIRECTORY")
            except (DevDBError, ValueError):
                raise DevDBError("UNOWNED_SOCKET_DIRECTORY") from None
        else:
            self.socket_dir.mkdir(mode=0o700)
            _write_private(self.socket_dir / "ownership.json", json.dumps(self._marker()))

    def _run(self, executable: str, args: list[str]) -> subprocess.CompletedProcess:
        environment = {k: v for k, v in os.environ.items() if not k.startswith("PG")}
        environment["LC_ALL"] = "C"
        try:
            return subprocess.run([str(PG_BIN / executable), *args], env=environment,
                                  capture_output=True, text=True, timeout=30)
        except (OSError, subprocess.TimeoutExpired):
            raise DevDBError("POSTGRES_TOOL_UNAVAILABLE") from None

    def prepare(self) -> dict:
        if self.marker_path.exists():
            self._validate()
            return {"state": "prepared", "port": self.port, "cluster_id": self.cluster_key}
        if self.runtime.exists():
            details = self.runtime.stat()
            if details.st_uid != os.getuid() or any(self.runtime.iterdir()):
                raise DevDBError("UNOWNED_RUNTIME")
        self.runtime.mkdir(mode=0o700, parents=True, exist_ok=True)
        self.runtime.chmod(0o700)
        _write_private(self.marker_path, json.dumps(self._marker()))
        self._socket_directory()
        password = secrets.token_urlsafe(32)
        _write_private(self.password_path, password + "\n")
        _write_private(self.passfile_path,
                       f"127.0.0.1:{self.port}:*:mvp_bootstrap:{password}\n")
        _write_private(self.admin_env_path,
                       f"PGHOST=127.0.0.1\nPGPORT={self.port}\nPGDATABASE=postgres\n"
                       f"PGUSER=mvp_bootstrap\nPGPASSFILE={shlex.quote(str(self.passfile_path))}\n")
        result = self._run("initdb", ["-D", str(self.data_dir), "-U", "mvp_bootstrap",
                           "--encoding=UTF8", "--locale=C", "--auth-host=scram-sha-256",
                           "--auth-local=scram-sha-256", "--pwfile", str(self.password_path)])
        if result.returncode != 0:
            raise DevDBError("INITDB_FAILED")
        self._validate()
        return {"state": "prepared", "port": self.port, "cluster_id": self.cluster_key}

    def _pid(self) -> int | None:
        pidfile = self.data_dir / "postmaster.pid"
        if pidfile.is_symlink():
            raise DevDBError("UNOWNED_PID")
        if not pidfile.exists():
            return None
        try:
            lines = pidfile.read_text().splitlines()
            if (len(lines) < 4 or Path(lines[1]).resolve() != self.data_dir
                    or int(lines[3]) != self.port or int(lines[0]) <= 1):
                raise DevDBError("UNOWNED_PID")
            return int(lines[0])
        except (OSError, ValueError):
            raise DevDBError("UNOWNED_PID") from None

    def connect(self) -> psycopg.Connection:
        self._validate()
        try:
            return psycopg.connect(host="127.0.0.1", port=self.port, dbname="postgres",
                                   user="mvp_bootstrap", passfile=str(self.passfile_path),
                                   sslmode="disable", connect_timeout=2, autocommit=True,
                                   options="-c statement_timeout=3000",
                                   application_name="ai_platform_devdb_a01")
        except psycopg.Error:
            raise DevDBError("CLUSTER_CONNECTION_FAILED") from None

    def status(self) -> dict:
        if not self.runtime.exists() or not any(self.runtime.iterdir()):
            return {"state": "unprepared", "port": self.port, "cluster_id": self.cluster_key}
        self._validate()
        pid = self._pid()
        if pid is None:
            return {"state": "stopped", "port": self.port, "cluster_id": self.cluster_key}
        result = self._run("pg_ctl", ["-D", str(self.data_dir), "status"])
        if result.returncode == 3:
            return {"state": "stopped", "port": self.port, "cluster_id": self.cluster_key}
        if result.returncode != 0:
            raise DevDBError("CLUSTER_STATUS_FAILED")
        with self.connect() as conn:
            row = conn.execute("SELECT current_setting('data_directory'),"
                               "current_setting('port'),current_setting('server_version'),"
                               "current_database(),current_user").fetchone()
        if Path(row[0]).resolve() != self.data_dir or int(row[1]) != self.port:
            raise DevDBError("WRONG_SERVER")
        return {"state": "running", "port": self.port, "cluster_id": self.cluster_key,
                "pid": pid, "server_version": row[2], "database": row[3], "runtime_role": row[4]}

    def start(self) -> dict:
        self._validate()
        if self.status()["state"] == "running":
            return self.status()
        self._socket_directory()
        with socket.socket() as probe:
            probe.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            try:
                probe.bind(("127.0.0.1", self.port))
            except OSError:
                raise DevDBError("PORT_IN_USE") from None
        options = shlex.join(["-h", "127.0.0.1", "-p", str(self.port), "-k", str(self.socket_dir),
                              "-c", "unix_socket_permissions=0700", "-c", "log_statement=none",
                              "-c", "log_min_error_statement=panic", "-c", "log_parameter_max_length=0",
                              "-c", "log_parameter_max_length_on_error=0"])
        log_path = self.runtime / "postgres.log"
        if not log_path.exists() and not log_path.is_symlink():
            _write_private(log_path, "")
        if log_path.is_symlink() or stat.S_IMODE(log_path.stat().st_mode) != 0o600:
            raise DevDBError("UNOWNED_RUNTIME")
        result = self._run("pg_ctl", ["-D", str(self.data_dir), "-l", str(log_path),
                                      "-o", options, "-t", "15", "-w", "start"])
        if result.returncode != 0:
            raise DevDBError("CLUSTER_START_FAILED")
        return self.status()

    def stop(self) -> dict:
        if self.status()["state"] != "running":
            return self.status()
        result = self._run("pg_ctl", ["-D", str(self.data_dir), "-m", "fast", "-t", "15", "-w", "stop"])
        if result.returncode != 0:
            raise DevDBError("CLUSTER_STOP_FAILED")
        return self.status()


def main() -> int:
    parser = argparse.ArgumentParser(description="Project-owned loopback PostgreSQL development cluster")
    parser.add_argument("action", choices=("prepare", "start", "status", "stop"))
    args = parser.parse_args()
    try:
        cluster = DevCluster()
        print(json.dumps(getattr(cluster, args.action)(), ensure_ascii=False))
        return 0
    except DevDBError as error:
        print(json.dumps({"error": {"code": str(error)}}))
        return 1
    except Exception:
        print(json.dumps({"error": {"code": "DEVDB_INTERNAL_ERROR"}}))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
