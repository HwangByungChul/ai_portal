---
created: 2026-10-12
updated: 2026-10-12
status: mock-local-verified
scope: DP10-01
---
# DP10 Agent 카탈로그 My Agent 이용 권한 구현 결과

## 사용자 요청과 반영

사용자는 상세 계획을 Obsidian에 저장하고 다음 작업을 개발하도록 승인했다. [[27 DP10 Agent 카탈로그 My Agent 이용 권한 상세 작업 계획서]]를 구현 전에 저장한 뒤, 실제 DB·API·React 화면을 연결했다. 제품 명칭·사용자 A안 홈·관리 A안 홈과 B안 승인·검증 흐름, 포트 분리와 환경별 설정을 유지했다. 이번 결과는 실제 앱의 좁은 기능 단위이며 전체 명세 완료나 운영 배포를 뜻하지 않는다.

## 구현 동작

- 사용자 AI 카탈로그: 현재 조직에서 허가된 고정 운영 Agent의 검색·범주·페이지·설명·실행 상태를 제공한다. 초안·다른 조직·지시문은 노출하지 않는다.
- My Agent: 개인 즐겨찾기 추가·해제·재조회와 서버 재시작 후 보존. 권한 회수 시 숨기고 재허가 시 기존 선호를 다시 표시한다. 즐겨찾기는 권한을 부여하지 않는다.
- 관리 Agent 관리: 계정과 조직 소속이 모두 활성인 후보만 서버 페이지로 조회한다. 전체 활성 사용자 또는 선택한 활성 사용자 최대200명을 지정하고 변경 확인을 받는다. 정책 revision·CAS·요청 UUID 재확인·감사 기록을 저장한다.
- 실행 연결: 카탈로그에서 고른 고정 자산 UUID를 질문에 전달한다. Agent를 바꾸면 이전 자산 UUID를 함께 보내지 않는다. 새 요청·대화 생성·claim/reserve/dispatch/finish/stream에 현재 이용 권한을 적용한다.
- 요약 연결: 기존 요약은 rules_rag Agent에 속한다. 규정 검색 이용 대상 정책을 요약 제출·재시도·worker에 적용하고 관리자 화면에 이를 안내한다. 과거 본인 이력의 소유 접근과 문서의 현재 ACL은 별도로 유지한다.
- 저장 결과 불명확: 같은 UUID와 body로 재확인하고 입력을 잠근다.409는 최신 상태를 읽고 사용자가 새 변경을 선택한다. 조직/계정/페이지 전환 시 이전 응답과 개인 데이터를 폐기한다.

## 파일과 구조

실제 프로젝트 루트는 `/Users/jwpios/antigravity/202610_AI 플랫폼`이다. 해당 루트 기준 변경 파일 목록과 SHA256은 시험27의 안전 evidence `source-hashes.json`에 보존한다.

| 부분 | 실제 파일 |
| --- | --- |
| DB | src/backend/migrations/029_agent_catalog_access.sql |
| API | src/backend/app/catalog/__init__.py, repository.py, routes.py; app/main.py, errors.py, tenants/repository.py, ai/repository.py, operations/routes.py |
| 사용자 UI | src/frontend/src/CatalogPage.tsx, HomePage.tsx, ChatPage.tsx; apps/user-web/src/App.tsx |
| 관리자 UI | src/frontend/src/AgentAccessEditor.tsx, AgentSettingsPage.tsx |
| 공통·빌드 | src/frontend/packages/api-contract/src/types.ts, packages/ui/src/styles.css, src/styles.css, src/App.tsx, scripts/verify-portal-builds.mjs |
| 검증 | backend/tests/test_catalog.py, test_catalog_migration.py, support.py, test_migrations.py, test_run_assets_migration.py, test_b_schema.py, test_auth_restart.py, test_operations.py; scripts/portal_test_control.py; frontend/tests/catalog.spec.ts, safe-reporter.ts |

신규 표 agent_access / agent_favorites / catalog_mutations는 forced RLS와 제한된 RPC를 사용한다. 전체40표·migration30개·security 함수112개다. 조회할 때 기본 정책 행을 생성하지 않고 기존 사용자의 전체 허용을 유지한다. Agent 행의 공유/갱신 잠금으로 허가와 회수의 순서를 보장하며 외부 통신 중 DB transaction을 유지하지 않는다.

## 검증과 로컬 반영

- 서버는 관련 고유 **421건의 최신 결과가 모두 통과**했다. 여러 검사 결과를 사례별로 대사한 숫자이며 한 번의 전체 suite 성공으로 표현하지 않는다. 마지막 요약 관련120건과 최종 카탈로그·보존38건은 각각 모두 통과했다.
- 브라우저는 기존71건과 새 화면6건, 총 **77건의 최신 결과가 모두 통과**했다. 초기 실패와 보정 후 재검사를 구분해 시험27에 기록한다.
- 두 앱 타입·분리 빌드 통과: 사용자23모듈 / 관리자22모듈, 관리 기능의 사용자 번들 은닉 확인. 합성 계정의 데스크톱 카탈로그·관리 화면과390px 모바일을 실제 이미지로 확인했다.
- primary local: private600 백업 후 SQL029만 적용, 기존37표 전체 행과 prior29개 checksum 보존, 재적용 무변경. 현재40표·migration30개·security 함수112개.
- API8000·사용자5173·관리5174 복구, health·카탈로그/정책/My Agent 읽기와 자기 smoke 세션 logout 통과. 새 카탈로그 표는 읽기 점검 후에도0행이다. primary reset·모의 Agent/질문 생성·정책/즐겨찾기 변경·유료 호출0. 로그인/로그아웃은 인증·감사 기록을 정상적으로 변경하며 보존 대사는 이 smoke 전에 수행했다.


실패·보정 내역, 최신 사례별 결과와 보존 근거는 [[27 DP10 카탈로그 권한과 보존 검증 결과]]에 기록한다. 안전 증거만 Vault에 저장하고 인증 정보·DB dump·원시 로그·JUnit 실패 본문은 공유하지 않는다. Obsidian 파일 저장과 내용 대사는 수행하며 GUI 렌더링은 미검증이다.

## 미완료와 다음 순서

이번 카탈로그는 고정 운영 Agent 두 종류에 한정한다. 신규 초안의 일반 승인·게시·동적 실행, Model/Prompt/Tool/Workflow, 태그·랭킹·복제·구독·부서·기한·권한 신청 승인·계열사 공유는 후속이다. 원문 F 기능 또는 DP10 전체의 완료 판정은 변경하지 않는다. 거버넌스F050–060의 기존 제외와 PPTX/OCR 사용자 보류를 유지한다. Entra ID는 선정·테스트 환경 준비 예정 상태로, 실제 기관 연동과 운영 배포는 별도 미검증이다.

다음은 계획15의 순서에 따라 DP13 모델 Registry/Gateway 상세 계획이다. 이후 Builder·일반 자산 승인/게시와 연결해 동적 자산 카탈로그로 확장한다.
