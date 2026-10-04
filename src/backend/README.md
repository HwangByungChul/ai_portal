# AI 플랫폼 backend — A01 실행 기반

현재 기능은 `/api/v1/health` 생존 확인 API와 프로젝트 전용 PostgreSQL 실행 도구다. 로그인/조직/관리/AI API는 아직 없다. A02에서 업무 DB·runtime 역할/RLS를, A03에서 실제 인증을 구현한다.

## 환경과 설치

확인한 환경: macOS x86_64, Python3.13.2, PostgreSQL15.18(Homebrew). 이미 설치된 Node22.23.1은 A05의 화면 환경에서 사용한다. 전역 기본 Node는 변경하지 않았다. Docker는 필요하지 않다.

아래 명령은 프로젝트 루트에서 `cd src/backend`한 뒤 실행한다. `.venv`는 이 폴더 안에 생성하고 정확한 직접9개/전이 의존성30개는 requirements 파일로 고정한다. pip-tools는 lock 생성용 도구이며 앱 실행 의존성과 구분한다.

```bash
/Library/Frameworks/Python.framework/Versions/3.13/bin/python3 -m venv .venv
.venv/bin/python -m pip install --require-hashes -r requirements.lock
.venv/bin/python -m pip check
```

의존성을 변경할 때만 다음 명령으로 lock을 다시 만들고 실제 시험을 수행한다.

```bash
.venv/bin/python -m pip install pip-tools==7.6.1
.venv/bin/python -m piptools compile --generate-hashes --no-emit-index-url --no-emit-trusted-host --output-file requirements.lock requirements.in
```

## 상태 확인 API

기본 설정은 loopback127.0.0.1/mock이며 health는 DB 자격 없이 동작한다. `.env.example`은 설정 이름 예시다. 자동으로 `.env`나 관리자 자격 파일을 읽지 않는다. 잘못된 local origin/외부 bind는 설정 검증에서 거부한다.

```bash
.venv/bin/python -m uvicorn app.main:create_app --factory --host 127.0.0.1 --port 8000
```

다른 터미널에서 다음을 확인한다.

```bash
curl -i http://127.0.0.1:8000/api/v1/health
```

200, data.status=ok, Cache-Control=no-store, X-Request-ID를 반환한다. meta에는 서버 request_id/tenant_id=null/UTC server_time만 포함한다. 이 응답은 DB 준비나 인증·전체 플랫폼 완료를 의미하지 않는다. API 프로세스는 해당 실행 터미널에서 Ctrl-C로 종료한다.

## 전용 PostgreSQL

기존5432 서버와 별도로55432를 사용한다. `mvp_bootstrap`은 이 전용 클러스터의 초기 관리자다. 웹앱에 이 자격을 연결하지 않는다. A02에서 별도 업무 DB와 web/index/meter 역할을 분리한다.

```bash
.venv/bin/python -m scripts.devdb prepare
.venv/bin/python -m scripts.devdb start
.venv/bin/python -m scripts.devdb status
.venv/bin/python -m scripts.devdb stop
```

prepare는 처음만 initdb를 실행하며 기존 소유 클러스터에서는 비밀번호를 바꾸지 않는다. start/status/stop은 소유 marker/PG_VERSION/PID 파일/접속 서버의 실제 data_directory와 port를 검증한다. 실행 중인 타 서비스의 포트를 빼앗지 않는다. DB 삭제/reset이나 임의 datadir 입력 옵션은 없다.

`src/backend/.runtime`에는 데이터/소유 marker/관리 전용 passfile·admin.env/로그를 저장한다. 디렉토리는0700, 비밀/도구 로그는0600이고 Git에서 제외한다. 비밀번호는 명령 인수/표준출력/응답 JSON에 넣지 않는다. admin.env에는 비밀번호 대신 private passfile 위치가 있다. 계정·키·DB 자격 파일을 문서나 Git에 복사하지 않는다.

한글 프로젝트 경로의 길이 때문에 Unix 통신 폴더는 `/private/tmp/ai-portal-pg-<uid>-<소유경로지문>`에 둔다. 이 폴더도0700/소유 marker를 검사한다. DB 데이터는 프로젝트 안에 남는다. 프로그램은 다른 프로젝트의 통신 폴더를 재사용하지 않는다.

실행 중인 포트 충돌은 PORT_IN_USE다. 종료된 연결의 TIME_WAIT만 남은 경우는 재시작을 허용한다. UNOWNED_RUNTIME/UNOWNED_SOCKET_DIRECTORY/UNOWNED_PID/PG_VERSION_MISMATCH/PREPARATION_INCOMPLETE는 자동 삭제·초기화하지 않고 정제된 오류만 반환한다.

## 검증

```bash
.venv/bin/python -m pytest -q
```

A01에서19개 시험을 확인했다. DB 시험은55433의 자체 임시 클러스터만 사용하고 종료·정리한다. 개발55432나 기존5432를 reset하지 않는다. health/설정·쿠키와 무관한 미구현API404/소유 경로·symlink·소유 marker·PID·실제 초기화/중지/재시작·포트 충돌/TIME_WAIT/비밀·로그 권한을 검증한다.

현재 설치된 Starlette1.7.0은 TestClient의 httpx0.28.1 경로에 deprecation warning1개를 낸다.19개 시험은 정상 통과했으며 경고를 숨기지 않았다. 자동으로 httpx2를 추가하거나 버전을 변경하지 않았고, 다음 호환성 변경 시 별도로 검증한다.

상세 결과는 Obsidain의 `250.구현/02 인증과 테넌트 기반 구현 결과.md`, 증거는 `260.테스트/evidence/A-auth/A01-*.json`에 관리한다. 현재 로그인·소속/권한·RLS·화면·AI·전체V41/Q20 시험은 아직 미수행이다.
