# AI 플랫폼 backend — A 및 B01~04 완료

A 인증·조직·관리 API/화면·통합 검증과 B01 저장 기반, B02 운영 API, B03 본인 대화·접수, B04 모의 AI 실행·원자 예약/단일발사/정산·SSE를 완료했다. 현재27 API/16업무·infra1/9 migration·46고정security함수다. backend467 pass/실패0/경고0, build 성공/기존A browser20 pass를 확인했다. 새 B 사용자·운영 화면은 B05, GraphRAG는 C, 실제 OpenAI 대표호출은 B06이다. 유료 AI0건/0원이며 실제 OpenAI 연결 성공으로 해석하지 않는다. health200은 전체 플랫폼 완료를 뜻하지 않는다.

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

migrate는`ai_portal_mvp_test_<UUID>`의새시험DB/comment marker를생성한다. 000~008 SQL과SHA256 기록을단일transaction으로적용하고완료전에runtime접속을개방하지않는다. 반복CLI는기존설정을감지해거부한다. 재seed/비fixture/외부DB/변경된적용SQL도거부하며reset/drop CLI는제공하지않는다. 적용된migration은수정하지말고008이후새파일로추가한다. 시험용real예산행은실원장의reset허가가아니다.

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

A06 당시176개(A04까지172+A06신규4)가통과했다. 현재 B01은238개(기존176+신규62)다. 기존A작업의각시험횟수는이력이며현재횟수에중복합산하지않는다. A01 도구스모크는별도55433임시클러스터, A02는소유55432의새접두/marker DB만시험후정리한다. 처음55432가정지였으면종료후정지로되돌린다. 기존설정fixture/실원장/5432는reset하지않는다. 각fixture는자기event loop와pool을함께닫아닫힌loop를재사용하지않는다.

실제ai_web자체접속에서권한속성/무문맥·잘못된문맥/본인·조직·관리자경계/복합FK·불변binding/현재권한회수/SQL권한·제어함수/풀정상·rollback·취소·동시분리/checksum·초기화원자성/비fixture·재seed거부를검증했다. A03에서는실제인증/CSRF/cookie/만료·회수/횟수·동시제한/DB실패·현재capability·세션발급감사rollback을추가검증했다. A04의관리API/현재회수/CAS·감사원자성/읽기창/권한잠금재검사도검증했다. 브라우저20개와실DB장애/재시작도A06에서통합검증했다. 문서/Grant/Graph·실AI원장·전체V41/Q20은후속이다.

A06 당시 Starlette1.7.0 TestClient/httpx0.28.1 deprecation경고1개가있었다. 당시에는 경고를숨기거나httpx2를추가하지않았다. B01에서 SDK필수httpx2 2.13.1이설치돼TestClient가이를사용하며현재전체238시험은경고0이다. 기존httpx0.28.1 pin은유지했다. 상세결과는Obsidain `250.구현/02 인증과 테넌트 기반 구현 결과.md`,정제증거는 `260.테스트/evidence/A-auth/A04-*.json`에관리한다. A01/A02/A03증거는이력으로보존한다.

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

A06 당시최종176pass/경고1,frontend build/실제브라우저20pass. 인증된GET /api/v1/me/tenants20회p95 5.766ms(목표300ms)/idle불변. A06 당시승인계획pool대기5초·startupwait5초/statement5초/lock2초였으며, B01에서공통pool2초·idletransaction5초로정합시켰다. 실AI/검색성능으로이국소측정을확대하지않는다.

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

프로젝트 `.runtime/tokenizer-cache`(0700)에 o200k_base/cl100k_base BPE 파일(0600)을 고정 SHA256로 검증해 저장한다. 런타임은 이를 읽기만 하고 누락·변조·symlink면 TOKENIZER_NOT_READY로 차단하며 자동 다운로드하지 않는다. 일반 입력은 질문4000 codepoint/UTF-8 16KiB·지침2000자·최근 완전 메시지6개·6000토큰을 검사한다. 초과 이력은 오래된 메시지 단위로 제외하고 지침/현재 질문은 자르지 않는다. Chat framing+32 여유 토큰은 보수 추정이며 실제 usage와 동일함을 보장하지 않는다. B03에서 POST 대화/질문/취소의 실제 HTTP body stream을 JSON 해석 전에 32KiB로 제한한다.

