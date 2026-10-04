# AI 플랫폼 backend — A 완료 · B01 대화·원장 저장 기반

A 인증·조직·관리 API/화면·통합 검증을 완료했고 B01에서 추가5개 저장 모델·형식·권한을 구축했다. 업무16개와 infra1개다. 대화/run 업무 API는 B03, 예약·발사·정산 및 실제 AI는 B04 이후다. health200은 전체 플랫폼 완료를 뜻하지 않는다.

## 환경과 설치

확인 환경: macOS x86_64/Python3.13.2/PostgreSQL15.18(Homebrew). Node22.23.1은 A05에서사용한다. 전역 Node는변경하지않았으며Docker는필요없다.

프로젝트 루트에서 `cd src/backend`한뒤실행한다. `.venv`는이폴더안에두며직접11개 pin을 hash lock으로 고정했다. 기존9개에 openai3.24.0/tiktoken0.14.0을 추가하고 Python3.13용 설치/import/pip check를 확인했다. 현재 가상환경48개 배포판은 pip/pip-tools 등 설치 도구를 포함한 수이며, lock의 실행 의존성 수와 구분한다.

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

migrate는`ai_portal_mvp_test_<UUID>`의새시험DB/comment marker를생성한다. 000~005 SQL과SHA256 기록을단일transaction으로적용하고완료전에runtime접속을개방하지않는다. 반복CLI는기존설정을감지해거부한다. 재seed/비fixture/외부DB/변경된적용SQL도거부하며reset/drop CLI는제공하지않는다. 적용된migration은수정하지말고006이후새파일로추가한다. 시험용real예산행은실원장의reset허가가아니다.

A03에서는003,A04에서는004만기존active fixture에추가적용했고계정/세션/창이나web DSN/HMAC은reset하지않았다. 이후pending migration도private active fixture의소유를검증한뒤같은runner로적용한다. 기존데이터가있는DB에는seed를다시호출하지않는다.

```bash
.venv/bin/python - <<'PYCODE'
import json
from scripts.devdb import DevCluster, _read_private
from scripts.migrate import FixtureDatabase, apply_migrations
cluster = DevCluster()
registry = json.loads(_read_private(cluster.runtime / 'active-fixture.json'))
print({'applied': apply_migrations(FixtureDatabase(registry['database'], cluster))})
PYCODE
```

DB는먼저start 상태여야한다. 직접migration runner는private active fixture의`FixtureDatabase`만사용한다. 기존파일의checksum은동일해야하며pending파일만원자적용된다. 테스트의새DB는suite실행중각시험별로만생성/검증/정리한다.

업무11개: security의accounts/tenants/memberships/platform_access/managed_tenants/sessions/login_windows,portal의agent_configs/conversations,ops의project_budget/audit_events. infra.schema_migrations는별도도구테이블1개다. B01에서 portal.messages/runs와 ops.tenant_budgets/call_attempts/usage_events를 추가해 업무16개다. 전체31개/문서·Graph 모델은 후속이다.

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

DB자격이없는health전용모드(인증route없음):

```bash
.venv/bin/python -m uvicorn app.main:create_health_app --factory --host 127.0.0.1 --port 8000 --no-proxy-headers --no-access-log
```

실제인증API 모드는별도터미널에서private앱설정만주입한다. 다음블록은괄호의자식셸에서실행해다른터미널환경으로자격을남기지않는다. shell tracing은켜지않는다.

```bash
(
set -a
source .runtime/app.env
set +a
.venv/bin/python -m uvicorn app.main:create_app --factory --host 127.0.0.1 --port 8000 --no-proxy-headers --no-access-log
)
```

다른터미널에서확인한다.

```bash
curl -i http://127.0.0.1:8000/api/v1/health
```

200/data.status=ok/no-store/X-Request-ID/UTC meta를반환한다. health-only factory의인증경로만404이며기본factory는실제login/me/logout을제공한다. API는실행터미널에서Ctrl-C로종료하며pool도닫힌다. 전용DB는다음명령으로종료한다.

