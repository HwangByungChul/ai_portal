# AI 플랫폼 frontend — A05 및 B05 사용자·관리자 화면


실제 인증·조직·대화·운영 API에 연결된 로그인, 조직 선택, 본인 일반 대화, 사용자·Agent·사용량·플랫폼 운영 화면이다. 역할과 범위는 서버가 판단한다. 모의 화면51건과build를검증했고B06에서native실제일반3회/원장을확인했다. 실제모델을사용한브라우저시연자체는후속이며문서·GraphRAG는C작업이다.

## 설치와 실행

Node22.23.1은 기존 설치를 사용한다. 이 터미널에서만 선택하며 전역 기본값은 변경하지 않는다.

```bash
export PATH="$HOME/.nvm/versions/node/v22.23.1/bin:$PATH"
cd src/frontend
npm ci --no-audit --no-fund
npm run dev
```

backend/README.md의 순서대로 전용 DB와 실제 인증 API를 별도 터미널에서 실행한다. 포털은 http://127.0.0.1:5173, API는127.0.0.1:8000이며 Vite의 /api 프록시가 원래 Origin을 유지한다. 두 서버는 loopback 개발 환경이다. API의 local profile/CSRF 계약을 그대로 사용하고 별도 Gateway 제품은 없다. backend의 private app.env와 합성 비밀번호를 프론트 설정에 복사하지 않는다.

로그인 ID는 합성 액터 ID의 소문자(a-u1/a-adm/p-a 등), 비밀번호는 해당 active fixture의 backend/.runtime/fixture-secrets private 파일에서 확인한다. 공용 문서·명령 인수·공유 로그에 비밀번호/쿠키/CSRF를 넣지 않는다. 관리자는 조직 소속의 활성 상태·USER/TADMIN 역할만 변경하며 계정 전체 활성이나 PADMIN 부여는 하지 않는다.

## 인증 기반의 상태와 동작

- 새 탭/새로고침에서 현재 세션과 허용 조직을 조회한다. 조직이 여러 개면 직접 선택하고, 한 개면 조직명이 표시된 선택 상태로 연다. 조직0개는 별도 안내다.
- 현재 조직·CSRF·목록은 탭 메모리만 사용하며 localStorage/sessionStorage에 저장하지 않는다. 두 탭의 조직 선택은 독립이다.
- 조직 전환은 요청 취소·선택 세대 변경·이전 상태 정리 순서로 처리한다. 늦은 이전 조직 응답은 세대/주체/조직을 확인해 버린다. 요청 취소가 서버 변경을 되돌린다는 뜻은 아니다.
- 관리 API 응답의 tenant metadata도 현재 요청 조직과 일치해야 한다. 조회 실패는 과거 목록을 비우고 안전한 안내를 제공한다.
- 403에서는 현재 소속·권한을 다시 조회하고 관리 메뉴/목록을 정리한다. 409는 최신 목록을 조회한 뒤 직접 다시 변경하며 자동 저장 재시도는 없다.
- 초점/화면 복귀 시 현재 세션·권한을 재확인한다. 숨긴 탭의 반복 조회는 없고 GET은 서버 세션 활동 시각을 연장하지 않는다.
- 로그아웃 클릭 즉시 내용을 가린다. 서버 확정 뒤 세션을 정리하고 다른 탭에는 로그아웃 사실만 알린다. 503/통신 실패는 내용을 계속 가리고 확인 재시도를 제공한다.

## 빌드와 실제 브라우저 검증

```bash
npm run build
PLAYWRIGHT_SKIP_BROWSER_GC=1 npx playwright install chromium
npm run test:e2e -- tests/auth-tenants.spec.ts
```

Playwright는 scripts/portal_test_server.py로 자기 소유의 새 합성 DB/실제 API/Vite를 시작한다. 기존8000/5173이 사용 중이면 종료하지 않고 거부한다. tests/support.ts가 private 합성 비밀번호를 서버 쪽에서 읽으며 웹 번들에는 포함하지 않는다. portal_test_control.py는 private A05-config/소유 marker/PID/primary DB 배제를 확인한 시험 전용 조작만 수행한다. 제품 API에 장애·초기화 경로를 추가하지 않았다. 각 시험의 복원은 이 임시 DB에만 적용되며 실원장/기존 active fixture는 초기화하지 않는다.

종료 시 자식 서버/pool/해당 DB/합성 비밀번호 파일을 정리하고 원래 DB 상태를 복원한다. API와 Vite 환경은 분리되며 frontend 자식에게 AI/PG 자격을 넘기지 않는다. private 원문/정제 진단은 .runtime(0700/파일0600)/Git 제외다.

유일한 safe reporter는 public 결과에 정해진 시험 ID/status/duration만 기록하며 raw error/call log/본문/입출력/첨부를 저장하지 않는다. 실패 진단은 private 공간에서 비밀번호/비밀 형태 문자열을 치환한다. trace/video/자동 실패 screenshot은off다. 명시적 화면 캡처는 비밀번호와 ID가 비어 있는 로그인 화면만 수행한다.

