# AI 플랫폼 backend — A01~03 인증 기반

전용환경/첫11개업무테이블/RLS·풀과실제로그인·본인세션확인·로그아웃이구현되어있다. 조직/관리API·화면·AI는후속이다. health200은 전체 플랫폼 완료를 뜻하지 않는다.

## 환경과 설치

확인 환경: macOS x86_64/Python3.13.2/PostgreSQL15.18(Homebrew). Node22.23.1은 A05에서사용한다. 전역 Node는변경하지않았으며Docker는필요없다.

프로젝트 루트에서 `cd src/backend`한뒤실행한다. `.venv`는이폴더안에두며직접9개/전이포함30개는hash lock으로고정했다. A02/A03의추가의존성은없다.

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

migrate는`ai_portal_mvp_test_<UUID>`의새시험DB/comment marker를생성한다. 000~003 SQL과SHA256 기록을단일transaction으로적용하고완료전에runtime접속을개방하지않는다. 반복CLI는기존설정을감지해거부한다. 재seed/비fixture/외부DB/변경된적용SQL도거부하며reset/drop CLI는제공하지않는다. 적용된migration은수정하지말고004이후새파일로추가한다. 시험용real예산행은실원장의reset허가가아니다.

이번A03에서는기존active fixture에003만추가적용했고계정/세션/창이나web DSN/HMAC은reset하지않았다. 이후pending migration도private active fixture의소유를검증한뒤같은runner로적용한다. 기존데이터가있는DB에는seed를다시호출하지않는다.

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

최종122개(A01~02회귀71+A03신규51)가통과했다. A01 도구스모크는별도55433임시클러스터, A02는소유55432의새접두/marker DB만시험후정리한다. 처음55432가정지였으면종료후정지로되돌린다. 기존설정fixture/실원장/5432는reset하지않는다. 각fixture는자기event loop와pool을함께닫아닫힌loop를재사용하지않는다.

실제ai_web자체접속에서권한속성/무문맥·잘못된문맥/본인·조직·관리자경계/복합FK·불변binding/현재권한회수/SQL권한·제어함수/풀정상·rollback·취소·동시분리/checksum·초기화원자성/비fixture·재seed거부를검증했다. A03에서는실제인증/CSRF/cookie/만료·회수/횟수·동시제한/DB실패·현재capability·세션발급감사rollback을추가검증했다. 조직관리API·브라우저·문서/Grant/Graph·실AI원장·전체V41/Q20은후속이다.

Starlette1.7.0 TestClient/httpx0.28.1 deprecation경고1개가있다. 경고를숨기거나httpx2를자동추가하지않았으며시험은통과했다. 상세결과는Obsidain `250.구현/02 인증과 테넌트 기반 구현 결과.md`,정제증거는 `260.테스트/evidence/A-auth/A03-*.json`에관리한다. A01/A02증거는이력으로보존한다.