```bash
.venv/bin/python -m scripts.devdb stop
```

기본create_app은web DSN/HMAC이누락·부적합하면AUTH_CONFIGURATION_REQUIRED로시작거부한다. 잘못된DB role/marker도시작거부다. create_health_app만DSN없는생존확인에사용한다. 직접접속IP를쓰므로프록시헤더처리를끄고,URL/자격을접속로그에남기지않도록위옵션을사용한다.

## 실제 인증 계약

POST /api/v1/auth/login은JSON login_id/password와Origin=http://127.0.0.1:5173/X-Requested-With=ai-portal을받는다. 합성비밀번호는private fixture-secrets 파일에서만확인하며명령인수/문서/Git에복사하지않는다. 응답은본인user_id/display_name/session_expires_at/csrf_token,원문세션토큰은HttpOnly 쿠키만이다. CSRF는본인인증응답과private DB세션에서검증을위해사용한다.

GET /api/v1/auth/me는현재쿠키로세션/계정/인증revision/8h절대·30m idle을검증한다. 자동조회는idle을연장하지않는다. global 읽기/쓰기권한은독립계산하고writer에게만실제budget의공통운영상태/revision을준다. budget상태가없으면503이며전체비용/다른조직데이터를반환하지않는다.

POST /api/v1/auth/logout은같은Origin/지정헤더와유효세션의X-CSRF-Token을확인하고DB회수commit후logout_confirmed=true/쿠키삭제를반환한다. DB실패는503이며확정/쿠키삭제가없다. 이미무효인쿠키도Origin/지정헤더를확인한뒤정리한다. 재로그인은이전쿠키를회수한다.

로그인ID 실패5회/IP전체30회,15분창이며다음요청은429/Retry-After다. ID 성공은실패창만reset,IP창은reset하지않는다. HMAC은기존private설정을재사용하고재시작해도DB창/세션은유지한다. 실패count는오류응답전에commit하며동시요청도DB잠금으로직렬화한다.

local쿠키는ai_session_dev/HttpOnly/Lax/Path=/,HTTPS profile은__Host-ai_session/Secure/Domain없음이다. local은URL/직접client127.0.0.1만허용한다. HTTPS profile은쿠키계약시험이며원격TLS배포를완료한것이아니다. 두이름의쿠키/중복헤더를동시에받지않는다. 입력오류는필드명만,일반로그인실패는같은401,DB오류는안전한503/no-store로반환한다.

## 검증과 증거

```bash
.venv/bin/python -m pytest -q
```

현재최종176개(A04까지172+A06신규4)가통과했다. 기존A작업의각시험횟수는이력이며현재횟수에중복합산하지않는다. A01 도구스모크는별도55433임시클러스터, A02는소유55432의새접두/marker DB만시험후정리한다. 처음55432가정지였으면종료후정지로되돌린다. 기존설정fixture/실원장/5432는reset하지않는다. 각fixture는자기event loop와pool을함께닫아닫힌loop를재사용하지않는다.

실제ai_web자체접속에서권한속성/무문맥·잘못된문맥/본인·조직·관리자경계/복합FK·불변binding/현재권한회수/SQL권한·제어함수/풀정상·rollback·취소·동시분리/checksum·초기화원자성/비fixture·재seed거부를검증했다. A03에서는실제인증/CSRF/cookie/만료·회수/횟수·동시제한/DB실패·현재capability·세션발급감사rollback을추가검증했다. A04의관리API/현재회수/CAS·감사원자성/읽기창/권한잠금재검사도검증했다. 브라우저20개와실DB장애/재시작도A06에서통합검증했다. 문서/Grant/Graph·실AI원장·전체V41/Q20은후속이다.

