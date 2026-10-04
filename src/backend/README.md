# AI 플랫폼 backend — A01~02 실행 기반

전용 PostgreSQL 환경, 첫11개 업무테이블, 현재 세션·소속 기반 조직/개인 RLS, 웹 전용 연결 풀과 `/api/v1/health`가 구현되어 있다. HTTP 로그인·관리API·화면·AI는 후속이다. health200은 전체 플랫폼 완료를 뜻하지 않는다.

## 환경과 설치

확인 환경: macOS x86_64/Python3.13.2/PostgreSQL15.18(Homebrew). Node22.23.1은 A05에서사용한다. 전역 Node는변경하지않았으며Docker는필요없다.

프로젝트 루트에서 `cd src/backend`한뒤실행한다. `.venv`는이폴더안에두며직접9개/전이포함30개는hash lock으로고정했다. A02의추가의존성은없다.

```bash
/Library/Frameworks/Python.framework/Versions/3.13/bin/python3 -m venv .venv
.venv/bin/python -m pip install --require-hashes -r requirements.lock
.venv/bin/python -m pip check
```

의존성을변경할때만lock을재생성하고실제시험한다.

```bash
.venv/bin/python -m pip install pip-tools==7.6.1
.venv/bin/python -m piptools compile --generate-hashes --no-emit-index-url --no-emit-trusted-host --output-file requirements.lock requirements.in
```

## 전용 PostgreSQL과 초기화

기존5432와별도로127.0.0.1:55432를사용한다. `mvp_bootstrap`은전용클러스터의초기관리만수행하며앱에주입하지않는다. 소유marker/PG_VERSION/PID/data_directory/port를확인한다. 포트충돌은기존서버를종료하지않고거부한다.

```bash
.venv/bin/python -m scripts.devdb prepare
.venv/bin/python -m scripts.devdb start
.venv/bin/python -m scripts.devdb status
```

아직새fixture설정이없을때만다음을실행한다. 이번A02에서는이미실행했으므로,기존`.runtime/active-fixture.json`과`app.env`를유지하고start부터재사용한다.

```bash
.venv/bin/python -m scripts.migrate --fixture A-auth
.venv/bin/python -m scripts.seed --fixture A-auth
```

migrate는`ai_portal_mvp_test_<UUID>`의새시험DB/comment marker를생성한다. 000/001/002 SQL과SHA256 기록을단일transaction으로적용하고완료전에runtime접속을개방하지않는다. 반복CLI는기존설정을감지해거부한다. 재seed/비fixture/외부DB/변경된적용SQL도거부하며reset/drop CLI는제공하지않는다. 적용된migration은수정하지말고003이후새파일로추가한다. 시험용real예산행은실원장의reset허가가아니다.

직접migration runner가필요한후속작업은private active fixture를읽은`FixtureDatabase`에`apply_migrations`를호출한다. 기존파일의checksum은동일해야하며pending파일만원자적용된다. 테스트의새DB는suite실행중각시험별로만생성/검증/정리한다.

업무11개: security의accounts/tenants/memberships/platform_access/managed_tenants/sessions/login_windows,portal의agent_configs/conversations,ops의project_budget/audit_events. infra.schema_migrations는별도도구테이블1개다. 전체31개/문서·Graph 모델은후속이다.

## 자격과 현재 경계

- `ai_owner`/`ai_policy_executor`는NOLOGIN. ai_web/index/meter는별도LOGIN이며superuser/BYPASSRLS/상속/DB·역할생성/replication없음.
- ai_web은security원시테이블·전역비용원장직접조회·owner/index/meter역할전환이불가하다. 현재세션/소속의고정제어함수와개인대화RLS만사용한다.
- 대화/Agent/audit는ENABLE+FORCE RLS. 조직관리자/PADMIN도타인의개인대화우회없음. owner/tenant/Agent 수정권한없고updated_at만수정한다.
- 본인세션/소속문맥은서버검증후transaction-local로설정한다. 기본READ COMMITTED에서매SQL현재권한을확인하고정상/rollback/취소후문맥이남지않는다. effective_role을클라이언트권한증표로사용하지않는다.
- pool은lifespan에서open/wait/close하며접속과checkout에서web역할/DB marker/소유·권한을검사한다. 거부된연결도즉시닫는다.