Decimal 고정 price-20261004-v1: 생성 예약3.64원, 질의/문서 임베딩 예약각0.20원. 환율2000원/USD·보호계수1.2·0.01원 올림의 내부 추정이며 실제 청구 환율/금액이 아니다. 토큰/model/tier 불일치는 비용0으로 변환하지 않고 거부한다. SDK 설치는 호출 성공 검증과 구분하며 제공자 어댑터/재시도0은 B04 이후 연결한다.

최종 B01 시험 결과는 Obsidain250.구현/04 일반 대화와 중앙 AI 구현 결과.md와260.테스트/evidence/B-chat/B01-*.json에서 관리한다. A06의176회 기록·A-auth 증거는 당시 결과로 보존하고 현재 suite에 중복 합산하지 않는다.

B01 당시 검증: backend238pass/경고0/208.77초,build/기존A browser20pass/runner error0/28.21초. 검증소스 로컬commit `189f95a76ca09862903320ab86b03f87caf069cd`;정확소스지문은B-chat/B01-test-summary.json에기록했다.

## B02 실제 운영 API — 화면 연결과 AI는 후속

기본 API는 기존A8개(health포함)+B02운영11개=19개다. 006의SECURITY DEFINER 함수5개를추가해전체21개이며owner는NOLOGIN ai_policy_executor/고정search_path/PUBLIC execute없음이다. operations_authorize/operations_row_allowed 2개는web에EXECUTE를주지않은내부함수,read_window/read/mutate만web이호출한다. parameter-bound 고정SQL만사용한다.

| 경로 | 현재 계약 |
|---|---|
| GET /api/v1/agents | 현재조직멤버의general/rules_rag 최소목록. 지침/모델/키/settings없음. enabled와실행준비를구분하며B02에서는두pipeline미연결로available=false/FEATURE_NOT_READY다. disabled/미준비budget/중지·한도차단은우선사유로반환한다. |
| GET·PATCH /api/v1/admin/agents/{agent_key} | 담당TADMIN/PADMIN만허용. PATCH는name≤80/description≤500/instructions≤2000 중1개이상+expected_revision. null/빈name·지침/추가model/key/tool/URL/권한field거부. GET만권한있는관리자에게지침을반환한다. |
| PUT /api/v1/admin/agents/{agent_key}/availability | strict enabled bool/양의expected_revision. rules_rag 설정을활성화해도실제RAG준비가되지는않는다. |
| GET /api/v1/usage/me | 본인+현재조직/period 기본10월. operation별실DBcall count,known_tokens/추정비용·예약/unknown분리. 타인/조직전체잔여·개인본문없음. |
| GET /api/v1/admin/usage | 담당조직만/cursor UUID/limit기본20·최대50/period. 최소call metadata/상태·추정비용·예약·known token/unknown. 개인질문/대화/initiator·provider ID/claim없음. |
| GET·PUT /api/v1/admin/budget | 담당조직배정/local cap·기발생비용·예약·blocked/revision. PUT는local_cap_krw 문자열/expected_revision만. local≤allocated/≤25000. 기존비용아래로local을낮춰도비용을지우지않고차단상태로남긴다. |
| GET /api/v1/platform/summary | active PADMIN+global_usage_read. current tenant불필요/metadata tenant=null. 프로젝트합산배정·승인30,000/운영25,000·추정/예약/unknown·enabled/revision만. |
| PUT /api/v1/platform/availability | active PADMIN+global_stop_write 독립권한. strict enabled/expected_revision. stop_latch가남은재개는409 REVIEW_REQUIRED,중지·재개는과거run재실행/비용삭제없음. |
| PUT /api/v1/platform/tenant-budgets/{tenant_id} | active PADMIN+명시관리소속/X-Tenant-ID=path. allocated_cap_krw 문자열/expected_revision. 합산≤프로젝트운영상한/예약·발생비용재배정금지. 배정축소는local cap도min으로낮춘다. global_usage_read/stop_write가조직배정권한을대체하지않는다. |

금액 입력은 `"12500"` 또는 `"12500.00"` 형식의양의또는0 decimal 문자열이다. JSON number/bool·음수/NaN/Infinity/지수표기/소수3자리/추가권한field는422다. 응답금액도문자열이며실제청구액이아닌내부추정이다. period는월첫날date, execution_mode는서버설정고정이며HTTP body/query로변경할수없다. 중복/미허용query도422,모든응답no-store다.

