"""Foreground, loopback-only Mock pilot; Ctrl-C cleans only its owned harness.

Reuses the marked disposable browser harness. No primary resets, real key,
gold graph inserts, new dependency, or network provider dispatch.
"""
from pathlib import Path
from types import SimpleNamespace
import json, os, signal, subprocess, sys, time
from uuid import uuid4
from scripts.devdb import _read_private, _write_private
from scripts.c06_evaluate import Api
from app.db import DB_MARKER

BACKEND = Path(__file__).resolve().parents[1]
RUNTIME = BACKEND / '.runtime'
CONFIG = RUNTIME / 'A05-fixture.json'
READY = RUNTIME / 'P270-ready.json'
ACCESS = RUNTIME / 'P270-access-private.md'
STOP = False


def stop(signum, frame):
    global STOP
    STOP = True


def main():
    import httpx
    if CONFIG.exists() or READY.exists() or ACCESS.exists():
        raise RuntimeError('PILOT_RUNTIME_ALREADY_EXISTS')
    for sig in (signal.SIGTERM, signal.SIGINT):
        signal.signal(sig, stop)
    env = {k: v for k, v in os.environ.items() if not k.startswith(('AI_', 'PG'))}
    child = None
    api = None
    owned_files = []
    try:
        with os.fdopen(os.open(RUNTIME / 'P270-harness-private.log', os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600), 'w') as log:
            child = subprocess.Popen([sys.executable, '-m', 'scripts.portal_test_server'], cwd=BACKEND, env=env, stdout=log, stderr=log)
            deadline = time.monotonic() + 30
            while not STOP and time.monotonic() < deadline:
                if child.poll() is not None:
                    raise RuntimeError('PILOT_HARNESS_FAILED')
                if CONFIG.exists():
                    config = json.loads(_read_private(CONFIG))
                    if config['pid'] != child.pid or config['kind'] != 'A05-disposable-browser' or config['marker'] != DB_MARKER:
                        raise RuntimeError('PILOT_OWNERSHIP_MISMATCH')
                    try:
                        if httpx.get('http://127.0.0.1:5173/api/v1/health', timeout=.5, trust_env=False).status_code == 200:
                            break
                    except httpx.HTTPError:
                        pass
                time.sleep(.1)
            else:
                if STOP:
                    return 0
                raise RuntimeError('PILOT_READY_TIMEOUT')
            subprocess.run([sys.executable, '-m', 'scripts.portal_test_control', 'c05-enable'], cwd=BACKEND, env=env, check=True, stdout=subprocess.DEVNULL, stderr=log)
            secret = json.loads(_read_private(Path(config['secret_path'])))
            state = SimpleNamespace(passwords=secret['passwords'], tenant_ids=config['tenants'], actor_ids=config['actors'])
            api = Api(state)
            for title, raw, private in [
                ('파일럿 합성 여신 규정', '여신심사의 담당 부서는 심사1팀이다.\n여신심사의 위험 검토 승인 부서는 위험관리팀이다.\n', False),
                ('파일럿 개인 리허설', '가상사용자의 개인 시연 리허설은 수요일 정오에 진행한다.\n', True),
            ]:
                meta = {'client_upload_id': str(uuid4()), 'title': title, 'visibility': 'private' if private else 'org', 'reader_ids': [], 'media_type': 'text/plain'}
                if private:
                    meta['owner_user_id'] = config['actors']['A-U1']
                receipt = api.data('A-ADM', 'A', 'POST', '/admin/documents', files={'metadata': (None, json.dumps(meta), 'application/json'), 'file': ('pilot.txt', raw.encode(), 'text/plain')})
                job = api.terminal('A-ADM', 'A', '/admin/jobs/' + receipt['job_id'], 'terminal')
                if job['state'] != 'completed':
                    raise RuntimeError('PILOT_DOCUMENT_NOT_PUBLISHED')
            aliases = ['A-ADM', 'A-U1', 'A-U2', 'B-ADM', 'B-U1', 'DUAL']
            guide = '# P270 비공개 접속 안내\n\n주소: http://127.0.0.1:5173\n모의 전용 / 현재 실행 중에만 유효 / 종료하면 자료·계정 삭제\n\n|계정 별칭|로그인 ID|비밀번호|\n|---|---|---|\n'
            guide += ''.join(f'|{a}|{a.lower()}|{state.passwords[a]}|\n' for a in aliases)
            _write_private(ACCESS, guide); owned_files.append(ACCESS)
            _write_private(READY, json.dumps({'kind': 'P270-owned-mock-pilot', 'pid': os.getpid(), 'harness_pid': child.pid, 'mode': 'mock', 'paid_dispatches': 0, 'documents_published': 2, 'access_file': str(ACCESS)})); owned_files.append(READY)
            print(json.dumps({'status': 'ready', 'mode': 'mock', 'documents_published': 2, 'access_file': str(ACCESS), 'stop': 'Ctrl-C'}), flush=True)
            while not STOP:
                if child.poll() is not None:
                    raise RuntimeError('PILOT_HARNESS_EXITED')
                time.sleep(.1)
    finally:
        if api:
            api.close()
        if child and child.poll() is None:
            child.terminate()
            # The harness owns DB/source cleanup; never kill unrelated processes.
            child.wait(timeout=15)
        for path in owned_files:
            path.unlink(missing_ok=True)
    return 0


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except Exception as error:
        print(json.dumps({'status': 'failed', 'error': type(error).__name__, 'credentials_printed': False}), flush=True)
        raise SystemExit(1)
