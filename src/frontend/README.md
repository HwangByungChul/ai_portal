# AI 통합 포털 frontend — I250-A05

실제 인증·조직 API에 연결된 로그인, 조직 선택 공통 헤더, 사용자 관리 화면이다. 사용자 역할/관리 범위는 서버가 판단한다. 대화 화면은 준비 상태이며 AI 대화·문서·GraphRAG는 후속 작업이다.

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

## 상태와 동작

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