쓰기에는기존Origin/X-Requested-With/CSRF가필수다. actor·현재권한을잠금후재검사하고변경/revision/audit/성공session touch를한transaction에저장한다. stale revision409/범위를넘는배정409 BUDGET_LIMIT_CONFLICT,잠금/감사실패503·전체rollback. GET은idle을연장하지않는다. 조직read는A관리조회와동일HMAC user:tenant의DB120/min창을공유하고공통read는별도user:platform창이다. 재로그인으로초기화하지않는다.

web의agent_configs.settings 직접SELECT를제거하고안전열만유지했다. policy executor의추가권한은관리설정/비용metadata/허용열변경뿐이며message.body/run.config_snapshot/call.dispatch_claim_hash나원장직접INSERT/UPDATE/DELETE는없다. 조직예산·call·usage의executor RLS는고정함수가검증한현재scope만허용한다. 배정합계검사때만프로젝트행잠금아래다른조직의비콘텐츠예산을계산하며출력에넣지않는다.

시험용 A/B각12,500원·mock/real4개 조직예산과general/rules_rag 활성설정은새일회용Bfixture에만준비했다. 기존active fixture에는006만적용하며개인계정·세션·원장·app.env를보존한다. 미배정된조직예산은usage/budget503,Agent목록은BUDGET_NOT_READY(또는AGENT_DISABLED)로차단한다. real의기존accounted/reserved를새0으로덮어쓰거나bootstrap seed를반복하지않는다. 실제사용준비/초기배정은권한있는운영준비단계에서별도확인할사항이다.

B02결과·84신규시험(실제HTTP11경로/재시작1포함)·전체회귀는Obsidain250.구현/04 일반 대화와 중앙 AI 구현 결과.md와260.테스트/evidence/B-chat/B02-*.json에관리한다. 실제운영화면은B05,대화/run접수B03/AI예약·발사·정산/SSE는B04이며유료AI0원이다.

B02 당시 검증: backend 322 pass/경고 0/300.79초, build 성공/기존 A browser 20 pass/runner error 0/28.78초. 검증 소스 로컬 commit `aae2ace8cab56b3393bb9fafd89adde4caf1faf6`; 정확 소스 지문은 B-chat/B02-test-summary.json에 기록했다. 새 B 운영 화면과 실제 AI 호출은 후속 단계다.

## B03 대화·질문 접수와 취소 — 실행은 B04에서 연결

현재 A8+B02 11+B03 7=26개 API다. B03은 본인 질문과 accepted run을 저장한다. background worker나 모델 호출을 시작하지 않으며 결과·답변을 생성하지 않는다. Agent 목록의 pipeline 준비 상태도 아직 false다. 중간 단계에서 accepted가 지속되는 것은 실행 연결 전 상태이며 사용자가 취소할 수 있다.

| 경로 | 입력·응답 |
|---|---|
| POST /api/v1/conversations | agent_key=general, 선택 client_conversation_id UUID. 새 대화 201, 같은 owner/tenant/client ID·Agent 재전송 200. 다른 Agent 409. |
| GET /api/v1/conversations | 본인 현재 조직 목록, created_at+UUID 순서·recent_state, limit 기본20/최대50·서명 cursor. 타인 제목/본문·전체 count 없음. |
| GET /api/v1/conversations/{conversation_id}/messages | 현재 조직+본인만 질문/저장 완료된 답변/상태 조회. purged payload와 미완료 assistant는 숨김. 타인/타조직 ID 404. |
| POST /api/v1/runs | client_send_id UUID/agent_key/general/prompt/conversation_id(UUID 또는 null). 새·미종결 재전송 202, 종결 재전송 200. 다른 payload는 SEND_ID_CONFLICT 409. |
| GET /api/v1/runs/by-send/{client_send_id} | 응답 유실 시 같은 ID의 접수 여부와 현재 run 조회. 현재 조직+owner의 접수가 없으면 404. |
| GET /api/v1/runs/{run_id} | 현재 owner의 저장 state/stage/revision/content_status/usage_status/execution_mode/result 조회. snapshot/hash/지침·claim 없음. |
| POST /api/v1/runs/{run_id}/cancel | 양의 strict expected_revision. accepted/no call→cancelled 200, running→cancel_requested 202. 이미 종결/취소 접수는 저장 상태 유지. |