최종 build와20개 실제 Chromium 시험 통과. 역할/활성 변경·403/만료/회수·409/503·로그아웃 재확인/두 탭/늦은 실제 A 응답·모바일·서버 cursor 페이지·비밀번호 fill 실패 정제를 확인했다. A04의172개 백엔드 회귀 결과는 과거 증거이며 A06에서 통합 재검증한다.

## 정확 버전과 근거

Node v22.23.1/npm 10.9.8, React/react-dom19.3.0, Vite8.3.2, plugin-react6.1.1, TypeScript7.0.2, @types/react·react-dom19.3.0, @types/node22.20.5, @playwright/test1.63.0. 직접9개와 전체73개 lock 항목(다른 플랫폼 optional 포함)을 package-lock v3/integrity로 고정했다. 이 기기 npm ci는30개를 설치했다. React compiler package/최적화는 도입하지 않았다.

공식 [Vite 환경 조건](https://vite.dev/guide/), [Playwright 설정](https://playwright.dev/docs/test-configuration), [React 효과 정리](https://react.dev/learn/synchronizing-with-effects), [npm React](https://registry.npmjs.org/react), [npm React plugin](https://registry.npmjs.org/@vitejs%2fplugin-react). 정확 버전은 설치 lock과실제build/browser 결과로 확인했다.

산출물: docs/Obsidain/200.프로젝트실행/250.구현/02 인증과 테넌트 기반 구현 결과.md 20~23절,260.테스트/evidence/A-auth/A05-*.json 및 빈 로그인 화면2장. A06/B/C·전체 플랫폼 완료는 후속이다.


## B05 대화와 운영 화면

/workspace: 본인 대화·Agent·질문·작성 중 초안·저장 확정 답변·취소. /usage: 본인 사용량. /admin/agents: 현재 관리 조직의 고정 Agent 설정·중지/재개. /admin/usage: 조직 최소 사용량·로컬 한도·관리 소속 PADMIN의 현재 조직 배정. /platform: 독립 플랫폼 조회/변경 capability. 기존 /admin/members를 유지한다. 문서·GraphRAG 검색은 준비 중이다.

일반 질문은 crypto.randomUUID 전송 식별자를 탭 메모리에 유지한다. 접수 응답을 잃으면 같은 ID GET으로 확인하고 실제404인 경우에만 같은 payload를 최대1회 재전송한다. 추가 불명은 조회만 하며 새 전송을 보류한다. 초안은 저장 미확정으로 표시하고 SSE terminal/EOF 후 현재 권한 GET으로 저장 답변을 확정한다. 이벤트는 조직/run/선택 세대/해제/epoch/sequence/64KiB 한도를 검증하고 초안 전체를 교체한다. 취소와 완료가 겹치는 동안 과거 revision 조회로 상태를 되돌리지 않는다. 숨긴 화면의 반복 조회를 중단하며 복귀 시 현재 세션과 저장 대화를 확인한다. GET 일시 실패 재시도는1초/3초 최대2회이며 변경 API는 자동 재시도하지 않는다.

Agent와 한도 변경은 서버 응답 후만 성공 표시한다. 409는 현재값을 다시 읽고 직접 재편집한다. 권한이 회수되면 본문/설정/비용과 해당 메뉴를 제거한다. 사용량의 unknown은 예약 유지/확인 필요로 표시하며 실제·모의 합계와 최종 공급자 청구액을 구분한다. 운영 화면에는 개인 대화 링크/본문/제목이 없다.

검증: backend477 pass, build pass, 기존A20+새B31=51 browser pass. 전체 화면 재현은 `npm run test:e2e -- tests/auth-tenants.spec.ts tests/chat-operations.spec.ts`. 테스트는 모의 제공자와 소유 확인된 폐기용 DB를 사용한다. 등록된 실제 키를 시험 API에 전달하지 않으며 trace/video/질문·답변 공개 캡처0다. 새 시각 점검 이미지는 합성 계정의 질문/본문/초안을 비운 화면만 private .runtime에0600으로 둔다. 기존 A05 로그인 PNG는 보존한다.

기본 A/B 환경은 B05에서 모의 시연을 준비했으므로 backend README의 시작 절차 후 이 화면을 사용할 수 있다. 현재 개발 서버는 정지 상태다. 실제 OpenAI는 B06 native3회를검증했으며real브라우저시연/GraphRAG는후속검증대상이다.

B06 현재전체결과는250.04 24~26절/260 B06 JSON이다. frontend소스는B05이후변경없으며최종build/A20+B31=51통과했다. 기본모의설정을유지한다.


## 개발 서비스 시작·종료 쉘 — 2026-10-11

이 폴더에서 `./start.sh`로 백그라운드 실행하고 `./stop.sh`로 종료한다. 스크립트가 실행한 PID·시각이 일치하는 프로세스만 종료하며 중복 실행과 포트 충돌을 확인한다. 로그는 `.runtime/service-control/service.log`에 기록한다. 기존 설치·설정이 필요하며 데이터 초기화나 패키지 설치는 수행하지 않는다.
Node22.23.1과 기존 node_modules를 사용한다. API는 별도 backend/start.sh로 먼저 실행한다.
전체 사용 안내: `docs/Obsidain/200.프로젝트실행/270.파일럿적용/01 개발 서비스 시작 및 종료 안내.md`.