`.runtime`은0700/Git제외,비밀·도구로그는0600이다. bootstrap.password/pgpass/admin.env/runtime-roles.json은초기화용,app.env는web DSN/HMAC만,fixture-secrets는합성비밀번호만저장한다. 앱은자동으로이파일들을읽지않으며관리환경을source하지않는다. 원문비밀번호/쿠키/CSRF/DB자격을명령인수·화면·로그·Git에복사하지않는다.

합성manifest9액터와시험용추가4액터를난수비밀번호/Argon2id로초기화한다. TADMIN은membership역할이고PADMIN은별도platform_access와명시관리소속이다. 두Agent는disabled,대화행은DB경계시험의메타데이터만있다. seed세션은HTTP로그인성공증거가아니다.

Unix통신폴더는한글경로길이때문에 `/private/tmp/ai-portal-pg-<uid>-<소유지문>`의0700/marker를검사해사용한다. 데이터는프로젝트안에유지한다. stop은자기datadir만대상이며다른PG프로세스를종료하지않는다. 소유오류는자동삭제/초기화하지않는다.

## 실행과 종료

DB자격이없는health전용모드:

```bash
.venv/bin/python -m uvicorn app.main:create_app --factory --host 127.0.0.1 --port 8000
```

A02의웹전용DB pool까지확인하는모드는별도터미널에서private앱설정만주입한다. 다음블록은괄호의자식셸에서실행해다른터미널환경으로자격을남기지않는다. shell tracing은켜지않는다.

```bash
(
set -a
source .runtime/app.env
set +a
.venv/bin/python -m uvicorn app.main:create_app --factory --host 127.0.0.1 --port 8000
)
```

다른터미널에서확인한다.

```bash
curl -i http://127.0.0.1:8000/api/v1/health
```

200/data.status=ok/no-store/X-Request-ID/UTC meta를반환한다. HTTP인증경로는아직404다. API는실행터미널에서Ctrl-C로종료하며pool도닫힌다. 전용DB는다음명령으로종료한다.

```bash
.venv/bin/python -m scripts.devdb stop
```

A03에서는인증앱의web DSN/HMAC 누락을시작거부로전환한다. 지금DSN이설정된앱의잘못된role/marker는시작거부이며DSN없는모드는health만이다.

## 검증과 증거

```bash
.venv/bin/python -m pytest -q
```

최종71개(A01회귀19+A02신규52)가통과했다. A01 도구스모크는별도55433임시클러스터, A02는소유55432의새접두/marker DB만시험후정리한다. 처음55432가정지였으면종료후정지로되돌린다. 기존설정fixture/실원장/5432는reset하지않는다. 각fixture는자기event loop와pool을함께닫아닫힌loop를재사용하지않는다.

실제ai_web자체접속에서권한속성/무문맥·잘못된문맥/본인·조직·관리자경계/복합FK·불변binding/현재권한회수/SQL권한·제어함수/풀정상·rollback·취소·동시분리/checksum·초기화원자성/비fixture·재seed거부를검증했다. HTTP인증·브라우저·문서/Grant/Graph·실AI원장·전체V41/Q20은후속이다.

Starlette1.7.0 TestClient/httpx0.28.1 deprecation경고1개가있다. 경고를숨기거나httpx2를자동추가하지않았으며시험은통과했다. 상세결과는Obsidain `250.구현/02 인증과 테넌트 기반 구현 결과.md`,정제증거는 `260.테스트/evidence/A-auth/A02-*.json`에관리한다. A01증거는이력으로보존한다.