모든 경로는 기존 세션 쿠키와 단일 X-Tenant-ID가 필요하다. 쓰기는 Origin/X-Requested-With/CSRF를 함께 검사한다. role/user_id/model/API키/mode 입력은 허용하지 않는다. cursor는 HMAC으로 본인·조직·조회 종류·대화 ID에 묶으며 다른 문맥이나 변조는 422다. 재로그인해도 같은 본인·조직의 현재 권한이면 cursor 사용 가능하며 권한을 저장한 토큰으로 쓰지 않는다. cursor와 limit 외 추가·중복 query는 422다.

질문은 원래 공백·Unicode를 보존한다. 공백만/4000 codepoint 초과/잘못된 UTF-8 surrogate/NUL은 422, UTF-8 body는 최대16KiB다. 실제 POST JSON stream이 32KiB를 넘으면 Content-Length 유무와 무관하게 해석 전 413 PAYLOAD_TOO_LARGE로 차단한다. instructions+최근 허용된 완전 메시지 최대6개+질문은 오프라인 tokenizer로 6000token을 확인한다. 오래된 history는 메시지 전체를 제외하며 system/질문을 절단하지 않는다. 필수 입력 초과는 TOKEN_LIMIT_EXCEEDED 422, tokenizer cache 미준비는 SERVICE_UNAVAILABLE 503, 저장·provider 0이다.

RAG run이나 document_refs 필드가 명시된 요청은 FEATURE_NOT_READY 409다. 아직 문서 검색과 ACL이 없어 general로 자동 대체하지 않는다. existing conversation의 Agent가 다르면 CONVERSATION_AGENT_MISMATCH 409가 우선이다.

서버 SHA256 요청 hash는 원래 prompt/Agent/원래 conversation_id(처음 null 포함)/빈 document_refs를 정규 JSON으로 계산하며 session·HTTP request_id는 제외한다. 응답 유실/재전송은 원래 ID와 입력을 그대로 유지한다. 처음 null이었다면 재전송에서도 null을 유지하며 서버가 만든 conversation_id로 요청을 바꾸지 않는다. 같은 문장의 새로운 정상 전송은 새 UUID이고 별도 실행으로 저장되지만 미종결 한도는 검사한다.

identity→Agent→project→tenant→conversation/run 잠금 아래 현재 권한을 재검사한다. 원래 null 대화+accepted run+user message+safe audit+성공 idle touch+접수창은 동일 transaction으로 저장한다. 서로 다른 세션의 경합도 project lock 대기 뒤 기존 전송 ID를 다시 확인한다. 내부 capacity scope는 다른 run의 metadata COUNT만 하고 본문은 반환하지 않는다. 미종결 user1(조직 간 합산)/tenant2/project4는 서버 mode의 상태로 계산하고 신규 성공 접수만 user/tenant당10/min에 기록한다. 같은 ID 재전송은 새 한도·slot을 쓰지 않고, 현재 owner 접근이 유효하면 Agent/한도/공통 중지 후에도 원래 상태를 돌려준다.

접수 시 현재 조직 budget 준비/Agent enable/global stop/latch/local·project 최소 생성 예약액3.64 여유를 검사하지만 실제 예약금을 늘리지 않는다. B04는 dispatch 직전 다시 원자 허가·예약해야 한다. 이미 비용·예약이 있는 원장을 0으로 초기화하지 않는다. 기존 primary는 예산 미배정/Agent disabled를 보존했으며 새 접수는 안전하게 차단된다. A/B 각12500·Agent 활성과 동시성 확인용 임시 C는 일회용 시험 DB에만 존재한다.

취소는 owner 확인 후 CAS이며 accepted에 기존 call이 있으면 REVIEW_REQUIRED 409로 보존한다. 취소나 완료 상태만으로 비용을 0으로 만들지 않는다. run의 call이 reserved/dispatched면 estimated, usage_unknown이면 unknown, settled가 있으면 final, 미발사 해제만이면 none이다. 최종 usage는 실제 provider 토큰 확인을 뜻하며 청구 금액 확정은 아니다. 감사/잠금/DB 실패는 질문·run·대화·접수창·idle을 전체 rollback하고 503, 충돌은 안전한409다. 조회·재전송·반복 취소는 idle을 연장하지 않는다.