Starlette1.7.0 TestClient/httpx0.28.1 deprecation경고1개가있다. 경고를숨기거나httpx2를자동추가하지않았으며시험은통과했다. 상세결과는Obsidain `250.구현/02 인증과 테넌트 기반 구현 결과.md`,정제증거는 `260.테스트/evidence/A-auth/A04-*.json`에관리한다. A01/A02/A03증거는이력으로보존한다.

## 실제 조직·관리 API 계약 — A04

GET /api/v1/me/tenants는현재쿠키의본인활성조직만items에반환한다. PADMIN표시는활성platform_access+명시active managed_tenants인조직만이며전역capability와독립이다. 조직0개도인증은유지된다.

GET /api/v1/admin/memberships는X-Tenant-ID UUID헤더하나가필수다. 허용조직의TADMIN/담당PADMIN만조회하며cursor UUID/limit 기본20·최대50을받는다. items는user_id/display_name/role/active/revision만,다음페이지는next_cursor다. active는조직소속의상태이며전역계정active를변경하지않는다. 사용자/조직별1분120회·다음429/Retry-After이며재로그인으로초기화되지않는다. GET은idle을연장하지않는다.

PATCH /api/v1/admin/memberships/{user_id}는JSON active(strict bool)/expected_revision(양의정수)를받는다. PUT .../{user_id}/role은role USER 또는TADMIN/expected_revision을받는다. Origin/X-Requested-With/CSRF/현재조직헤더는필수이며추가body필드는422다. TADMIN은다른일반USER의소속활성만,담당PADMIN은다른USER↔TADMIN역할/활성변경을허용한다. 자기·플랫폼관리자대상(비활성/미담당포함)·PADMIN부여는차단한다.

행잠금뒤현재권한을재검사하고변경/revision+1/audit/성공세션touch를한transaction에서처리한다. 권한확인뒤없는조직대상404,stale revision409,감사실패·잠금시간초과503이며실패변경은rollback한다. 메타데이터tenant_id는허용된현재문맥만반환한다. 쿠키/CSRF·비밀번호를curl명령이나공유로그에복사하지않는다. 화면연결과브라우저검증은A05다.

## 포털 화면 연결 — A05

src/frontend의README대로같은터미널에서Node22.23.1을선택하고npm ci/npm run dev로실행한다. 포털주소는http://127.0.0.1:5173,이API는127.0.0.1:8000이다. Vite가/api를같은출처로연결하고Origin은바꾸지않는다. 로그인/조직선택/사용자관리는실제API를사용하며프론트설정에web DSN/HMAC/합성비밀번호를복사하지않는다.

A05에서는새시험전용scripts/portal_test_server.py/control.py로별도marker DB/실제API/Vite/Chromium을실행했다. 기존active fixture/실원장의reset권한을추가하지않았고제품HTTP에fault경로는없다. 20개브라우저시험/build통과,테스트종료후API연결0/해당DB·비밀번호파일정리/전용55432정지를확인했다. 기존11개업무테이블과private설정·migration5개·합성9개파일은보존했다. 전체백엔드172시험은A04기록이며A06에서프론트와통합재검증한다.

## 첫 기능 A 통합 검증 — A06

`tests/test_auth_restart.py`는실제127.0.0.1:8000 child/별도합성DB로재시작·절대/유휴만료·소속회수/RLS·실DB stop/start와login/logout/member 503·복구/명시retry를검증한다. 자신이생성한child와소유55432만제어하며외부서버를종료하지않는다. API와fixture양쪽pool을닫은후잔여0을확인하고DB/비밀번호파일을정리한다.

최종176pass/경고1,frontend build/실제브라우저20pass. 인증된GET /api/v1/me/tenants20회p95 5.766ms(목표300ms)/idle불변. 현재A승인계획pool대기5초·startupwait5초/statement5초/lock2초, 공통pool2초·idletransaction5초정합은B01에서다룬다. 실AI/검색성능으로이국소측정을확대하지않는다.

