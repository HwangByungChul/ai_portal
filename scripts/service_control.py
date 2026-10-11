"""Local service lifecycle; never signal an unowned process or reset the database."""
import fcntl
import hashlib
import json
import os
from pathlib import Path
import signal
import socket
import subprocess
import sys
import time
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "src/backend"
FRONTEND = ROOT / "src/frontend"
PYTHON = BACKEND / ".venv/bin/python"

def identity(pid):
    if type(pid) is not int or pid <= 1:
        return None
    result = subprocess.run(["/bin/ps", "-p", str(pid), "-o", "lstart="],
                            capture_output=True, check=False)
    if result.returncode or not result.stdout.strip():
        return None
    return hashlib.sha256(result.stdout.strip()).hexdigest()

def private_open(path, flags):
    return os.open(path, flags | os.O_NOFOLLOW, 0o600)

def load_record(path):
    try:
        with os.fdopen(private_open(path, os.O_RDONLY)) as f:
            data = json.load(f)
        if set(data) != {"pid", "identity", "service"}:
            raise ValueError("잘못된 실행 기록입니다.")
        return data
    except FileNotFoundError:
        return None

def owned(record, service):
    return bool(record and record["service"] == service and record["identity"]
                and identity(record["pid"]) == record["identity"])

def listening(port):
    with socket.socket() as sock:
        sock.settimeout(0.5)
        return sock.connect_ex(("127.0.0.1", port)) == 0

def stop_owned(record, service, timeout=20):
    if not owned(record, service):
        return True
    os.kill(record["pid"], signal.SIGTERM)
    until = time.monotonic() + timeout
    while time.monotonic() < until:
        if not owned(record, service):
            return True
        time.sleep(0.1)
    return False

def main():
    if len(sys.argv) != 3 or sys.argv[1] not in ("backend", "frontend") or sys.argv[2] not in ("start", "stop"):
        raise ValueError("사용법: service_control.py backend|frontend start|stop")
    service, action = sys.argv[1:]
    folder = BACKEND if service == "backend" else FRONTEND
    runtime = folder / ".runtime/service-control"
    runtime.mkdir(mode=0o700, parents=True, exist_ok=True)
    if runtime.is_symlink() or runtime.parent.is_symlink():
        raise ValueError("실행 기록 폴더의 링크는 허용하지 않습니다.")
    os.chmod(runtime, 0o700)
    record_path = runtime / "process.json"
    with os.fdopen(private_open(runtime / "control.lock", os.O_RDWR | os.O_CREAT), "w") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        record = load_record(record_path)
        port = 8000 if service == "backend" else 5173
        if action == "stop":
            if not owned(record, service):
                if record:
                    record_path.unlink()
                print(f"{service}: 이 스크립트로 실행한 서비스가 없습니다."
                      + (" 해당 포트의 다른 프로세스는 유지했습니다." if listening(port) else ""))
                return
            if not stop_owned(record, service):
                raise ValueError("정상 종료 대기 시간이 초과됐습니다. 기록과 로그를 확인하세요.")
            record_path.unlink(missing_ok=True)
            print(f"{service}: 종료했습니다." + (" 데이터베이스는 유지했습니다." if service == "backend" else ""))
            return
        if owned(record, service):
            print(f"{service}: 이미 실행 중입니다. http://127.0.0.1:{port}/")
            return
        if record:
            record_path.unlink()
        if listening(port):
            raise ValueError(f"포트 {port}가 다른 프로세스에서 사용 중입니다. 해당 프로세스를 먼저 확인하세요.")
        env = {k: v for k, v in os.environ.items() if not k.startswith(("AI_", "PG"))}
        if service == "backend":
            if not (BACKEND / ".runtime/app.env").is_file():
                raise ValueError("기존 backend/.runtime/app.env 설정이 필요합니다.")
            command = [str(PYTHON), "-m", "uvicorn", "app.main:create_app", "--factory",
                       "--env-file", ".runtime/app.env", "--host", "127.0.0.1", "--port", "8000",
                       "--no-proxy-headers", "--no-access-log"]
        else:
            node = Path.home() / ".nvm/versions/node/v22.23.1/bin/node"
            vite = FRONTEND / "node_modules/vite/bin/vite.js"
            if not node.is_file() or not vite.is_file():
                raise ValueError("Node 22.23.1과 frontend/node_modules 설치가 필요합니다.")
            command = [str(node), str(vite), "--host", "127.0.0.1", "--port", "5173", "--strictPort"]
        log_path = runtime / "service.log"
        with os.fdopen(private_open(log_path, os.O_WRONLY | os.O_CREAT | os.O_APPEND), "a") as log:
            os.chmod(log_path, 0o600)
            if service == "backend":
                db = subprocess.run([str(PYTHON), "-m", "scripts.devdb", "start"], cwd=BACKEND,
                                    env=env, stdout=log, stderr=log, timeout=30)
                if db.returncode:
                    raise ValueError(f"데이터베이스 시작 실패. 로그: {log_path}")
            process = subprocess.Popen(command, cwd=folder, env=env, stdin=subprocess.DEVNULL,
                                       stdout=log, stderr=log, start_new_session=True)
        record = {"pid": process.pid, "identity": identity(process.pid), "service": service}
        if not record["identity"]:
            process.terminate()
            process.wait(timeout=10)
            raise ValueError("프로세스 실행 정보를 확인할 수 없습니다.")
        temp = runtime / f"process-{os.getpid()}.tmp"
        with os.fdopen(private_open(temp, os.O_WRONLY | os.O_CREAT | os.O_EXCL), "w") as f:
            json.dump(record, f)
        os.replace(temp, record_path)
        url = f"http://127.0.0.1:{port}/" + ("api/v1/health" if service == "backend" else "")
        ready = False
        for _ in range(150):
            if process.poll() is not None:
                break
            try:
                with urllib.request.urlopen(url, timeout=0.5) as response:
                    ready = response.status == 200
            except OSError:
                pass
            if ready:
                break
            time.sleep(0.2)
        if not ready:
            if stop_owned(record, service):
                record_path.unlink(missing_ok=True)
            raise ValueError(f"서비스 준비 실패. 로그: {log_path}")
        print(f"{service}: 실행했습니다. http://127.0.0.1:{port}/")
        print(f"로그: {log_path}")

if __name__ == "__main__":
    try:
        main()
    except (ValueError, OSError, subprocess.SubprocessError) as error:
        print(f"실행 오류: {error}", file=sys.stderr)
        sys.exit(1)