007은 고정 security 함수9개(전체30)를 추가한다. NOLOGIN policy executor의 필요한 messages/run snapshot SELECT는 owner-scope 고정 함수에만 적용한다. run_scope/추가 문맥은 transaction-local이며 pool 재사용 시 사라진다. 내부 sequence scope는 purged/미완료 메시지의 sequence_no만 계산해 중복 번호를 막는다. web의 request_hash/config_snapshot 직접 읽기와 messages/runs 직접 쓰기, index/meter의 콘텐츠와 새 함수 EXECUTE, 모든 원장 raw 쓰기는 계속 거부한다. helpers authorize/row_allowed/view는 web EXECUTE를 주지 않았다.

B03 시험·결과는 Obsidain250.구현/04 일반 대화와 중앙 AI 구현 결과.md의 B03 절,05 대화 접수 상세 작업 계획.md,260.테스트/evidence/B-chat/B03-*.json에 연결한다. B04 연결 전에는 accepted 접수·조회·취소 검증만 완료이며 AI 응답·SSE·새 화면·Graph/Q20 완료로 해석하지 않는다.

B03 현재 검증: backend 399 pass/경고 0/477.85초, build 성공/기존 A browser 20 pass/runner error 0/34.64초. 검증 소스 로컬 commit `40a28621652d91b04ee7eb613955db5b0bb813f5`; 정확 소스 지문은 B-chat/B03-test-summary.json에 기록했다. 새 B 운영 화면과 실제 AI 호출은 후속 단계다.


## B04 실행 활성화와 경계

기본값 `AI_EXECUTION_ENABLED=false`는 기존 접수 점검 환경을 보존한다. 실행 시 비공개 서버 설정에서 `AI_EXECUTION_ENABLED=true`, `AI_MODE=mock`, 별도 `AI_METER_DSN`을 공급한다. web은 ai_web, meter는 ai_meter 역할과 기존 전용 DB/55432/소유 표식을 확인한다. 공개 .env.example에는 DSN·키를 넣지 않는다. 현재 기본 DB는 Agent가 중지되어 있고 조직 예산이 미설정이다. 이번 단계에서는 기존 app.env나 예산을 변경·초기화하지 않았다. 새 시연 준비는 기존 사용·예약을 보존하는 방식으로 B05에 인계한다.

실행 관리자는 DB 세션 리더 잠금으로 한 프로세스만 허용한다. 기동 시 미종결 작업은 interrupted로 바꾸고 재호출하지 않는다. 종결 실패 run에 남은 호출도 미발사 증거가 있으면 해제하고, 발사됐으면 unknown으로 정리한다. 모의 예산과 실제 예산은 분리한다. TTL·취소·재시작으로 기발생 비용이나 종료 불명 슬롯을 풀지 않는다.

예약 3.64원/전체 슬롯2·조직1/허가10초, 실행 lease60초/heartbeat20초/총180초다. SDK는 실제 고정 endpoint·gpt-4o-mini/default/출력1024/include_usage/storeFalse/자동재시도0을 사용하고 전체 생성60초를 별도 적용한다. B04 시험은 가짜 HTTP만 사용했다. SDK3.24.0의 좁은 응답 검증 hook에서 숫자 자동 변환 전에 strict 검증한다. SDK 업그레이드 시 가짜 전송과 실제 B06 호환 검증을 다시 해야 한다. 실제 모드 키·meter·tokenizer 준비 누락은 차단하며 모의 모드로 자동 전환하지 않는다.

SSE `GET /api/v1/runs/{run_id}/events`는 현재 세션·X-Tenant-ID·Accept:text/event-stream이 필요하다. 조직/본인 조회를 재검사하고 매 본문 이벤트 직전에 권한을 새로 확인한다. snapshot/draft_delta/status/terminal/delivery_error,64KiB 초안/250ms batch/15초 keepalive,run1/user2 구독 제한이다. draft_delta는 bounded full draft의 replace 이벤트이며 sequence와 execution_epoch는 해당 구독/실행 세대에 적용한다. 재연결은 snapshot 조회이고 새로운 AI 호출을 만들지 않는다. 부분 응답이나 SSE 종료 자체는 저장 성공이 아니다.

실행 시험: `.venv/bin/python -m pytest tests/test_ai_ledger.py tests/test_ai_provider.py tests/test_execution.py tests/test_b_restart.py tests/test_b_http.py -q`. 원장 직접 쓰기·meter 본문 읽기·다른 사용자의 대화 접근은 계속 거부한다. 공개 증거는 B-chat/B04-*.json이다.