정제증거는Obsidain260.테스트/evidence/A-auth의summary.json/test-results.json/db-boundaries.json/README.md,다음B01계획은250.구현/03 일반 대화와 중앙 AI 구현 계획.md다. 이 절은 A06 당시 검증 이력이다. B01 현재 상태는 다음 절을 따른다. A/B01 통과로 전체V41/Q20 완료를 표시하지 않는다. 원본로그/JUnit/비밀은.runtime안의private로만보관한다.

## B01 대화·원장 저장 기반과 오프라인 토큰 준비

005만 기존 active fixture에 추가 적용하며 기존11개 업무행/private app.env·HMAC·000~004 checksum을 보존한다. 새5개 테이블은 아직 비어 있고 primary에 대화/run이나 비용을 임의 생성하지 않는다. Agent는 기존 disabled를 유지한다.

- 새5개는 ai_owner 소유/ENABLE+FORCE RLS/PUBLIC 권한 제거. web SELECT는 본인·현재 조직의 메시지와 최소 run 열만 허용하며 request_hash/config_snapshot을 직접 읽을 수 없다. 관리자의 개인 본문 예외가 없다.
- pending assistant는 공개하지 않고 completed/answer만 읽는다. 본문 분류·owner/Agent·대상 run/모드·origin session 소유 복합FK와 불변 trigger를 사용한다. B는 general만이며 Job·RAG 본문/임베딩 call은 DB에서도 차단한다. C의 새 migration에서 확장한다.
- 사용량 event UPDATE/DELETE를 trigger로 거부하고 token 정수/합계·필드 allowlist, 가격 snapshot·logical step·settle/release 상호배타 키를 적용한다. 실제 reserve/dispatch/settle CAS는 B04의008에서 구현할 예정이다. 현재 runtime의 원장 직접 읽기·쓰기는 거부한다.
- web 최대4/meter 최대2의 별도 자격 pool을 configure/checkout마다 검증한다. 둘 다 borrower 대기2초/startup wait5초/statement5초/lock2초/idle-in-transaction5초다. meter는 본문·세션 고정함수·web/owner 역할 전환이 불가하다. 설정의 meter_dsn은 SecretStr/repr 제외이며 B04 연결 전 기본 앱에서 meter pool을 자동 열지 않는다.

필요한 공개 인코딩 파일을 최초1회 준비한다. 키나 유료 AI 호출은 필요 없다.

```bash
.venv/bin/python -m scripts.prepare_tokenizers
```

프로젝트 `.runtime/tokenizer-cache`(0700)에 o200k_base/cl100k_base BPE 파일(0600)을 고정 SHA256로 검증해 저장한다. 런타임은 이를 읽기만 하고 누락·변조·symlink면 TOKENIZER_NOT_READY로 차단하며 자동 다운로드하지 않는다. 일반 입력은 질문4000 codepoint/UTF-8 16KiB·지침2000자·최근 완전 메시지6개·6000토큰을 검사한다. 초과 이력은 오래된 메시지 단위로 제외하고 지침/현재 질문은 자르지 않는다. Chat framing+32 여유 토큰은 보수 추정이며 실제 usage와 동일함을 보장하지 않는다. HTTP JSON32KiB 제한은 B03에서 연결한다.

Decimal 고정 price-20261004-v1: 생성 예약3.64원, 질의/문서 임베딩 예약각0.20원. 환율2000원/USD·보호계수1.2·0.01원 올림의 내부 추정이며 실제 청구 환율/금액이 아니다. 토큰/model/tier 불일치는 비용0으로 변환하지 않고 거부한다. SDK 설치는 호출 성공 검증과 구분하며 제공자 어댑터/재시도0은 B04 이후 연결한다.

최종 B01 시험 결과는 Obsidain250.구현/04 일반 대화와 중앙 AI 구현 결과.md와260.테스트/evidence/B-chat/B01-*.json에서 관리한다. A06의176회 기록·A-auth 증거는 당시 결과로 보존하고 현재 suite에 중복 합산하지 않는다.
