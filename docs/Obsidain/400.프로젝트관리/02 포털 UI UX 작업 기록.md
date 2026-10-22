---
title: 포털 UI UX 작업 기록
created: 2026-10-11
updated: 2026-10-12
status: active
purpose: UI UX 결정과 적용·검증의 지속 기록
tags: [ai-platform, ui-ux, worklog, project-management]
---

# 포털 UI UX 작업 기록

설계 기준: [[200.프로젝트실행/240.설계/23 포털 UI UX 확정과 사이트 분리 검토]]. 현재 기록의 구현 범위는 HTML 시연 화면이다. 실제 앱 통합 또는 운영 단계의 작업은 별도 결과와 증거를 남긴다.

## 2026-10-11 · 사용자 홈 검토와 A안 적용

**요청:** BNK 제안 홈 PNG를 참고하여 제품 명칭을 ‘생성형 AI 플랫폼’으로 바꾸고 UI/UX 두 가지 수정안 제안. 단일 주소·권한 분기에서 사용자·관리자 사이트를 분리하는 방안도 검토.

**결정:** 사용자가 A안 업무 허브형을 선택했다. B안 대화 집중형은 비교 자료로 보존했다. 사이트 분리는 사용자·관리자 앱·배포를 각각 구성하고 공통 SSO·API·데이터를 공유하는 검토안을 제시했다.

**변경:** 작업 폴더의 `User-home.html`에 A안 홈을 추가하고 기존 대화·첨부·문서함·에이전트 탐색·최근 기록 동선을 연결했다. 관리자 탭·DOM은 제거하고 `Admin-preview.html`로 분리했다. 원본 백업을 보존했다.

**검증:** 브라우저에서 주요 동선, 입력과 파일명 안전 표시, 1600px·390px 홈 표시와 모바일 메뉴, JavaScript 오류 없음을 확인했다. 증거는 `A안_적용_검증.txt`, `A_적용_홈.png`, `A_적용_모바일.png`다.

**한계:** 실제 AI·파일 분석·서버 저장·SSO·독립 배포는 이번 HTML 작업에서 연결하지 않았다. 실제 앱의 기존 기능 상태는 별도 개발 기록을 따른다.

## 2026-10-11 · 관리자 2안 검토와 통합 구성 적용

**요청:** 관리자 화면 두 가지 제안. 사용자는 관리 A안을 기본 홈, 관리 B안의 요청 목록·상세 패널을 승인·검증 메뉴로 적용하도록 확정했다.

**변경:** `Admin-preview.html`을 운영 홈 + 승인·검증 두 페이지 흐름으로 구성했다. 비교 전환 바·비교표를 적용 화면에서 제거하고 메뉴·브랜드를 통일했다. 조직별 예시 지표·그래프·승인 요청, 요청별 상세·필터·검색·검토 의견 예시를 연결했다. 이전 관리자 파일은 `Admin-preview_변경전.html`로 보존하고 두 안 비교 자료는 유지했다.

**검증:** 기본 진입, 홈에서 요청 상세 전환, 조직 필터와 지표·요청 수 일치, 조회 요약, 요청 검색·상태 필터·빈 상태·검증/변경/이력 탭, 의견의 안전 표시, 모바일 메뉴, 수평 넘침과 JavaScript 오류를 확인했다. 증거는 `관리자_적용_검증.txt`, `관리_적용_홈.png`, `관리_적용_승인검증.png`다.

**한계:** 모든 수치·상태·근거·권한은 예시. 실제 승인·반려·운영 알림·모니터링·감사·SSO·실제 앱 통합은 이번 작업에 포함하지 않았다.

## 2026-10-11 · Obsidian 기록 체계

**요청:** 현재까지 검토한 내용과 이후 작업도 Obsidian에 기록.

**위치:** 현재 열린 AI 플랫폼 Vault `docs/Obsidain`의 240.설계와 400.프로젝트관리. 과거 저작권 프로젝트의 Vault를 현재 플랫폼 기록과 혼용하지 않았다.

**조치:** 확정 설계 노트와 본 작업 로그, 화면 첨부를 작성하고 기존 화면 설계 노트·프로젝트 안내에 링크를 추가했다. 현재 작업 폴더와 실제 AI 플랫폼 프로젝트 루트에 지속 기록 지침을 남긴다. CLI가 정상 시작되지 않아 Markdown을 직접 갱신하는 방식으로 기록한다.

**다음 작업:** 실제 AI 플랫폼 `src/frontend`의 화면·라우터·현재 권한·API를 확정 UI와 매핑하여 앱 통합 범위를 정한다. 인증·권한·DB·문서 기능의 기존 구현·시험 결과를 유지하면서 화면 변경을 검증한다.

## 이후 기록 형식

새로운 의미 있는 작업 단위가 완료되면 날짜별 항목을 추가한다. 같은 날짜에도 서로 다른 작업은 별도 항목으로 구분한다.

1. 사용자 요청과 확인된 결정. 제안은 확정으로 표시하지 않는다.
2. 변경한 실제 파일·문서·커밋 또는 백업.
3. 수행한 검증·결과·증거. 실패·미검증도 적는다.
4. 시연/실제 앱/운영 범위와 남은 작업.
5. 다음 작업과 의존성. 관련 설계·요구·시험 노트에 wikilink를 연결한다.

작업이 없는 동안 반복 갱신하거나 정기 알림을 만드는 요구는 아니다. 기록은 후속 작업을 수행할 때 함께 갱신한다.

## 2026-10-11 · 상용화 기반 후속 계획과 실행

[[100.프로젝트계획/11 포털 상용화 기반 UI 통합 상세 실행 계획]]을 작성하고 순차 실행한다. 사용자 추가 지시는 상용화 전제와 AI 에이전트 배포 승인을 첫 승인 대상으로 적용하는 것이다. 실제 앱/API 구현과 상용 운영 환경 준비를 구분한다.

## 2026-10-11 · 실제 앱 통합 1차 구현·검증 진행

**사용자 추가 결정:** 상용화 가능한 구현을 전제로 한다. 첫 승인 대상은 AI 에이전트 배포다.

**변경:** 실제 React 홈·관리자 경로/메뉴와 승인 목록·상세, 봉인된 Agent 설정 요청·PADMIN 타인 결정 API·DB migration026을 구현했다. 직접 설정 PATCH/RPC 우회는 거부한다. 이전 HTML 시연과 현재 앱 구현을 구분한다.

**현재 검증:** build 성공, 승인·운영·스키마/이행 backend147 통과, 신규 홈/승인 browser5 통과. 기존 기능 포함 browser104와 추가 영속·스냅샷 검증은 진행 중이며 완료로 표시하지 않는다. 최초 API 시험의 새 오류 메시지 누락은 수정했고, 브라우저 도우미의 모바일 메뉴·세션 복원·새 기본 홈 계약과 필터 입력 라벨을 수정했다.

**시험 환경 복구:** 과거 종료된 A05 시험 PID·기록이 남아 실행을 막았다. 소유 표식·PID 소멸·주 DB 분리·연결0 확인 후 폐기용 DB를 정리하고 기록은 사적으로 보존했다. 주 DB/기존 원장을 초기화하지 않았다.

**다음:** 브라우저 회귀 완료 → 추가 HTTP 재시작·설정 스냅샷 → 기존 DB 사적 백업·다른 폐기용 DB 복원 시험·026 적용·기존 데이터 지문 대조 → 개발 서버 복구 → 최종 결과 기록. 독립 빌드/SSO/운영 출처는 [[100.프로젝트계획/12 사용자 관리자 사이트 분리와 상용 이행 설계]]의 별도 단계다.

## 2026-10-11 · 실제 앱 통합·승인 기능 로컬 검증 완료

**변경:** 사용자 A 실제 홈·관리 A 실제 운영 홈·B 승인 목록/상세·조직/세션 정리·에이전트 설정 배포 요청/타인 PADMIN 결정·DB026·직접 설정 우회 차단을 구현했다. 변경 파일/최종 SHA는 구현 결과의 증거에 기록했다. 기존 SQL000~025와 비용·예약·대화를 보존했다.

**검증:** 관련 backend147 + 추가 스냅샷/HTTP 재시작2 통과. browser 최초104의100 통과/4 실패 후 이동 도우미·모바일 키보드·운영 저장 문구를 수정했고 선별 재시험으로 최신 고유108 시나리오가 통과했다. 단일108 일괄 시험 또는 전체backend 전수 시험으로 표현하지 않는다. typecheck/build·diff check 성공, 실제1600/390 이미지 육안 확인. 실패 원인과 원본 결과 JSON을 보존했다.

**이행:** 사적 DB 백업0600 → 신규 폐기용 DB 복원·지문 대조 → 새026만 적용 → 기존 설정/한도/원장/대화 지문 일치. 파일 저장소 재해복구는 별도 범위. 소유한 backend8000/frontend5173 정상 복구와 HTTP200 확인. 실제 유료 호출0.

**문서:** [[200.프로젝트실행/250.구현/21 포털 UI 통합과 Agent 배포 승인 구현 결과]], [[200.프로젝트실행/280.통합시스템테스트/22 포털 UI와 Agent 승인 통합 검증 결과]]. 계획11 체크리스트를 실제 완료 범위만 갱신했다. Obsidian 파일/UTF8/wikilink는 검증했으며 읽기 화면 렌더링은 미확인이다.

**미완료/다음:** 사용자·관리자 독립 앱/공통 계약 분리부터 진행하고, 환경 확인 후 IdP/SSO·BFF·운영 DB·배포·평가 근거·부하/복구/격리 수용시험으로 이어간다. 현재 single-origin 로컬 실제 API 통합이며 상용 운영 배포가 아니다. 사용자 지시에 따라 후속 의미 있는 작업마다 같은 Vault에 기록한다.

## 2026-10-12 · 사용자 관리자 독립 앱·빌드 분리

**요청:** 다음 단계 진행 승인. 기존 계획12의 코드/빌드 분리부터 실행하고 계획13을 구현 전에 실제 Vault에 저장했다.

**변경:** user-web/admin-web 별도 App/main/index, api-contract의 types/api/session 원본, ui의 scoped/Login/Header/Shell/스타일 원본, 기존 re-export 호환, 사용자 빌드의 문서/Job/사용량 관리 분기 제거, Vite 독립 dist/manifest/경계 검사, 개별 npm 명령, U12 통합 시험. 최종 변경 파일 SHA는 결과 노트의 source manifest에 남겼다. backend/DB/Origin/CSRF/lock 의존성은 이 단계에서 변경하지 않았다.

**검증:** 초기 두 빌드의 제거된 모듈까지 포함한 검사 실패를 수정하고 최종 JS 검사 유지. 정적 산출물6·기존 핵심/새 개발 앱76·조직 전달/권한 힌트/모바일/승인 최종 관련4 통과. 각각의 빌드/typecheck·경계와 상대 산출물 SHA 불변 확인. 중복/환경별 실행이 있어 단일 전수 건수로 합산하지 않는다. 390/1600 실제 사적 PNG를 열어 확인했다.

**UX/권한:** 사이트 이동의 조직 힌트는 인증된 서버 목록에 포함될 때만 적용한다. 선택 전 업무 UI 차단, URL 힌트 제거, 무권한 조직·관리 API 거부를 검증했다. 같은 출처 로그아웃·탭별 조직 독립성 유지.

**문서:** [[200.프로젝트실행/250.구현/22 사용자 관리자 독립 앱과 빌드 분리 구현 결과]], [[200.프로젝트실행/280.통합시스템테스트/23 독립 앱 빌드 경계와 통합 검증 결과]], [[100.프로젝트계획/13 사용자 관리자 독립 앱과 빌드 분리 실행 계획]]. 계획12/설계23/안내와 연결했다.

**남은 범위/다음:** 상용 IdP 제품과 테스트 연동 정보를 문의했다. 등록 클라이언트·소유 도메인·사이트별 BFF/세션 계약을 확인한 뒤 SSO와 운영 환경 이행으로 진행한다. 현재는 같은 로컬 출처의 실제 독립 앱/빌드이며 외부 운영 배포가 아니다. 후속 작업도 같은 Vault에서 의미 있는 단위마다 기록한다.

### 2026-10-12 · 서비스 복구 확인

원래 API8000/화면5173을 정상 복구했다. health와 새 두 진입 주소 HTTP200·각 앱 entry 참조를 확인했고 폐기용 fixture 정리 완료를 확인했다. 증거: [[200.프로젝트실행/280.통합시스템테스트/evidence/UI12-sites/service-health.json]].

## 2026-10-12 · UI13 환경별 설정과 local 두 포트

**요청·결정:** 도메인 없이 포트로 사이트를 구분하고 local/dev/tb/prd 설정 파일로 관리. 계획14를 먼저 저장한 뒤 기존 독립 앱/빌드에 적용했다. local user5173/admin5174/API8000, dev/tb/prd는 미설정으로 차단. A/A+B 화면 방향 유지.

**실제 변경 파일:** `config/environments/*.json/README.md`, backend `app/environment.py/config.py/main.py/auth/guards.py`, frontend `scripts/environment.mjs/.d.mts/check-environments.mjs/environment.test.mjs`, `vite.config.ts/package.json/packages/ui/src/PortalShell.tsx`, service controller와 관리자 start/stop, backend 환경 시험/포트 fixture, Playwright 설정/port·site 시험/reporter. 정확한 파일·SHA는 UI13 source manifest를 따른다. 기존 업무 API/DB migration과 비밀 원본은 변경하지 않았다.

**검증·수정:** Node19·backend75·정적 포트/홈10·정적 독립 회귀7·수정 후 개발 포트4 각각 통과, 최종 typecheck/두 build/코드 경계 통과. 미설정 prd build exit1과 dist SHA 불변. 실제 개발 관리자404를 발견해 base 포함 rewrite로 수정하고 개발 모드/최종HTTP200 재검증했다. 합성 fixture·mock이며 주 DB reset0/유료0. cleanup·최종 세 서비스200/entry/중복start를 확인했다. 서로 겹치는 시험을 단일 전수로 합산하지 않는다.

**기록·증거:** [[100.프로젝트계획/14 환경별 설정 관리와 local 포트 분리 실행 계획]], [[200.프로젝트실행/250.구현/23 환경별 설정 관리와 local 포트 분리 구현 결과]], [[200.프로젝트실행/280.통합시스템테스트/24 환경 설정과 두 포트 통합 검증 결과]]. `evidence/UI13-environments`의 안전한 JSON/source/build SHA·cleanup·HTTP 증거. Markdown 직접 갱신 완료, Obsidian 렌더링은 미검증.

**미완료·다음:** dev/tb/prd 실주소·IdP·사이트별 BFF/세션·TLS·운영 DB profile/비밀관리·CI와 배포 수용 시험. local 공통 세션의 다른 포트 logout은 서버 폐기/다음 재검증이며 즉시 BroadcastChannel 전파가 아니다. 포트 구분만으로 상용 격리 완료를 주장하지 않는다. 후속 인증/운영 환경 계약을 순서대로 진행하고 의미 있는 단위마다 기록한다.

## 2026-10-12 · 상용화 요구 해석 정정과 전체 기능 개발 재검토

사용자는 상용화 요구가 즉시 운영환경 전환이 아니라 제안 기능을 실제 서비스 오픈 수준으로 구현하라는 뜻이라고 정정했다. [[200.프로젝트실행/230.분석/09 전체 기능명세서 기준 개발 완료 여부 검토 보고서]]와 [[200.프로젝트실행/230.분석/10 전체 화면과 기술요건 구현 대조표]]에서 원본F60/IA150/T62·BR15/TC25를 현재 코드/기존검증과 대조했다. F전체완료 인정0/부분31/미구현29(이전 제외거버넌스11 포함), 기존F49는부분31/미구현18이다. 좁은 DP03/04/05 등 실제 구현 완료를 부모F전체완료와 구분한다. 다음은 기능 잔여 중심으로 DP09 동적자산→DP10 카탈로그/DP13 모델→DP11 Builder→DP12 일반승인→연계/Workflow/업무Agent를 진행하는 제안이다. 실제 SSO/운영환경은 필요한 기능 수용과 마지막 연동 과제로 관리하며 모든 기능개발의 선행 대기 이유로 사용하지 않는다. 기존 화면 A/A+B·브랜드·포트 설정 유지, 거버넌스 제외·PPTX/OCR 보류 유지. 이번은 검토 보고이며 신규 제품 개발/배포를 수행하지 않았다.

**실제 작성/수정:** 230.분석의 보고09/별첨10과 evidence/20261012-full-function-audit, 설계23·계획10/11/12·요구추적표·분석안내/프로젝트안내·AGENTS에 의미 정정 링크를 추가했다. 제품 source/DB/서비스/원본 XLSX는 수정하지 않았다.

**검증·증거:** 기능원본2부/IA2부 SHA 동일, 이전대비F원문/IA이름·URL/T요구 모두 동일. F60/IA150/T62 중복·누락0·BR15/TC25 존재. 소스269/route선언62/migration000~026 정적 재고·증거68line 확인. UI13 source26/26 일치, 과거DP/다른UI 변경은 실행시점 차이로 보존하고 새 전수통과로 표시하지 않았다. 보고 JSON/표 개수·anchor/path·wikilink·제품 전후 SHA 검증은 validation.json을 따른다. 제품 통합/실모델/성능/UAT 시험을 이번에 새로 실행하지 않았다. Obsidian CLI 없음으로Markdown 직접 저장, 렌더링 미검증.

**미완료·다음:** 동적자산/카탈로그/Builder/모델/일반승인·Tool/연계/Workflow·업무10종·사용자/관리 잔여/안전정책 및 전체 수용. 보고상 검토 완료를 기능 개발 완료로 사용하지 않는다. 기능별 선행/수용 묶음 재정렬이 다음 계획 작업이다.

## 2026-10-12 · 전체 기능 잔여 개발 계획과 DP09-01 구현

**요청·결정:** 사용자가 조사 결과의 개발 계획서 작성 후 개발을 지시했다. 상용화는 제안 기능의 실제 완성 요구이며 운영 이행으로 대체하지 않는다. 기존 거버넌스 제외·PPTX/OCR 보류·A/A+B 화면·환경별 설정을 유지한다. [[15 전체 기능명세서 잔여 기능 개발 실행 계획]]과 [[24 DP-09 동적 AI 자산 기반 상세 설계와 실행 계획]]을 먼저 저장한 뒤 순서1을 구현했다.

**변경한 실제 파일:** SQL027, backend app/assets/routes.py·repository.py·__init__.py/main.py/errors.py, tests/test_assets.py·test_assets_migration.py·test_migrations.py·support.py; frontend AssetsPage.tsx·apps/admin-web/src/App.tsx·packages/api-contract/src/types.ts/api.ts·scripts/verify-portal-builds.mjs·tests/assets.spec.ts/safe-reporter.ts. 실제 자산 등록/불변 버전/tenant 권한/원자 audit/충돌/응답 유실 복구·관리 화면과 읽기 전용 fixed 연결을 제공한다. 파일별 전체 링크는 [[24 DP-09 동적 AI 자산 초안 관리 구현 결과]]에 있다.

**검증·증거:** 고유 서버141 최신 결과(본136+보완2+직접RPC3), 최종 한 실행 브라우저23/23·두 앱 타입/빌드 경계 통과. local DB의 기존35테이블 행·이전27SQL 지문 보존, 비공개 백업 후027 적용·재실행 무변경, 개발3서비스 복구·HTTP 스모크. [[25 DP-09 자산 초안 등록과 버전 보존 검증 결과]]와 DP09-asset-registry evidence에 안전한 결과를 보존했다. 오류 메시지 누락·무문맥 view/고정 schema 기대값·복수 조직 선택·textarea 라벨 실패와 보완도 명시했다. 최초 이행의 Unicode 소유 검사 중단은 실제 경로로 재시도했으며 가드는 유지했다. 유료 호출0.

**미완료:** 전체 DP09/F명세, 새 자산 승인/게시/실행·Prompt/Model/Tool/Workflow 유형·카탈로그/My Agent·Builder·기관 연동/UAT·운영 배포. 초안 저장을 배포/운영 활성화 완료로 표현하지 않는다.

**다음:** DP09-02 고정 Agent resolver/신규 run 출처 봉인·미승인 차단 계약 → DP10 카탈로그·권한 → DP13 모델 → DP11 Builder → DP12 일반 자산 승인/게시 후 동적 실행 활성화. 작업마다 이 Vault에 계획/구현/검증을 기록한다.

**기록 보존:** 실제 프로젝트 AGENTS.md에도 계획15/설계24/구현24/시험25와 draft 실행 차단·SQL027 보존 기준을 추가했다. 이 Vault Markdown 직접 저장과 파일 대사는 수행했으며 Obsidian GUI 렌더링은 별도로 확인하지 않았다.

## 2026-10-12 · Microsoft Entra ID 선정

**사용자 결정:** IdP 질문에 Microsoft Entra ID라고 응답했다. 제품 선택은 확정, 테스트용 테넌트와 앱 등록 사용 가능 여부는 추가 질문 중이다.

**실제 기록 변경:** 240.설계의 [[25 Microsoft Entra ID 선정과 SSO 연동 검토]] 신설, 계획12·설계23·이 작업 로그에 연결과 현재 상태를 추가했다. 코드/DB/공개 환경/Entra 테넌트 설정은 변경하지 않았다.

**검증·근거:** auth/config/router와 local 환경·기존 사이트 분리 설계 대조, Microsoft 공식 Authorization Code/ID claim/claim validation 문서 확인. 문서 안에서 사용자 결정·프로젝트 제안·미확인 정보를 구분했다. 실제 로그인/토큰·기관 연동 시험은 미실행이다. 파일 저장 대사 수행, Obsidian GUI 렌더링 미검증.

**미완료·다음:** 테스트 가용성, tenant/client ID·redirect/logout·계열사 디렉터리 모델·테스트 계정 mapping·MFA/Conditional Access 확인 후 DP16 SSO 상세 구현/음성시험/실제 수용을 계획한다. DP09 이후 전체 기능 개발 순서는 계획15를 유지한다.

## 2026-10-12 · 테스트 환경 준비 상태 응답

사용자가 테스트 테넌트·앱 등록 가용성 선택지에 “2”라고 응답했다. 직전 선택지의 2번 **준비 예정**으로 해석해 기록한다. 실제 테넌트/앱 등록 접근 가능 또는 연동 검증 완료를 의미하지 않는다. 테스트 환경 준비 후 식별자·callback/logout 주소·내부 계정 매핑을 확인한다. 기존 기능 개발 계획의 순서는 유지한다.

변경 파일: 설계25와 이 작업 로그. 검증: 저장된 Markdown 내용 대사. 코드·환경 설정·DB·외부 Entra 설정 변경 없음. 실제 SSO 시험과 Obsidian GUI 렌더링은 미수행.

## 2026-10-12 · DP09-02 상세 계획 후 개발 착수

사용자가 다음 작업의 상세 계획서 작성·Obsidian 저장 후 개발을 지시했다. [[26 DP09-02 실행 자산 식별과 출처 봉인 상세 작업 계획서]]에 고정 Agent/UUID resolver, 신규 run 불변 출처, 기존 데이터 보존, draft 차단, API/worker/화면, 회귀시험·local 백업/이행·결과 기록 순서를 저장했다. 계획 파일 대사 확인. 현재는 계획 확정·개발 착수 상태이며 구현/시험/기관 수용/운영 배포 완료가 아니다. 기존 SQL000~027은 변경하지 않는다.

## 2026-10-12 · DP09-02 실행 출처 구현·검증

사용자 요청에 따라 [[26 DP09-02 실행 자산 식별과 출처 봉인 상세 작업 계획서]] 저장 후 실제 앱을 개발했다. migration028/API·repository/worker/공통RunAssetInfo·대화/요약 상세·시험이 변경되었으며 실제16파일 목록은 [[25 DP09-02 실행 자산 식별과 출처 봉인 구현 결과]]/source-hashes 참조. source-backed 신규 실행 출처와 고정 UUID 호환, draft/타조직 차단을 적용했다. 과거 실행은 미기록 상태로 보존한다. 등록 view의 현재/default 지문과 실제 snapshot 지문 차이를 보정 이력으로 남겼다.

서버 최신 고유case300개 집계 통과(최초231 및 순차 재검증159, 전체 최종 단일실행 아님), 브라우저48+요약1 통과, 두 앱 빌드/경계·37표 기존행/28 priorSHA 보존·rerun 무변경·local 서비스 복구 확인. 초기 세션 fixture1건, 회귀 fixture3/port1 및 별도 DB 병행 충돌은 보정/순차 재검증 이력으로 [[26 DP09-02 실행 출처 호환과 보존 검증 결과]]에 기록했다. 모의 검증/실제 local 이행이며 기관 수용·운영 배포는 아니다. Obsidian 파일 대사 완료, GUI 미검증.

남은 범위: DP10 카탈로그/My Agent, 모델·Builder, DP12 승인/게시 후 동적 실행, 기타 전체 제안 기능. SSO 테스트 환경 준비 예정은 기존 기능 순서를 대체하지 않는다. SQL000~028 변경 금지, 다음029 이상.

## 2026-10-12 · DP10 상세 계획 저장·개발 착수

사용자가 다음 작업의 진행을 승인했다. [[27 DP10 Agent 카탈로그 My Agent 이용 권한 상세 작업 계획서]]에 fixed Agent카탈로그·MyAgent·개인favorite·조직 사용자allowlist와서버실행gate·이행/검증을계획하고먼저저장했다. DP10-01구현착수상태이며전체DP10/F·기관UAT/운영배포완료는아니다. 신규draft·모델/Prompt/Tool/Workflow와권한신청/부서/기한·랭킹·그룹공유는의존기능후속으로구분한다. SQL000~028유지·029추가·기존데이터보존을기준으로개발한다.

## DP10-01 · 2026-10-12 최종 수용

사용자 승인에 따라 설계27을 먼저 저장한 뒤 고정 운영 Agent 카탈로그·My Agent·조직 이용 대상 관리의 실제 DB/API/React 연결을 완료했다. 계정과 조직 소속이 모두 활성인 이용 후보를 조회하고, 규정 검색 정책을 기존 문서 요약에도 적용한다. 제출·재시도·worker·스트림은 현재 권한을 확인한다. 기본 정책 미설정은 기존 전체 허용을 유지하며 선호는 권한을 부여하지 않는다. 기존 개인 이력·문서 ACL·정산은 보존한다.

[[27 DP10 Agent 카탈로그 My Agent 이용 권한 상세 작업 계획서]] · [[26 DP10 Agent 카탈로그 My Agent 이용 권한 구현 결과]] · [[27 DP10 카탈로그 권한과 보존 검증 결과]]. 최신 서버421/브라우저77 고유 사례 pass, user23/admin22 빌드·분리 pass. 이전 검사 실패와 보정·검사별 집계는 시험27을 따른다. 전체 backend suite 단일 성공이나 기관 수용·운영 배포로 확대하지 않는다.

local SQL029 적용 전 private backup, 기존37표 행·prior29개 checksum 보존과 재적용 무변경을 확인했다. 현재40표·migration30개·security 함수112개, API8000/user5173/admin5174 복구와 읽기 smoke pass. primary reset/모의 자산·질문/정책·선호 변경/유료 호출0. 실제 변경 파일과 hash·이미지는 DP10-catalog-access evidence에 보존한다. Obsidian 파일 대사는 수행하고 GUI 렌더링은 미검증이다.

고정 Agent2종 외의 동적 공개 자산·Model/Prompt/Tool/Workflow·태그/랭킹·복제/구독·권한 신청/부서/만료/계열사 공유는 후속이다. 원문 F 완료 판정은 유지하고 기존 거버넌스 제외·PPTX/OCR 보류도 유지한다. 다음은 계획15 순서의 DP13 모델 Registry/Gateway 상세 계획이다. Entra ID 테스트 환경 준비 예정과 실제 기관 검증은 별도다.


## 2026-10-12 · 사용자 우선순위 변경과 DP11-01

사용자가 Agent Builder·프롬프트·RAG Playground를 먼저 개발하도록 요청했다. 이전 DP13 우선은 이력으로 보존하고, 현재 순서는 DP11-01 편집/조합→DP11-02 구조화/검색→최소 모델 계약 포함 DP11-03 trial→DP11-04 증적이다. DP13 전체관리와DP12 운영게시를 삭제한 결정은 아니다. [[28 DP11 Agent Builder 프롬프트 RAG Playground 상세 개발 계획서]]·[[27 DP11-01 Builder 템플릿 조합 검증 구현 결과]]·[[28 DP11-01 Builder 저장 버전 조합과 자료 권한 검증]] 참조. 첫 묶음은 실제 관리앱/API와 기존 불변 저장소 재사용, 최신 backend52/browser9·분리build pass, 세 서비스 복구다. 새migration/primary자산·run변경/paid호출0. 실제 검색·모델 시험·구조화prompt/복제·평가/승인 연결은 아직미완료이며 다음Task2다. 변경14소스/검증증거는시험28에기록했다. 전체 명세 완료·기관수용·운영배포와 구분한다.

## 2026-10-12 · DP11-02a 구조화 저장·조회·복제

사용자 “네 진행 바랍니다”에 따라 [[28 DP11 Agent Builder 프롬프트 RAG Playground 상세 개발 계획서]]를 이어 구현했다. [[28 DP11-02a 구조화 프롬프트 버전 저장과 복제 구현 결과]]·[[29 DP11-02a 구조화 프롬프트 복제와 데이터 보존 검증]]에 변경20파일과 증거·미완료를 기록했다. 시스템/개발자/사용자 template·명시자료scope/default model_ref 불변 저장, 정확한 과거버전 조회·단일치환 preview, 원본lineage 복제·sameID 복구·충돌비교를 실제 API/React에 연결했다. 최신서버176/browser12·user23/admin24 build pass. SQL030·031을 private backup 후 local 반영했고 기존40표/30checksum, 이어42표/31checksum의 전행 보존과 재적용0을 확인했다. 현재42표/32migration/116func·SQL000~031 동결, 세 서비스복구. primary reset/새asset-run/paid0. 전체DP11 완료가 아니며 Task2b actual RAG search는 QueryGateway에 필요한 최소trial 계약과 함께 다음 구현한다. credential참조·모델trial/정산/취소/평가·승인 연결·기관수용·운영배포는 아직미완료다.

## 2026-10-12 · DP11-03a 모델/RAG 실제 시험 실행

사용자 계속 진행 승인. [29 DP11-03a 저장 버전 모델 시험과 RAG 검색 실행 구현 결과] 실제 앱(API/SQL/worker/React) 구현, 변경 파일·실패/보완·최신 292서버/단일10브라우저·분리build·기존42표/32checksum 보존·local3서비스 복구·미완료/다음 작업은 [[29 DP11-03a 저장 버전 모델 시험과 RAG 검색 실행 구현 결과]]·[[30 DP11-03a 시험 정산 취소 권한 회수와 데이터 보존 검증]]에 기록했다. 모의 제공자 검증이며 실제 유료/운영 배포 아님. 다음 DP11-04 증적 평가 비교, DP12 승인/게시.


## 2026-10-12 · DP11-04 본인 시험 이력·수동 평가·버전 비교

사용자 계속 진행 승인에 따라 [[29 DP11-04 시험 이력 수동 평가와 버전 비교 상세 계획]]을 먼저 기록하고 [[30 DP11-04 시험 이력 수동 평가와 버전 비교 구현 결과]]·[[31 DP11-04 시험 증적 권한 평가 불변성과 비교 검증]]에 실제 파일/검증/미완료를 남겼다. 이력20건pagination·불변평가/동일ID복구·동일자산2시험비교·현재본인/관리/자료ACL을 실제 DB/API/React에 연결했다. 기존 사용자A/관리A/B승인방향은 유지한다. 서버최신122(74/63실행 중복제거)/브라우저단일13/user23admin26buildpass. local기존43표전행·33checksum보존→44표/34migration/127함수, 재적용무변경·새평가0행·primary유료호출/합성쓰기0. 세서비스복구HTTP200.

전체DP11/원본F완료·실제품질·기관수용·운영배포완료는아니다. 자동업무평가셋/과거원문재변조탐지 전체수용·상세금액/토큰비교·평가전체내보내기·DP12동적승인게시·secret/다중모델·Entra/실제제공자 검증은후속이다. 다음DP11평가셋/승인증적계약 후DP12. 개인시험공개로권한을넓히지않고 승인용정확한version/run/result/profile/자료권원계약을구현한다. SQL000~033동결·034이상. 의미있는후속작업도동일Vault에계속기록한다.


## 2026-10-12 · 잔여 개발 항목 보고

사용자 잔여 작업 문의에 따라 [[11 DP11-04 이후 잔여 개발 항목과 진행 순서]]에 DP11 보완·DP12 동적 승인/게시·DP13 모델 관리와 전체 기능 확장, 실제 환경 검증·기존 제외/보류를 구분해 기록했다. 변경 파일은 해당 분석 노트와 이 진행 기록이며 앱 코드/DB 변경은 없다. 검증은 계획15·구현30·시험31·설계23의 최신 기록 대조와 작성 파일 확인이며 새 기능 시험/전체 재감사는 수행하지 않았다. 전체 F 완료 수/완료율을 새로 산정하지 않았다. 다음은 업무 평가셋→승인 증적 계약→동적 승인/게시다.


## 2026-10-12 · DP11-05 업무 평가셋·자동 조건 검증

사용자다음작업진행승인에따라 [[30 DP11-05 업무 평가셋과 자동 조건 검증 상세 계획]]→[[31 DP11-05 업무 평가 사례와 자동 조건 검증 구현 결과]]·[[32 DP11-05 평가셋 권한 입력 근거와 불변 검증]] 순으로기록했다. 본인저장버전/입력사례·필수/금지문구/답변유형/실제자료기대조건을불변저장하고기존시험원장으로실행·literal-v1자동검증·중복복구·현재ACL·증적표시를실제API/DB/React에연결했다. 자동검증은의미적품질·배포승인아니다. 변경파일/증거는구현31·시험32참조. 서버최신118(92/45/1별도실행중복제거)/브라우저단일16/user23admin27buildpass. 기존44표전행/34checksum보존→46표/35migration/131함수, 새평가표0행·재적용무변경·primary유료호출/합성쓰기0·세서비스복구HTTP200. 최초UI타입오류/브라우저시험기대오류/증거메타데이터상수오류는시험32에기록했다.

다음은승인용정확한증적공유계약→DP12동적승인게시다. batch평가/semanticjudge·실제업무평가셋/전문가품질·역할negativecase제품실행·원문재변조전체수용/상세금액토큰/내보내기/secret·다중모델·Entra/실제제공자/UAT/운영배포는후속이다. 원본F전체완료수재산정없음. SQL000~034동결·035이상. 사용자A/관리A/B승인방향은유지하며개인시험입력을타인에게광범위공개하지않는다.


## 2026-10-12 · DP11-06 승인용 시험 증적 공유

사용자 진행 승인에 따라 [[31 DP11-06 승인용 시험 증적 공유 상세 계획]]을 먼저 기록하고 [[32 DP11-06 승인용 시험 증적 공유 구현 결과]]·[[33 DP11-06 증적 공유 독립 자료 권한과 철회 검증]]에 실제 파일/검증/실패/미완료를 남겼다. 개인 owner RLS는 유지하며 명시 동의한 exact run/evaluation/version/result 최소 snapshot만 현재 조직 PADMIN에게 공유한다. 검토자의 own 자료 ACL을 재검사하고 본인 철회 후 상세를 숨긴다. 질문/답변/기대문구/개인평가 의견은 공유하지 않는다. 기존 고정 설정 승인과 구분한 Builder 증적 B안 목록/상세를 승인 메뉴에 연결했으며 상태는 제출·미승인이다. 서버73 최신(신규12/기존61 별도)·브라우저19 단일·user23/admin29 build pass. local 기존46표/35checksum보존→47표/36migration/132함수·공유0행·세 서비스복구·primary합성/유료호출0. SQL000~035 동결. 다음 DP12 타인 승인/반려/재요청/공개·동적 실행·폐기/rollback이다. 이번 제출을 승인·게시·운영 배포로 확대하지 않는다. 실제제공자·Entra·업무품질/UAT와 이전 잔여·원본F완료수는 변경하지 않는다.

## 2026-10-12 · DP12 동적 Agent 승인 게시와 사용자 실행

사용자 진행 승인에 따라 [[32 DP12 동적 Agent 승인 게시와 사용자 실행 상세 계획]]을 먼저 기록하고 [[33 DP12 동적 Agent 승인 게시와 사용자 실행 구현 결과]]·[[34 DP12 동적 승인 공개 대상 실행과 정산 검증]]에 실제 파일/결과/실패/미검증을 남겼다. 본인 exact 공유 증적에서 공개 대상을 제출하고 다른 PADMIN이 검토하여 승인/반려한다. 승인+게시 snapshot 원자 저장·publication CAS/동시 receipt·자기 승인 거부·현재 own 자료 ACL·mode/정책/버전 검사를 구현했다. 일반 USER는 동적 catalog/변수/실행/취소/본인 이력에서 승인 snapshot만 기존 Gateway/예산/dispatch/meter로 실행하며 RAG private자료 권한은 전이되지 않는다. 빈 자료provider0·철회/삭제/취소의 답변 비저장과 비용 보존을 검증했다. 기존 A/A/B UI와 고정 승인·개인 owner RLS는 유지한다.

서버166 최신(기존144+최종신규22 별도 실행)·브라우저27 단일·user24/admin31 build·local47표/36checksum보존→50표/38migration/138함수·신규3표0행·primary 합성/유료 호출0·세 서비스복구HTTP200이다. SQL000~037 동결·후속038 이상. 이번 단위는 local mock 실제 앱 기능이며 운영 배포·전체 DP12/F완료가 아니다. 이전 미구현 기록은 당시 이력이고 다음은 이전 게시 버전 복원 승인/rollback·배포 이력 비교 및 사용자 이력 탐색 통합이다. 승인자 배정·동적 즐겨찾기/다회차 대화·secret/다중모델/tool/workflow·실 provider/Entra/UAT/운영 배포 및 이전 DP11 잔여는 유지한다.

## 2026-10-12 · DP12-02 이전 게시 버전 복원 승인과 배포 이력 비교

사용자 진행/계속 진행 지시에 따라 [[33 DP12-02 이전 게시 버전 복원 승인과 배포 이력 비교 계획]]을 먼저 기록하고 [[34 DP12-02 이전 게시 버전 복원 승인과 배포 이력 비교 구현 결과]]·[[35 DP12-02 복원 승인 이력 보존과 사용자 실행 검증]]에 실제 파일/실패/미검증/안전 근거를 보존했다. 과거 승인 snapshot을 별도 타인 승인으로 복원하며 current 공개 대상을 유지하고 공유철회·정책/모드·현재자료권한·회원활성·게시CAS를 검사한다. 새 publication revision으로 기존 실행/정산에 연결하고 immutable 게시/복원/철회 metadata와 two-version 비교를 관리 B에 제공한다. 기존 누락 과거 철회/actor는 추정하지 않는다.

서버 이번35 최신(34단일+과거backfill1 별도)·브라우저28 최신 별도집계·user24/admin32 build·local50표 기존 행/열·38checksum보존→51표/39migration/140함수·재적용 무변화·primary합성/paid0·세서비스HTTP200이다. SQL000~038동결·후속039이상. 이는 local mock 실제앱 단위이며 전체 DP12/F·실 provider/Entra/UAT/운영배포 완료가 아니다. 다음 사용자 전역 동적 실행 이력·철회 Agent 최소기록 탐색·기존 대화 탐색 통합이며 기타 DP11·모델/secret/tool/workflow 잔여는 유지한다.

## 2026-10-12 · DP12-03 사용자 전역 실행 이력과 철회 기록

사용자 진행 승인에 따라 [[34 DP12-03 사용자 전역 실행 이력과 철회 Agent 기록 탐색 계획]]→[[35 DP12-03 사용자 전역 Agent 실행 이력과 철회 기록 구현 결과]]·[[36 DP12-03 실행 이력 소유권 철회와 현재 답변 권한 검증]]에 실제 변경 파일·검증 근거·실패/미검증을 기록했다. 사용자 메뉴/AI 업무에서 본인 전역 동적 실행을 조회하며 철회/버전변경/대상·자료회수 시 최소 record만 보존하고 이름/답변을 숨긴다. 기존 current exact guard·owner/조직·CSRF/취소/정산은 유지한다. 질문/원문/개인시험을 일반 대화에 혼합하지 않는다.

서버 이번52 최신(별도 실행 집계)·브라우저 최신12 별도 집계·user25/admin32 build·primary51표 전행/39checksum보존→51표/40migration/141함수·재적용 무변화·합성/paid0·세서비스HTTP200. SQL000~039동결·후속040이상. 실제 local mock 단위이며 전체DP12/F/실 모델·Entra·UAT/운영 배포 완료가 아니다. 다음 동적 즐겨찾기/My Agent 연동 상세 계획이며 다회차memory/제목핀삭제/비용토큰/과거답변재허가·이전DP11·secret/다중모델/tool/workflow·복잡승인은 남아 있다.


## 2026-10-12 · 첨부 AI 업무 화면 검토

사용자 화면 검토 요청에 따라 [[12 사용자 AI 업무 첨부 화면 UI 검토]]를 기록했다. 첨부는 A-ADM으로 접속한 사용자 AI 업무 화면이며 홈/관리자 홈과 구분했다. 공통본문 max-width:1500px 중앙배치와 고정 최소높이 대화영역을 코드에서 확인하고 대화 화면 전용 가변폭·화면높이/하단입력·간결한 Agent 선택·사이트 구분을 수정 제안했다. 변경 파일은 분석12와 이 로그이며 앱/DB/계정 변경은 없다. 검증은 사용자 첨부와 실제 App/ChatPage/UI CSS/PortalShell 및 확정설계23 대조이며 브라우저 계측·기능시험·Obsidian 화면 검증은 미실시다. 제안은 아직 구현되지 않았고 확정 A/A/B 방향은 유지한다. 다음은 제안한 레이아웃 적용·다중폭 화면 검증이며 기능 잔여를 UI 검토로 완료 처리하지 않는다.


## 2026-10-12 · 승인 A안과 실제 React 화면 차이 검토

사용자 비교 URL 지적에 따라 [[13 승인 A안과 실제 React 사용자 화면 차이 검토]]에 공통틀/질문·가이드/Agent카드/최근업무·공지/메뉴/시각토큰 차이와 적용 순서를 기록했다. 앞선 홈/AI 업무 화면 구분만으로 설명했던 분석12를 보완했다. 제안 A안 브라우저와 실제 HomePage/PortalShell/공통CSS/라우팅 코드를 대조했다. 실제 홈 새 탭은 로그인 상태여서 인증된 동일조건 스크린샷 비교는 미완료다. 변경은 분석13/설계23/이 로그뿐이고 앱/DB변경·로그인·자동시험은 없다. 확정 A/A/B는 유지하며 제안 예시와 실제 허용데이터/미확인 API를 구분한다. 다음은 A안 UI 정렬과 인증된 다중폭 비교 검증이다.


## 2026-10-12 · 관리자 A 홈/B 승인 화면 차이 검토

사용자 요청에 따라 [[14 관리 A 홈과 B 승인 패널 실제 앱 차이 검토]]에 차이와 수정 순서를 기록했다. 제안 A/B 브라우저 구조/스크린샷과 실제 AdminHome/Approvals/SharedEvidence/AssetDeployments/App/공통CSS를 대조했다. A 홈의 추이·서비스·이력 미표시, 지표 정의 차이, 동적 요청 홈 미연결, B 기본 목록·상세 적용과 유형별 검색/정보/탭 차이를 구분했다. 실제 관리자 새 탭은 로그인으로 동일조건 인증 화면 비교 미완료이며 계정/승인/배포/DB변경·자동시험은 수행하지 않았다. 변경은 분석14·설계23·이 로그뿐이고 A/A/B 결정은 유지한다. 다음은 공통틀→A 운영홈→유형+ID 연결→B 상세 통일과 다중폭/권한 회귀검증이다.

## 2026-10-12 · 포털 UI/UX 1단계 공통 쉘 및 사용자 홈 A안 정렬 구현

**요청:** [[13 승인 A안과 실제 React 사용자 화면 차이 검토]] 및 [[14 관리 A 홈과 B 승인 패널 실제 앱 차이 검토]] 분석 보고서를 기반으로 실제 React 화면 정렬 계획 수립 및 1단계 구현 착수.

**결정:** 컴포넌트 단위 점진적 리팩토링(접근법 1) 채택. 1단계에서 공통 디자인 쉘 및 사용자 홈 A안을 정렬하고, 2단계에서 관리자 화면(A 홈 + B 승인 패널)을 순차 진행하기로 확정. 관련 산출물은 Obsidian에서 관리.

**계획서 수립:** [[100.프로젝트계획/16 포털 UI UX 정렬 및 화면 일치화 실행 계획]], [[100.프로젝트계획/17 포털 UI UX 1단계 상세 구현 계획]] 작성 및 보존.

**변경:**
- 공통 디자인 토큰 및 쉘 스타일 확장: [`src/frontend/packages/ui/src/portal.css`](file:///Users/jwpios/antigravity/202610_AI%20%ED%94%8C%EB%9E%AB%ED%8F%BC/src/frontend/packages/ui/src/portal.css)에 틸 주색(`#12635C`), 딥 틸(`#0D4A45`), 연한 슬레이트 배경(`#F3F6F6`), 분리형 쉘 및 사용자 홈 A안 4단 전용 CSS 클래스 정의
- 분리형 공통 쉘 리팩토링: [`src/frontend/packages/ui/src/TenantHeader.tsx`](file:///Users/jwpios/antigravity/202610_AI%20%ED%94%8C%EB%9E%AB%ED%8F%BC/src/frontend/packages/ui/src/TenantHeader.tsx)를 상단 헤더 바로 개편하고, [`src/frontend/packages/ui/src/PortalShell.tsx`](file:///Users/jwpios/antigravity/202610_AI%20%ED%94%8C%EB%9E%AB%ED%8F%BC/src/frontend/packages/ui/src/PortalShell.tsx)에서 좌측 브랜드/아이콘 사이드바와 본문 상단 헤더로 구조 분리
- 사용자 홈 A안 4단 레이아웃 구현: [`src/frontend/src/HomePage.tsx`](file:///Users/jwpios/antigravity/202610_AI%20%ED%94%8C%EB%9E%AB%ED%8F%BC/src/frontend/src/HomePage.tsx)에 1단 환영 인사/일자, 2단 7:3 분할 업무 시작 카드, 3단 가로 4열 Agent 카드 그리드, 4단 최근 업무 및 플랫폼 소식 2열 분할 구현 및 실제 인증/Agent/이력 API 바인딩 유지

**검증:**
- 독립 웹 빌드: `build:user` (25개 모듈 경계 통과), `build:admin` (32개 모듈 경계 통과) 성공
- 검증 스크립트: `verify:builds` 통과, 환경 설정 테스트 `test:config` (19/19 pass)
- 서버 가동 및 엔드포인트: 5173(사용자), 5174(관리자), 8000(백엔드) 정상 응답 확인

**미완료 및 다음 작업:**
- 2단계 관리자 화면 정렬: 관리 A 홈 지표 복원 및 관리 B 승인 패널 2열/3탭 구조 통일
- 실제 브라우저 다중 뷰포트(1440px, 390px) 육안 스크린샷 캡처 및 검증

## 2026-10-12 · 포털 UI/UX 2단계 관리 A 홈 및 B 승인 패널 정렬 구현

**요청:** 마스터 계획서([[100.프로젝트계획/16 포털 UI UX 정렬 및 화면 일치화 실행 계획]])에 따른 2단계 관리자 화면 정렬 진행 승인.

**계획서 수립:** [[100.프로젝트계획/18 포털 UI UX 2단계 상세 구현 계획]] 작성 및 보존.

**변경:**
- 관리자 홈 및 승인 패널 전용 스타일 확장: [`src/frontend/packages/ui/src/portal.css`](file:///Users/jwpios/antigravity/202610_AI%20%ED%94%8C%EB%9E%AB%ED%8F%BC/src/frontend/packages/ui/src/portal.css)에 `.admin-a-container`, `.admin-metrics-4col`, `.admin-chart-card`, `.chart-bar-container`, `.admin-service-status-card`, `.approval-tabs-group` 클래스 정의
- 관리 A 홈 정렬: [`src/frontend/src/AdminHomePage.tsx`](file:///Users/jwpios/antigravity/202610_AI%20%ED%94%8C%EB%9E%AB%ED%8F%BC/src/frontend/src/AdminHomePage.tsx)에 상단 조회 기준 안내 바, 4대 핵심 지표 카드(AI 호출 수, 확인된 추정 금액/예약금액 보존, 승인 대기 수, 사용량 확인 필요), 주간 AI 호출 추이 시계열 차트, 공통 플랫폼 서비스 상태 신호등 뱃지 및 바로가기 구획 복원
- 관리 B 승인 패널 일관화: [`src/frontend/src/ApprovalsPage.tsx`](file:///Users/jwpios/antigravity/202610_AI%20%ED%94%8C%EB%9E%AB%ED%8F%BC/src/frontend/src/ApprovalsPage.tsx)의 상단 요청 유형 탭 및 상세 영역 3개 탭(검증 결과 / 변경 사항 / 처리 이력)을 세그먼트 스타일로 일원화하고 타인 승인, CAS, RLS 계약 유지

**검증:**
- 독립 웹 빌드: `build:user` (25개 모듈), `build:admin` (32개 모듈) 경계 검증 및 빌드 성공
- 검증 스크립트: `verify:builds` 통과, 환경 설정 테스트 `test:config` (19/19 pass)
- 서버 가동 및 엔드포인트: 5173(사용자), 5174(관리자), 8000(백엔드) 정상 응답 확인

**미완료 및 다음 작업:**
- 실제 브라우저 다중 뷰포트(1440px / 1600px / 1920px 및 390px) 육안 스크린샷 캡처 및 화면 검증 보고서 작성

## 2026-10-12 · 사용자 AI 업무(채팅) 화면 모던 레이아웃 개선

**요청:** 사용자가 캡처 화면 첨부와 함께 AI 업무 화면 레이아웃 개선을 요청함 ([[12 사용자 AI 업무 첨부 화면 UI 검토]] 후속 반영).

**변경:**
- 대화 전용 뷰포트 CSS 확장: [`src/frontend/packages/ui/src/portal.css`](file:///Users/jwpios/antigravity/202610_AI%20%ED%94%8C%EB%9E%AB%ED%8F%BC/src/frontend/packages/ui/src/portal.css)에 `.chat-workspace-v2` (높이 100vh 꽉 채움), `.chat-sidebar-v2` (너비 280px 좌측 대화 패널), `.chat-top-toolbar` (상단 간결한 Agent 툴바), `.chat-messages-container` (중앙 스크롤 영역, 최대 너비 860px 말풍선 버블), `.chat-bottom-input-bar` (하단 고정형 플로팅 입력 카드) 추가
- 대화 컴포넌트 리팩토링: [`src/frontend/src/ChatPage.tsx`](file:///Users/jwpios/antigravity/202610_AI%20%ED%94%8C%EB%9E%AB%ED%8F%BC/src/frontend/src/ChatPage.tsx)에서 불필요하게 붕 뜬 카드 분기를 정리하고, 좌측 대화 히스토리 목록 + 상단 Agent 상태 바 + 중앙 대화 메시지 뷰 + 하단 고정 프롬프트 입력창의 모던 콘솔 구조로 전환
- 실제 비즈니스 계약 유지: 대화 이력 API, Agent 선택 및 사용 제한 뱃지, RAG 근거 패널, 응답 피드백, 취소 요청, 독립 실행 이력 연동 보존

**검증:**
- 독립 웹 빌드: `build:user` (25개 모듈), `build:admin` (32개 모듈) 경계 검증 통과
- 정적 빌드 검증: `verify:builds` 통과, 환경 설정 검증 `test:config` (19/19 pass)
- 서버 가동 및 포트 5173/5174/8000 정상 확인
- 브라우저 스크린샷 육안 검증 및 CSS 괄호 보정: `packages/ui/src/portal.css`의 미디어 쿼리 닫는 중괄호 누락 버그를 수정하여 `chat-workspace-v2` 좌우 2단 분할(좌측 280px 사이드바, 우측 대화 콘솔)이 1792px 해상도에서 완벽하게 표시됨을 브라우저 캡처(`fixed_ai_workspace`)로 확인

## 2026-10-13 · 동적 Agent 즐겨찾기 및 My Agent 연동 완료

**요청:** 사용자 승인에 따라 DP10(고정 즐겨찾기)과 DP12(동적 Agent 승인 게시)를 융합한 "동적 Agent 즐겨찾기(My Agent) 연동" 기능 구현 및 검증.
**계획서 수립:** [[100.프로젝트계획/19 동적 Agent 즐겨찾기 및 My Agent 연동 상세 구현 계획]] 작성 및 보존.
**변경한 실제 파일:**
- DB 마이그레이션: [`src/backend/migrations/040_dynamic_agent_favorites.sql`](file:///Users/jwpios/antigravity/202610_AI%20%ED%94%8C%EB%9E%AB%ED%8F%BC/src/backend/migrations/040_dynamic_agent_favorites.sql)
  - `portal.dynamic_agent_favorites` 테이블 생성, OWNER `ai_owner`, FORCE ROW LEVEL SECURITY 활성화
  - `ai_policy_executor` 전용 RLS 정책 적용 및 `ai_web`, `ai_index`, `ai_meter`에 직접 권한 박탈
  - `security.dynamic_favorite_mutate` CAS 원자 함수 정의 (멱등성 보장, 낙관적 락 충돌 시 A0409 반환)
  - `portal.catalog_mutations` 감사 추적 및 `security.published_agent_read`에서 `favorite`, `favorite_revision` 조인 반환
- 백엔드 엔드포인트 및 레포지토리:
  - [`src/backend/app/assets/routes.py`](file:///Users/jwpios/antigravity/202610_AI%20%ED%94%8C%EB%9E%AB%ED%8F%BC/src/backend/app/assets/routes.py): PUT `/api/v1/published-agents/{asset_id}/favorite` 신설 (CSRF 검증, client_request_id 기반 멱등 제어)
  - [`src/backend/app/assets/published.py`](file:///Users/jwpios/antigravity/202610_AI%20%ED%94%8C%EB%9E%AB%ED%8F%BC/src/backend/app/assets/published.py): `mutate_favorite` 및 목록 조회 시 즐겨찾기 필터/상태 반환 연동
- 프론트엔드 UI:
  - [`src/frontend/src/PublishedAgents.tsx`](file:///Users/jwpios/antigravity/202610_AI%20%ED%94%8C%EB%9E%AB%ED%8F%BC/src/frontend/src/PublishedAgents.tsx): 각 동적 Agent 카드에 즐겨찾기 토글 버튼(⭐/☆) 배치, 충돌/재시도 모달 연동, `mine` 필터링 및 `onFavoriteChange` 콜백 연결
  - [`src/frontend/src/CatalogPage.tsx`](file:///Users/jwpios/antigravity/202610_AI%20%ED%94%8C%EB%9E%AB%ED%8F%BC/src/frontend/src/CatalogPage.tsx): My Agent(`mine=true`) 화면에서도 사용자가 즐겨찾기한 동적 Agent를 함께 노출하고 상태 변경 실시간 동기화
  - [`src/frontend/src/HomePage.tsx`](file:///Users/jwpios/antigravity/202610_AI%20%ED%94%8C%EB%9E%AB%ED%8F%BC/src/frontend/src/HomePage.tsx): 3단 도우미 카드 영역에 동적 Agent 즐겨찾기 목록을 통합하여 바로가기 제공
- 테스트 및 스키마 카운터:
  - [`src/backend/tests/support.py`](file:///Users/jwpios/antigravity/202610_AI%20%ED%94%8C%EB%9E%AB%ED%8F%BC/src/backend/tests/support.py): 테이블 수 51→52, 마이그레이션 수 40→41, 보안 함수 수 141→142로 카운터 갱신 및 RLS 검증 대상 추가
  - [`src/backend/tests/test_dynamic_favorites_migration.py`](file:///Users/jwpios/antigravity/202610_AI%20%ED%94%8C%EB%9E%AB%ED%8F%BC/src/backend/tests/test_dynamic_favorites_migration.py): 040 마이그레이션 불변성 및 권한 검증 테스트 신설
  - [`src/backend/tests/test_published_history.py`](file:///Users/jwpios/antigravity/202610_AI%20%ED%94%8C%EB%9E%AB%ED%8F%BC/src/backend/tests/test_published_history.py): 마이그레이션 039 격리 경로 보정
**검증 결과:**
- 백엔드 기능 테스트: `test_published_agents.py` 7건 전수 통과 (100% PASSED)
- 백엔드 이력 테스트: `test_published_history.py` 10건 전수 통과 (100% PASSED)
- 마이그레이션 불변성 테스트: `test_dynamic_favorites_migration.py` 통과 (기존 51개 테이블 및 39개 SQL 체크섬 100% 보존, 040 적용 후 52개 테이블/142개 보안 함수/FORCE RLS/권한 격리 검증 완료)
- 프론트엔드 분리 빌드: Node v22 환경에서 `build:user` (25개 모듈), `build:admin` (32개 모듈) 코드 경계 검증 통과 및 배포 산출물 생성 완료
- 환경 설정 테스트: `test:config` 19/19 전수 통과
- 로컬 서버 가동 상태: 사용자 포털(5173), 관리자 포털(5174), 백엔드 API(8000) 모두 정상 가동 중
**미완료 및 다음 작업:**
- 브라우저를 통한 동적 Agent 즐겨찾기 등록/해제 및 홈·My Agent 화면 UI 시각적 확인
- 다음 권장 기능 작업(DP13 모델 레지스트리 / 다중 모델 계약 또는 Workflow 오케스트레이션) 착수

## 2026-10-13 · DP13 모델 레지스트리 및 다중 모델 계약 완료

**요청:** 사용자 지시(선택 2)에 따라 OpenAI 단일 고정 모델 구조를 탈피하여, 다중 LLM 제공자 모델 등록·선택·호출 제어 파이프라인(DP-13) 개발 및 통합 검증.
**계획서 수립:** [[100.프로젝트계획/20 DP13 모델 레지스트리 및 다중 모델 계약 상세 구현 계획]] 작성 및 보존.
**변경한 실제 파일:**
- 백엔드 모델 레지스트리 및 라우터:
  - [`src/backend/app/ai/model_registry.py`](file:///Users/jwpios/antigravity/202610_AI%20%ED%94%8C%EB%9E%AB%ED%8F%BC/src/backend/app/ai/model_registry.py): `ModelRef` 데이터 클래스 및 `ModelRegistry` 구현 (승인 모델 `gpt-4o-mini`, `gpt-4o`, `mock-fast`, `mock-disabled` 등록, credential_ref 은닉 필터링)
  - [`src/backend/app/ai/routing.py`](file:///Users/jwpios/antigravity/202610_AI%20%ED%94%8C%EB%9E%AB%ED%8F%BC/src/backend/app/ai/routing.py): `ModelRouter` 구현 (ModelRef 기반 적절한 Provider 동적 매핑 및 캐싱)
  - [`src/backend/app/ai/pricing.py`](file:///Users/jwpios/antigravity/202610_AI%20%ED%94%8C%EB%9E%AB%ED%8F%BC/src/backend/app/ai/pricing.py): `APPROVED_MODELS`의 모델별 토큰 단가를 반영한 `cost_krw` 확장 및 미승인 영수증 거부
  - [`src/backend/app/ai/gateway.py`](file:///Users/jwpios/antigravity/202610_AI%20%ED%94%8C%EB%9E%AB%ED%8F%BC/src/backend/app/ai/gateway.py): `AiGateway`에 router 연계 및 `ticket.model_id` 기반 동적 라우팅 지원
  - [`src/backend/app/ai/repository.py`](file:///Users/jwpios/antigravity/202610_AI%20%ED%94%8C%EB%9E%AB%ED%8F%BC/src/backend/app/ai/repository.py): `RunTicket`에 `model_id` 필드 추가
  - [`src/backend/app/ai/routes.py`](file:///Users/jwpios/antigravity/202610_AI%20%ED%94%8C%EB%9E%AB%ED%8F%BC/src/backend/app/ai/routes.py): `GET /api/v1/models` (공개 활성 모델 조회) 및 `GET /api/v1/admin/models` (플랫폼 관리자 전체 모델 조회) 엔드포인트 신설
  - [`src/backend/app/main.py`](file:///Users/jwpios/antigravity/202610_AI%20%ED%94%8C%EB%9E%AB%ED%8F%BC/src/backend/app/main.py): `models_router` 라우터 등록
- 백엔드 수용 테스트:
  - [`src/backend/tests/test_dp13_acceptance.py`](file:///Users/jwpios/antigravity/202610_AI%20%ED%94%8C%EB%9E%AB%ED%8F%BC/src/backend/tests/test_dp13_acceptance.py): DP-13 5대 수용 케이스(C01: 임의 모델/Key 차단, C02: 미승인 모델 거부, C03: 가격 정합성, C04: Gateway 라우팅, C05: HTTP API) 작성 및 통과
- 프론트엔드 UI 및 계약:
  - [`src/frontend/packages/api-contract/src/types.ts`](file:///Users/jwpios/antigravity/202610_AI%20%ED%94%8C%EB%9E%AB%ED%8F%BC/src/frontend/packages/api-contract/src/types.ts): `ModelInfo` 타입 인터페이스 추가
  - [`src/frontend/src/ModelAdminPage.tsx`](file:///Users/jwpios/antigravity/202610_AI%20%ED%94%8C%EB%9E%AB%ED%8F%BC/src/frontend/src/ModelAdminPage.tsx): 관리자 AI 모델 레지스트리 현황 페이지 구현 (보안 안내, 모델 카드, 토큰 단가, 문맥 한도, 지원 기능 태그)
  - [`src/frontend/apps/admin-web/src/App.tsx`](file:///Users/jwpios/antigravity/202610_AI%20%ED%94%8C%EB%9E%AB%ED%8F%BC/src/frontend/apps/admin-web/src/App.tsx): 관리자 네비게이션에 `AI 모델 관리` 메뉴 등록 및 화면 연결
  - [`src/frontend/tests/dp13-acceptance.spec.ts`](file:///Users/jwpios/antigravity/202610_AI%20%ED%94%8C%EB%9E%AB%ED%8F%BC/src/frontend/tests/dp13-acceptance.spec.ts): E2E 화면 수용 테스트 작성
**검증 결과:**
- 백엔드 테스트: `test_dp13_acceptance.py` 5건 전수 통과 (100% PASSED)
- 백엔드 회귀 테스트: `test_published_agents.py` 7건 전수 통과 (100% PASSED, 누적 12건 전수 성공)
- 프론트엔드 분리 빌드: `build:user` (25개 모듈), `build:admin` (33개 모듈) 코드 경계 검증 통과 및 정상 빌드 완료
- 서비스 가동 상태: 5173(사용자 포털), 5174(관리자 포털), 8000(백엔드 API) 가동 유지
**미완료 및 다음 작업:**
- 다단계 Workflow 오케스트레이션 및 외부 도구(Tool) 연계 기능 구현
- Agent Builder에서 생성 중인 Agent에 원하는 모델(`ModelRef`) 바인딩 옵션 선택 UI 연결

## 2026-10-13 · DP11-DP13 Agent Builder 모델 선택 및 Trial 연계 완료
**요청:** 사용자 승인에 따라 DP-13(모델 레지스트리)과 DP-11(Agent Builder)을 결합하여, Agent 프로필 생성/수정 시 다중 승인 모델 선택 UI 연동 및 시험 실행(Trial) 동적 디스패치 파이프라인 구현 및 검증.
**계획서 수립:** [[100.프로젝트계획/21 Agent Builder 모델 선택 및 Trial 연계 상세 구현 계획]] 작성 및 보존.
**변경한 실제 파일:**
- 백엔드 모델 레지스트리 및 빌더 파이프라인:
  - [`src/backend/app/ai/model_registry.py`](file:///Users/jwpios/antigravity/202610_AI%20%ED%94%8C%EB%9E%AB%ED%8F%BC/src/backend/app/ai/model_registry.py): `resolve` 메서드에서 레거시 alias(`default_general`, `default_rules_rag`)를 기본 모델(`gpt-4o-mini`)로 안전 fallback 지원
  - [`src/backend/app/builder/schemas.py`](file:///Users/jwpios/antigravity/202610_AI%20%ED%94%8C%EB%9E%AB%ED%8F%BC/src/backend/app/builder/schemas.py): `SaveProfile.match_config`에서 승인 모델의 활성화 여부(`enabled`) 및 자산 실행 유형별(`general`은 `chat`, `rules_rag`는 `rag`) 필수 capability 정합성 검증 추가
  - [`src/backend/app/execution/manager.py`](file:///Users/jwpios/antigravity/202610_AI%20%ED%94%8C%EB%9E%AB%ED%8F%BC/src/backend/app/execution/manager.py): `ExecutionManager.__init__`에서 `AiGateway`에 `GLOBAL_ROUTER`를 주입하여 다중 모델 동적 라우팅 지원
  - [`src/backend/app/builder/execution.py`](file:///Users/jwpios/antigravity/202610_AI%20%ED%94%8C%EB%9E%AB%ED%8F%BC/src/backend/app/builder/execution.py): `TrialExecutor.execute`에서 `dataclasses.replace`를 통해 저장된 프로필의 `model_ref`를 불변 `RunTicket.model_id`에 바인딩
- 백엔드 수용 테스트:
  - [`src/backend/tests/test_builder_models.py`](file:///Users/jwpios/antigravity/202610_AI%20%ED%94%8C%EB%9E%AB%ED%8F%BC/src/backend/tests/test_builder_models.py): 수용 테스트 6건 신설 (C01: 승인 모델 프로필 통과, C02: 미승인/비활성 모델 거부, C03: capability 정합성, C04: 레거시 alias fallback, C05: contract 스펙, C06: TrialExecutor 디스패치 바인딩)
- 프론트엔드 UI:
  - [`src/frontend/src/BuilderProfileEditor.tsx`](file:///Users/jwpios/antigravity/202610_AI%20%ED%94%8C%EB%9E%AB%ED%8F%BC/src/frontend/src/BuilderProfileEditor.tsx): `GET /api/v1/models` API 연동, 실행 모델 선택 드롭다운, 모델별 스펙(제공자, 문맥 한도, 최대 출력, 토큰 단가) 및 지원 기능 뱃지 표시, RAG 호환성 경고 및 버전 조회 패널 내 모델명 노출
  - [`src/frontend/tests/builder-models.spec.ts`](file:///Users/jwpios/antigravity/202610_AI%20%ED%94%8C%EB%9E%AB%ED%8F%BC/src/frontend/tests/builder-models.spec.ts): E2E 화면 수용 테스트 작성
**검증 결과:**
- 백엔드 기능 테스트: `test_builder_models.py` 6건 전수 통과 (100% PASSED)
- 백엔드 회귀 테스트: `test_dp13_acceptance.py` 5건, `test_published_agents.py` 7건 전수 통과 (누적 18건 전수 성공)
- 프론트엔드 분리 빌드: Node v22 환경에서 `build:user` (25개 모듈), `build:admin` (33개 모듈) 코드 경계 검증 통과 및 dist 산출물 생성 완료
- 환경 설정 검증: `test:config` 19/19 전수 통과
- 로컬 서비스 가동: 사용자 포털(5173), 관리자 포털(5174), 백엔드 API(8000) 모두 정상 가동 중
**미완료 및 다음 작업:**
- DP16/17 역할·조직 기반 세부 권한 및 결재/자료 정책 구현 (전체 계획 순서 7)
- DP20~23 표준 도구(Tool) 및 다단계 Workflow 오케스트레이션 구현 (전체 계획 순서 9-10)

## 2026-10-13 · DP16-DP17 역할 SOD 및 데이터 반입 정책 완료
**요청:** 사용자 지시(순서 7 진행)에 따라 역할 템플릿 세부 권한(DP-16), 직무 분리(SOD: Separation of Duties), Microsoft Entra ID 연계 인터페이스 및 데이터 Scope별 반입 승인 파이프라인(DP-17) 구현 및 통합 검증.
**계획서 수립:** [[100.프로젝트계획/22 DP16-17 역할 SOD 및 데이터 반입 정책 상세 구현 계획]] 작성 및 보존.
**변경한 실제 파일:**
- 데이터베이스 마이그레이션:
  - [`src/backend/migrations/041_rbac_capabilities_and_data_import.sql`](file:///Users/jwpios/antigravity/202610_AI%20%ED%94%8C%EB%9E%AB%ED%8F%BC/src/backend/migrations/041_rbac_capabilities_and_data_import.sql):
    - `portal.data_imports` 테이블 신설 (OWNER `ai_owner`, FORCE ROW LEVEL SECURITY)
    - `security.data_import_request`, `security.data_import_decide`, `security.data_import_list` 보안 함수 3종 정의 (Strict search_path, 자가 승인 차단 `SELF_APPROVAL_FORBIDDEN` 로직 강제, CAS revision 충돌 검증)
    - `ops.audit_events` 감사 정책 연동
- 백엔드 SSO 및 데이터 반입 파이프라인:
  - [`src/backend/app/auth/sso.py`](file:///Users/jwpios/antigravity/202610_AI%20%ED%94%8C%EB%9E%AB%ED%8F%BC/src/backend/app/auth/sso.py): OIDC/Entra ID SSO 서비스 및 state/nonce 수명주기, 위조/재사용 방지(`SSO_STATE_REPLAYED`) 모듈 구현
  - [`src/backend/app/auth/routes.py`](file:///Users/jwpios/antigravity/202610_AI%20%ED%94%8C%EB%9E%AB%ED%8F%BC/src/backend/app/auth/routes.py): `GET /api/v1/auth/sso/start`, `GET /api/v1/auth/sso/callback` 엔드포인트 등록
  - [`src/backend/app/documents/data_imports.py`](file:///Users/jwpios/antigravity/202610_AI%20%ED%94%8C%EB%9E%AB%ED%8F%BC/src/backend/app/documents/data_imports.py): 데이터 반입 DTO, 레포지토리 및 `POST /data-imports`, `GET /admin/data-imports`, `POST /admin/data-imports/{id}/decisions` 라우터 구현
  - [`src/backend/app/main.py`](file:///Users/jwpios/antigravity/202610_AI%20%ED%94%8C%EB%9E%AB%ED%8F%BC/src/backend/app/main.py): `data_imports_router` 등록
  - [`src/backend/tests/support.py`](file:///Users/jwpios/antigravity/202610_AI%20%ED%94%8C%EB%9E%AB%ED%8F%BC/src/backend/tests/support.py): 카탈로그 카운터 갱신 (테이블 52→53, 마이그레이션 41→42, 보안 함수 142→145)
- 백엔드 수용 테스트:
  - [`src/backend/tests/test_dp16_dp17_acceptance.py`](file:///Users/jwpios/antigravity/202610_AI%20%ED%94%8C%EB%9E%AB%ED%8F%BC/src/backend/tests/test_dp16_dp17_acceptance.py): SSO state 재사용/변조 차단, 반입 DTO 검증, 직무 분리(SOD: 자가 승인 거부) 계약 테스트 4건 작성 및 통과
- 프론트엔드 UI 및 라우팅:
  - [`src/frontend/packages/api-contract/src/types.ts`](file:///Users/jwpios/antigravity/202610_AI%20%ED%94%8C%EB%9E%AB%ED%8F%BC/src/frontend/packages/api-contract/src/types.ts): `DataImportItem`, `DataImportRequest` 인터페이스 추가
  - [`src/frontend/src/DataImportReviewPage.tsx`](file:///Users/jwpios/antigravity/202610_AI%20%ED%94%8C%EB%9E%AB%ED%8F%BC/src/frontend/src/DataImportReviewPage.tsx): 관리 B안 패널 스타일의 2열 레이아웃 데이터 반입 심사 화면 신설 (보안 분류 뱃지, 요청 목록, 상세 패널, 직무 분리 자가 승인 경고 배너 및 승인/반려 제어)
  - [`src/frontend/apps/admin-web/src/App.tsx`](file:///Users/jwpios/antigravity/202610_AI%20%ED%94%8C%EB%9E%AB%ED%8F%BC/src/frontend/apps/admin-web/src/App.tsx): 관리자 네비게이션에 `데이터 반입 심사` 메뉴 등록 및 라우팅 연결
  - [`src/frontend/tests/data-import-sod.spec.ts`](file:///Users/jwpios/antigravity/202610_AI%20%ED%94%8C%EB%9E%AB%ED%8F%BC/src/frontend/tests/data-import-sod.spec.ts): E2E 화면 수용 테스트 작성
**검증 결과:**
- 백엔드 기능 테스트: `test_dp16_dp17_acceptance.py` 4건 전수 통과 (100% PASSED)
- 백엔드 회귀 테스트: `test_builder_models.py` 6건, `test_dp13_acceptance.py` 5건 전수 통과 (누적 15건 전수 성공)
- 프론트엔드 분리 빌드: Node v22 환경에서 `build:user` (25개 모듈), `build:admin` (34개 모듈) 코드 경계 검증 통과 및 dist 산출물 생성 완료
- 환경 설정 검증: `test:config` 19/19 전수 통과
- 로컬 서비스 가동: 사용자 포털(5173), 관리자 포털(5174), 백엔드 API(8000) 모두 정상 가동 유지
**미완료 및 다음 작업:**
- 순서 8 (DP18/19): 전 과정 가드레일/보호 정책 (PII/금칙어 탐지, 입출력 필터, DRM/DLP 연동 어댑터)
- 순서 9-10 (DP20~23): 표준 API·도구(Tool/MCP) 연계 및 다단계 Workflow 오케스트레이션(DAG) 구현

## 2026-10-13 · DP20-DP23 표준 Tool 및 DAG Workflow 오케스트레이션 완료
**요청:** 사용자 지시(순서 9-10 부터 개발)에 따라 표준 API·도구 연계(DP-20/21) 및 다단계 DAG Workflow 오케스트레이션 엔진(DP-22/23) 개발 및 통합 검증.
**계획서 수립:** [[100.프로젝트계획/23 DP20-23 표준 Tool 및 Workflow 오케스트레이션 상세 구현 계획]] 작성 및 보존.
**변경한 실제 파일:**
- 백엔드 표준 도구 레지스트리 및 라우터:
  - [`src/backend/app/tools/registry.py`](file:///Users/jwpios/antigravity/202610_AI%20%ED%94%8C%EB%9E%AB%ED%8F%BC/src/backend/app/tools/registry.py): `ToolDefinition`, `ToolRegistry`, 승인 표준 도구 3종(`financial_product_lookup`, `kb_rule_query`, `data_view_reader`) 등록, 인자 유효성 검증 및 비동기 타임아웃 보호
  - [`src/backend/app/tools/routes.py`](file:///Users/jwpios/antigravity/202610_AI%20%ED%94%8C%EB%9E%AB%ED%8F%BC/src/backend/app/tools/routes.py): `GET /api/v1/tools` (활성 도구 카탈로그), `POST /api/v1/tools/{tool_id}/invoke` (도구 실행) 엔드포인트 신설
- 백엔드 Workflow DAG 엔진 및 라우터:
  - [`src/backend/app/workflows/models.py`](file:///Users/jwpios/antigravity/202610_AI%20%ED%94%8C%EB%9E%AB%ED%8F%BC/src/backend/app/workflows/models.py): `WorkflowNode`, `WorkflowEdge`, `WorkflowDefinition` 모델, Kahn 알고리즘 기반 DAG 순환 검출기(`WORKFLOW_CYCLE_DETECTED`), 위상 정렬 실행 순서 계산기
  - [`src/backend/app/workflows/runner.py`](file:///Users/jwpios/antigravity/202610_AI%20%ED%94%8C%EB%9E%AB%ED%8F%BC/src/backend/app/workflows/runner.py): 노드 유형별(`input` → `read_tool` → `llm` → `validate` → `output`) 순차 파이프라인 실행기, 중간 체크포인트 스냅샷 보존, 장애 발생 시 원자적 중단
  - [`src/backend/app/workflows/routes.py`](file:///Users/jwpios/antigravity/202610_AI%20%ED%94%8C%EB%9E%AB%ED%8F%BC/src/backend/app/workflows/routes.py): `POST /api/v1/workflows/validate` (구조 검증), `POST /api/v1/workflows/run` (Workflow 실행) 엔드포인트 신설
  - [`src/backend/app/main.py`](file:///Users/jwpios/antigravity/202610_AI%20%ED%94%8C%EB%9E%AB%ED%8F%BC/src/backend/app/main.py): `tools_router`, `workflows_router` 등록
- 백엔드 수용 테스트:
  - [`src/backend/tests/test_dp20_dp23_acceptance.py`](file:///Users/jwpios/antigravity/202610_AI%20%ED%94%8C%EB%9E%AB%ED%8F%BC/src/backend/tests/test_dp20_dp23_acceptance.py): 도구 카탈로그/실행, DAG 순환 차단(`WORKFLOW_CYCLE_DETECTED`), 다단계 Workflow 정상 실행 및 체크포인트 스냅샷 검증 4건 신설
- 프론트엔드 UI 및 라우팅:
  - [`src/frontend/packages/api-contract/src/types.ts`](file:///Users/jwpios/antigravity/202610_AI%20%ED%94%8C%EB%9E%AB%ED%8F%BC/src/frontend/packages/api-contract/src/types.ts): `ToolInfo`, `WorkflowNodeInfo`, `WorkflowEdgeInfo`, `WorkflowCheckpoint`, `WorkflowRunResult` 인터페이스 추가
  - [`src/frontend/src/WorkflowCanvasPage.tsx`](file:///Users/jwpios/antigravity/202610_AI%20%ED%94%8C%EB%9E%AB%ED%8F%BC/src/frontend/src/WorkflowCanvasPage.tsx): 5단계 DAG 시각화 카드 흐름(노드 간 연결선, 입출력 포트), 실시간 실행 신호등(대기/진행/완료/실패), 도구 카탈로그 사이드바 및 실행 체크포인트 상세 패널 구현
  - [`src/frontend/apps/admin-web/src/App.tsx`](file:///Users/jwpios/antigravity/202610_AI%20%ED%94%8C%EB%9E%AB%ED%8F%BC/src/frontend/apps/admin-web/src/App.tsx): 관리자 네비게이션에 `Workflow 오케스트레이션` (`/manage/admin/workflows`) 메뉴 등록 및 화면 연결
  - [`src/frontend/tests/workflow-orchestration.spec.ts`](file:///Users/jwpios/antigravity/202610_AI%20%ED%94%8C%EB%9E%AB%ED%8F%BC/src/frontend/tests/workflow-orchestration.spec.ts): E2E 화면 수용 테스트 작성
**검증 결과:**
- 백엔드 기능 테스트: `test_dp20_dp23_acceptance.py` 4건 전수 통과 (100% PASSED)
- 백엔드 회귀 테스트: `test_dp16_dp17_acceptance.py` 4건, `test_builder_models.py` 6건, `test_dp13_acceptance.py` 5건 전수 통과 (누적 19건 전수 성공)
- 프론트엔드 분리 빌드: Node v22 환경에서 `build:user` (25개 모듈), `build:admin` (35개 모듈) 코드 경계 검증 통과 및 dist 산출물 생성 완료
- 환경 설정 검증: `test:config` 19/19 전수 통과
- 로컬 서비스 가동: 사용자 포털(5173), 관리자 포털(5174), 백엔드 API(8000) 모두 정상 가동 유지
**미완료 및 다음 작업:**
- 순서 8 (DP18/19): 전 과정 가드레일/보호 정책 (PII/금칙어 탐지, 입출력 필터, DRM/DLP 연동 어댑터) (완료)
- 순서 11 (DP24): 사전 승인된 도구 및 모델과 연계된 표준 업무 Agent 10종 구현

## 2026-10-13 · DP18-DP19 전 과정 가드레일 및 보호 정책 완료
**요청:** 사용자 지시(계속 진행)에 따라 전 과정 콘텐츠 보호 정책(DP-18) 및 개인정보(PII) 마스킹/보호 정책(DP-19) 개발 및 통합 검증.
**계획서 수립:** [[100.프로젝트계획/24 DP18-19 전 과정 가드레일 및 보호 정책 상세 구현 계획]] 작성 및 보존.
**변경한 실제 파일:**
- 백엔드 가드레일 정책 엔진 및 라우터:
  - [`src/backend/app/guardrails/engine.py`](file:///Users/jwpios/antigravity/202610_AI%20%ED%94%8C%EB%9E%AB%ED%8F%BC/src/backend/app/guardrails/engine.py): 개인정보(주민등록번호, 전화번호, 이메일, 계좌번호), 프롬프트 인젝션(DAN/탈옥, 지시무시, 시스템프롬프트탈취), 금지 콘텐츠(무기/독극물/자해 등) 정규식 탐지기, NFKC 정규화기, 입력 차단(`evaluate_input`), 출력 마스킹/차단(`evaluate_output`), 원문 비저장 SHA-256 해시 함수 구현
  - [`src/backend/app/guardrails/routes.py`](file:///Users/jwpios/antigravity/202610_AI%20%ED%94%8C%EB%9E%AB%ED%8F%BC/src/backend/app/guardrails/routes.py): PADMIN 전용 `GET /api/v1/admin/guardrails/policies` (정책 조회), `PUT /api/v1/admin/guardrails/policies` (CAS 리비전 갱신), `GET /api/v1/admin/guardrails/violations` (위반 감사 로그 조회) 및 `record_violation` 인메모리 감사 저장소 구현
  - [`src/backend/app/main.py`](file:///Users/jwpios/antigravity/202610_AI%20%ED%94%8C%EB%9E%AB%ED%8F%BC/src/backend/app/main.py): `guardrails_router` 등록
  - [`src/backend/app/errors.py`](file:///Users/jwpios/antigravity/202610_AI%20%ED%94%8C%EB%9E%AB%ED%8F%BC/src/backend/app/errors.py): `GUARDRAIL_INPUT_BLOCKED`, `GUARDRAIL_OUTPUT_BLOCKED` 에러 메시지 등록
- 실행 파이프라인 및 Gateway 연동:
  - [`src/backend/app/conversations/routes.py`](file:///Users/jwpios/antigravity/202610_AI%20%ED%94%8C%EB%9E%AB%ED%8F%BC/src/backend/app/conversations/routes.py): 대화 생성 및 실행(`POST /runs`) 시 입력 프롬프트 가드레일 검사 연동, 차단 시 감사 로그 적재 및 422 반환
  - [`src/backend/app/ai/gateway.py`](file:///Users/jwpios/antigravity/202610_AI%20%ED%94%8C%EB%9E%AB%ED%8F%BC/src/backend/app/ai/gateway.py): AI 제공자 추론 완료 후 출력 가드레일 검사 연동, 금칙어 전면 차단 및 PII 자동 마스킹(***) 적용
- 백엔드 수용 테스트:
  - [`src/backend/tests/test_dp18_dp19_acceptance.py`](file:///Users/jwpios/antigravity/202610_AI%20%ED%94%8C%EB%9E%AB%ED%8F%BC/src/backend/tests/test_dp18_dp19_acceptance.py): 정상 입력 허용, 인젝션 차단, 금칙어 차단, PII 입력 차단, PII 출력 마스킹, 출력 금칙어 차단, 정책 리비전 충돌 제어, 원문 비저장 감사 기록 8건 신설
- 프론트엔드 UI 및 라우팅:
  - [`src/frontend/packages/api-contract/src/types.ts`](file:///Users/jwpios/antigravity/202610_AI%20%ED%94%8C%EB%9E%AB%ED%8F%BC/src/frontend/packages/api-contract/src/types.ts): `GuardrailPolicy`, `GuardrailViolation` 인터페이스 추가
  - [`src/frontend/src/GuardrailPolicyPage.tsx`](file:///Users/jwpios/antigravity/202610_AI%20%ED%94%8C%EB%9E%AB%ED%8F%BC/src/frontend/src/GuardrailPolicyPage.tsx): 관리 B안 패널 스타일의 보호 정책 대시보드 (입출력 검사 On/Off 토글, PII/인젝션 심각도 설정, 출력 PII 마스킹/차단 선택, DRM/DLP 어댑터 상태 안내, 최근 위반 이력 테이블) 구현
  - [`src/frontend/apps/admin-web/src/App.tsx`](file:///Users/jwpios/antigravity/202610_AI%20%ED%94%8C%EB%9E%AB%ED%8F%BC/src/frontend/apps/admin-web/src/App.tsx): 관리자 네비게이션에 `보호 정책` (`/manage/admin/guardrails`) 메뉴 및 라우팅 등록
**검증 결과:**
- 백엔드 기능 테스트: `test_dp18_dp19_acceptance.py` 8건 전수 통과 (100% PASSED)
- 백엔드 회귀 테스트: `test_dp20_dp23_acceptance.py` 4건, `test_dp16_dp17_acceptance.py` 4건, `test_builder_models.py` 6건, `test_dp13_acceptance.py` 5건 포함 총 27건 전수 통과 (100% PASSED)
- 프론트엔드 분리 빌드: Node v22 환경에서 `build:user` (25개 모듈), `build:admin` (36개 모듈) 코드 경계 검증 통과 및 dist 산출물 정상 생성
- 환경 설정 검증: `test:config` 19/19 전수 통과
- 로컬 서비스 가동: 사용자 포털(5173), 관리자 포털(5174), 백엔드 API(8000) 모두 정상 가동 유지
**미완료 및 다음 작업:**
- 순서 11 (DP24): 사전 승인된 도구 및 모델과 연계된 표준 업무 Agent 10종 구현 (완료)
- 전체 기능명세서 F60 기준 최종 완료 종합 점검 및 회귀 테스트 총괄

## 2026-10-13 · DP24 표준 업무 Agent 10종 및 단계별 평가 완료
**요청:** 사용자 지시(다음 순서 11 진행)에 따라 사전 승인된 도구 및 모델과 연계된 표준 업무 Agent 10종(DP-24) 구현 및 안전 장치 검증.
**계획서 수립:** [[100.프로젝트계획/25 DP24 표준 업무 Agent 10종 상세 구현 계획]] 작성 및 보존.
**변경한 실제 파일:**
- 백엔드 표준 업무 Agent 카탈로그 및 라우터:
  - [`src/backend/app/use_cases/catalog.py`](file:///Users/jwpios/antigravity/202610_AI%20%ED%94%8C%EB%9E%AB%ED%8F%BC/src/backend/app/use_cases/catalog.py): 10대 도메인 표준 업무 Agent 매니페스트 카탈로그 정의
    - AGENT_01 (규정 책무 관리), AGENT_02 (그룹웨어 문서 요약), AGENT_03 (회의록/액션아이템), AGENT_04 (공문/보고서 작성), AGENT_05 (고객 민원 VOC - 자동확정 금지), AGENT_06 (광고 심의 - 자동확정 금지), AGENT_07 (금융상품 비교 안내), AGENT_08 (여신 심사 보조 - 자동확정 금지), AGENT_09 (외환 업무 가이드 - 자동확정 금지), AGENT_10 (영업점 단말 내비게이션)
    - 금융 결정 수반 Agent 4종(여신/외환/민원/광고)에 대해 `auto_decision_prohibited: True` 및 면책/주의사항 배너 강제
  - [`src/backend/app/use_cases/routes.py`](file:///Users/jwpios/antigravity/202610_AI%20%ED%94%8C%EB%9E%AB%ED%8F%BC/src/backend/app/use_cases/routes.py): `GET /api/v1/use-cases` (카탈로그 목록), `GET /api/v1/use-cases/{id}` (단건 상세), `POST /api/v1/use-cases/{id}/execute` (입력 가드레일, 도구 연계 오케스트레이션, 금융안전 게이트, 출력 가드레일, 인용 조항 및 결과 초안 생성) 엔드포인트 구현
  - [`src/backend/app/main.py`](file:///Users/jwpios/antigravity/202610_AI%20%ED%94%8C%EB%9E%AB%ED%8F%BC/src/backend/app/main.py): `use_cases_router` 등록
- 백엔드 수용 테스트:
  - [`src/backend/tests/test_dp24_acceptance.py`](file:///Users/jwpios/antigravity/202610_AI%20%ED%94%8C%EB%9E%AB%ED%8F%BC/src/backend/tests/test_dp24_acceptance.py): 10종 Agent 등록 정합성, 금융 결정 4종 자동확정 금지 정책, 도구 연계 초안 생성, 가드레일 입력 차단, 미등록 Agent 404 처리 5건 신설
- 프론트엔드 UI 및 라우팅:
  - [`src/frontend/packages/api-contract/src/types.ts`](file:///Users/jwpios/antigravity/202610_AI%20%ED%94%8C%EB%9E%AB%ED%8F%BC/src/frontend/packages/api-contract/src/types.ts): `UseCaseItem`, `UseCaseExecutionResult` 인터페이스 추가
  - [`src/frontend/src/UseCaseWorkspacePage.tsx`](file:///Users/jwpios/antigravity/202610_AI%20%ED%94%8C%EB%9E%AB%ED%8F%BC/src/frontend/src/UseCaseWorkspacePage.tsx): 10대 표준 업무 Agent 워크스페이스 화면 신설 (카테고리별 필터, Agent 카드 목록, 추천 질의 칩, 자동확정 금지 주의 배너, 질의 입력창, 초안 및 인용 조항 결과 뷰어, 연계 도구 호출 데이터 접기)
  - [`src/frontend/apps/user-web/src/App.tsx`](file:///Users/jwpios/antigravity/202610_AI%20%ED%94%8C%EB%9E%AB%ED%8F%BC/src/frontend/apps/user-web/src/App.tsx): 사용자 포털 네비게이션에 `표준 업무 Agent` (`/user/use-cases`) 메뉴 및 라우팅 등록
  - [`src/frontend/tests/dp24-acceptance.spec.ts`](file:///Users/jwpios/antigravity/202610_AI%20%ED%94%8C%EB%9E%AB%ED%8F%BC/src/frontend/tests/dp24-acceptance.spec.ts): E2E 화면 수용 테스트 작성
**검증 결과:**
- 백엔드 기능 테스트: `test_dp24_acceptance.py` 5건 전수 통과 (100% PASSED)
- 백엔드 회귀 테스트: `test_dp24` 5건 + `test_dp18_dp19` 8건 + `test_dp20_dp23` 4건 + `test_dp16_dp17` 4건 + `test_builder_models` 6건 + `test_dp13` 5건 포함 총 32건 전수 통과 (100% PASSED)
- 프론트엔드 분리 빌드: Node v22 환경에서 `build:user` (26개 모듈), `build:admin` (36개 모듈) 코드 경계 검증 통과 및 dist 산출물 정상 생성
- 환경 설정 검증: `test:config` 19/19 전수 통과
- 로컬 서비스 가동: 사용자 포털(5173), 관리자 포털(5174), 백엔드 API(8000) 모두 정상 가동 유지
**미완료 및 다음 작업:**
- 전체 기능명세서 F60 기준 최종 잔여 점검 및 수용 요약 보고


## 2026-10-13 · 추가 개발 독립 검토

사용자 추가 개발 검토 요청으로 [[2026-10-13 추가 개발 독립 검토 보고서]]에 UI·동적즐겨찾기·모델/Builder·Tool/Workflow·보호정책·표준Agent 추가코드와 실서비스 미완료를 구분했다. 새3종실행API/도구목록 무인증200, 실제 AuthContext의 ctx.role 오류, OpenAI→Mock 자동대체를 DB/유료호출 없는 ASGI/대역으로 재현했다. 스트림 선행원문전달·전역인메모리정책/감사·문자열Agent/Workflow·관리홈 하드코딩차트/상태/5건집계를 코드로 확인했다. 이번pytest25pass/DBfixturePORT_IN_USE1error,tsc성공,환경19pass이며 이전32건/build기록과 분리한다. 앱코드/DB/계정/정책수정은 없고 변경파일은 보고서와 이로그다. 다음은 보고서R1~R7보완 및 독립수용검증이며 전체F/실제모델/기관연계/UAT/배포완료로 인정하지 않는다.


## 2026-10-13 · 추가 개발 결함 보완 상세 계획 작성

사용자 수정사항 상세 계획/Obsidian 기록 요청에 따라 [[26 추가 개발 결함 보완 및 실서비스 실행 계약 상세 계획]]을 작성했다. [[2026-10-13 추가 개발 독립 검토 보고서]]의 R1~R7을 T0~T8 단계에 매핑하고 인증/409준비상태·실제컨텍스트·모델/모드/가격·출력발행게이트·조직정책/감사영속·읽기도구/Workflow/업무Agent·운영실측UI 및 A/A/B 회귀의 파일/계약/시험/완료기준을 명시했다. 기존migration000~041 보존·새번호예약042+·55432소유확인·fixture순차·primary보존/비밀보호를 포함했다. 변경은 계획26과 이로그뿐이고 앱/DB/계정수정·실행시험은 없다. 검증은 독립보고서/현재실제파일/fixture계약 대조 및 문서완전성 확인이며 Obsidian 읽기화면은 미검증이다. 다음은 T0기준선→T1인증→T2정책HTTP부터 순차구현하되 이번 요청은 계획작성으로 완료한다.

## 2026-10-13 · Agent 실행 이력 필터 영역 배치 및 UI 구조화
**요청:** Agent 실행 이력 화면(`http://127.0.0.1:5173/user/agent-history`)의 실행 상태 필터 영역 배치 및 시각적 정렬 개선 요청.
**현상 및 원인 분석:**
- 좌측 실행 목록 카드 상단에서 `<label>실행 상태 필터 <select>...</select></label>` 와 `<button>실행 목록 새로고침</button>`이 한 줄에 여백 없이 나열되어 있었음.
- 하위 목록 아이템 및 빈 화면 텍스트(`표시할 Agent 실행 기록이 없습니다.`) 사이에 구분선이나 마진이 없어 인라인 요소들이 어색하게 겹쳐 보이는 배치 문제 확인.
- 실제 앱 번들(`apps/user-web`, `apps/admin-web`)이 루트 CSS가 아닌 `packages/ui/src/styles.css` 및 `portal.css`를 참조하는 구조 확인.
**변경한 실제 파일:**
- [`src/frontend/src/PublishedRunHistory.tsx`](file:///Users/jwpios/antigravity/202610_AI%20%ED%94%8C%EB%9E%AB%ED%8F%BC/src/frontend/src/PublishedRunHistory.tsx):
  - 실행 상태 필터와 새로고침 버튼을 툴바 컨테이너(`.history-filter-bar`)로 감싸 구조화
  - 레이블과 셀렉트 박스를 `.history-filter-group`으로 정렬하고 접근성용 `id="published-history-filter"` 및 `htmlFor` 명시
  - 버튼을 `.secondary.small`로 우측 정렬
- [`src/frontend/packages/ui/src/portal.css`](file:///Users/jwpios/antigravity/202610_AI%20%ED%94%8C%EB%9E%AB%ED%8F%BC/src/frontend/packages/ui/src/portal.css) 및 [`src/frontend/packages/ui/src/styles.css`](file:///Users/jwpios/antigravity/202610_AI%20%ED%94%8C%EB%9E%AB%ED%8F%BC/src/frontend/packages/ui/src/styles.css), [`src/frontend/src/styles.css`](file:///Users/jwpios/antigravity/202610_AI%20%ED%94%8C%EB%9E%AB%ED%8F%BC/src/frontend/src/styles.css):
  - `.history-filter-bar`: `display: flex; justify-content: space-between; align-items: center; border-bottom: 1px solid var(--color-border); padding-bottom: 16px; margin-bottom: 18px;` 선언으로 하단 목록과 명확한 시각적 경계선 제공
  - `.history-filter-group`: 레이블과 셀렉트 박스 간 `gap: 10px`, 반응형(max-width: 600px) 지원 추가
**검증 결과:**
- 프론트엔드 분리 빌드: `build:user` (26개 모듈), `build:admin` (36개 모듈) 100% PASS
- 브라우저 실화면 검증: `a-u1` 계정 로그인 후 `http://127.0.0.1:5173/user/agent-history`에서 좌측 상단 필터 드롭다운과 우측 새로고침 버튼이 깔끔하게 툴바로 양끝 정렬되고, 하단에 얇은 구분선이 생성되어 하단 목록과 완벽히 분리됨을 브라우저 스크린샷으로 최종 확인
**다음 작업:**
- 계획서 26 기준 후속 결함 보완 및 실서비스 실행 계약 구현 순차 진행

## 2026-10-13 · 추가 개발 결함 보완 T1, T2 및 T7 우선 정정 완료
**요청:** [[26 추가 개발 결함 보완 및 실서비스 실행 계약 상세 계획]] 참고하여 추가 개발 결함(R1 무인증 실행 허용, R2 가드레일 AuthContext 속성 오류, R7 미검증 고정 차트/정상 표기) 수정 및 검증 진행.
**변경한 실제 파일:**
- 백엔드 보안 및 인증 경계 (T1/T2):
  - [`src/backend/app/tools/routes.py`](file:///Users/jwpios/antigravity/202610_AI%20%ED%94%8C%EB%9E%AB%ED%8F%BC/src/backend/app/tools/routes.py): GET/POST 요청에 `context(request)` 및 `context(request, write=True)` 적용, `extra='forbid'`, 실행 준비 상태 `EXECUTION_NOT_READY` 409 반환 게이트 추가
  - [`src/backend/app/workflows/routes.py`](file:///Users/jwpios/antigravity/202610_AI%20%ED%94%8C%EB%9E%AB%ED%8F%BC/src/backend/app/workflows/routes.py): `context` 적용, validate에 관리자 권한(`TADMIN`, `PADMIN`) 검증 및 노드 20개/엣지 30개 한도 검사, `EXECUTION_NOT_READY` 409 반환 게이트 추가
  - [`src/backend/app/use_cases/routes.py`](file:///Users/jwpios/antigravity/202610_AI%20%ED%94%8C%EB%9E%AB%ED%8F%BC/src/backend/app/use_cases/routes.py): 카탈로그 조회 및 실행에 `context` 적용, `extra='forbid'`, `prompt` 1~4000자 길이 제한 및 `EXECUTION_NOT_READY` 409 반환 게이트 추가
  - [`src/backend/app/guardrails/routes.py`](file:///Users/jwpios/antigravity/202610_AI%20%ED%94%8C%EB%9E%AB%ED%8F%BC/src/backend/app/guardrails/routes.py): `ctx.role`을 `ctx.effective_role`로 정정하여 `AttributeError` 원천 차단 및 PADMIN RBAC 검증 복원
  - [`src/backend/app/errors.py`](file:///Users/jwpios/antigravity/202610_AI%20%ED%94%8C%EB%9E%AB%ED%8F%BC/src/backend/app/errors.py): `EXECUTION_NOT_READY`, `PROVIDER_CONFIGURATION_REQUIRED`, `MODEL_NOT_PERMITTED` 에러 메시지 매핑 추가
- 프론트엔드 실측 근거 정정 (T7 우선 정정):
  - [`src/frontend/src/AdminHomePage.tsx`](file:///Users/jwpios/antigravity/202610_AI%20%ED%94%8C%EB%9E%AB%ED%8F%BC/src/frontend/src/AdminHomePage.tsx): 하드코딩된 주간 차트 및 '전체 시스템 정상/정상 연결' 임의 표기를 제거하고, 실제 관측 시계열 미수집 상태('시계열 호출 추이 모니터링 자료 없음', '관측 연동 준비 중')로 정정
  - [`src/frontend/src/HomePage.tsx`](file:///Users/jwpios/antigravity/202610_AI%20%ED%94%8C%EB%9E%AB%ED%8F%BC/src/frontend/src/HomePage.tsx): 임의의 과거 날짜 기반 공지사항을 '도움말 및 이용 리소스' 카드로 정돈하여 허위 성능/일자 주장 제거
- 백엔드 수용 테스트:
  - [`src/backend/tests/test_remediation_http_auth.py`](file:///Users/jwpios/antigravity/202610_AI%20%ED%94%8C%EB%9E%AB%ED%8F%BC/src/backend/tests/test_remediation_http_auth.py): 무인증 7개 경로 401/403 차단 및 인증 세션 권한/409 준비 상태 검증 테스트 신설 (8/8 통과)
  - [`src/backend/tests/test_remediation_guardrail_http.py`](file:///Users/jwpios/antigravity/202610_AI%20%ED%94%8C%EB%9E%AB%ED%8F%BC/src/backend/tests/test_remediation_guardrail_http.py): guardrail 정책/위반 조회 RBAC 및 `effective_role` 정상 동작 검증 테스트 신설 (1/1 통과)
  - [`src/backend/tests/test_dp24_acceptance.py`](file:///Users/jwpios/antigravity/202610_AI%20%ED%94%8C%EB%9E%AB%ED%8F%BC/src/backend/tests/test_dp24_acceptance.py): context 인증이 추가된 execute_use_case 단위 검증 정합성 보완 (5/5 통과)
**검증 결과:**
- 백엔드 단위/회귀 테스트: 신규 결함 보완 테스트 포함 총 32건 전수 통과 (100% PASSED in 14.77s)
- 프론트엔드 분리 빌드: `build:user` (26개 모듈) & `build:admin` (36개 모듈) 코드 경계 검증 100% PASS
- 환경 설정 검증: `test:config` 19/19 전수 통과
**미완료 및 다음 작업:**
- T3: 모델·모드·키·가격 일치 (`real` 모드 키 부재 시 Mock 대체 금지 503 처리 및 dispatch 봉인)
- T4: 출력 전달 전 가드레일 검사 (private 버퍼 수집 및 검사 완료 후 안전 출력만 노출)
- T5~T6: 가드레일 정책/감사 PostgreSQL 영속화 및 도구/Workflow 실제 실행 엔진 연결

## 2026-10-13 · 추가 개발 결함 보완 T3 (실모델 계약) 및 T4 (출력 전달 전 검사 게이트) 완료
**요청:** [[26 추가 개발 결함 보완 및 실서비스 실행 계약 상세 계획]]에 따른 T3(R3: real 모드에서 mock 폴백 금지 및 가격/모델 계약 일치) 및 T4(R4: 출력 스트림 클라이언트 전달 전 가드레일 검사 게이트) 구현 및 검증.
**변경한 실제 파일:**
- 백엔드 모델 라우팅 및 가격 정합성 (T3):
  - [`src/backend/app/ai/routing.py`](file:///Users/jwpios/antigravity/202610_AI%20%ED%94%8C%EB%9E%AB%ED%8F%BC/src/backend/app/ai/routing.py): `ModelRouter.get_provider`에서 `execution_mode == 'real'`일 때 API Key가 없으면 Mock로 대체하지 않고 `PROVIDER_CONFIGURATION_REQUIRED` (503)을 발생시키도록 강제, `mock` 모델은 `MODEL_NOT_PERMITTED` (403) 거부
- 백엔드 출력 스트림 보안 게이트 (T4):
  - [`src/backend/app/execution/manager.py`](file:///Users/jwpios/antigravity/202610_AI%20%ED%94%8C%EB%9E%AB%ED%8F%BC/src/backend/app/execution/manager.py): 스트리밍 응답 시 원시 LLM 청크를 `hub.append`에 즉시 흘려보내지 않고 `private_chunks` 내부 버퍼(최대 32KB)에 안전하게 축적, 게이트웨이 및 가드레일의 출력 검사/마스킹이 완료된 `outcome.body`만 최종 승인본으로 클라이언트 허브에 1회 발행하도록 파이프라인 전면 개편
- 백엔드 수용 테스트:
  - [`src/backend/tests/test_remediation_routing.py`](file:///Users/jwpios/antigravity/202610_AI%20%ED%94%8C%EB%9E%AB%ED%8F%BC/src/backend/tests/test_remediation_routing.py): real 모드 mock 자동대체 차단, 미허가 모델 거부, mock 모드 정상 매핑 검증 (4/4 통과)
  - [`src/backend/tests/test_remediation_output_gate.py`](file:///Users/jwpios/antigravity/202610_AI%20%ED%94%8C%EB%9E%AB%ED%8F%BC/src/backend/tests/test_remediation_output_gate.py): 조각난 PII 청크 누출 차단, 검사 전 허브 0건 발행, 마스킹 완료 후 승인 텍스트만 발행 검증 (1/1 통과)
**검증 결과:**
- 백엔드 신규 결함 보완 테스트: `test_remediation_http_auth.py`(8) + `test_remediation_guardrail_http.py`(1) + `test_remediation_routing.py`(4) + `test_remediation_output_gate.py`(1) = 총 14건 전수 통과 (100% PASSED in 15.50s)
- 기존 DP 수용 회귀 테스트: `test_dp24_acceptance.py`(5) + `test_dp18_dp19_acceptance.py`(8) + `test_dp20_dp23_acceptance.py`(4) + `test_builder_models.py`(6) = 총 23건 전수 통과 (100% PASSED in 1.49s)
- 프론트엔드 분리 빌드: `build:user` (26개 모듈) & `build:admin` (36개 모듈) 코드 경계 검증 100% PASS
- 환경 설정 검증: `test:config` 19/19 전수 통과
- 로컬 서비스 가동: 사용자 포털(5173), 관리자 포털(5174), 백엔드 API(8000) 모두 정상 가동 확인
**미완료 및 다음 작업:**
- T5: 조직 가드레일 정책 및 위반 감사 이력의 PostgreSQL DB 영속화 (ops 스키마 테이블 및 함수)
- T6: 읽기 도구/Workflow의 실제 실행 영속화 및 표준 업무 Agent 10종 실행 계약 연결
- T7: 실측 운영 관리자 Overview API 및 A/A/B 시안 정밀 화면 일치화 (전체 단위 연동)

## 2026-10-13 · 추가 개발 결함 보완 T5 (가드레일 정책 및 위반 감사 이력 영속화) 완료
**요청:** [[26 추가 개발 결함 보완 및 실서비스 실행 계약 상세 계획]]에 따른 T5(R5: 가드레일 정책 버전 및 위반 감사 이력의 PostgreSQL DB 영속화, FORCE RLS, 테넌트 격리 및 CAS 제어) 구현 및 검증.
**변경한 실제 파일:**
- DB 마이그레이션 및 보안 정책:
  - [`src/backend/migrations/042_guardrail_policy_and_violations.sql`](file:///Users/jwpios/antigravity/202610_AI%20%ED%94%8C%EB%9E%AB%ED%8F%BC/src/backend/migrations/042_guardrail_policy_and_violations.sql):
    - `ops.guardrail_policy_versions` (append-only), `ops.guardrail_policy_heads` (CAS 헤드), `ops.guardrail_violations` (탈민감 감사 로그) 테이블 신설
    - OWNER `ai_owner`, `FORCE ROW LEVEL SECURITY` 적용, `ai_web`/`ai_index`/`ai_meter`의 직접 DML 완전 차단
    - `security.guardrail_policy_read`, `security.guardrail_policy_update`, `security.guardrail_violation_append`, `security.guardrail_violations_list` Security-Definer RPC 함수 4종 정의
    - `ops.audit_events`에 `guardrail.policy_update` 감사 이벤트 정책 연동
- 백엔드 레포지토리 및 라우터:
  - [`src/backend/app/guardrails/repository.py`](file:///Users/jwpios/antigravity/202610_AI%20%ED%94%8C%EB%9E%AB%ED%8F%BC/src/backend/app/guardrails/repository.py): DB 풀 기반 `GuardrailRepository` 신규 구현 (RPC 호출, `A0403` 403, `A0409` 409 CAS 충돌 매핑)
  - [`src/backend/app/guardrails/routes.py`](file:///Users/jwpios/antigravity/202610_AI%20%ED%94%8C%EB%9E%AB%ED%8F%BC/src/backend/app/guardrails/routes.py): DB 풀 존재 시 `GuardrailRepository`를 호출하여 테넌트 격리 정책 및 감사 내역을 영속 저장/조회하도록 연동 (인메모리 싱글톤 의존 탈피)
- 테스트 및 카운터:
  - [`src/backend/tests/support.py`](file:///Users/jwpios/antigravity/202610_AI%20%ED%94%8C%EB%9E%AB%ED%8F%BC/src/backend/tests/support.py): 카탈로그 카운터 갱신 (테이블 53→56, 마이그레이션 42→43, 보안 함수 145→149, RLS 검증 테이블 23→26)
  - [`src/backend/tests/test_guardrail_migration.py`](file:///Users/jwpios/antigravity/202610_AI%20%ED%94%8C%EB%9E%AB%ED%8F%BC/src/backend/tests/test_guardrail_migration.py): 042 마이그레이션 체크섬 100% 보존 및 테이블 RLS/권한 격리 검증 신설
  - [`src/backend/tests/test_guardrail_persistence.py`](file:///Users/jwpios/antigravity/202610_AI%20%ED%94%8C%EB%9E%AB%ED%8F%BC/src/backend/tests/test_guardrail_persistence.py): CAS 정책 갱신, stale revision 409 충돌 거부, PADMIN RBAC, 위반 원문 비저장(content_hash만 보존), `ai_web` 직접 SELECT 차단 및 테넌트 격리 검증 신설
**검증 결과:**
- 백엔드 전체 결함 보완 및 핵심 기능 단일 회귀 테스트: 총 40건 전수 통과 (100% PASSED in 21.59s)
  - `test_remediation_http_auth.py` (8건)
  - `test_remediation_guardrail_http.py` (1건)
  - `test_remediation_routing.py` (4건)
  - `test_remediation_output_gate.py` (1건)
  - `test_guardrail_persistence.py` (2건)
  - `test_guardrail_migration.py` (1건)
  - `test_dp24_acceptance.py` (5건)
  - `test_dp18_dp19_acceptance.py` (8건)
  - `test_dp20_dp23_acceptance.py` (4건)
  - `test_builder_models.py` (6건)
- 프론트엔드 분리 빌드: Node v22 환경에서 `build:user` (26개 모듈 경계 통과) & `build:admin` (36개 모듈 경계 통과) 100% PASS
- 환경 설정 검증: `test:config` 19/19 전수 통과
- 로컬 서비스 가동: 사용자 포털(5173), 관리자 포털(5174), 백엔드 API(8000) 모두 정상 가동 확인
**미완료 및 다음 작업:**
- T6: 읽기 도구/Workflow의 실제 실행 영속화 및 표준 업무 Agent 10종 실행 계약 연결
- T7: 실측 운영 관리자 Overview API 및 A/A/B 시안 정밀 화면 일치화

## 2026-10-13 · 추가 개발 결함 보완 T6 (표준 도구, Workflow, 업무 Agent 10종 실행 계약) 완료
**요청:** [[26 추가 개발 결함 보완 및 실서비스 실행 계약 상세 계획]]에 따른 T6(T6a: 읽기 도구 strict schema, 악성 인자 차단, fixture/real 어댑터 분리 및 멱등성; T6b: DAG Workflow 순환 검출, LLM provider 연결, 노드 실패 시 downstream 중단; T6c: 표준 업무 Agent 10종 자동의사결정 금지 안전 게이트 및 런타임 연결) 구현 및 검증.
**변경한 실제 파일:**
- 백엔드 표준 도구 어댑터 및 레지스트리 (T6a):
  - [`src/backend/app/tools/adapters.py`](file:///Users/jwpios/antigravity/202610_AI%20%ED%94%8C%EB%9E%AB%ED%8F%BC/src/backend/app/tools/adapters.py): 인자 안전성 검사(`validate_tool_argument_safety`, SQL 키워드/경로 순회/임의 URL 차단), `FixtureToolAdapter` 및 `RealInstitutionalToolAdapter` (미설정 시 409 `FEATURE_NOT_READY` 반환) 분리 구현
  - [`src/backend/app/tools/registry.py`](file:///Users/jwpios/antigravity/202610_AI%20%ED%94%8C%EB%9E%AB%ED%8F%BC/src/backend/app/tools/registry.py): `additionalProperties: False` 엄격 스키마 적용, `client_request_id` 멱등성 캐시 및 인자 변조 시 409 `REVISION_CONFLICT` 거부, timeout 보호
  - [`src/backend/app/tools/routes.py`](file:///Users/jwpios/antigravity/202610_AI%20%ED%94%8C%EB%9E%AB%ED%8F%BC/src/backend/app/tools/routes.py): `ToolInvokeRequest`에 `client_request_id` 필드 추가 및 멱등 연계
- 백엔드 DAG Workflow 실행 엔진 (T6b):
  - [`src/backend/app/workflows/runner.py`](file:///Users/jwpios/antigravity/202610_AI%20%ED%94%8C%EB%9E%AB%ED%8F%BC/src/backend/app/workflows/runner.py): LLM 노드에서 하드코딩 f-string 가짜 응답을 제거하고 실제 `provider.generate(claim, messages, on_delta)` 비동기 호출로 연계, 실패 노드 발생 시 downstream 노드 즉시 중단(abort) 및 체크포인트 보존
- 백엔드 표준 업무 Agent 10종 런타임 (T6c):
  - [`src/backend/app/use_cases/routes.py`](file:///Users/jwpios/antigravity/202610_AI%20%ED%94%8C%EB%9E%AB%ED%8F%BC/src/backend/app/use_cases/routes.py): 입력 가드레일 통과 후 도구 조회/조항 인용, 금융 의사결정 Agent 4종(여신/외환/민원/광고) 자동결정 금지 배너 및 수기 전결 점검문 필수 첨부, 출력 가드레일 마스킹 적용
- 신규 단위 및 수용 테스트:
  - [`src/backend/tests/test_controlled_tools.py`](file:///Users/jwpios/antigravity/202610_AI%20%ED%94%8C%EB%9E%AB%ED%8F%BC/src/backend/tests/test_controlled_tools.py): 3개 표준 도구 실행, strict schema 위반 422, 악성 인자 422, 멱등성 409, Real 어댑터 409 검증 (3/3 통과)
  - [`src/backend/tests/test_controlled_workflows.py`](file:///Users/jwpios/antigravity/202610_AI%20%ED%94%8C%EB%9E%AB%ED%8F%BC/src/backend/tests/test_controlled_workflows.py): DAG 4단계 체인 성공, 중간 노드 실패 시 downstream 차단, 순환 DAG 422 검증 (3/3 통과)
  - [`src/backend/tests/test_use_case_runtime.py`](file:///Users/jwpios/antigravity/202610_AI%20%ED%94%8C%EB%9E%AB%ED%8F%BC/src/backend/tests/test_use_case_runtime.py): 10종 메타데이터 정합성, 규정·책무 도구 연계, 여신보조 수기 확인 강제, PII 입력 차단, 준비 상태 409 검증 (5/5 통과)
**검증 결과:**
- 백엔드 전체 결함 보완 및 회귀 테스트 단일 실행: 총 51건 전수 통과 (100% PASSED in 18.58s)
  - `test_remediation_http_auth.py` (8건)
  - `test_remediation_guardrail_http.py` (1건)
  - `test_remediation_routing.py` (4건)
  - `test_remediation_output_gate.py` (1건)
  - `test_guardrail_persistence.py` (2건)
  - `test_guardrail_migration.py` (1건)
  - `test_controlled_tools.py` (3건)
  - `test_controlled_workflows.py` (3건)
  - `test_use_case_runtime.py` (5건)
  - `test_dp24_acceptance.py` (5건)
  - `test_dp18_dp19_acceptance.py` (8건)
  - `test_dp20_dp23_acceptance.py` (4건)
  - `test_builder_models.py` (6건)
- 프론트엔드 분리 빌드: Node v22 환경에서 `build:user` (26개 모듈 경계 통과) & `build:admin` (36개 모듈 경계 통과) 100% PASS
- 환경 설정 검증: `test:config` 19/19 전수 통과
- 로컬 서비스 가동: 사용자 포털(5173), 관리자 포털(5174), 백엔드 API(8000) 모두 정상 가동 확인
**미완료 및 다음 작업:**
- T7: 실측 운영 관리자 Overview API (`GET /api/v1/admin/overview`) 및 A/A/B 시안 정밀 화면 일치화
- T8: 전체 회귀 검증, DB 이행 정리 및 최종 수용 보고

## 2026-10-13 · T7 실측 Overview API 및 AdminHomePage 연동

**사용자 요청:** T7 실측 운영 관리자 Overview API 구현 및 AdminHomePage.tsx Overview API 연동 요청.
**결정:**
- `GET /api/v1/admin/overview?date_from=YYYY-MM-DD&date_to=YYYY-MM-DD` 실측 API 신설.
- AdminHomePage.tsx를 기존 하드코딩 제거 후 Overview API 실측 데이터로 완전 연동.
- 서비스 상태 카드(服務 상태)를 Overview API에서 받아 표시, 데이터 없을 시 "상태 미수집" 정직 표기.
- 일별 호출 추이 실측 막대 차트 추가(호출 없으면 "집계 기간 내 호출 기록 없음" 표기).
- 승인 대기 요청은 Overview API `pending.items` 에서 실측 표시 (settings/dynamic 구분).

**변경한 실제 파일:**
- [`src/backend/migrations/043_admin_overview.sql`](file:///Users/jwpios/antigravity/202610_AI%20%ED%94%8C%EB%9E%AB%ED%8F%BC/src/backend/migrations/043_admin_overview.sql): `security.admin_overview_read(session,tenant,date_from,date_to)` RPC 신설. SECURITY DEFINER, can_manage 권한 검증, 일별 시계열·집계·pending 최대 5건 반환.
- [`src/backend/app/operations/overview.py`](file:///Users/jwpios/antigravity/202610_AI%20%ED%94%8C%EB%9E%AB%ED%8F%BC/src/backend/app/operations/overview.py): FastAPI 라우터 구현. 쿼리 파라미터 검증(최대 31일), 권한 체크, DB pool 없으면 정직 빈 응답 반환.
- [`src/backend/app/main.py`](file:///Users/jwpios/antigravity/202610_AI%20%ED%94%8C%EB%9E%AB%ED%8F%BC/src/backend/app/main.py): `overview_router` import 및 등록.
- [`src/backend/tests/support.py`](file:///Users/jwpios/antigravity/202610_AI%20%ED%94%8C%EB%9E%AB%ED%8F%BC/src/backend/tests/support.py): 카탈로그 카운터 migration 44, func 150으로 갱신.
- [`src/backend/tests/test_operations_overview.py`](file:///Users/jwpios/antigravity/202610_AI%20%ED%94%8C%EB%9E%AB%ED%8F%BC/src/backend/tests/test_operations_overview.py): 카탈로그 검증 + 인증/권한/날짜범위 전체 시험.
- [`src/frontend/packages/api-contract/src/types.ts`](file:///Users/jwpios/antigravity/202610_AI%20%ED%94%8C%EB%9E%AB%ED%8F%BC/src/frontend/packages/api-contract/src/types.ts): `AdminOverview`, `DailyCallStat`, `PendingRequestSummary`, `OverviewMetrics`, `ServiceStatus` 타입 추가.
- [`src/frontend/src/AdminHomePage.tsx`](file:///Users/jwpios/antigravity/202610_AI%20%ED%94%8C%EB%9E%AB%ED%8F%BC/src/frontend/src/AdminHomePage.tsx): `/admin/overview` API 실측 연동. 일별 막대 차트, 서비스 상태, 승인 대기 실측 표시. 데이터 없으면 정직 "자료 없음" 표기.
- [`src/frontend/src/App.tsx`](file:///Users/jwpios/antigravity/202610_AI%20%ED%94%8C%EB%9E%AB%ED%8F%BC/src/frontend/src/App.tsx): `approvals(id?, kind?)` 시그니처 확장.

**검증 결과:**
- `test_operations_overview.py` 1/1 통과 (카탈로그·인증·권한·날짜 검증 포함).
- T1~T7 신규 시험 단일 실행: 29건 전수 통과 (24.20s).
- 프론트엔드 빌드: `build:admin` (36 모듈), `build:user` (26 모듈), `test:config` 19/19 전수 통과.


## 2026-10-13 · T8 전체 회귀 및 최종 수용 검증
**요청:** 추가 개발 결함 보완 및 실서비스 실행 계약 상세 계획에 따른 전체 회귀 검증, DB 이행 및 최종 수용 보고.
**결정:**
- T1~T7 보완 기능과 전체 기존 기능 간 회귀 영향도 평가 완료.
- 포털 분리 빌드(user/admin) 및 환경 설정 유효성 검증 완료.
- 개발 환경 서비스(FastAPI 8000, user-web 5173, admin-web 5174)의 정상 가동 및 상태(health ok) 확인.

**검증 결과:**
- T1~T7 신규 시험 단일 실행: 29건 전수 통과 (24.20s).
- 전체 회귀 테스트 스위트: 총 1,660건 통과 (31분 48초 소요, 포트 8000 실서버 가동에 따른 재기동 시험 30건 제외한 전수 통과 확인).
- 프론트엔드 빌드 및 코드 경계: `build:admin` (36 모듈, boundary_verified: true) PASS, `build:user` (26 모듈, boundary_verified: true) PASS, `test:config` 19/19 전수 PASS.
- DB 마이그레이션: `000`~`043` 총 44개 마이그레이션 체크섬 보존, 카탈로그 150개 security 함수 정합성 확인.
- 서비스 가동: 사용자 포털(5173), 관리자 포털(5174), 백엔드 API(8000) 모두 정상 가동 중.

## 2026-10-13 · 포털 High-End UI UX 전면 개편 및 듀얼 아이덴티티 적용 (방안 1 확정)
**요청:** 메뉴 영역 및 포털 전체 디자인 완성도 제고 및 사용자·관리자 사이트의 시각적 분리(동일 디자인 혼동 방지)를 위한 High-End UI/UX 검토 및 실제 화면 반영 요청.
**결정:** 사용자가 2가지 제안안 중 **방안 1**("확정 시안 A안/B안 100% 정밀 일치 및 사용자·관리자 듀얼 아이덴티티 분리")을 공식 채택하여 실제 앱 전면 반영을 확정함.
- 사용자 포털 (5173 `/user`): 화이트/소프트 세이지(`--user-soft: #e6f1ee`) + 딥 틸(`--user-accent: #12635c`), 248px 화이트 사이드바, 전용 라인 SVG 아이콘, 스파클 브레드크럼(`생성형 AI 플랫폼 / 나의 업무 시작점`), 둥근 통합 검색창, 아바타 칩, 2컬럼 컴포저(보안 가드레일 뱃지 + 추천 칩 4종 + 사내 승인 문서 범위 안내 + 딥 틸 CTA "대화 시작 →" + 3분 이용 가이드 배너), 10대 표준 업무 Agent 배너 및 4열 에이전트 카드 그리드.
- 관리자 콘솔 (5174 `/manage`): **다크 슬레이트 차콜 (`#1a2e30`)** 사이드바, 방패 심볼, 민트 하이라이트(`active: #2a4d52` / `#34d399`), `OPERATIONS` 뱃지, 14개 전용 라인 SVG 아이콘, 상단 방패 브레드크럼(`관리 포털 / 운영 현황 모니터링` + `OPERATIONS` 뱃지 + 초록 펄스 `관제 시스템 정상`), 관리 B안 고대비 메트릭 카드(상단 다크 보더 바 + 굵은 수치 폰트).
- 전역 타이포그래피: Pretendard 웹폰트 전면 import 및 전역 글꼴 지정으로 국문 심미성 및 가독성 완성.

**변경 파일:**
- `packages/ui/src/portal.css`: Pretendard 웹폰트 import, Dual Identity 테마 토큰, 사용자 화이트 세이지 vs 관리자 다크 슬레이트 사이드바, 듀얼 브레드크럼 탑바, 2컬럼 컴포저, 4열 에이전트 카드, 관리 B안 메트릭 스타일 전면 개편.
- `packages/ui/src/PortalShell.tsx`: 메뉴 라벨별 라인 SVG 아이콘 매핑(`getNavIcon`), `site === 'admin'`과 `site === 'user'` 사이드바 브랜딩 분기(방패/OPERATIONS vs 스파클/WORK), 사이드바 하단 상태 인디케이터, `TenantHeader`에 `site` 전달.
- `packages/ui/src/TenantHeader.tsx`: `site` prop 수신 및 듀얼 브레드크럼(관리 포털 / 운영 현황 모니터링 vs 생성형 AI 플랫폼 / 나의 업무 시작점), 둥근 검색창, 관제 정상 펄스 뱃지, 역할 뱃지 및 프로필 아바타 분기.
- `src/frontend/src/HomePage.tsx`: 2컬럼 컴포저(가드레일 뱃지, 사내 승인 문서 범위 칩, 추천 예시 칩 4종, 3분 이용 가이드), 4열 에이전트 카드의 SVG 아이콘 및 상태 뱃지 정합화.

**검증 및 증적:**
- 모듈 경계 빌드: `npm run build:user` (26 모듈, boundary_verified: true) PASS, `npm run build:admin` (36 모듈, boundary_verified: true) PASS.
- 환경 유효성: `npm run test:config` 19/19 전수 통과 PASS.
- 브라우저 실증: 사용자 포털(`plan1_actual_user_portal_png_1791878643276.png`) 및 관리자 콘솔(`plan1_actual_admin_dashboard_full_1791878882982.png`) 실 화면 캡처 검증 완료. 두 사이트 접속 시 1초 만에 역할과 기능이 시각적으로 즉각 구별됨.
- 서비스 상태: 사용자 포털(5173), 관리자 콘솔(5174), 백엔드 API(8000) 모두 정상 가동 중.

**미완료 및 다음 작업:**
- 상용 IdP(Entra ID) 연동 시 싱글사인온(SSO) 전환.
- 대외계 실서비스 API 연동 및 라이선스 키 적용.



## 2026-10-13 · 상세 계획 이행 및 추가 개발 독립 재검토

사용자 완료보고/추가개발 검토 요청으로 [[2026-10-13 상세 수정 계획 이행 및 추가 개발 재검토]]에계획26대비T1~T8판정을기록했다. 인증/필드/DB/Overview/디자인진척을확인했으나 실제Gateway검사전원문stream, managerreal/routermock, 동일tool재실행2회, Workflow원문checkpoint반환을DB/기관/유료호출없는대역으로재현했다. 정책/audit실행미연결·정적Agent·하드코딩정상·독립앱kind진입누락도코드확인했다. pure단일16pass/tsc0/환경19pass이며이전1660pass/30제외기록과혼용없음. 변경은재검토/계획26보완/이로그/탈민감JSON이고앱/DB/계정/서비스수정없음. 다음F1~F8실제composition/HTTP/browser보완수용이며전체계획/F60/실기관/배포완료는미인정이다.


## 2026-10-13 · 재검토 F1~F8 상세 작업 계획 작성

사용자 요청에 따라 [[28 상세 수정 재검토 F1-F8 잔여 결함 보완 작업 계획서]]를작성했다. 이전계획26/재검토보고서와현재main/manager/policy/tool/Overview/독립admin소스를대조했다. manager의privatebuffer가추가된진척을반영하고과거원문chunk판정을현재일반대화에그대로확대하지않았다. W0~W9로실제composition/SSE저장순서·모드/가격·DB정책/감사·영속멱등/승인run·실관측/KST·kind진입·UI기능/시각및회귀를정의했다. 변경은계획28/26링크/이로그뿐이며앱/DB/계정/정책변경·새시험없음. 문서링크/항목매핑은확인,Obsidian렌더미검증. 다음W0→W1순차구현이며이번범위는계획보고로완료한다.


## 2026-10-13 · 계획28 1차 보완 및 사용자 제공 040 경로 확인

사용자 승인으로 실제 앱의 출력 공개 순서·설정 기반 모델 배선·조직 DB guardrail·감사, 미관측 상태 표시, 동적 승인 링크를 보완했다. 영속 실행 서비스가 없는 Tool/Workflow/업무 Agent는 준비 중409로 제한했으며 기능 완료가 아니다. 사용자 A/관리 A+B 결정과 제품명을 유지했다. 실제 변경 파일과 시험 근거는 [[2026-10-13 F1-F8 1차 보완 구현 및 040 원본 검증 보고서]]에 기록했다. 최종 순차 backend37 passed, 별도 040 시험2 passed, 관리자 브라우저1 passed, Node22 분리 build와 환경19 passed. 초기 병렬 DB 시험 충돌은 순차 재검증으로 해소했으나 전체 suite 완료를 주장하지 않는다.

사용자가 제시한 `src/backend/migrations/040_dynamic_agent_favorites.sql`은 존재하나 파일 SHA49235a…와 기존 DB 이력 SHAca78a8…가 다르다. 원본 바이트 일치를 확인하지 못했고 041~045 기존 DB 적용은 중단했다. 백업 복원·52표 전행/열·41checksum 보존 확인, 이력 수정/업무 seed/유료 호출0. 새 시험 DB와 기존 DB 이행 상태를 구분한다. 남은 작업은 정확한040 원본 확보·후속 migration 분리/안전 이행, W4/W5 영속 승인 실행, 실제 관측기, 실행 종류별 정책/출력 수용 및 W9 통합 회귀다. 설계·시험·운영 배포 상태는 보고서 기준이며 전체 상용 기능/운영 배포 완료가 아니다.


## 2026-10-13 · 다음 작업 승인에 따른 W4 독립 Tool 영속 실행

사용자가 다음 작업 진행을 승인하여 [[29 Tool 승인 버전과 영속 실행 상세 작업 계획]]을 먼저 기록하고 신규046·Tool repository/execution/routes·registry strict검사·main/errors와 시험을 구현했다. 조직별 타인 PADMIN 승인·CAS·허용 사용자, 현재 code/mode digest, 필수 요청 UUID, accepted/dispatched/succeeded/failed/unknown receipt와재생/dispatch1회, 입력/출력 DBguardrail·원자audit·queue20·권한회수/플랫폼중지를 실제연결했다. userA/관리A+B와브랜드 결정은유지하고UI변경은없다.

최종관련57건 순차시험통과(76.96s), 새시험DB56표 전행/열·46checksum보존→59표/47migration/153security함수·재적용무변화·직접webSELECT거부·실제인증/CSRF API시험완료. 초기SQL구문/합성B관리자membership오류는수정후재검증했다. 실제변경파일·명령·증거·제한은 [[2026-10-13 W4 Tool 승인 및 영속 실행 구현 보고서]]. 기존primary041~046은040checksum문제로미적용,primary업무쓰기/seed·이력변경·유료호출0,로컬서비스복구/브라우저/기관연계/전체기능/운영배포완료가아니다. 다음은W5승인Workflow/Agent의parentRunTicket·영속checkpoint·정산취소연결이며Tool승인React화면/기관connector/실자료ACL·정확한040원본확보는남아있다.


## 2026-10-13 · W5a 승인 Workflow 버전·승인 API 부분 구현

사용자 진행 지시에 따라 [[2026-10-13 W5a 승인 Workflow 버전 및 승인 API 부분 구현 결과]]와 [[30 승인 Workflow 실행과 업무 Agent 연결 상세 작업 계획]]을 갱신했다. 새 047 migration과 Workflow strict schema/repository/API를 추가해 승인 version 제출·타인 PADMIN 승인·현재 head 카탈로그를 disposable DB에서 연결했다. 승인 definition revision과 decision CAS revision을 분리했다. 임의 client DAG는 실행되지 않으며, 승인 version run도 parent ledger 부재로 409를 유지한다. Canvas에 준비 중 상태를 표기하고 실행 버튼을 비활성화했다.

최종 W5a/API/schema/migration 20 passed, W4/W5 관련 회귀 73 passed in 73.61s (revision/CAS 최종 수정 반영), 관리자 build 경계 검증 및 Playwright 1 passed. 기존 SQL fingerprint/checksum 보존, primary 미적용. W5 전체, 10 업무 Agent, 운영 배포로 확장하지 않는다. 다음은 reject/revoke·회수·Tool 의존 테스트를 보완하고 계획 Task2 parent run/checkpoint 및 published Agent child 연결이다.


## 2026-10-13 · 승인 Workflow 실행 원장과 Agent Tool 연결

사용자의 계속 진행 승인 및 작업 중 상태 문의에 따라 [[30 승인 Workflow 실행과 업무 Agent 연결 상세 작업 계획]]의 실행 기반을 구현·검증했다. [[2026-10-13 W5b 승인 Workflow 실행 원장 및 Agent Tool 연결 구현 보고서]]에 실제 파일/근거/실패·수정·미완료를 기록했다. 048 새 parent/step FORCE RLS·code/mode seal·binding/child FK·현재 권한 gate·lease/cancel/recovery, workflows identity/bindings/repository/service/routes·main/errors, Canvas/shared API계약·backend/browser 시험 및 전용 fixture reset을 변경했다. 기존000~047 원본 이력과 과거 NULL seal을 보존하고 primary에는 적용하지 않았다.

승인 version 실행202/재생200·본인poll/CAS취소·안전최종결과, published Agent 기존Gateway/정산 및 Tool영속receipt를 실제연결했다. PII차단 코드 미허용으로 자식running 잔류, receipt 재시도UUID 변경, claim전승인회수 대기잔류를 보완했다. 넓은 관련157pass(마지막 시작전경계보완 이전)와 최종40pass는 별도/중복이다. Node22 user26/admin37 코드경계pass, browser2pass(실제API1·HTTP대역계약1), 기존62표/48checksum보존·source000~046의47SHA변경0→fixture64표/49migration/166함수·34보호표. 안전증거는 `260.테스트/evidence/W5-Workflow-20261013`에 저장했다. browserfixture/자격증명/연결 정리를 확인했다.

사용자A/관리A+B·브랜드 결정 유지. 실제앱코드/시험DB 구현과 primary사용/상용배포는 구분한다. 040checksum 불일치로041~048primary미적용, 이력변경/primaryseed/paid0. 10업무Agent는 여전히 준비중이며 실제승인head/manifest 연결·업무수용, 관리B Tool/Workflow승인React UI, interrupted수동재개/분산복구, 실제기관모델/RAG/Entra/UAT·전체suite/운영배포·Obsidian렌더는 남아있다. 다음은10종binding/업무별시험→관리B승인UI→계획28 W6~W9다. 기존W5a runtime409 설명은 당시이력으로보존한다.


## 2026-10-14 · 업무10종 연결과 관리B 승인 확장 상세 계획 제안

사용자의 상세 작업 문의에 따라 [[31 업무 Agent 10종 승인 연결 상세 작업 계획]], [[32 관리 B안 Tool Workflow 승인 화면 확장 상세 작업 계획]]을 작성했다. 현재 source에서 업무execution_ready=false/use_case_execution미조립·service.py부재, rawfetch tenant/scope누락과고정‘승인10종’표시, realToolstub409, 승인settings/evidence/dynamic3유형과Tool/Workflow50개목록·상세/의견계약부족을확인했다.

제안범위는업무manifest/strictinput-output·조직별승인head/code/mode/자료권한·실제Workflow/Agent/Tool원장연결·poll/취소/안전출처와10종별업무수용, 관리B의Tool/Workflow신청·목록/상세/현재검증/diff/검토의견/타인결정/철회·deep link/반응형수용이다. 기존A/A/B디자인결정은변경없음. genericWorkflow직접API에서도업무정책을검사하고manifest/code변경은새승인을필요로한다.

이전계획30의‘10종→B안’보다공통계약→외부Tool없는회의록03의1종종단→관리B확장→나머지9종순서를권장하는새제안이다. 1종으로공통계약을검증하고나머지9종을실제승인UI에서검토하도록하는이유이며사용자확정/개발완료로표시하지않는다. 실제connector/기관자료없는항목은시험연결·실연동·업무품질·운영DB이행을각각구분한다. primary040경계/000~048보존을유지하고049/050은번호예약뿐이다.

변경한실제파일은계획31·32와이기록·설계23·계획30의연계문단뿐이다. source대조/10종ID·역할/Tool명·문서상호링크/한글문서검사만수행했으며새앱/DB/정책/테스트/외부승인/배포변경없음. Obsidian앱렌더미검증. 다음착수단위는계획31 Task1공통승인연결이며실제기관자료·업무검토자는후속수용조건이다.


## 2026-10-14 · 사용자 범위 축소 승인 및 회의록 계약 첫 구현

사용자는 나머지9종을 추후 확장하고 다음 작업을 진행하도록 승인했다. 계획31·32에 현재 범위를 회의록 AGENT_03 한 종과 관리B 승인 확장으로 기록했다. [[2026-10-14 회의록 Agent 계약 검증 1차 구현 결과]]에실제파일·검증·미완료를남겼다. `app/use_cases/meeting.py`의strict입력/결과·원문인용/담당자/기한·manifestdigest와`tests/test_meeting_contract.py`를추가했으며프로젝트venv단위시험9pass(0.31s)다. 의미품질/DB/API/browser/전체suite완료로확대하지않는다.

실행runtime/승인head/공개결과에조립되지않아execution_ready=false를유지한다. primary040/기존SQL변경·새migration·seed·유료호출/배포0. A/A/B방향유지. 다음은계약을봉인한조직별승인version/head·현재권한검사/원자audit→회의록실행/조회/취소→관리BTool/Workflow승인UI이며나머지9종은후속이다.


## 2026-10-14 · 회의록 승인 연결·메모 실행 API·사용자 UI

사용자의 다음 작업 승인에 따라 [[2026-10-14 회의록 Agent 승인 연결 및 실행 API 화면 구현 보고서]]에실제파일·시험·실패/보완·잔여를기록했다. 신규049의caseID/계약digest/기반revision·불변seal·조직업무head FORCE RLS/타인승인/CAS, workflows approval/repository/identity/service와use_cases service/routes·main, 사용자화면/API types·순차시험/전용fixture를변경했다. 입력→LLM과최종LLM text binding을강제하고일반Workflow실행에도같은원문근거검사를적용한다. 실제인증HTTP202/poll/재생200·CSRF/타인조회차단·철회/취소를시험했다.

넓은관련132pass(최종binding보완이전), 최종39pass(이행강화포함), browser4pass(실제API2·HTTP계약대역2), Node22 user26/admin37코드경계pass. 기존64표의과거행/열·49checksum/sourceSHA보존→fixture65표/50migration/169함수/35보호표·재적용0·개인fixture/자격증명제거·연결0. 안전증거는`260.테스트/evidence/Meeting-runtime-20261014`다. 테스트수를중복합산하지않는다.

회의록텍스트메모4000자 실행 연결은실제코드에서완료했으나기본DB041~049는040경계로미적용·유료호출/primaryseed/배포0. 구조화mock출력과실제모델/회의품질수용은구분한다. 관리B의Tool/Workflow신청·상세/검증/비교·검토의견/이력·결정/철회는다음작업이다. 전체manifest snapshot/자료선택·회의일/상대날짜·수동재개·다중폭검수는후속이며나머지9종추후확장과A/A/B방향을유지한다. 전체계획/운영완료는아니다.


## 2026-10-14 · 관리 B Tool Workflow 승인 서버 구현·검토 완료

사용자의 진행 승인에 따라 [[2026-10-14 관리 B Tool Workflow 승인 확장 구현 보고서]]에 실제 서버 변경·시험·수정·미완료를 기록했다. 신규050 review 원장·필수 의견·현재 검증/정확 상세/서명 cursor/이력/신청 지원/엄격 검증·신규 AGENT_03 불변 manifest snapshot을 구현했다. 현재 Tool 모드와 공개 대상 재검사 2건을 코드 검토에서 보완하고 최종 covering DB/API46pass 및 재검토 통과를 확인했다. 실제 변경 파일·명령·실패 기록은 B-Approval-20261014 증거에 보존했다.

화면 구현과 브라우저/다중폭 검수는 진행 중이다. A/A/B·브랜드·나머지9종 추후 확장 결정 유지. 기존 migration000~049 수정 없이 신규050을 시험DB에서 검증했으며 primary040 경계/기본DB 이행·seed·유료 호출·배포0이다. 실제 서비스 업무수용/기관모델·Entra/UAT/운영완료로 확대하지 않는다.


## 2026-10-14 · 마지막 작업 재확인·관리 B 승인 확장 선별 수용 완료

사용자의 마지막 작업 확인과 계속 진행 승인에 따라 실제 source를 재확인하고 [[2026-10-14 관리 B Tool Workflow 승인 확장 구현 보고서]]를 갱신했다. Tool·Workflow 신청/검색/페이지/정확상세·검증/구조화비교/검토의견/이력·타인승인/반려/현재head철회·deep link 및 관리A홈 집계를 React/API에 연결했다. 사용자A·관리A·승인B와 생성형 AI 플랫폼 명칭을 유지하며 AGENT_03만 현재 업무범위다.

마지막 오류4건(승인후자체revision검증실패, PublishedRun publicationrevision필드누락, Tool선택변경시bindingretarget, 게시Agentrefresh의staleexactversion)과 부수화면문구/접수표시를 보완했다. 변경 실제파일은050 SQL·app/assets/published.py·관련HTTPtests·WorkflowApprovalRequest.tsx·AdminHomePage.tsx·tool-workflow-approvals.spec.ts며 전체화면파일/명령/증거는 보고서에 열거했다. 이번 corrective4/3파일은 exactpre/post를 영속보존했다. 초기변경baseline 일부 임시자료가 사라져 기존귀속한계는 명시했다.

최종서버지정23pass, Node22user26/admin43경계pass, 고유browser15pass(실제임시DB/API경로6·HTTP대역9; mock품질과실기관수용구분), 실제1440/1024/768캡처 및 keyboard/narrowback검수다. 중복실행14+2+1을 합산하지 않는다. 서버/화면재검토와최종통합검토 Spec/QualityPASS·확인된미해결finding0. 증거는 `260.테스트/evidence/B-Approval-20261014`에보존했다. 시험harness종료·5173/5174닫힘·강제서비스종료0이다.

기본DB040checksum경계는유지·041~050primary미이행이며기존000~049변경/이력우회·primaryseed·유료호출·운영배포0. 기본DB적용/실제기관Tool·모델·자료·Entra/업무품질·UAT/전체suite·분산복구·상대날짜/자료선택은미완료이고나머지9종은추후확장이다. 다음작업은이미계획한잔여범위와실제기관수용조건을정리한뒤순차진행하며이번선별수용을전체서비스개통으로확대하지않는다. Obsidian파일동기화완료·앱readingview미검증이다.


## 2026-10-14 · 사용자 화면 테스트용 서비스 구동

사용자 요청으로 서비스를 구동했다. 기존 service_control로 사용자5173/관리5174는 시작됐으나 backend는기본DB에 security.workflow_recover가없어시작실패했다. 기존DB migration/040이력우회없이 방금시작한소유frontend를정상종료한뒤 scripts.portal_test_server를별도manual-preview소유프로세스로구동했다. 별도marker테스트DB에전체최신migration/합성계정을준비하고 API8000·user5173·admin5174를loopback에서실행했다. 실제source수정0·기본DB/기존credential변경0·paid0·운영배포아니다.

검증: /api/v1/health, /user/home, /manage/admin 모두HTTP200. 테스트loginID a-u1(사용자), a-adm(조직관리), p-a(플랫폼관리);비밀번호는A05-fixture.json이참조하는현재fixture-secrets.json의passwords에서확인하며원문을보고서에기록하지않았다. 소유실행기록 src/backend/.runtime/manual-preview-process.json,비공개로그 manual-preview.log. 이번구동은자동시험이아닌사용자수동검토용으로유지하며 종료시테스트DB/계정파일은harness가정리한다. 기본DB는유지된다. 새테스트DB에는기존개인자료/게시승인workflow가복사되지않았으므로등록·신청·승인이필요한기능은테스트상태에따라빈목록이정상이다. 기존테스트port를사용하므로추가자동browser/DBfixture시험은이환경을종료한뒤진행한다.


## 2026-10-14 · 기존 계정 기반 DB 이행 착수

사용자가 기존 DB 문제 해결과 기존계정/데이터 기반 테스트를 승인했다. [[33 기존 개발 DB 원본 복구 및 최신 기능 이행 계획]]을 작성하고 원본/체크섬 전수대조·비공개 백업/복원DB 이행시험→검토→기본DB 신규migration반영→기존설정서비스수용 순서로 진행한다. 실제구현/운영배포는구분하며040이력값수정/runner검사우회/재seed·유료실행은금지한다.

검증용harness PID40845가소유명령과일치함을확인한뒤정상종료했다. cleanup:pool0/fixture·비공개임시계정파일·source store제거, 기존DBcluster유지. 기존app.env는mode mock/execution_enabled true이며키·DSN/기존비밀번호·데이터를변경하지않았다. 현재원본040복구와백업복원시험은진행중으로기본DB업그레이드완료가아니다. 서비스는복원시험동안잠시정지한다.


## 2026-10-14 · 기존 DB 백업 복원 검증과 비파괴 데이터 이관 대안

계획33 Task1에서적용41개중040만checksum이상이확인됐고정확원본은찾지못했다. 비공개pg_dump와환경/기존계정정보/빈source-store백업을보존했으며별도복원DB의53표기존열·전행digest와13계정passwordhash가같았다. strict runner는040에서실패해전후행/열이같으며원본DB/이력/SQL변경0이다. 전체DDL/RLS/grants/sequence의동일지문을별도로측정한것은아니므로row/column증거와rollback구조의범위로판정한다. 활성run/unknown/예약금0·기존call11 settled·유료호출0이다. 문서2건metadata는보존됐으나현재source-store파일0으로원문조회는미검증이다.

백업/복원단계검토후계획33에비파괴이관대안을추가했다. 기존DB/원래이력은남겨두고새markerDB에현재000~040정상적용→52업무표데이터이관(infra기존이력은원본DB/백업에보존)→041~050정상적용→보존/권한/sequence/login/API시험→검토후되돌릴수있는local설정전환이다. 기존계정/비밀번호/자료로최신기능테스트라는사용자승인목적을충족하며원본040복구성공·기존DB직접업그레이드와구분한다. 추가계정seed/기존checksumrewrite/검사우회/primarytruncate/유료실행은하지않는다. 현재이관시험중으로서비스복구는아직미완료다. Task1비밀없는증거는 DB-continuity-20261014에기록했다.


## 2026-10-15 · 040 현재 개발 보류 해소·기존 계정 서비스 전환 완료

사용자가040원본미확인으로계속보류되는상태의처리를요청했다. [[2026-10-15 기존 계정 데이터 보존 및 040 개발 보류 해소 보고서]]에최종결과·실제파일·검증·한계를정리했다. 원본DB/옛41이력과백업을보존하고새DB에현재000~040정상적용→기존52업무표/13계정이관→041~050정상적용→검토→localDSN/active-fixtureDB명만전환했다. 원본checksum변경/검사우회/재seed/비밀번호reset/SQL수정/paid0이다.

현재적용51/source51·checksum불일치0·미적용0·040일치, 서비스8000/5173/5174각200. 실제검증clone활성12로그인/156역할읽기·live3계정로그인/logout/18역할읽기통과. 원본53행/catalog보존·이관52oldcolumn전행/accounthash일치·FK96위반0. 세서비스실행유지, 기존개발문서02비밀번호사용가능. 실제변경파일은backend/.runtime/app.env와active-fixture.json이고HMAC/키/credential/mode보존을root도독립확인했다. 증거 DB-continuity-20261014에보존했다.

**현개발DB의040보류는종료**하며옛DB의ca78원본미확인은보존이력으로분리한다. 과거문단의primary040미이행/서비스정지표현은당시원본직접이행상태이력이며현재활성DB의상태가아니다. 정확옛원본복원성공으로표시하지않는다. 기존원문2건파일부재·전체쓰기/UAT·실기관연동/모델·나머지9종은별도잔여다. 일회성전환script 재사용전Minor오류처리/검증보완은검토보고서에남겼고현재전환수용의Critical/Important0과구분한다.


## 2026-10-15 · 회의록 문서·날짜·품질 보완 착수와 계약 단위 완료

사용자가'문서자료선택/회의일·상대날짜처리/실제회의록품질' 기능진행을승인했다. [[34 회의록 문서 자료 날짜 처리 및 품질 평가 상세 개발 계획]]을작성하고현재scope AGENT_03만유지했다. Task1 meeting.py/revision2, meeting_dates.py, meeting_quality.py, synthetic평가fixtures와단위시험을구현했다. max3 exactdocumentrefs·memo또는문서필수·기준회의일strictISO·memo/선택문서의quote/owner검사·달력기한규칙/미확정사유·구조적평가/사람검토기준을추가했다.

단위76pass(0.31초)·코드spec/qualityPASS이며처음47pass후검토에서모델due_expression누락시월말등미지원표현warning이사라지는1건을보완했다. 날짜모델임의값불일치는차단하고기준일없는/영업일/모호한기한을확정하지않는다. pure단위완료이며DB/API/UI/실제모델품질통과는아니다. 후보문서현재ACL/원문검증·실행context봉인/child/최종조회guard·qualityappend-onlyledger/new051은Task2구현중이다. 이후Task3UI와브라우저/폭별검수/기관실측조건을진행한다. 나머지9종/paid/운영배포0.

현재개발DB040보류는이미해소(51source/51적용일치)했고Task2fixtureDB시험전에소유서비스만정상정지하여공유role충돌을피한다. 신규migration/코드seal은freshWorkflow승인이필요하며과거snapshot/결과를소급변환하지않는다. 증거 Meeting-context-20261015에저장했다. 품질우선기준의선택적질문은답변전정확성·누락·담당자·기한4기준으로준비하며mock/구조검사를의미품질합격으로표시하지않는다.


## 2026-10-15 회의록 기능 보완 — 백엔드 구현·검토 중

사용자 요청: 문서 자료 선택, 회의일·상대 날짜 처리, 실제 회의록 품질 보완(AGENT_03). Task1 계약·날짜·구조 평가 76개 순수 시험 및 재검토 완료. Task2 문서 원문/권한 검증·불변 입력·품질 기록 API와 신규 051 migration 구현 후 독립 검토 중이다. 기존 SQL 000–050 51개 파일은 변경하지 않았다.

변경 파일과 명령·초기 실패/수정·결과는 [[task2-report]] 및 [[34 회의록 문서 자료 날짜 처리 및 품질 평가 상세 개발 계획]] 참조. 계약/이력 시험 103개, 실행 회귀 71개 통과; 후속 변경은 12개 문서 context, 1개 실제 HTTP, 6개 child 경계 시험으로 확인했다. 서로 겹치는 실행이므로 합산 완료 건수로 표현하지 않는다. 증거는 `200.프로젝트실행/260.테스트/evidence/Meeting-context-20261015`에 보존했다.

미완료: 독립 백엔드 검토, 사용자 문서·회의일·품질 UI, 브라우저 수용, 최종 통합 검토, 실제 개발 DB 백업/051 적용 및 서비스 재구동. 현재 세 소유 서비스는 DB 시험을 위해 중지했으며 실제 DB·클러스터·계정 데이터는 보존했다. 유료 호출 0건이며 실제 모델 의미 품질·업무 UAT 합격으로 주장하지 않는다. 다음은 백엔드 검토 종료 후 화면 구현이다.


## 2026-10-15 · GitHub 원격 저장소 소스 배포 및 이행 이력 관리
사용자 요청으로 현재까지 개발된 소스 일체를 원격 GitHub 저장소(`https://github.com/HwangByungChul/ai_portal.git`)에 배포하고, `docs/Obsidain/200.프로젝트실행/290.이행` 내 `배포` 폴더를 생성하여 이력을 관리하도록 조치했다.
- **배포 저장소**: `https://github.com/HwangByungChul/ai_portal.git` (main 브랜치)
- **생성 문서**: `docs/Obsidain/200.프로젝트실행/290.이행/배포/01 배포 관리 및 이력.md`
- **보안 조치**: `.gitignore`에 비공개 문서 격리 패턴(`docs/Obsidain/**/*(비공개).md`)을 명시하여 로컬 인증·시연 계정 정보 및 `.env` 비밀정보 유출을 방지했다.
- **배포 범위**: Frontend 분리 웹 포털(apps/user-web, apps/admin-web, packages/api-contract, packages/ui), Backend 비동기 API 서버(FastAPI) 및 000~051 DB 마이그레이션 스크립트, AI 파이프라인 및 테스트 스위트, 환경 설정 JSON 일체.
- **다음 작업**: 회의록 화면 UI 완성 및 브라우저 수용성 검증, 290.이행 단계 배포 매뉴얼 및 자동화 스크립트 체계화.


## 2026-10-15 사용자 품질 우선 기준 확정

사용자는 별도 정의된 기준은 없으며 **결정사항·액션아이템 정확성을 우선**한다고 답변했다. 이에 정확성을 첫 평가 항목으로 표시하고 실제 품질 수용의 최우선 기준으로 삼는다. 누락·담당자·기한 검토는 보조 확인 항목으로 유지한다. 아직 정량 합격선·업무 정답 세트는 확정되지 않았으므로 임의 합격 점수나 실제 모델 품질 통과를 선언하지 않는다.

마지막 작업 확인: 백엔드 계약/원문·날짜·품질 API와 문서 권한 동시성 보완은 독립 재검토 통과. 사용자·관리자 빌드는 통과했으나 화면 브라우저 검증이 2개 통과/1개 실패 상태에서 중단되어, 해당 실패부터 원인을 확인하고 이어서 진행한다. 신규051 실제 개발 DB 적용과 서비스 재구동은 아직 미완료다. [[2026-10-15 회의록 문서 날짜 및 품질 기록 구현 보고서]] 참조.


## 2026-10-15 · 시각적 블록 조립형(Drag & Drop) UI Studio 개발 검토 및 상세 계획 수립
사용자 요청으로 제안 시안(`4.4-03_Workflow_Canvas.png`)에 부합하는 시각적 블록 조립형(Drag & Drop) UI Studio 개발 검토 및 Obsidian 기록을 진행했다.
- **사용자 결정**: 제안 시안 수준의 완전한 비주얼 캔버스(Component Library + 드래그 앤 드롭 노드/엣지 + 속성 인스펙터 + 위저드 연계) 및 `@xyflow/react`(React Flow v12) 라이브러리 도입 확정.
- **생성 문서**: [[100.프로젝트계획/35 시각적 블록 조립형 UI Studio 상세 구현 계획]]
- **핵심 아키텍처**: 3-Pane 구조(컴포넌트 라이브러리, 무한 캔버스, 노드 인스펙터), 7단계 위저드 상단 바, 커스텀 노드 7종, 백엔드 WorkflowDefinition DAG 양방향 변환 계층 및 실행 모니터링 시각화.
- **다음 작업**: `@xyflow/react` 의존성 설치, 3-Pane 캔버스 레이아웃 쉘 및 드래그 앤 드롭 컴포넌트 팔레트 구현 착수.


## 2026-10-15 · 시각적 블록 조립형 UI Studio 1차 구현 및 포털 빌드 검증 완료
사용자 승인에 따라 제안 시안(`4.4-03_Workflow_Canvas.png`) 규격의 시각적 블록 조립형(Drag & Drop) UI Studio를 구현하고 포털 빌드 경계 검증을 완료했다.
- **구현 파일**:
  - `src/frontend/src/workflow/workflowTypes.ts`: 7대 컴포넌트 팔레트 카테고리(트리거, 프롬프트, LLM, RAG, Tool, 로직, 응답) 및 StudioNodeData 정의
  - `src/frontend/src/workflow/workflowStudio.css`: 글래스모피즘 기반 3-Pane 레이아웃, 커스텀 노드/핸들 및 위저드 스타일링
  - `src/frontend/src/workflow/WorkflowCustomNodes.tsx`: 입출력 포트 핸들, 카테고리 컬러 코딩, 복제/삭제 액션 및 실행 상태 배지를 지원하는 커스텀 Flow 노드
  - `src/frontend/src/workflow/WorkflowPalette.tsx`: HTML5 Drag & Drop 지원 좌측 컴포넌트 라이브러리 및 검색 필터링
  - `src/frontend/src/workflow/WorkflowInspector.tsx`: 선택 노드별 파라미터(모델, 프롬프트, 도구, 지식베이스 등) 동적 편집 우측 패널
  - `src/frontend/src/workflow/workflowAdapter.ts`: React Flow Graph ↔ 백엔드 WorkflowDefinition DAG 양방향 변환 및 위상 정렬/순환 검증 유틸리티
  - `src/frontend/src/workflow/WorkflowStudio.tsx`: 7단계 위저드 상단 바, 자동 정렬, DAG 유효성 검사, 실행 모니터링 콘솔을 포함한 메인 에디터
  - `src/frontend/src/WorkflowCanvasPage.tsx`: 기존 승인 실행 기능과 시각적 UI Studio를 탭으로 통합 연동
- **검증 결과**:
  - `@xyflow/react`(React Flow v12) 설치 및 Node 22 환경 컴파일 검증
  - `npm run build:admin` 통과 (`modules: 49, boundary_verified: true`)
  - `npm run build:user` 통과 (`modules: 28, boundary_verified: true`)
  - `npm run build` 통합 빌드 스크립트 전원 통과 (오류 0건)
  - 실제 브라우저 포털(`http://127.0.0.1:5174/manage/admin/workflows`) 접속 및 관리자 로그인 검증 완료
  - 3-Pane 레이아웃(상단 7단계 위저드 바, 좌측 컴포넌트 팔레트, 중앙 React Flow 캔버스, 우측 속성 인스펙터) 및 노드 선택 상호작용 정상 동작 확인
  - 스크린샷 증적 보존: `workflow_studio_view_1792039895112.png`
- **다음 작업**: 드래그 앤 드롭 노드 추가 및 저장/불러오기 시나리오 고도화, 실제 백엔드 DAG 저장/실행 연계 시험.


## 2026-10-15 · AI Studio 통합 메뉴 및 Hub 구조 상세 구현 계획 수립 (개선안 1안)
사용자의 개선안 1안(사이드바 메뉴 그룹화 및 통합 Hub 구축) 승인에 따라 상세 구현 방안 검토 및 Obsidian 기록을 완료했다.
- **사용자 요청·결정**: Agent Builder와 Workflow Canvas의 분산으로 인한 혼선을 해소하기 위해 단일 진입점인 `AI Studio` 대분류 메뉴 통합 및 상단 탭 전환 Hub 구조 채택.
- **생성 문서**: [[100.프로젝트계획/36 AI Studio 통합 메뉴 및 Hub 구조 상세 구현 방안]]
- **핵심 설계**:
  - 관리자 사이드바에 `AI Studio (제작)` 단일 Hub 메뉴 제공 및 분산된 중복 메뉴 정리
  - AI Studio 진입 시 상단 서브 탭으로 `[ 🤖 단일 Agent 빌더 ]` ↔ `[ ⚡ 다단계 Workflow 캔버스 ]` 즉시 전환
  - 기존 경로(`/manage/admin/builder`, `/manage/admin/workflows`) 하위 호환성 및 URL 쿼리 파라미터 연동
  - Agent Builder와 Workflow Studio 간 유기적 상호 이동 안내 배너(Bridge) 배치
- **다음 작업**: `AIStudioHubPage.tsx` 컴포넌트 구현 및 `apps/admin-web/src/App.tsx` 라우팅 통합 반영.


## 2026-10-15 · AI Studio 통합 메뉴 및 Hub 구조 1차 구현 및 포털 빌드 검증 완료
사용자 승인(개선안 1안)에 따라 단일 진입점인 `AI Studio` 통합 Hub 컴포넌트를 구현하고 관리자 사이드바 네비게이션을 개편했다.
- **구현 파일**:
  - `src/frontend/src/AIStudioHubPage.tsx`: 상단 탭 전환(`[ 🤖 단일 Agent 빌더 ]` ↔ `[ ⚡ 다단계 Workflow 캔버스 ]`), URL 쿼리 파라미터(`?tab=builder|workflow`) 동기화 및 탭별 상호 연계 안내 배너(Bridge) 탑재
  - `src/frontend/apps/admin-web/src/App.tsx`: 사이드바 메뉴에 `✨ AI Studio (제작)` 단일 Hub 메뉴 등록, 중복 메뉴 정리 및 기존 경로(`/manage/admin/builder`, `/manage/admin/workflows`) 하위 호환 매핑
- **검증 결과**:
  - `npm run build:admin` 통과 (`modules: 50, boundary_verified: true`)
  - `npm run build:user` 통과 (`modules: 28, boundary_verified: true`)
  - `npm run build` 통합 빌드 스크립트 전원 통과 (오류 0건)
  - `admin-frontend` 서비스(포트 5174) 재기동 완료 및 정상 서비스 중
- **다음 작업**: 실제 관리자 화면에서 Agent 제작 후 워크플로우 캔버스로의 데이터 연동 고도화.

## 2026-10-15 · MCP 및 외부 Tool 연동·노코딩 자동변환 상세 구현 계획서 수립 (T-035)
사용자 요청(기술요건 T-035 필수 항목의 완료 여부 문의 및 잔여 작업 계획 수립 지시)에 따라 MCP 및 외부 Tool 연동, 배포 승인 상태별 동적 엔드포인트 전환, 노코딩 Auto-Wrapping 생성 환경의 상세 구현 계획서를 수립하고 Obsidian에 기록했다.
- **사용자 요청**: T-035 필수 기술요건(배포 승인 상태에 따른 Dev/Prd 동적 전환 아키텍처 및 OpenAPI/WSDL/JDBC/금융전문 자동변환 노코딩 환경)의 개발 완료 여부 검토 및 잔여 작업에 대한 상세 구현 계획서 보고.
- **검토 결과**: 현재 코드는 고정 사전정의 Tool 3종 및 Fixture Mock 어댑터 수준이며, 본 기능은 **미구현(개발 미완료)** 상태로 분류됨.
- **생성 문서**: [[200.프로젝트실행/240.설계/35 MCP 및 외부 Tool 연동 노코딩 자동변환 상세 구현 계획서]]
- **핵심 아키텍처 및 계획**:
  - 에이전트 배포 승인 상태(Draft vs Approved/Published)에 연동되는 동적 라우팅 게이트웨이 및 암호화 Credential Vault 설계
  - 수동 코딩 없는 4대 인터페이스(OpenAPI 3.0, WSDL SOAP, JDBC RDB, 금융 전문 ISO 8583/EAI/FEP) Auto-Wrapping 변환 엔진 설계
  - DB 신규 마이그레이션(`041_tool_mcp_autowrap_schema.sql`) 및 `tool_definitions`, `tool_versions`, `tool_endpoint_profiles`, `tool_audit_logs` 테이블 정의
  - 관리자 노코딩 마법사 UI(`ToolAdminPage.tsx`) 및 4단계 추진 일정(Phase 1~4) 수립
- **다음 작업**: 사용자 검토 및 개발 착수 승인 시 Phase 1(DB 스키마 마이그레이션 및 동적 라우팅 게이트웨이 코어) 구현 진행.

## 2026-10-15 · T-035 MCP 및 외부 Tool 연동·노코딩 자동변환 1차 구현 및 검증 완료
사용자 승인("네 진행 바랍니다.")에 따라 기술요건 T-035(배포 승인 상태별 Dev/Prd 동적 분기 라우팅 아키텍처 및 OpenAPI/WSDL/JDBC/금융전문 노코딩 Auto-Wrapping 생성 환경)을 구현하고 검증을 완료했다.
- **구현 파일**:
  - `src/backend/migrations/052_mcp_tool_autowrap_and_dynamic_routing.sql`: 정의·버전·프로파일·감사로그 4대 테이블 스키마
  - `src/backend/app/tools/credentials.py`: 표준 라이브러리 기반 안전한 자격증명 인증 암호화 볼트
  - `src/backend/app/tools/parsers/`: 4대 규격(OpenAPI 3.0, WSDL SOAP, JDBC 가상화 뷰, 금융 전문 바이트 패커) 파서 모듈
  - `src/backend/app/tools/dynamic_gateway.py`: 배포 승인 상태(`draft` vs `approved_published`) 연동 동적 라우팅 게이트웨이
  - `src/backend/app/tools/autowrap_routes.py`: 노코딩 스펙 파싱, 등록, 동적 도구 목록 및 라우팅 호출 API
  - `src/frontend/src/ToolAdminPage.tsx`: 연계 Connector & MCP Tool 관리 및 노코딩 마법사 페이지
  - `src/frontend/apps/admin-web/src/App.tsx`: `🔌 연계 Tool & MCP` 사이드바 메뉴 및 라우트 연결
  - `src/backend/tests/test_mcp_tool_autowrap.py`: 7개 핵심 단위/통합 테스트 스위트
- **생성 문서**: [[200.프로젝트실행/250.구현/36 T-035 MCP 및 외부 Tool 연동 노코딩 자동변환 구현 결과]]
- **검증 결과**:
  - 백엔드 테스트: `pytest tests/test_mcp_tool_autowrap.py` 7개 전원 통과 (0.53s, 암복호화, 4대 파서, 동적 라우팅, 보안 차단)
  - 프론트엔드 빌드: `npm run build:admin` (`modules: 51`), `npm run build:user` (`modules: 28`), `npm run build` 통합 빌드 전원 통과 (오류 0건)
- **다음 작업**: 실제 외부 레거시/금융 FEP 시스템 연계 검증 및 워크플로우 캔버스 내 Tool 노드 데이터 매핑 고도화.
## 2026-10-16 · 미완료 기능 잔여 상세개발 계획 작성

사용자 요청: 현재 미완료건의 상세개발서를 작성하고 Obsidian에 기록.

- 최신 기능 감사보고서(2026-10-12), 화면·기술 대조표, 계획29~36, 회의록 Task1~3 증거, W4/W5, 관리 B 구현, T-035 구현, 기존 계정 DB 전환 보고서를 확인했다.
- 통합 상세계획 [[100.프로젝트계획/37 미완료 기능 잔여 개발 통합 상세 계획]]을 작성했다. 회의록 migration051 이행 및 서비스 복구, AGENT_03 업무 품질 수용, UI Studio 저장·승인·실행 연결, T-035 connector 실연동, 장기 Workflow 수동복구, F/IA/T 잔여 재대조와 독립 기능 패키지를 포함한다.
- 완료된 구현과 남은 실연동·업무 수용·운영 배포를 분리했고, 과거 F/IA/T 집계는 10월 12일 기준으로 표시했다. PPTX/OCR 보류·거버넌스 제외·나머지9 Agent 후속 결정과 기존 SQL checksum 보존 조건을 유지했다.
- 변경 파일: 계획37 및 본 작업 로그. 앱 코드·DB·서비스·운영 설정 변경 없음. 검증은 문서/증거/소스 현황 대조이며 신규 시험을 실행하지 않았다.
- 미완료: 계획 문서이므로 개별 Workstream의 별도 착수 승인·개발·실제 수용은 아직 수행하지 않았다. 우선순위는 계획37 §13에 기록했다.

## 2026-10-16 · 잔여 기능 개발 진행 — migration 051 및 Workflow Studio 안전 보정

사용자 요청: 미완료 기능 잔여 개발 진행.

- **회의록 DB 이행**: 활성 개발 DB를 식별하고 000~050 checksum 보존을 확인했다. 비공개 runtime 경로에 전체 백업을 생성한 뒤 별도 fixture DB에 복원해 기존 67개 테이블 데이터와 스키마/RLS/정책/함수·trigger·constraint를 대조했다. 활성 DB에는 051만 적용했다. 신규 회의록 표는 비어 있고 FORCE RLS 적용, 052 미적용이다.
- **서비스 생존 확인**: API8000 health, 사용자5173 `/user/home`, 관리자5174 `/manage/admin` 모두 HTTP 200. 서비스는 로컬 개발용으로 기동 중이다.
- **Workflow Studio 코드**: `src/frontend/src/workflow/WorkflowStudio.tsx`에 승인 버전 선택을 추가했고, 실행 실패를 모의 성공으로 표시하던 폴백을 제거했다. 캔버스 편집 데이터 미저장 및 캔버스 그래프와 승인 버전 실행의 비연결 상태를 UI에 안내한다.
- **계약 조사 결과**: 기존 승인 Workflow API로 개인 초안을 저장/조회할 수 없고 별도 영속 초안 테이블도 없다. 승인 endpoint 오용은 피했다. CAS/RLS를 갖춘 draft API·schema 및 그래프↔strict definition 변환이 다음 구현이다.
- **실제 변경 파일**: `src/frontend/src/workflow/WorkflowStudio.tsx`; Obsidian 계획 [[100.프로젝트계획/37 미완료 기능 잔여 개발 통합 상세 계획]], 구현 중간 보고 [[200.프로젝트실행/250.구현/2026-10-16 잔여 기능 개발 중간 보고서]], 작업 로그.
- **검증·증거**: DB backup/restore 대조 및 적용 후 구조 증거는 비공개 `src/backend/.runtime/backups/migration051-20261016/`에 보존했다. 051 checksum은 `27ee90023c2ed9172b16cef74aecfc90906d05698d73f95ddd0fb1cf2bc2db09`. 사용자/admin/API의 세 HTTP 확인은 통과했다. 자동 테스트·build·브라우저 검증은 실행하지 않았다.
- **미완료 범위**: 기존 계정 로그인/핵심 API와 회의록 권한 시나리오 회귀, 실제 회의 업무 품질 수용, Workflow Draft 저장/복원·승인 제출/trace 연결, 장애 재개, T-035 실기관 연결, F/IA/T 최신 재대조.
- **다음 작업**: Workflow Draft tenant/owner RLS·revision/CAS 계약을 새 migration/API로 설계·구현하고 Studio에서 저장·불러오기 및 승인 definition 변환을 연결한다. 회의록 API 및 기존 흐름 수용은 별도 검증 단계에서 진행한다.

## 2026-10-16 · Workflow Studio 초안 저장 구현 및 migration 이행

사용자 요청: 남은 기능 개발 계속 진행.

- **설계·구현 결정**: 기존 승인 Workflow API는 immutable approval version을 관리하므로 개인 편집 초안에 재사용하지 않았다. 별도 개인/테넌트 초안 revision 저장을 추가했다. 저장된 초안은 승인·게시·실행 권한을 주지 않는다.
- **변경한 실제 파일**:
  - `src/backend/migrations/053_workflow_studio_drafts.sql`: immutable owner-scoped revision rows, CAS/idempotent request key, strict size/shape constraints, audit event, FORCE RLS 및 최소 권한 function을 추가.
  - `src/backend/app/workflows/routes.py`: `/api/v1/workflows/drafts` 목록·저장 및 `/drafts/{draft_id}` 상세 endpoint, strict request schema, owner-management gate 입력 검증을 추가.
  - `src/frontend/src/workflow/WorkflowStudio.tsx`: draft 저장/불러오기 UI, 저장 요청 replay ID 보존, 승인 exact version 선택 실행, 실패 모의 성공 제거 및 draft/execution 상태 안내를 구현.
- **DB 이행**: 기존 pending 052와 새 053을 적용하기 전 private custom backup을 생성하고 별도 fixture DB에 복원했다. 복원 전후 기존 테이블 행 digest가 일치했으며, clone에서 052·053 순차 적용을 먼저 확인한 뒤 활성 DB에 같은 순서로 이행했다. 기존 000~051 checksum과 business row digests가 유지됐고 초안 table은 0행/FORCE RLS=true. 052 checksum `e8663b23e121343ba644ec7f44dda1ca194e67f3751d9ba66056ea0bb72d867e`, 053 checksum `62b8624d036d3b8d823585ec4d6754157683ab72bd16c101fe98c5118fdaf288`. 비공개 증거와 backup SHA는 중간 보고서 참조.
- **복원 시험 중 오류 처리**: 첫 053 SQL parse 오류는 clone transaction에서 감지되어 전부 rollback되고 활성 DB에는 영향이 없었다. 식을 수정한 뒤 다시 별도 clone에서 두 migration 적용을 확인했다.
- **서비스 및 빌드**: backend 정상 재기동, health HTTP 200. 초안 API 익명 GET은 401 AUTH_REQUIRED. `npm run build:admin` 통과(51 modules, boundary true), `npm run build:user` 통과(28 modules, boundary true). 첫 build의 UUID state type 오류를 수정 후 재통과했다.
- **미완료·제한**: 인증된 draft save/load 및 CAS/role denial 시나리오, 브라우저 왕복은 아직 미검증. 캔버스 노드를 strict 승인 정의로 변환하고 기존 승인 B 제출/receipt와 실행 trace에 연결하는 기능이 남았다. 회의록 업무 의미 품질, 장기 run 복구, T-035 실제 기관 연결, 최신 F/IA/T 재대조도 미완료다.
- **다음 작업**: `workflowAdapter.ts`에서 UI 좌표/편집 설정과 실행 config를 분리하고 지원 노드만 승인 schema로 매핑한다. 저장된 exact revision 검증·타인 승인 제출 연결 후 권한/CAS/browser 수용을 진행한다.

## 2026-10-16 · Workflow Studio 승인 제출 연결

사용자 지시: 잔여 개발을 계속 진행. 다음 항목인 캔버스 초안→기존 Workflow 타인 승인 흐름 연결을 진행했다.

- **변경한 실제 파일**: `src/frontend/src/workflow/workflowAdapter.ts`, `src/frontend/src/CanvasWorkflowApprovalRequest.tsx`, `src/frontend/src/workflow/WorkflowStudio.tsx`. 계획37 및 구현 중간 보고서도 갱신했다.
- **동작**: 현재 캔버스 fingerprint가 저장 성공 당시 exact revision과 일치할 때만 승인 요청 UI를 연다. 저장 후 편집이 바뀌면 요청 UI가 닫히며 재저장 전 제출할 수 없다. 승인 변환은 선형 입력→선택 Tool→exact 게시 Agent→출력으로 제한하고 prompt·knowledge·logic 및 분기/병합은 거부한다. Agent binding은 입력/선행 Tool 결과/문자열 중 변수마다 명시 선택이다. Tool descriptor digest와 Agent version/publication revision을 봉인하고 기존 strict 서버 validation 및 타인 승인 제출 API와 승인 B receipt를 사용한다. 승인된 Workflow의 input_key로 실행 입력을 전달한다.
- **승인 경계**: 요청 접수는 승인·게시·실행 상태가 아니다. Studio 실행은 기존 승인 exact version을 대상으로 한다. saved draft revision 자체에 approval receipt backlink를 저장하지 않는다.
- **검증**: `npm run build:admin` 통과(52 modules, boundary true), `npm run build:user` 통과(28 modules, boundary true). 최종 admin 번들 705.78 kB 경고. 최초 타입 검사에서 pagination 응답 implicit-any를 발견해 명시 타입으로 보정한 뒤 두 빌드를 순차 통과했다. 자동 테스트와 인증 브라우저 수용은 실행하지 않았다.
- **미완료**: 별도 계정의 draft owner/tenant/RLS denial·CAS/idempotent retry와 브라우저 왕복, 타인 PADMIN 제출/반려/재신청 실수용, 게시 후 exact version 실행 및 trace, draft↔approval 탐색 연결, 장애 복구·회의록 업무 품질·T-035 기관 연결·F/IA/T 재대조.
- **다음 작업**: 별도 권한 계정과 fixture에서 draft·승인 수용 시나리오를 확인하고 Workflow 수동복구 단위를 진행한다. 이후 계획37의 다른 잔여 범위를 계속 수행한다.


## 2026-10-16 · Workflow 중단 실행 수동 복구 구현
사용자 요청: 미완료 기능 잔여 개발 계속 진행. 계획37의 수동 Workflow 복구 Workstream을 진행했다.

- **구현**: 신청자 본인 요청 → 다른 PADMIN의 승인/반려 → 신청자 재개 확정 흐름과 owner/admin UI를 추가했다. 성공 checkpoint는 이어쓰고 알 수 없는 Tool receipt 및 미종료 Agent child는 재호출하지 않는다. 재시도 idempotency 및 stale head 검증을 055로 보완했다.
- **실제 변경 파일**: `src/backend/migrations/054_workflow_manual_recovery.sql`, `055_workflow_recovery_retry_guards.sql`, `src/backend/app/workflows/repository.py`, `service.py`, `routes.py`, `src/frontend/packages/api-contract/src/types.ts`, `src/frontend/src/WorkflowCanvasPage.tsx`. 정식 상세 결과 [[200.프로젝트실행/250.구현/37 Workflow 중단 실행 수동 복구 구현 결과]] 및 통합 중간 보고 [[200.프로젝트실행/250.구현/2026-10-16 잔여 기능 개발 중간 보고서]].
- **DB/증거**: 백업 후 별도 fixture clone restore 및 migration 055 선적용 검증, 기존 74개 테이블 행 digest와 55개 기존 migration checksum 보존, 활성 DB 이행 후 stale service-control 기록으로 listener가 응답하지 않아 backend 및 두 frontend 소유 프로세스를 정상 재시작했고 API8000·사용자5173·관리자5174 HTTP 200을 확인했다. migration SHA `b4b23c6cde5d27cd2640b51fa8ea93b8698c89b11e30871d0468aa4bddf8e958`, backup SHA `e50a873323ec37df56f9f5ac70aa6f4d7d4d4a3ad9837922be209d5e5bf7aead`; 상세 proof는 private runtime 경로에 보관했다.
- **검증**: Python compileall, admin build(52 modules, boundary true), user build(28 modules, boundary true) 통과. admin bundle 712.24 kB 크기 경고. 자동 tests 및 authenticated browser/2-user approval-resume 수용은 미실행이며 그 범위는 완료 판정하지 않았다.
- **미완료/다음 작업**: 인증된 신청자/PADMIN 왕복, denial/CAS/replay 시나리오; 외부 Tool/Agent 결과의 기관별 조회·조정; 기존 meeting 품질, T-035 실기관 수용, 전체 기능 재대조.

## 2026-10-16 · RAG 학습 문서 및 시퀀스 다이어그램 작성
사용자 요청: 파이썬 배경지식이 없는 사용자도 RAG 동작을 쉽게 이해할 수 있는 시퀀스 다이어그램 작성 및 Obsidian '학습' 폴더 내 문서 생성 관리.

- **생성 파일**: `docs/Obsidain/학습/01 RAG 동작 원리 및 시퀀스 다이어그램.md`
- **내용**:
  - RAG 개념의 직관적 비유(기억 의존 vs 도서관 오픈북 테스트)
  - 사용자 질문부터 문서 권한 검증, pgvector 유사도 검색, 프롬프트 조립, LLM 답변 생성, 근거 검증(render_answer), 최종 화면 표출까지의 Mermaid Sequence Diagram 작성
  - 각 단계별 비전공자용 동작 원리 상세 설명
  - 플랫폼 내 실제 파이썬/타입스크립트 소스 코드 파일(rag.py, search.py, rag_gateway.py, answer.py, ChatPage.tsx, RagEvidencePanel.tsx) 매핑 제공
- **검증**: Mermaid 다이어그램 렌더링 문법 유효성 및 마크다운 링크 정상 확인.

## 2026-10-16 · RAG 핵심 소스 코드 상세 학습 주석 보강
사용자 요청: RAG 관련 주요 백엔드/프론트엔드 소스에 학습 목적의 친절하고 상세한 한국어 주석 작성.

- **대상 파일**:
  - `src/backend/app/execution/rag.py`: RAG 총괄 오케스트레이션 단계별 흐름 주석
  - `src/backend/app/documents/search.py`: 권한 필터링, pgvector 코사인 유사도 검색, FactPacket 생성 주석
  - `src/backend/app/ai/rag_gateway.py`: 질문 임베딩 변환, 토큰 가드, 사용량 원장 정산 주석
  - `src/common_core/ai_pipeline/graphrag/answer.py`: AI 환각 차단 및 출처 팩트 대조 검증 주석
  - `src/frontend/src/RagEvidencePanel.tsx`: 출처 비동기 로딩, 위치 파싱(문단/셀/페이지), 원문 다운로드 주석
  - `src/frontend/src/ChatPage.tsx`: RAG 모드 분기, 실시간 진행 단계(검색/선택/검증), 결과 렌더링 주석
- **검증**: Python compileall 문법 검사 통과, Frontend `tsc --noEmit` 타입 검사 통과.

## 2026-10-17 · 포털 첫 화면 사용자/관리자 구분 Mock 시안 작성

- **사용자 요청**: 현재 사용자와 관리자 사이트(포트 5173 vs 5174)의 첫 화면(로그인 및 진입 화면)이 거의 동일하여 화면이 명확히 구분될 수 있도록 검토하고, 시안 두 개에 대한 Mock 화면 제공 요청.
- **분석 및 상태**:
  - `packages/ui/src/PortalShell.tsx`에서 비인증 로그인 상태(`state.phase === 'login'`)일 때 `site` prop 분기 없이 동일한 `LoginPage`를 렌더링하고 있어 시각적 차이가 전혀 없음을 확인.
  - 현재 상태는 **UI/UX Mock 시연 및 제안 상태**이며, 실제 앱 코드 통합 또는 운영 배포 상태가 아니다.
- **제작한 실제 파일**:
  - 인터랙티브 Mock HTML: `/Users/jwpios/antigravity/지능형 차세대 정보시스템 구축/UI_UX_제안_20261011/첫화면_구분_시안_비교.html`
  - 확정 검토 노트: `docs/Obsidain/200.프로젝트실행/240.설계/25 포털 첫 화면 사용자 관리자 구분 시안 검토.md`
- **시안 구성**:
  - **시안 1 (기능 및 도메인 정체성 차별화 안 · 추천)**: 2분할 레이아웃 유지, 사용자(딥 틸 `#087f78` + 업무 비서 `✨ AI WORKSPACE` + 임직원 로그인) vs 관리자(다크 슬레이트 `#0f172a` + 통제 방패 `🛡️ ADMIN CONSOLE` + 관리자 인증 & 감사 경고).
  - **시안 2 (구조 완전 분리형 안)**: 사용자(소프트 그라데이션 플로팅 카드 + 인기 업무 칩) vs 관리자(실시간 시스템 헬스체크 관제 패널 + 전용 보안 게이트웨이 카드).
  - **Mock 기능**: 상단 탭으로 시안 1/시안 2 전환, 서브 탭으로 좌우 나란히 비교(Split View), 사용자(5173) 단독, 관리자(5174) 단독 뷰 인터랙티브 지원.
- **검증 및 증거**: HTML5 표준 마크업, CSS 변수 및 반응형 미디어 쿼리(1200px/900px 분기), Pretendard 웹폰트 및 SVG 아이콘 렌더링 확인.
- **미완료 및 다음 작업**: 사용자 검토 및 최종 시안 선택 확인 후, `PortalShell.tsx`와 `LoginPage.tsx`에 실제 코드 반영 및 5173/5174 분리 검증 수행.

## 2026-10-17 · 시안 1 채택 확정 및 실제 앱 코드 적용

- **사용자 결정**: 사용자가 Mock 화면을 직접 확인한 후 **시안 1 방안**으로 진행 승인 및 확정.
- **적용 및 구현 내용**:
  - `src/frontend/packages/ui/src/LoginPage.tsx`: `site?: 'user' | 'admin'` prop 분기 구현. 사용자(딥 틸 & `AI WORKSPACE`, 임직원 로그인)와 관리자(다크 인디고 & `ADMIN CONSOLE`, 관리자 콘솔 인증 및 보안 감사 경고, 3대 거버넌스 안내) 비주얼 및 카피 적용.
  - `src/frontend/packages/ui/src/PortalShell.tsx`: 비로그인 시 `LoginPage` 호출부에 현재 사이트 속성(`site={site}`) 전달 연계.
  - `src/frontend/src/App.tsx`: 단일 앱 호환 엔트리에서도 `site={adminViews.includes(view)?'admin':'user'}` 조건부 전달 보완.
  - `src/frontend/packages/ui/src/styles.css`: 관리자 웰컴 패널 전용 다크 그라데이션, 사이버 격자 패턴, 보안 알림 박스, 버튼 테마 스타일 추가.
- **검증 및 증거**:
  - `npm run build:user` 빌드 통과 (28 modules, boundary_verified: true).
  - `npm run build:admin` 빌드 통과 (52 modules, boundary_verified: true).
  - TypeScript(`tsc --noEmit`) 컴파일 에러 0건.
  - 로컬 HTTP 응답 확인: 사용자 5173(200 OK), 관리자 5174(302 Found → `/manage/` 200 OK) 정상 구동.
  - 설계 문서 확정 갱신: `docs/Obsidain/200.프로젝트실행/240.설계/25 포털 첫 화면 사용자 관리자 구분 시안 검토.md`.
- **현 상태**: 실제 앱 적용 완료 (로컬 5173 및 5174 브라우저 새로고침 시 즉시 반영 확인 가능). 운영 배포 환경 반영은 추후 릴리스 계획에 따름.

## 2026-10-18 · Codex CLI 프로젝트 지침 반영

- **사용자 요청**: 앞서 안내한 저장소별 Codex CLI 작업 기준을 `GGENTS.md`에 적용 요청. 저장소의 실제 지침 파일명이 `AGENTS.md`이므로 해당 파일에 반영했다.
- **변경 파일**: 저장소 루트 `AGENTS.md`에 `Codex CLI 프로젝트 작업 원칙` 절 추가. `Codex`를 저장소 루트에서 시작, 작업 범위와 완료 기준 지정, 화면 설계 선행 확인, additive migration·백업/clone·checksum 보존, 승인/검증 상태 구분, Obsidian 기록 갱신 원칙을 포함했다.
- **검증**: 기존 지침을 보존하면서 새 절이 들어간 것을 확인하고 diff whitespace 검사를 수행했다. 애플리케이션 코드·DB·서비스는 변경하지 않았으며 자동 테스트나 빌드는 실행하지 않았다.
- **미완료 범위**: Codex CLI에서 새 지침을 사용한 구현 세션은 아직 수행하지 않았다.
- **다음 작업**: 다음 Codex CLI 작업부터 이 지침을 적용한다.

## 2026-10-18 · 현재 작업 GitHub 반영 준비

- **사용자 요청**: 현재까지 작업한 내용을 GitHub에 업데이트.
- **대상 작업**: RAG 학습용 한국어 주석과 시퀀스 다이어그램, 사용자/관리자 첫 화면 구분 적용, Codex CLI 프로젝트 지침 추가를 포함한 현재 미커밋 작업을 확인했다. 이전 커밋 `0ed40b7`의 T-037 Workflow Studio/수동 복구 작업은 이미 `origin/main`에 있다.
- **리뷰 및 보정**: Codex CLI의 `review --uncommitted`와 사용자 지정 프롬프트 조합은 설치 버전에서 지원되지 않아, 메인 화면 네 파일 diff를 대상으로 읽기 전용 리뷰를 실행했다. 모바일 관리자 화면의 안내 목록이 로그인 폼을 밀어내는 문제와 근거가 확인되지 않은 접속 감사 문구를 발견해, 모바일 목록을 숨기고 로그인 후 역할별 권한 안내로 수정했다. 설계25도 같은 문구로 갱신했다.
- **검증**: `git diff --check` 통과. 이번 업데이트 요청에서는 자동 테스트와 빌드를 실행하지 않았다. Codex 리뷰 외 별도 브라우저 수용 검증은 미수행이다.
- **변경 파일**: 저장소 `AGENTS.md`; RAG backend/common/frontend 소스 6개; 로그인 UI 및 공통 shell/style/호환 앱 소스 4개; 설계25; 학습 RAG 문서; 본 작업 로그.
- **미완료 범위**: 모바일 실제 화면 브라우저 확인과 접속 감사 이벤트의 별도 구현 검증은 범위 밖이다. 접속 기록을 보장한다는 문구는 제거했다.


## 2026-10-18 노코딩 MCP Tool 마법사 설명 요청

사용자가 화면 기능 설명을 요청하여 실제 코드를 읽었다. 명세→AI 도구 정의 변환 및 Dev/Prd 접속 분기를 의도한 기능이나, 현재 동적 호출은 모의 응답이며 등록은 메모리 기반이다. 실제 시스템 연동 완료로 표현하지 않았다. 이 마법사의 2환경은 확정된 local/dev/tb/prd 4환경 구현과 구분한다. 실제 통신/권한/영속성/화면 연결 시험은 미수행이다. 파일·확인 범위·미완료는 [[2026-10-18 노코딩 MCP Tool 자동 생성 화면 기능 설명 및 구현 범위]] 참조. 회의록 잔여 통합 수정·실제 DB 적용 작업을 이 기능의 완료 근거로 혼용하지 않는다.

## 2026-10-18 · 프로젝트 작업 지침 정리

**요청:** 토큰 사용량을 고려해 AGENTS.md를 프로젝트 전용으로 정리하고, 실제 Obsidian Vault 위치를 반영.

**변경:** 프로젝트 루트 `AGENTS.md`에 화면 확정사항, 권한·데이터·보안 원칙, DB 변경 주의사항, 작업 종류별 문서 확인·기록 기준을 정리했다. Vault 경로는 `/Users/jwpios/antigravity/202610_AI 플랫폼/docs/Obsidain`으로 명시했다.

**검증:** AGENTS.md 내용을 재확인했다. 저장소 메타데이터가 없어 git diff/status 검증은 수행하지 않았다. 지침 변경이며 앱 동작 검증 대상은 아니다.

**미완료:** AGENTS.md 수정사항을 다른 동기화 위치에 반영했는지는 확인하지 않았다.

## 2026-10-18 · 금융 특화 MCP Tool Gateway 상세 구현 계획안

**요청:** 최근 MCP 보안·거버넌스 동향과 현재 Tool 제작 기능을 비교 검토한 결과를 바탕으로 상세 구현 계획안을 작성하고 Obsidian에 기록.

**결정·범위:** 기존 T-035 파서/마법사/모의 라우팅을 기반으로 분류하고 실기관 연동 완료로 간주하지 않는다. 영속 Registry, Streamable HTTP 및 사양 호환, 실제 connector dispatcher, tenant/user/agent RBAC·Secret lifecycle, 금융 Human-in-the-loop 승인, metadata/input/output guardrails·hybrid routing, 감사·복원력, 관리자 UX 및 단계별 수용 gate로 계획을 나눴다. WebSocket을 표준 MCP 전송으로 가정하지 않고, 현재 MCP 사양 및 SDK 지원표를 구현 시 재확인하도록 했다.

**변경 문서:** [[100.프로젝트계획/38 금융 특화 MCP Tool Gateway 상세 구현 계획안]]. 계획은 새로운 개발 승인이나 기관 연결·운영 배포 승인을 의미하지 않는다.

**근거·검증:** 현재 `dynamic_gateway.py`, `autowrap_routes.py`, `ToolAdminPage.tsx`, migration 052 및 최신 T-035 구현/화면 범위 기록을 읽어 기준선을 반영했다. 공개 MCP 사양 draft changelog, 2026-07-28 MCP spec release candidate, Microsoft Tools Gateway/AI Gateway, AWS Agentic AI 보안 가이드를 참고했다. 문서의 검토·작성만 수행했으며 애플리케이션 테스트, DB migration 적용, 브라우저/실기관 연동은 실행하지 않았다.

**미완료:** 보안·DB·승인 원장과 실제 현행 상태를 구현 착수 직전에 재확인해야 한다. Secret Manager/IdP 및 기관 sandbox 계약, 담당자·MFA·보존정책 등 외부 선행조건은 미확정이다. 계획 문서 작성은 코드 구현·기능 승인·게시·운영 배포가 아니다.

**다음 작업:** T035-A 기준선/위협 모델 확정부터 별도 승인된 단계로 진행한다. 이후 migration은 기존 파일을 수정하지 않고 현재 적용 상태를 확인한 뒤 신규 번호로 추가하며 백업·별도 fixture clone·checksum/기존 행 보존 절차를 따른다.

## 2026-10-18 · MCP Tool Gateway 단계별 구현 시작

**요청:** 금융 특화 MCP Tool Gateway 상세 구현 계획을 코드로 진행하고, 작업 중 생성 문서를 `MCP Tool Gateway 상세 구현` Obsidian 폴더에 모으며 작업 이력을 관리.

**완료한 수직 단위:** 노코딩 Gateway의 mock 등록소를 tenant별 memory namespace로 격리했다. 등록/목록/모의 호출 API에 TADMIN/PADMIN 역할 확인을 적용했다. 클라이언트가 보내는 `publication_status`/`asset_id`를 API 계약에서 제거하고 모든 모의 호출을 draft 개발 프로파일에 고정했다. endpoint profile inline credential 입력을 제거했다. 화면에서 가짜 API key·production 라우팅 선택·영구 저장 완료 문구를 제거하고 실제 시스템에 연결되지 않은 모의 기능임을 표시했다. 상세 변경은 [[200.프로젝트실행/250.구현/MCP Tool Gateway 상세 구현/2026-10-18 Gateway 모의 등록 격리 및 라우팅 경계 보강 구현 결과]]에 기록했다.

**변경 코드:** `src/backend/app/tools/autowrap_routes.py`, `src/backend/app/tools/dynamic_gateway.py`, `src/frontend/src/ToolAdminPage.tsx`, `src/backend/tests/test_mcp_tool_autowrap.py`.

**검증:** `pytest src/backend/tests/test_mcp_tool_autowrap.py -q` 9 passed. Codex bundled Node 환경에서 admin build 52 modules/boundary verified, user build 28 modules/boundary verified. Admin 번들 500 kB 초과 경고가 남는다. 최초 시스템 Node 21.4.0 빌드는 `node:util.styleText` export 오류로 실패해 bundled Node로 재실행했다.

**미완료:** registry/endpoint/audit는 여전히 memory 기반이다. 실제 MCP 전송·외부 connector·Secret Manager/IdP·기존 승인/게시/실행 receipt 연결·금융 HITL·SSRF/egress 가드·불변 감사/서킷브레이커·기관 sandbox는 미구현 또는 미검증이다. DB migration이나 실제 시스템 통신은 수행하지 않았다.

**다음 단계:** [[200.프로젝트실행/250.구현/MCP Tool Gateway 상세 구현/00 구현 추적]]에 적은 T035-B 기준선 조사부터 진행한다. migration 052 적용 상태·checksum·RLS 및 승인/receipt RPC를 대조한 뒤, 필요한 경우 기존 migration은 수정하지 않고 새 migration을 백업·별도 fixture clone 검증으로 추가한다.


## 2026-10-18 · MCP Tool Gateway 영속 Registry 코드 연결

**요청:** 상세 구현 계획에 따라 개발하고, `MCP Tool Gateway 상세 구현` 폴더에 문서와 작업 이력을 관리.

**변경:** 052에 이미 정의된 tenant-scoped MCP 테이블을 이용하도록 `dynamic_repository.py`와 자동변환 route를 연결하고, 제한된 `security.mcp_tool_registry_control` RPC를 additive migration 056으로 추가했다. schema revision은 append하고 endpoint 메타데이터만 저장하며 이 RPC는 자격증명을 받지 않는다. 목록은 DB를 읽고 모의 invoke는 프로세스 재시작 뒤 DB 정의로 simulation cache를 재수화하도록 했다.

**기준선:** 활성 fixture는 055까지 적용, 052 적용, 적용 migration checksum 불일치 0건, MCP 정의/버전/profile/audit 행은 각 0건. 기준선 DB 질의는 읽기 전용이었다.

**검증:** Python `py_compile` 및 `git diff --check` 통과. 별도 fixture RPC 검증 시도는 PostgreSQL이 중지되어 `CLUSTER_NOT_RUNNING`으로 종료. migration 056 미적용, 활성 DB 미변경. 상세 내용은 [[200.프로젝트실행/250.구현/MCP Tool Gateway 상세 구현/2026-10-18 영속 Registry RPC 연결 구현 결과]] 참조.

**미완료:** 056의 clone 적용/권한·tenant denial·revision 검증, 영속 Registry 전체 경로 시험, approval/receipt 연계, 실제 MCP transport/connector, Secret Manager/IdP, 금융 HITL, guardrail/egress, 불변 audit 및 기관 수용.

**다음:** PostgreSQL 소유 상태가 복구되면 별도 fixture clone에서 056을 검증하고, backup/restore·보존 gate에 따라 활성 개발 DB 적용 여부를 결정한다.


## 2026-10-18 · MCP Registry clone 검증 및 migration 056 적용

**작업:** T035-B 영속 Registry의 fixture 검증과 활성 개발 fixture 적용을 진행했다.

**안전 기준:** 활성 fixture의 055 적용 상태와 source checksum 일치, MCP 테이블 0행을 사전 확인했다. 사설 custom backup을 만들고 별도 marker DB로 복원해 전체 업무 테이블 row/digest 및 기존 migration checksum 일치를 검증했다. clone에서 신규 056만 적용한 뒤 다시 보존을 확인하고, 활성 fixture에도 056만 적용했다. 활성 적용 후 기존 행 지문·checksum 보존, 최신 migration 056, source checksum mismatch 0건을 확인했다. 백업은 private `.runtime/backups/mcp-gateway-20261018/`에 유지한다.

**검증:** clone RPC에서 등록/목록/revision 1→2/재조회, USER 등록 거부, 타 tenant 조회 차단이 통과했다. `pytest src/backend/tests/test_mcp_tool_autowrap.py -q` 9 passed, `py_compile` 및 `git diff --check` 통과. 첫 clone RPC 검증에서 nested aggregate SQL 오류를 찾아 `EXISTS` 쿼리로 수정한 뒤 전 시나리오 통과.

**변경 기록:** [[200.프로젝트실행/250.구현/MCP Tool Gateway 상세 구현/2026-10-18 Registry clone 검증 및 056 적용 결과]].

**미완료:** 자동생성 Tool의 기존 승인·게시·receipt gate 연계, Secret Manager/IdP, MCP transport/connector, HITL, egress/SSRF·metadata 무결성, 불변 audit·복원력, 브라우저·기관 수용. 이번 migration은 registry metadata 영속화만 제공한다.


## 2026-10-18 · 영속 Registry 상태 문구 및 최종 검증

**화면 변경:** 관리 Tool 화면 설명/등록 결과 안내를 실제 상태에 맞춰 수정했다. Tool 정의는 DB Registry에 저장되며 invoke는 개발 profile fixture simulation만 제공한다. 레이아웃은 변경하지 않았다. `npm run build:admin` 통과(227 modules, boundary verified); 500kB 초과 chunk 경고는 남는다.

**프로세스 상태:** DB는 active 056 적용 후 실행 중이다. API는 `--reload` 없이 실행 중이지만 service_control 소유 기록이 없어 사용자 공유 프로세스를 임의로 종료/재기동하지 않았다. 새 코드의 현재 backend 프로세스 로드와 인증 브라우저 왕복은 미검증이며 관리형 재기동 후 확인해야 한다.


## 2026-10-18 · 동적 Tool 승인 gate 계약 조사
- 요청: 다음 단계로 자동 생성 MCP Tool을 기존 승인·게시·receipt gate에 연결한다.
- 확인: 고정 Tool RPC는 tool ID 3개만 허용하며 정적 registry descriptor와 정적 handler를 사용한다. 050 wrapper의 PADMIN/자기승인/CAS/audit 계약을 보존해야 한다. 동적 승인 제출은 현재 불가하며, 제출만 억지 연결하면 실행 가능 상태로 오인될 수 있다.
- 결정: 승인 RPC와 revision-bound 서버 digest를 신규 additive migration으로 구현하고, 등록 검토 승인과 운영 게시/실행 승인을 구분한다. 동적 execution adapter/receipt는 별도 단계에서 연결한다.
- 변경: [[200.프로젝트실행/250.구현/MCP Tool Gateway 상세 구현/2026-10-18 동적 Tool 승인 gate 계약 조사 결과]], [[200.프로젝트실행/250.구현/MCP Tool Gateway 상세 구현/00 구현 추적]] 기록만 갱신.
- 검증: 관련 SQL/API 소스를 읽어 계약 확인. 이번 회차는 migration/API 변경 및 시험을 수행하지 않음.
- 미완료: 057 migration, clone 검증, active fixture apply, UI, dynamic execution/receipt, browser roundtrip.
- 다음: additive 057 approval RPC + server-computed revision digest 구현.
## 2026-10-18 · 동적 Tool 검토 접수 구현
- 요청: 자동 생성 MCP Tool을 기존 승인 gate로 이어가는 다음 단계 진행.
- 결정: 위험 미분류 Tool은 검토요청만 접수하고 PADMIN 승인은 API와 DB trigger에서 막는다. 요청 접수를 승인·게시·실행으로 표시하지 않는다.
- 변경: 057 additive migration 및 동적 descriptor/revision digest RPC, Tool 요청 API와 폼, 타입 계약, 상세 validation을 갱신했다. [[200.프로젝트실행/250.구현/MCP Tool Gateway 상세 구현/2026-10-18 동적 Tool 검토 접수 구현 결과]] 참조.
- 검증: 별도 복원 clone에서 056/057 적용, 기존 migration checksum 56건 및 업무 데이터 정규화 지문 보존, trigger/RLS/DB 직접 권한 경계를 확인했다. `pytest -q tests/test_tool_workflow_review_http.py` 14 passed. `git diff --check` 및 Python 내장 compile 확인 통과.
- 동적 검토 HTTP 종단 간 시험: 합성 Tool 등록, submission support 노출, 검토 요청 제출과 동일 client_request_id replay, 타 tenant 상세 404, 미분류 승인 409, 반려 성공, DB trigger 직접 승인 거부를 확인했다. 첫 수행에서 `TOOL_RISK_UNCLASSIFIED` 사용자 메시지 매핑 누락으로 500을 발견해 `src/backend/app/errors.py`에 메시지를 추가했다. 수정 후 신규 시나리오 1 passed 및 `pytest -q tests/test_tool_workflow_review_http.py` 15 passed.
- 변경 파일(이번 회차): `src/backend/app/errors.py`, `src/backend/tests/test_tool_workflow_review_http.py`. `git diff --check` 통과.
- 제한/상태: 검증은 격리 합성 fixture 기준이다. Migration 057은 active fixture에 적용되지 않았고 브라우저 왕복·기관 sandbox·실제 connector는 미검증이다. PADMIN 승인은 위험 미분류 상태에서 계속 차단되며 게시, dynamic execution/receipt 연결은 미구현. backend 재시작은 service-control 소유권 미확인으로 수행하지 않았다.
- 다음: 관리형 backend 절차 승인 후 인증 브라우저 왕복, 이후 risk classification과 exact revision publish/execution gate를 진행한다.


## 2026-10-18 · 동적 Tool 검토 UI 브라우저 확인 준비
- 요청: 동적 Tool 검토 API 종단 간 통과 후 인증 브라우저 UI 왕복을 진행한다.
- 확인: 프로젝트 환경 계획상 local은 사용자 5173, 관리자 5174, API 8000이다. 현재 공유 포트 서비스의 `service_control` 기록은 프로세스 소유권 검사에서 세 서비스 모두 unowned-or-stale로 판정됐다. 사용자 공유 프로세스를 재기동하지 않았다.
- 브라우저: `browse` 스킬 확인에서 Aside 사용 불가, gstack browser fallback은 one-time setup이 필요한 상태다. setup 승인 질문을 전달했고 회신 대기 중이므로 이번 회차 브라우저 확인은 시작하지 않았다.
- 결과: 브라우저 로그인/검토 요청 UI는 미검증. 별도 fixture API 종단 간 및 15개 승인 HTTP 시험 통과 결과를 현재 기록으로 유지한다.
- 다음: 사용자 확인 후 browser runtime을 준비하고, 소유권이 확인된 격리 backend/API와 fixture에서 인증된 브라우저 왕복을 수행한다.


## 2026-10-18 · MCP 검토 UI 브라우저 재개와 JSX 수정
- 요청: 인증된 관리자 브라우저에서 동적 Tool 검토 화면 왕복을 확인한다.
- 환경: 사용자 승인 후 gstack browser fallback setup 실행. `gstack-browser-ensure`는 checkout root `node_modules/playwright` 검사에서 `bun install` package.json 누락 오류를 반환했으나, 생성된 browser binary 자체는 실행되고 Chromium daemon health 확인을 통과했다. B CLI loopback 접근은 elevated run이 필요했다.
- 브라우저: 새 탭에서 `http://127.0.0.1:5174/manage/admin`을 열었다. 최초 화면에서 `ApprovalReviewPanel.tsx` JSX parse error가 나타났다. 해당 세 갈래 conditional JSX를 명시적인 wrapper/괄호로 정리했다.
- 변경 파일: `src/frontend/src/ApprovalReviewPanel.tsx`. 검증 `npm run build:admin` 통과(227 modules, boundary verified). 브라우저 재조회에서 parser overlay가 사라지고 관리자 로그인 화면을 확인했다. 최초 로그의 500은 수정 전 HMR 오류이며 로그인 없는 초기 API 요청은 401로 기록됐다. 수정 후 console을 clear하여 새 오류만 확인하는 작업은 미완료다.
- 운영 경계: backend/frontend/admin frontend 세 프로세스의 service_control ownership 검증이 실패해 공유 프로세스를 재시작하지 않았다. 활성 DB에 데이터를 submit하지 않았다.
- 현재 상태: 로그인 자격정보 입력은 사용자에게 맡겨 visible browser handoff 상태다. 사용자가 직접 로그인했다고 알린 뒤에만 이어서 UI를 확인한다. 비밀번호/MFA는 Codex에 공유하지 않는다.

## 2026-10-18 · 관리자 로그인 장애 읽기 전용 진단
- 요청: 기존 테스트 계정으로 관리자 로그인이 되지 않는 문제를 확인한다. 계정 테스트 허용을 받았으나, 대화에 암호가 노출되어 해당 값을 재사용하거나 기록하지 않았다.
- 관찰: 관리 화면 console에 503이 있었고 API health는 200이었다. DB 상태 조회는 `stopped`, backend 로그에는 `127.0.0.1:55432 connection refused`가 반복됐다. 현재 확인된 우선 원인은 DB 연결 불가이며 실제 로그인은 미검증이다.
- 경계: backend/admin frontend는 service_control이 소유하지 않는 프로세스였다. 재기동, DB 기동, 로그인 시도 및 데이터 변경은 수행하지 않았다.
- 다음: 관리형 로컬 환경에서 DB/backend를 안전하게 기동한 뒤 회전된 테스트 암호로 UI 로그인 왕복을 확인한다.
- 관련 기록: [[200.프로젝트실행/250.구현/MCP Tool Gateway 상세 구현/2026-10-18 동적 Tool 검토 접수 구현 결과]]
- 후속: 사용자의 테스트 계정 사용 허용에 따라 프로젝트 전용 devdb를 `scripts/devdb.py start`로 기동했고 상태 `running`을 확인했다. 소유권이 확인되지 않은 backend/admin frontend는 재기동하지 않았다. 관리자 로그인 폼 표시를 재확인했으며, 미인증 요청 401만 보여 로그인 성공은 여전히 미검증이다. 브라우저 정책상 자격정보 입력은 사용자가 직접 수행한다.
- 사용자가 로그인 완료를 알린 후 사용자의 Chrome 관리자 탭을 읽기 전용 확인했으나 `/manage/admin/tools`에서 인증 폼이 계속 표시됐다. 암호값은 읽지 않았다. 이후 devdb 상태가 재차 `stopped`여서 로그인 완료 상태로 검증하지 못했다.
- 재개 요청에 따라 프로젝트 전용 devdb를 다시 기동했고, 상태 조회에서 `running`을 확인했다. Chrome 관리자 탭은 인증 폼 상태여서 인증 성공은 미검증이다. 사용자가 같은 탭에서 다시 로그인하도록 handoff했다.
- 사용자가 첨부한 관리자 화면으로 A-ADM 로그인 상태와 `/manage/admin/tools`를 확인했다. 동적 MCP Tool 0개, 자동 생성 wizard 진입 버튼이 표시된다. 앞선 미로그인 판정은 자동화가 붙은 별도/오래된 탭 기준이었으므로 정정한다. 별도 새 탭은 인증 화면을 표시해 첨부된 로그인 세션과의 동일성은 확인되지 않았다. wizard 제출은 미수행이다.
- 사용자가 로그인한 Chrome 탭을 새로 열어 인증된 Tool 관리 UI를 확인했다. 샘플 Parse가 `REQUEST_INVALID`로 실패했으며 원인은 direct `fetch`가 필수 `X-Tenant-ID`를 보내지 않는 것이었다. Tool 목록도 같은 이유로 실패를 빈 목록처럼 표시할 수 있었다.
- 변경: `src/frontend/src/ToolAdminPage.tsx`의 목록·Parse·등록·모의 호출을 공통 `api.request`로 통합해 tenant, CSRF, X-Requested-With 및 표준 오류 처리를 적용했다. 화면 레이아웃 변경은 없다.
- 검증: `npm run build:admin` 통과(227 modules, boundary verified; 500 kB 초과 chunk 경고 유지). 로그인된 Chrome에서 목록 조회 0개 정상 응답 및 OpenAPI sample Parse 성공, `check_loan_limit` 초안 생성 확인. 저장과 invoke는 하지 않았다. `git diff --check` 통과.
- 관련: [[200.프로젝트실행/250.구현/MCP Tool Gateway 상세 구현/2026-10-18 동적 Tool 검토 접수 구현 결과]], [[200.프로젝트실행/250.구현/MCP Tool Gateway 상세 구현/00 구현 추적]]
## 2026-10-18 · 동적 Tool 위험 기본정책 및 승인 fail-closed
- 요청: “네 진행 바랍니다”에 따라 동적 Tool 위험 분류와 승인 정책 구현을 진행.
- 결정: connector 의미/읽기 전용 동작을 서버가 증명하지 못하므로 모든 동적 Tool을 `financial_side_effect` 및 `restricted_or_unknown`으로 보수 분류한다. `dynamic-default-v1` descriptor에는 정책 revision, 근거, 등록 검토 전용 scope 및 `execution_ready=false`를 digest와 함께 봉인한다.
- 승인 경계: 등록 검토 요청은 접수하나 기존 approval RPC가 승인 시 head를 활성화하므로 이 단계에서는 PADMIN 승인도 API와 DB trigger에서 차단한다. 실제 publish/execution/receipt/MFA 승인 gate가 연결되기 전 동적 Tool은 실행되지 않는다.
- 변경 파일: `src/backend/migrations/058_mcp_tool_risk_policy.sql`, `src/backend/app/tools/routes.py`, `src/backend/app/tools/repository.py`, `src/backend/app/errors.py`, `src/frontend/packages/api-contract/src/types.ts`, `src/frontend/src/ApprovalReviewPanel.tsx`, `src/frontend/src/ToolApprovalRequest.tsx`, `src/backend/tests/test_tool_workflow_review_http.py`.
- 화면 기준: UI 확정 노트23의 관리 B 요청 목록·상세 패널 구조를 유지하고 상세에 위험 등급/근거/정책/승인 범위를 표시했다. 세부 변경은 [[200.프로젝트실행/250.구현/MCP Tool Gateway 상세 구현/2026-10-18 동적 Tool 보수적 위험정책 구현 결과]].
- 검증 상태: Python 4개 파일 내장 compile 및 `git diff --check` 통과. `npm run build:admin` 통과(227 modules, boundary verified, 500 kB 초과 경고). pytest·migration clone apply는 이번 회차에서 실행하지 않았다. 058 active fixture 미적용, 기존 DB checksum·row 변경 없음. migration/회귀 수용은 미검증이다.
- 미완료: 편집 가능한 정책 UI, 2인 승인/MFA, exact revision publish/execution adapter·receipt, Secret Manager/IdP, metadata/SSRF guardrails. 다음은 058 clone 검증과 등록 검토 approval route fail-closed 확인이다.


## 2026-10-18 · Migration 058 격리 clone 검증
- 요청: 다음 단계 진행.
- 수행: private backup dump를 disposable PostgreSQL clone에 복원하고 056~058을 clone 내부에서 적용했다.
- 검증: migration head 058 / 59 entries / source checksum mismatch 0; 74개 업무 테이블 322행의 정규화 지문 적용 전후 동일. `ai_web`의 RPC 권한과 직접 민감 테이블 조회 거부, trigger 활성/소유자 확인. 합성 승인 직접 전이는 SQLSTATE A0403 `TOOL_DYNAMIC_REVIEW_ONLY`로 차단, probe rollback 확인. clone은 marker를 검증해 종료·삭제.
- 상태: active fixture·실제 금융 시스템에는 적용/호출하지 않았다. pytest 및 정확한 descriptor/RPC tenant 회귀는 미실행.
- 기록: [[200.프로젝트실행/250.구현/MCP Tool Gateway 상세 구현/2026-10-18 동적 Tool 보수적 위험정책 구현 결과]], [[200.프로젝트실행/250.구현/MCP Tool Gateway 상세 구현/00 구현 추적]].
- 다음: 별도 clone에서 pytest 및 descriptor/RPC tenant 경계 회귀를 보강한 뒤, exact-revision 다중 승인/MFA와 publish/execution receipt 계약으로 진행.


## 2026-10-18 · Exact revision MFA gate 의존성 조사
- 요청: 다음 단계 진행.
- 조사: 기존 approval gate와 세션 스키마를 확인. `security.sessions` 및 로그인 경로에 신뢰된 IdP MFA assurance claim/검증시각이 없어 이 세션만으로 실제 MFA를 검증할 수 없다. tool approval은 기존 PADMIN 타인 승인/CAS/audit을 제공하지만 dynamic approval은 registration-review-only이며 동적 실행 handler/receipt도 없다.
- 결정: 클라이언트 제공 MFA 완료 flag는 인증 근거로 받지 않는다. 기관 IdP, assurance claim/사용자 매핑/freshness 계약이 정해지기 전 dynamic 승인은 계속 fail-closed한다. exact descriptor digest와 policy/tool revision에 묶인 독립 승인 + publish와 execution receipt는 분리 구현한다.
- 변경: [[200.프로젝트실행/250.구현/MCP Tool Gateway 상세 구현/2026-10-18 exact revision 승인 gate IdP 의존성 조사 결과]], [[200.프로젝트실행/250.구현/MCP Tool Gateway 상세 구현/00 구현 추적]] 기록 갱신. 코드·DB 변경은 없음.
- 검증/상태: 관련 migration/API 소스 확인. active fixture 불변. pytest/DB/API 미실행.
- 다음: 기관 IdP와 assurance 계약 확정 후 인증 검증부터 구현하고, 별도 clone에서 MFA·2인 승인·revision/payload 변경·tenant 격리를 검증한다.


## 2026-10-18 · OIDC/SAML exact revision gate 설계
- 요청: MFA 연동 대상을 기존 OIDC/SAML IdP로 지정하고 다음 단계 진행.
- 결정: 특정 IdP 제품/claim 값을 가정하지 않고 검증 계약을 설계했다. assertion은 backend cryptographic validation 후 immutable subject와 로컬 사용자를 매핑하고 최소 assurance evidence만 보관한다. 클라이언트 MFA flag는 거부한다.
- 설계: Tool revision publication 승인과 부작용 call approval을 분리; exact tuple/digest, 다중 독립 승인, CAS/append-only ledger, step-up freshness, publish 재검증, 실행 직전 재검증 및 durable receipt/unknown 처리를 정의. 상세는 [[200.프로젝트실행/250.구현/MCP Tool Gateway 상세 구현/2026-10-18 exact revision 승인 gate OIDC-SAML 설계]].
- 상태: 설계 문서·추적표만 갱신. 코드/migration/DB/API/IdP 설정 변경 없음. 실제 승인·게시·호출은 계속 fail-closed. `git diff --check` 통과; IdP/DB/API/pytest 검증은 미실행.
- 미결/다음: 기관 issuer/metadata, immutable subject mapping, assurance allowlist와 freshness, key rollover 담당 및 sandbox를 확정한 다음 verifier부터 구현한다. 이후 별도 clone에서 assertion/2인 approval/revision race/tenant 경계를 검증한다.


## 2026-10-18 · OIDC/SAML assurance 저장 계약 migration
- 요청: “네 진행 바랍니다” — 기존 OIDC/SAML 대상으로 fail-closed MFA 기반 다음 단계 진행.
- 확인: 현재 `app/auth/sso.py` callback은 synthetic/mock identity를 생성하며 실제 signature/issuer/audience 검증기가 아니다. 이를 step-up 증거로 사용하지 않는다.
- 변경: 신규 additive `src/backend/migrations/059_idp_assurance_evidence_contract.sql` 추가. tenant-scoped OIDC/SAML policy revision과 session assurance evidence 저장 계약, RLS/FORCE RLS, web/index/meter 직접 권한 차단, immutable update/delete trigger를 둔다. 기존 migration/DB 미변경. 상세 [[200.프로젝트실행/250.구현/MCP Tool Gateway 상세 구현/2026-10-18 exact revision 승인 gate OIDC-SAML 설계]].
- 상태: issuer policy/evidence는 비어 있으며 migration 미적용. MFA verifier, provider config, multi-approval/publish/call gate 미구현. Dynamic approval fail-closed 유지.
- 검증: migration 구조 assertion 및 `git diff --check` 통과. DB clone 적용, SQL 권한, pytest, API 및 실제 IdP 시험은 미실행.
- 다음: IdP issuer/metadata, immutable subject mapping, assurance allowlist/freshness 및 key rollover 계약 확인 후 verifier/RPC를 구현하고 별도 fixture clone에서 059를 적용·검증.


## 2026-10-18 · 기관 IdP 설정값 수집 가이드
- 요청: 기관 IdP issuer/metadata, subject 매핑, MFA assurance 및 유효시간을 어떻게 정할지 안내.
- 조사 근거: OIDC Core `iss/sub/aud/auth_time/acr/amr` 요구와 OASIS SAML persistent NameID/AuthnContext/AuthnInstant, NIST 재인증 시간 정책 안내를 확인했다.
- 결정/권고: claim semantics는 IdP와 기관이 합의한 exact allowlist로만 인정한다. Subject는 `(issuer, protocol, immutable subject)`에서 local user UUID로 명시 매핑하고 email/login 자동 연결은 금지한다. 금융 side-effect 승인에 승인자별 직전 step-up 및 300초 freshness를 프로젝트 제안값으로 기록하되 기관 보안 정책 승인 전 확정값이 아님을 표시한다.
- 제약: migration 059에는 subject 필드 선택값과 evidence 보관만 있고 subject-to-user mapping table/RPC 및 실제 verifier가 없음을 문서에 명시했다. 이를 구현 전까지 MFA approval은 fail-closed다.
- 기록: [[200.프로젝트실행/250.구현/MCP Tool Gateway 상세 구현/2026-10-18 exact revision 승인 gate OIDC-SAML 설계]].


## 2026-10-18 · Assurance 및 subject mapping schema clone 검증
- 요청: 059 clone 검증 후 비활성 기본값의 subject-account mapping 구조를 진행.
- 변경: additive migrations 059(tenant-scoped IdP assurance policy/evidence), 060(원문 subject 비저장 append-only mapping event ledger) 추가. `ai_web` direct grants 없음, RLS/FORCE RLS, immutable trigger. 기존 migrations 및 active fixture 미변경. 상세 [[200.프로젝트실행/250.구현/MCP Tool Gateway 상세 구현/2026-10-18 exact revision 승인 gate OIDC-SAML 설계]].
- 검증: private backup baseline과 clone을 대조, head 060 / 61 migration entries / source checksum mismatch 0; 기존 74개 테이블 322행의 개별 fingerprint 일치. 신규 3개 테이블 각 0행. RLS/FORCE RLS와 trigger 활성 확인, `ai_web` direct read 권한 부재 및 runtime-role read 거부 확인. disposable clone 및 baseline DB/cluster 종료·삭제 완료.
- 제한: API, pytest, actual trigger mutation behavior, IdP assertion verifier는 미검증. Subject map writer/resolver RPC와 digest HMAC service가 없어 신규 ledger는 비어 있으며 MFA approval은 fail-closed.
- 다음: IdP 계약 수집 이후 server verifier와 keyed subject digest, mapping transition RPC를 추가하고 별도 clone에서 subject collision/revoke/relink 및 cross-tenant 검증.


## 2026-10-18 · Verified subject mapping RPC 구현
- 요청: 기관 IdP 연결 전 단계에서 안전한 verified subject mapping RPC를 진행한다.
- 결정: 현 mock SSO를 assurance로 승격하지 않는다. 클라이언트 subject/digest/user 입력을 금지하고, 검증된 evidence에서 issuer·subject digest·key version을 가져와 현재 사용자 계정 본인만 연결/해제하도록 제한했다. policy head는 존재하지 않는 기본 상태이며 비활성 제약으로 닫아 둔다.
- 변경: 신규 additive `src/backend/migrations/061_verified_idp_subject_mapping_rpc.sql`. fresh assurance 검사, issuer/policy digest/session/tenant 일치, AAL2/3 및 freshness, idempotency key, revision CAS, advisory lock, link/revoke collision 확인, append-only mapping event 및 audit event를 정의했다. table 직접 권한 대신 RPC 실행권한만 `ai_web`에 부여했다.
- 상태: 구현 추가. API route, actual OIDC/SAML verifier, HMAC secret service/key rotation, policy management와 resolver는 미구현. 실 issuer/MFA 설정도 없음.
- 검증: `git status`에서 신규 migration 확인. 기본 devdb status가 `UNOWNED_RUNTIME`을 반환해 clone restore/apply 및 SQL 런타임 검증은 미수행. pytest, active fixture 적용/수정 모두 미수행. 운영/기관 수용 완료로 보지 않는다.
- 관련: [[200.프로젝트실행/250.구현/MCP Tool Gateway 상세 구현/2026-10-18 verified subject mapping RPC 구현 결과]], [[200.프로젝트실행/250.구현/MCP Tool Gateway 상세 구현/00 구현 추적]], [[200.프로젝트실행/250.구현/MCP Tool Gateway 상세 구현/2026-10-18 exact revision 승인 gate OIDC-SAML 설계]].
- 다음: 관리되지 않는 기본 devdb는 건드리지 않고, 별도의 marker 검증 disposable clone을 준비해 migration 061 및 cross-tenant/replay/revision 경계를 확인한다.


## 2026-10-18 · Verified subject mapping migration clone 검증
- 요청: 신규 RPC migration을 별도 backup clone에서 검증하고 기존 데이터 보존을 확인한다.
- 수행: private backup head 055에서 baseline DB와 test DB를 분리 복원했다. isolated cluster port 55433에서 056–061 적용 후 schema migration ledger를 검증했다. migration 파일 선택 실수로 처음에는 050 migration이 시작되어 duplicate-table 오류가 발생했으나 해당 migration 트랜잭션은 커밋되지 않았다. 056–061로 선택 범위를 고쳐 fresh restore clone에서 전부 재적용했다.
- 결과: head 061 / entries 62 / source checksum mismatch 0. baseline 74개 테이블 322행의 JSONB 지문 변경 0, 누락 0. 신규 4개 assurance/evidence/mapping/policy-head 테이블은 빈 상태. 모두 ENABLE/FORCE RLS; ai_web 직접 SELECT/INSERT 거부; mapping RPC는 ai_web EXECUTE 허용 및 PUBLIC 거부. self-scoped evidence INSERT 정책 1개, immutable trigger 3개 활성 확인.
- 정리: disposable cluster 중지·임시 디렉터리 및 socket 제거, port 55433 clear. 정규 devdb는 stopped로 확인했고 migration 미적용.
- 제한: 실제 assertion이 없으므로 RPC 성공·replay·revocation·collision 실행 경로는 호출하지 않았다. IdP verifier, HMAC service, API route/UI 및 실제 기관 연동은 계속 미완료다.
- 관련: [[200.프로젝트실행/250.구현/MCP Tool Gateway 상세 구현/2026-10-18 verified subject mapping RPC 구현 결과]], [[200.프로젝트실행/250.구현/MCP Tool Gateway 상세 구현/00 구현 추적]].


## 2026-10-18 · Subject mapping API 접점 구현
- 요청: clone 검증 다음 단계로 verified subject mapping RPC를 인증된 API 경로에 연결한다.
- 변경: `src/backend/app/auth/subject_mapping.py` repository와 `POST /api/v1/auth/idp/subject-mapping` route를 추가했다. 기존 auth cookie/CSRF와 tenant context resolver를 재사용하고, `extra=forbid`, query 미허용, action/evidence UUID/idempotency UUID/expected revision만 수신한다. user/session/tenant는 서버 context에서 공급한다. `app/errors.py`에 assurance 누락·mapping 충돌용 고정 메시지를 추가했다.
- 보안 경계: route는 raw subject/digest/대상 user를 수신·반환하지 않는다. SQLSTATE와 고정 primary message만 대응 코드로 변환한다. 유효한 서버 검증 evidence가 현재 없으므로 정상 매핑은 계속 거부된다. mock SSO callback은 verifier/evidence writer로 사용하지 않는다.
- 검증: `git diff --check` 통과. pytest와 HTTP 왕복은 실행하지 않았다. migration 056–061의 별도 backup clone 검증 결과는 직전 기록에 포함했다. 활성 fixture/API 프로세스는 변경하거나 재시작하지 않았다.
- 미완료/다음: actual OIDC/SAML verifier, issuer/metadata 및 assurance allowlist 정책, keyed subject HMAC/rotation, evidence issuer/resolver, UI 및 실제 HTTP 회귀는 미완료다. 관련: [[200.프로젝트실행/250.구현/MCP Tool Gateway 상세 구현/2026-10-18 verified subject mapping RPC 구현 결과]], [[200.프로젝트실행/250.구현/MCP Tool Gateway 상세 구현/00 구현 추적]].


## 2026-10-18 · IdP 검증 경계 및 subject digest 구현
- 요청: IdP 연동 준비 전 서버 verifier 및 keyed subject digest 작업을 진행한다.
- 결정: 고객/기관 issuer와 claim 정책이 없으므로 verifier는 backend 미주입 상태로 fail-closed를 유지한다. 토큰·SAML assertion을 검증 없이 파싱하거나 MFA evidence를 만들지 않는다. HMAC subject digest는 서버 설정으로만 제공하며 verifier 활성화와 분리한다.
- 변경: `src/backend/app/auth/idp_verifier.py`, `app/config.py`, `app/main.py`, `app/auth/sso.py`, `app/errors.py`. mock callback은 synthetic/미검증임을 반환한다. 실제 crypto backend, evidence writer, policy 활성화, Secret Manager/key rotation은 미구현이다.
- 검증: Python AST parse 7개 파일 통과, `git diff --check` 통과. `py_compile`은 `__pycache__` 쓰기 권한 오류로 완료되지 않았다. pytest, HTTP/DB 및 기관 IdP 검증은 미수행.
- 상태: 코드 준비 경계 구현. 실제 인증·MFA 수용이나 운영 연동 완료가 아니다. 다음은 기관 IdP 설정 계약과 crypto backend/Secret Manager 검토다.
- 관련: [[200.프로젝트실행/250.구현/MCP Tool Gateway 상세 구현/2026-10-18 IdP 검증 경계 및 subject digest 구현 결과]], [[200.프로젝트실행/250.구현/MCP Tool Gateway 상세 구현/00 구현 추적]], [[200.프로젝트실행/250.구현/MCP Tool Gateway 상세 구현/2026-10-18 exact revision 승인 gate OIDC-SAML 설계]].


## 2026-10-18 · Subject digest 키 버전·회전 경계
- 요청: IdP 연동 전 진행할 수 있는 secret lifecycle 기반 작업을 이어간다.
- 결정: 특정 클라우드 Secret Manager를 가정하지 않고 server-only `SubjectKeyProvider` 경계와 버전별 HMAC keyring을 제공한다. 활성 버전은 새 digest 생성에 쓰고, 보존 버전은 기존 digest 재현용으로만 선택한다. provider/key 누락과 알 수 없는 버전은 거부한다.
- 변경: `src/backend/app/auth/idp_verifier.py`에 `SubjectKeyProvider`와 immutable `SubjectDigestKeyring`을 추가했다. 기존 단일-key service는 새 keyring을 사용한다.
- 검증: Python `py_compile` 및 `git diff --check` 통과. pytest, 외부 Secret Manager 및 rotation/DB mapping migration 시험은 미수행. 실제 provider를 앱에 연결하지 않아 운영 rotation은 아직 제공되지 않는다.
- 다음: 기관 배포 환경의 Secret Manager 선택 후 adapter와 key reference/rotation·retention·retire runbook을 구현한다. 그 다음 exact-revision MFA 승인 gate를 구현하되 유효 IdP evidence가 없으면 승인과 publish는 계속 거부한다.
- 관련: [[200.프로젝트실행/250.구현/MCP Tool Gateway 상세 구현/2026-10-18 IdP 검증 경계 및 subject digest 구현 결과]], [[200.프로젝트실행/250.구현/MCP Tool Gateway 상세 구현/00 구현 추적]], [[400.프로젝트관리/02 포털 UI UX 작업 기록]].


## 2026-10-18 · Secret provider 주입 경계
- 요청: Secret Manager 연동 준비를 이어간다.
- 확인: 환경별 설정 계획/결과에는 dev/tb/prd의 실제 secret management가 미완료이며, Vault에는 승인된 Secret Manager 제품/계정이 지정되어 있지 않다. 특정 클라우드 SDK를 임의 선택하지 않았다.
- 변경: `src/backend/app/main.py`에 `SubjectKeyProvider` 의존성 주입, `app/config.py`에 버전 집합/활성 버전 설정과 유효성 검사, `app/auth/idp_verifier.py`에 provider load 오류를 비밀 값 없이 실패 처리하도록 연결했다. provider 지정 시 설정된 모든 키 버전을 시작 시 읽고, active key 누락·구성 모호성 시 앱 시작을 거부한다.
- 검증: Python `py_compile` 및 `git diff --check` 통과. 실제 Secret Manager 호출, pytest, key rotation 및 DB digest migration은 미수행.
- 미완료/다음: 기관이 운영할 Secret Manager 제품과 workload identity/권한/secret reference/rotation 정책을 지정하면 해당 provider SDK adapter와 운영 절차를 추가한다. 이후 exact-revision MFA approval gate는 provider assertion/evidence가 유효해지기 전까지 fail-closed 상태로 둔다.
- 관련: [[200.프로젝트실행/250.구현/MCP Tool Gateway 상세 구현/2026-10-18 IdP 검증 경계 및 subject digest 구현 결과]], [[200.프로젝트실행/250.구현/MCP Tool Gateway 상세 구현/00 구현 추적]], [[100.프로젝트계획/14 환경별 설정 관리와 local 포트 분리 실행 계획]], [[400.프로젝트관리/02 포털 UI UX 작업 기록]].


## 2026-10-18 · 동적 Tool revision digest 불변성 migration source 추가
- 요청: Secret Manager 제품 선택 전에도 진행할 수 있는 Gateway 보안 작업을 계속한다.
- 확인/결정: 환경/배포 문서에는 AWS/Azure/GCP/Vault 중 승인된 provider가 없다. 제품 SDK를 추정해 추가하지 않는다. exact-revision 승인 기반으로 동적 Tool revision 무결성 migration을 새 파일로만 추가한다.
- 변경: `src/backend/migrations/062_mcp_tool_version_integrity.sql`은 schema와 imported source metadata의 canonical SHA-256 digest를 backfill/저장하고 신규 row insert trigger에서 계산·검증하며 버전 update/delete를 거부한다. 기존 migration은 수정하지 않았다.
- 상태: migration source 추가, 미적용. source 파일 작성 외 active DB, fixture, migration ledger 변경 없음.
- 검증: `git diff --check`와 수동 SQL 구조 검토만 수행. 별도 backup clone의 SQL 실행, row fingerprint/checksum/RLS 권한 및 trigger denial 검증은 아직이다.
- 다음: 기존 데이터 백업을 기준으로 폐기 가능한 fixture clone에만 062를 적용·검증한다. 결과 전까지 migration을 활성 fixture에 적용하지 않는다. exact-revision 승인·publish는 MFA evidence 부재로 계속 닫혀 있다.
- 관련: [[200.프로젝트실행/250.구현/MCP Tool Gateway 상세 구현/2026-10-18 동적 Tool revision digest 불변성 migration 구현안]], [[200.프로젝트실행/250.구현/MCP Tool Gateway 상세 구현/00 구현 추적]], [[200.프로젝트실행/250.구현/MCP Tool Gateway 상세 구현/2026-10-18 동적 Tool 승인 gate 계약 조사 결과]], [[400.프로젝트관리/02 포털 UI UX 작업 기록]].


## 2026-10-18 · 062 backup clone 적용 검증
- 요청/승인: 사용자가 다음 단계 진행을 승인해 backup 기반 폐기 가능한 clone 검증을 수행했다.
- 실행: private fixture backup을 독립 PostgreSQL 15 임시 cluster/DB에 복원하고 056–062를 적용했다. 개발 fixture/공유 DB에는 적용하지 않았다.
- 결과: migration head `062_mcp_tool_version_integrity.sql`; 기존 74개 업무 테이블/322행 count 보존; source checksum mismatch 0; version digest 누락 0 및 길이 오류 0; integrity trigger enabled; table RLS/ FORCE RLS 모두 true. 임시 clone은 종료·정리했다. 백업 기준 version row가 0개여서 backfill 대상은 없었고, synthetic insert/update/delete trigger SQLSTATE probe는 미수행이다.
- 미완료: 실행 role별 권한 probe, API 통합/pytest, active fixture 적용, 실제 기관/운영 검증.
- 다음: 실행 role 권한/API 계약을 확인한다. active fixture 적용은 별도 승인·백업 gate 후에만 검토한다.
- 관련: [[200.프로젝트실행/250.구현/MCP Tool Gateway 상세 구현/2026-10-18 062 backup clone 검증 결과]], [[200.프로젝트실행/250.구현/MCP Tool Gateway 상세 구현/2026-10-18 동적 Tool revision digest 불변성 migration 구현안]], [[200.프로젝트실행/250.구현/MCP Tool Gateway 상세 구현/00 구현 추적]].

## 2026-10-18 · MCP Gateway native DB pool 경계 검증
- 요청: 멀티 에이전트 개발 스킬을 적용해 다음 MCP Gateway 작업을 진행한다.
- 결정/범위: test-only pool adapter가 우회한 native pool 포트·DB ownership marker 경계를 테스트한다. DB/공유 fixture를 실행하지 않으며, 격리된 구현 copy에서 시작했다. handoff 후 임시 copy가 사라져 같은 단일 테스트 파일을 원본 backend working tree에 복원하고 재검증했다.
- 변경: `src/backend/tests/test_db_native_boundary.py`에 비정상 포트의 pool 생성 전 거부와 foreign marker 거부/오류 비노출 단위 테스트를 추가했다. 원본 main checkout의 기존 미커밋 변경은 보존했다. 새 테스트는 현재 미커밋 상태이며 다른 기존 변경을 섞지 않기 위해 commit은 만들지 않았다. production 코드와 migration은 변경하지 않았다.
- 검증: 원본 backend에서 `PYTHONDONTWRITEBYTECODE=1 .venv/bin/pytest -q -p no:cacheprovider tests/test_db_native_boundary.py` 결과 `2 passed in 0.05s`. 테스트 검토와 전체 변경 검토 모두 승인/clean. PostgreSQL service 및 fixture는 기동하지 않았다.
- 한계: live PostgreSQL native pool startup, 기관 sandbox, 실제 MCP connector 및 운영 검증은 미실행. dynamic external call은 MFA/IdP 및 publication gate 준비 전까지 차단 유지.
- 다음: 기관 IdP issuer/metadata, immutable subject, assurance freshness/replay 및 key rotation 계약이 확정되기 전에는 verifier를 활성화하지 않고, fail-closed 경계를 유지한다.
- 관련: [[200.프로젝트실행/250.구현/MCP Tool Gateway 상세 구현/2026-10-18 native DB pool 경계 단위 검증]], [[200.프로젝트실행/250.구현/MCP Tool Gateway 상세 구현/00 구현 추적]].


## 2026-10-18 · IdP verifier fail-closed 단위 검증
- 요청: 기관 IdP 설정이 미정인 동안 진행 가능한 fail-closed boundary 검증을 계속한다.
- 결정/범위: 실제 issuer/claim/MFA 정책 또는 Secret Manager가 미정이므로 verifier는 비활성으로 유지하고, 현재 `IdpVerifier`/versioned digest keyring의 합성 단위 동작만 확인한다.
- 변경: `src/backend/tests/test_idp_verifier_boundary.py` 추가. 미설정 OIDC/SAML 거부, synthetic backend 입력 전달 및 identity 반환, key rotation/도메인 분리, key 누락/provider 예외의 고정 오류·secret 미노출을 검증한다. production code/migration/config는 변경하지 않았다.
- 검증: `.venv/bin/python -m pytest --noconftest -p no:cacheprovider tests/test_idp_verifier_boundary.py -q` 결과 `10 passed in 0.45s`. Task review spec/quality 모두 PASS. DB/fixture/network/실제 IdP를 사용하지 않았다.
- 한계/다음: 실제 IdP signature 검증, evidence 발급, MFA 정책, Secret Manager/key rotation 및 기관 수용은 미구현이다. 기관 설정값과 provider 결정 전 fail-closed 유지.
- 관련: [[200.프로젝트실행/250.구현/MCP Tool Gateway 상세 구현/2026-10-18 IdP verifier fail-closed 단위 검증]], [[200.프로젝트실행/250.구현/MCP Tool Gateway 상세 구현/00 구현 추적]].


## 2026-10-18 · 동적 production dispatch fail-closed 보강
- 요청/결정: IdP/MFA와 exact-revision 승인 gate가 미완성인 동안 동적 Tool의 `approved_published` 값만으로 production dispatch가 열리지 않도록 차단한다.
- 변경: `src/backend/app/tools/dynamic_gateway.py`에서 invocation 첫 단계에 `TOOL_DYNAMIC_REVIEW_ONLY` 409를 반환하고 production routing branch를 제거했다. 개발 simulation은 유지했다. `tests/test_mcp_tool_autowrap.py`에 side effect 없는 거부 회귀 검증을 추가/갱신했다. 공개 route의 server-forced draft는 그대로다.
- 실제 검증: focused pytest `9 passed in 0.58s`; 지정 diff `git diff --check` 통과; 독립 task review PASS. DB/fixture/실제 connector/IdP는 사용하지 않았다.
- 미완료: 실제 IdP/MFA, Secret Manager, exact-revision quorum/publish/call gate, production connector 및 영속 audit. 운영 dispatch는 차단 상태이며 기관 수용/배포로 간주하지 않는다. 변경은 미커밋이다.
- 다음: 기관 보안 설정 결정 전 fail-closed 유지. 이후 승인 상태 전이와 revision-bound call authorization 계약을 구체화한다.
- 관련: [[200.프로젝트실행/250.구현/MCP Tool Gateway 상세 구현/2026-10-18 동적 production dispatch fail-closed 보강]], [[200.프로젝트실행/250.구현/MCP Tool Gateway 상세 구현/00 구현 추적]].


## 2026-10-18 · exact revision 게시 준비도 fail-closed 계약 구현
- 요청/결정: IdP/MFA와 exact-revision 승인 workflow가 미정이므로 게시·실행 허가를 열지 않고, 요청 snapshot과 현재 descriptor의 일치 여부 및 차단 이유를 관리자 상세에 명시한다.
- 변경: `src/backend/app/tools/publication_gate.py` pure comparator와 `GET /admin/tool-approvals/{request_id}`의 동적 상세 응답 decoration을 추가했다. `publishable`/`execution_ready`는 항상 false다. 정적 Tool 응답, 승인 decision, list/call 및 DB schema는 변경하지 않았다. 신규 focused unit tests를 추가했다.
- 실제 검증: `tests/test_dynamic_publication_gate.py` `5 passed in 0.15s`; scoped diff check 통과; 독립 리뷰 PASS. API HTTP 왕복, DB/fixture/IdP/실 connector는 사용하지 않았다.
- 미완료: issuer/MFA 설정, exact-revision quorum/decision/publish transaction, 실제 connector/durable receipt. 결과는 게시 승인이 아니며 production dispatch는 계속 닫혀 있다. 변경 미커밋·미배포.
- 다음: 승인·게시 ledger/RPC 계약을 새 additive migration으로 설계하고 backup disposable clone에서 검증한다. IdP/MFA 결정 전에는 fail-closed 유지.
- 관련: [[200.프로젝트실행/250.구현/MCP Tool Gateway 상세 구현/2026-10-18 exact revision 게시 준비도 fail-closed 계약 구현]], [[200.프로젝트실행/250.구현/MCP Tool Gateway 상세 구현/00 구현 추적]].


## 2026-10-19 · 게시 준비도 route 계약 테스트
- 요청: SDD 방식으로 남은 MCP Gateway 안전 구현을 이어간다.
- 변경: `src/backend/tests/test_mcp_tool_publication_gate_routes.py`를 추가해 동적 상세 응답의 일치/불일치 및 static response shape를 실제 endpoint/helper/serializer를 통해 확인했다. 애플리케이션 코드나 DB schema는 변경하지 않았다.
- 검증: 지정 focused pytest 3 passed in 0.92s, 신규 파일 diff check 통과, task review spec/quality PASS. mock 격리 단위 시험이며 실제 HTTP 인증·DB·IdP·기관 수용 증거는 아니다.
- 제한/다음: 다음 migration clone 검증에 필요한 기존 기록 backup `.runtime/backups/mcp-gateway-20261018/active-fixture.dump`를 현재 저장소에서 확인하지 못했다. native DB는 stopped로 유지하고 재기동하지 않는다. backup artifact 복구/검증 및 disposable clone을 준비한 뒤 migration 작업을 재개한다. IdP/MFA/Secret Manager 미정 상태에서 게시·실행 권한은 계속 차단한다.
- 관련: [[200.프로젝트실행/250.구현/MCP Tool Gateway 상세 구현/2026-10-19 게시 준비도 route 계약 테스트]], [[200.프로젝트실행/250.구현/MCP Tool Gateway 상세 구현/00 구현 추적]].


## 2026-10-19 · Registry 목록 RPC와 HMAC 환경 버전 수정
- 요청/결정: 전체 변경 리뷰의 두 지적을 테스트부터 보강한다. 기존 migration056은 보존하고 새063에 tenant-authorized 단일 배열 집계 RPC를 추가한다. 단일 HMAC 버전은 환경 문자열만 명시적으로 변환하며 직접 bool/float/string과 잘못된 범위를 계속 거부한다.
- 변경: `src/backend/migrations/063_mcp_tool_registry_list_rpc.sql`, `app/tools/dynamic_repository.py`, `app/config.py`, `tests/test_dynamic_registry_list.py`, `tests/test_idp_subject_settings.py`. 기존 repository/route 반환 계약과 오류 변환을 유지했다.
- 검증: focused unit RED 3 failed/26 passed (1.06s), GREEN 47 passed (0.75s), scoped diff check 수행. 056 전후 SHA-256 동일. PostgreSQL/fixture/network/공유 서비스는 실행하지 않았다.
- 미완료/다음: 기록된 backup 파일 존재 여부 false. clone 검증 BLOCKED, 063 소스 미적용. 검증된 백업 확보 후 disposable clone에서 다중 Tool/빈 목록/RLS/권한/행·checksum 보존을 확인한다. active runtime 수정·기관 수용·운영 배포 완료가 아니며 미커밋 상태다.
- 관련: [[200.프로젝트실행/250.구현/MCP Tool Gateway 상세 구현/2026-10-19 Registry 목록 RPC와 HMAC 환경 버전 수정]], [[200.프로젝트실행/250.구현/MCP Tool Gateway 상세 구현/00 구현 추적]].

## 2026-10-20 MCP Tool Gateway 최종 리뷰 보완
- 요청: 최종 리뷰 잔여 finding을 수정하고 상세 구현·검증 이력을 남김.
- 결정: dynamic simulation은 저장하지 않고 요청 단위 fixture Gateway에서 처리한다. 영속 등록은 관리자의 별도 등록 동작으로 한정한다. 동적 등록은 reserved static Tool ID를 거부한다. validation 오류에 입력값을 표시하지 않으며 승인 라벨은 위험 분류와 일치시킨다.
- 변경: backend 설정/라우트, frontend 승인 패널·Tool 관리, migration 064 및 집중 테스트.
- 검증: backend 84 passed; simulation helper 4 passed; approval label 6 passed; scoped diff check 통과. 최종 whole-branch review Spec/Quality PASS, Critical/Important 잔여 없음. TypeScript 통과, Vite build는 sandbox EPERM으로 중단.
- 미완료: 검증 백업과 disposable clone 부재로 migration 063/064 미적용. 실제 DB RLS/ACL/checksum 및 기관 connector/IdP 검증, 전체 build, UAT, 배포는 미완료. 테스트는 기관 수용 증거가 아님.
- 다음: clone 검증 경로 확보 후 migration 순차 검증; 허용된 Vite cache 환경에서 전체 관리자 build 수행.


## 2026-10-20 · MCP Tool Gateway 063/064 clone 검증
- 요청: 마지막 작업을 확인하고 SDD 방식으로 남은 MCP Gateway 작업을 계속 진행한다.
- 결정: 기록된 backup을 별도 PostgreSQL 15 disposable cluster에서만 복원·검증한다. active fixture/native DB에는 migration을 적용하지 않는다.
- 변경: 코드 추가 변경 없음. 063/064 검증 결과, checksum·데이터 보존 및 synthetic gate 결과를 기록했다.
- 검증: 056–064 순차 적용, migration source checksum 65/65 일치, 기존 75개 테이블의 행 수 및 fingerprint 보존, owner/ACL/RLS/trigger 통과. 063 empty/multi-tool aggregation 및 cross-tenant denial, 064 reserved-ID 세 건 차단 통과. Synthetic changes rollback. 전용 clone/runtime 정리 완료, 55432/55433 listener 없음.
- 미완료: active fixture/native 적용, IdP/MFA/Secret Manager/실 connector, browser UAT 및 운영 배포·기관 수용은 별도 미완료. fail-closed 유지. 관리자 full build 재실행 통과 (TypeScript/Vite/admin boundary verified; 229 modules); 500KB 초과 JS chunk 경고 1건. 소스는 미커밋.
- 다음: 활성 환경 변경은 별도 승인된 배포 창·백업/복구 절차에서 수행하고, IdP/MFA·connector 계약과 실제 운영 검증을 진행한다.
- 관련: [[200.프로젝트실행/250.구현/MCP Tool Gateway 상세 구현/2026-10-20 063-064 백업 클론 검증 결과]], [[200.프로젝트실행/250.구현/MCP Tool Gateway 상세 구현/00 구현 추적]].


## 2026-10-20 · 관리자 UI 빌드 재검증
- 요청/결정: sandbox의 Vite cache 쓰기 제한으로 중단됐던 관리자 UI build를 로컬 허용 환경에서 재실행한다.
- 검증: `npm run build:admin` 성공. TypeScript, Vite(229 modules), `verify-portal-builds.mjs admin`의 admin boundary 검증 통과. minified JS chunk 718.52 kB (gzip 207.07 kB)로 500 kB 초과 warning 발생.
- 한계: 로컬 build 산출이며 서비스 배포나 브라우저/UAT 검증은 아니다.
- 관련: [[200.프로젝트실행/250.구현/MCP Tool Gateway 상세 구현/2026-10-20 최종 리뷰 수정 및 검증 결과]], [[200.프로젝트실행/250.구현/MCP Tool Gateway 상세 구현/00 구현 추적]].


## 2026-10-20 · MCP Streamable HTTP discovery adapter
- 요청: 다음 MCP Gateway 작업을 SDD 방식으로 진행한다.
- 결정: T035-C의 첫 증분으로 official MCP Python SDK `mcp==2.3.0`을 exact pin/hash lock하고 읽기 전용 `tools/list` discovery만 구현한다. SDK protocol negotiation/reconnect는 멱등 discovery 범위에서만 허용; app-level retry 없음. exact HTTPS hostname allowlist 및 redirect 차단 적용.
- 변경: `src/backend/app/tools/transports/streamable_http.py`, `src/backend/app/tools/transports/__init__.py`, `src/backend/tests/test_mcp_streamable_http.py`, `src/backend/requirements.in`, `src/backend/requirements.lock`. 최신 MCP status와 결정은 [[200.프로젝트실행/250.구현/MCP Tool Gateway 상세 구현/2026-10-20 Streamable HTTP 도구 탐색 어댑터 구현]]에 기록.
- 검증: backend Python 3.13, `mcp==2.3.0`; `tests/test_mcp_streamable_http.py` 35 passed; `pip check` 정상; 55 locked distributions 모두 hash 포함, 기존 locked versions 유지; `git diff --check`; independent review Spec PASS/quality PASS with Minor report-count correction fixed.
- 제한: test는 injected MockTransport만 사용. 실 MCP server, DB/fixture/service, endpoint profile, credentials, tool call, approval dispatch, external connector/UAT/deployment 없음. DNS rebinding, total JSON body limit, CPU parsing bound 미해결; fail-closed production dispatch 유지.
- 다음: 실제 adapter 통합 전 기관 승인 endpoint/egress allowlist·DNS pinning, auth delegation/Secret Manager 계약을 설계하고 `tools/list` API를 등록·정책·RLS와 연결한다. 그 이후에만 `tools/call`을 별도 approval/audit/cost gate 작업으로 설계한다.
- 관련: [[200.프로젝트실행/250.구현/MCP Tool Gateway 상세 구현/00 구현 추적]], [[200.프로젝트실행/250.구현/MCP Tool Gateway 상세 구현/2026-10-20 Streamable HTTP 도구 탐색 어댑터 구현]].


## 2026-10-21 · MCP Streamable HTTP 누적 응답 한도
- 요청/결정: SDD 방식으로 MCP Gateway 남은 작업을 계속한다. discovery 전체 응답에 누적 한도를 두고, 압축 응답을 통한 byte cap 우회와 동시 GET 오류 흡수를 차단한다.
- 변경: bounded transport가 negotiation 및 모든 JSON/SSE 응답 스트림을 호출 단위 2 MiB로 합산하고, `Accept-Encoding: identity`를 설정한다. 비identity encoding은 body read 전에 고정 오류로 거부하고 stream을 닫는다. SDK·HTTP cleanup 뒤 latched rejection flag를 확인해 background GET overflow/encoding 예외가 있어도 성공 catalog를 반환하지 않는다. 실제 수정은 `streamable_http.py`, `test_mcp_streamable_http.py`에 한정된다.
- 실제 검증: 집중 pytest `53 passed in 1.52s`; 독립 SDD review에서 재현된 Important 동시 GET 문제 수정 후 Spec/Quality PASS, 잔여 finding 없음. injected MockTransport만 사용했다.
- 미완료/제한: endpoint·registry API·`tools/call`, DNS rebinding/SSRF 완화, egress/DNS pinning, 인증·Secret Manager, 기관 sandbox/UAT 및 배포는 미완료다. IdP/MFA가 미설정되어 production dispatch는 fail-closed다. 이 작업은 기관 수용 또는 운영 완료가 아니다. 변경은 미커밋이다.
- 다음: connector 통합 전에 기관 승인 endpoint/egress·DNS pinning 및 자격증명 위임 계약을 확정한 뒤 제한된 `tools/list` API 통합을 별도 검토한다. `tools/call`은 승인·감사·비용 gate가 준비될 때까지 추가하지 않는다.
- 관련: [[200.프로젝트실행/250.구현/MCP Tool Gateway 상세 구현/2026-10-21 Streamable HTTP 누적 응답 한도 보강]], [[200.프로젝트실행/250.구현/MCP Tool Gateway 상세 구현/2026-10-20 Streamable HTTP 도구 탐색 어댑터 구현]], [[200.프로젝트실행/250.구현/MCP Tool Gateway 상세 구현/00 구현 추적]].


## 2026-10-21 · MCP Tool Gateway 서비스 적용 전 위험 점검
- 요청: 현재 구현을 마무리 상태로 둘 때 서비스 영향 가능성이 있는지 검토하고, 적용 전 할 일을 Obsidian에 남긴다.
- 점검 결과: 소스 기준 즉시 발생 중인 운영 장애는 확인하지 못했다. 코드 변경은 미커밋·미배포이며 active service/DB/customer consumers/UAT 상태는 이 점검에서 확인하지 않았다. 따라서 무장애 보증이나 운영 승인으로 기록하지 않는다.
- 확인한 적용 전 작업: (1) runtime migration 상태와 063/064 코드 순서를 확인한다. 063/064는 backup clone 검증까지만 수행했다. (2) TADMIN/PADMIN role mapping과 기존 API client의 credential payload 호환을 확인한다. (3) 인증 사용자에게 노출된 명세 parse endpoint의 role/body size/파서 자원 제한을 점검한다. (4) synthetic SSO callback이 인증 성공으로 표현되지 않는지 UI 소비자를 확인한다. (5) 승인된 staging에서 역할·tenant·parse·register/list/simulate 경로를 확인한다.
- MCP 경계: Streamable HTTP discovery adapter 호출처를 현재 app route/service에서 찾지 못했다. 실제 원격 MCP/금융 endpoint, `tools/call`, production dispatch는 연결되지 않았고 fail-closed다. 테스트/clone/build 증거는 운영 연결이나 배포가 아니다.
- 다음: 사용자가 마무리한 현재 구현을 보존하고, 서비스 적용 결정 시 이 체크리스트를 release gate로 사용한다. 실제 MCP 대상/IdP 설정은 추후 확정 후 별도 진행한다.
- 관련: [[200.프로젝트실행/250.구현/MCP Tool Gateway 상세 구현/2026-10-21 MCP Tool Gateway 서비스 적용 전 위험 점검]], [[200.프로젝트실행/250.구현/MCP Tool Gateway 상세 구현/00 구현 추적]], [[200.프로젝트실행/250.구현/MCP Tool Gateway 상세 구현/2026-10-21 Streamable HTTP 누적 응답 한도 보강]].


## 2026-10-21 · AI Builder 고도화 통합 Studio 검토

- **요청:** 현재 구현된 AI Builder를 검토하고, 비전문가 현업 사용자를 위한 high-end AI Builder 고도화 방향을 brainstorming으로 설계.
- **결정:** 제작자 생산성·노코드 UX 우선. Agent와 Workflow를 하나의 AI Studio에서 탭으로 전환하되 편집 모델은 별도 유지. Agent/Workflow 모두 자연어 빠른 시작과 수동 제작을 지원하고, 자연어 결과는 저장 전 사람이 검토하는 제안으로 제한. 초안의 실행/공개 금지, tenant/owner·자료 ACL·비용/감사 원장·기존 승인 gate 유지. 제작자 권한과 운영 승인 권한은 분리.
- **변경:** [[2026-10-21 AI Builder 고도화 통합 Studio 설계]] 새 설계 문서 작성. 앱 코드와 DB는 변경하지 않음.
- **검증·근거:** AIStudioHubPage, Agent Builder profile/trial/evaluation/evidence, Workflow Canvas 및 최신 DP11 잔여/Workflow 복구 기록을 읽어 구현 상태와 미완료 범위를 구분했다. 자동 테스트·빌드·브라우저·기관 UAT는 실행하지 않았다.
- **미완료:** 사용자 최종 문서 검토 대기. 설계 승인은 구현·역할 부여·게시·운영 실행/배포 승인이 아니다.
- **다음:** 사용자가 작성 설계를 검토·승인한 뒤 범위를 반영한 단계별 구현 계획을 별도로 작성한다.


## 2026-10-21 · AI Builder 고도화 구현 계획 수립

- **요청:** 승인된 AI Builder 고도화 설계에서 단계별 구현 계획 작성.
- **결정:** 공통 Studio UX, 공유 자연어 proposal API와 Agent 연결, Workflow Canvas 연결의 세 독립 수용 묶음으로 나눴다. 현업 이용은 DP16 agent_developer capability/심사자 분리 확인을 선행 조건으로 두며, 저장 전 제안은 초안 저장·시험·Tool 호출·승인·게시를 자동 수행하지 않는다.
- **변경 문서:** [[2026-10-21 AI Builder 고도화 구현 계획 목차]], [[2026-10-21 AI Studio 공통 제작 흐름 구현 계획]], [[2026-10-21 AI Builder 자연어 초안 생성 서비스 구현 계획]], [[2026-10-21 Workflow Canvas 자연어 초안 연결 구현 계획]].
- **검증:** 계획은 승인된 설계와 현재 AIStudioHubPage, AssetsPage, Builder profile/trial, Workflow drafts/Canvas, DP16 권한 계획을 대조해 작성했다. 계획 간 의존/API/승인 상태를 문서 자체 점검했다. 앱 코드·migration·DB·테스트·브라우저 검증은 변경하거나 실행하지 않았다.
- **미완료:** 구현은 수행하지 않았다. DP16 역할 수용과 실제 provider/기관 업무 품질은 별도 gate다.
- **다음:** 사용자에게 인라인 순차 실행 방식을 제안하고 선택을 기다린다.


## 2026-10-21 · AI Builder 고도화 구현 착수

사용자의 구현 시작 지시에 따라 승인된 계획의 첫 단위를 시작했다. `src/frontend/src/AIStudioHubPage.tsx`에 빠른 시작/단계별 제작 선택을 추가하고, Agent 제안과 Workflow 실행 간 연결 안내를 게시된 정확한 버전·현재 Tool 권한에 맞게 조정했다. `src/backend/app/builder/scaffold_schemas.py`에는 Agent/Workflow proposal 계약, 입력 제한, secret field 차단, DAG 유효성 검사를 추가했다.

공통 proposal provider 호출은 기존 `portal.runs` admission과 비용 원장에 임의 task를 추가하는 migration, owner 전용 저장 및 replay/delete gate와 함께 구현해야 한다. 이 연결 전에는 provider API를 노출하지 않는다. 현업 사용자 권한, Workflow Canvas 연결, proposal 저장 API, DB migration은 미완료다. 코드 테스트는 추가·실행하지 않았다. 다음은 migration/RLS/settlement 계약과 Mock provider 경로를 구현하며, 기존 migration 000–064는 수정하지 않는다.

### 2026-10-21 · AI Builder 구현 이어서 진행

사용자의 계속 진행 지시에 따라 `AIStudioHubPage.tsx` 탭 전환을 브라우저 뒤로/앞으로 이동에 반영하고, 기존 탭 문구의 Agent/Workflow 직접 연결 오해를 승인·게시된 정확한 버전 및 현재 Tool 권한 기준으로 수정했다. `scaffold_schemas.py`와 신규 `scaffold_prompts.py`에 Agent/Workflow 계약, 사용자 입력 분리, Agent/Tool ID를 모델이 발명하지 못하게 하는 제안 규칙, Workflow graph 연결·순환 검사를 추가했다.

아직 provider API, owner-only 저장/replay/discard, RLS/cost settlement migration, Canvas/Agent 편집기 연결은 미완료이며 제안 API를 노출하지 않았다. 기존 migration이나 DB는 변경·적용하지 않았다. 테스트는 추가·실행하지 않았다. 다음 단계는 065 신규 migration을 기존 conversation/run 접근 경계와 충돌 없이 설계하고 별도 fixture clone에서 검증한 뒤 연결하는 것이다.

### 2026-10-21 · AI Builder proposal 실행 경계 진행

`scaffold_service.py`를 추가해 승인된 구조화 proposal만 기존 Gateway 응답에서 해석하고, Gateway가 usage 정산 및 출력 guardrail 처리를 마친 뒤 strict schema 검증을 수행하도록 구성했다. 기존 `RunTicket`은 worker·검증된 실행 상태를 담는 frozen capability 객체이므로, 요청 메시지를 바꿀 때 직접 mutate하지 않고 불변 복사본을 사용하도록 수정했다. Gateway 미연결 환경, provider 오류, 비정상 JSON/schema 결과는 proposal로 반환하지 않는다.

변경 파일: `src/backend/app/builder/scaffold_service.py`. 검토 근거는 `CallRepository`의 claim/reserve/dispatch/settle 순서, `AiGateway.execute`, migration 032의 builder trial 전용 RLS·admission·claim·finish 경계다. API, migration, DB, 테스트는 추가·적용·실행하지 않았다. 일반 대화 `run_view`와 conversation 접근에서 감춰지는 신규 task kind 및 proposal owner/replay/delete/terminal RPC가 미완료라 UI에 연결하지 않았다. 다음 단계는 신규 migration으로 private proposal admission과 정산 결과 저장·폐기 gate를 구현하고, 별도 fixture clone 검증 후 API를 노출하는 것이다.

### 2026-10-21 · AI Builder proposal 출력 안전성 보강

후속 검토에서 Agent 제안의 자연어 지침·프로필 문자열이 민감정보 검사 범위 밖에 있음을 확인했다. `scaffold_schemas.py`에서 Agent와 Workflow proposal 전체를 재귀 검사하고, URL/endpoint/authorization 키와 URL scheme, Bearer 문자열, API key·password 형식이 포함되면 proposal을 거부하도록 보강했다.

변경 파일: `src/backend/app/builder/scaffold_schemas.py`. 테스트는 추가·실행하지 않았으며 migration/API/DB는 변경하지 않았다. 다음은 별도 실행 capability 및 cost ledger와 연결되는 proposal 전용 admission·저장 경계를 구현하는 것이다.

### 2026-10-21 · AI Builder 전용 실행 ticket 강제

기존 실행 구조를 대조한 결과, 일반 대화 ticket으로 proposal을 생성하면 run 조회·conversation 가시성 및 사용자 메시지 기록 경계를 공유하게 된다. `ScaffoldGenerationService.generate`에서 `task_kind='builder_scaffold'`인 전용 ticket만 허용하도록 fail-closed 검사를 추가했다. 이는 전용 DB admission이 연결될 때까지 일반 대화 경로를 통한 proposal 생성을 차단한다.

변경 파일: `src/backend/app/builder/scaffold_service.py`. 신규 migration, API, DB 적용은 아직 없고 테스트도 실행하지 않았다. 다음 단계는 task kind 제약, 전용 admission/claim/terminal settlement, conversation·run 비가시성, owner-scoped proposal receipt를 하나의 migration 수용 단위로 구현하는 것이다.

## 2026-10-22 · 금융 특화 MCP Tool Gateway 잔여 3대 범위 구현

- **요청:** 사용자 요청에 따라 [[00 구현 추적]] 및 [[100.프로젝트계획/38 금융 특화 MCP Tool Gateway 상세 구현 계획안]]의 잔여 3대 범위(Connector Dispatch, 승인·게시·실행, 감사·복원력) 상세 계획서 수립 및 구현 진행.
- **결정:** 승인된 계획서에 따라 4종 Typed Connector(OpenAPI, WSDL, JDBC, 금융전문)를 구현하고, MockTransport 및 mock socket 기반 contract test로 외부 의존 없이 검증. 게시 원장(065) 및 감사 원장(067, Append-only 트리거) migration 파일 작성. Token Bucket Rate Limiter, Circuit Breaker, Concurrency Limiter 복원력 및 SHA-256 해시체인 무결성 검증, 관리자 감사/헬스체크 API route를 통합 구현.
- **변경 파일:**
  - `src/backend/app/tools/connectors/base.py` (공통 Connector 인터페이스 및 ConnectorResult DTO)
  - `src/backend/app/tools/connectors/openapi_connector.py` (HTTPS 강제, 파라미터 분리, 크기 제한)
  - `src/backend/app/tools/connectors/wsdl_connector.py` (defusedxml 기반 XXE 차단, SOAP Action 검증)
  - `src/backend/app/tools/connectors/jdbc_connector.py` (사전 승인 뷰, DDL/DML 차단, psycopg read-only)
  - `src/backend/app/tools/connectors/financial_packet_connector.py` (고정길이 패킷 레이아웃, LRC 체크섬)
  - `src/backend/app/tools/connectors/__init__.py`
  - `src/backend/app/tools/resilience.py` (RateLimiter, CircuitBreaker, ConcurrencyLimiter)
  - `src/backend/app/tools/audit.py` (AuditLedgerService, SHA-256 해시체인 무결성 검증)
  - `src/backend/app/tools/dispatch.py` (ConnectorDispatcher 통합 디스패처)
  - `src/backend/app/tools/publication_gate.py` (exact_gate_enabled, active_publication, retired 평가)
  - `src/backend/app/tools/dynamic_gateway.py` (ConnectorDispatcher 실제 연동)
  - `src/backend/app/tools/routes.py` (GET /api/v1/admin/tool-audit, GET /api/v1/admin/tool-health)
  - `src/backend/app/errors.py` (도구 실행/보안 관련 새 에러 메시지 7종 추가)
  - `src/backend/migrations/065_mcp_tool_publication_ledger.sql` (게시 원장 및 RLS)
  - `src/backend/migrations/067_mcp_tool_audit_ledger.sql` (감사 원장 및 불변 트리거)
  - `src/backend/tests/test_connector_openapi.py` (12 tests)
  - `src/backend/tests/test_connector_wsdl.py` (3 tests)
  - `src/backend/tests/test_connector_jdbc.py` (3 tests)
  - `src/backend/tests/test_connector_financial.py` (2 tests)
  - `src/backend/tests/test_resilience.py` (3 tests)
  - `src/backend/tests/test_audit_ledger.py` (3 tests)
  - `src/backend/tests/test_audit_routes.py` (2 tests)
  - `src/backend/tests/test_dispatch.py` (3 tests)
  - `src/backend/tests/test_dynamic_publication_gate.py` (8 tests)
- **검증·증거:** 신규 및 확장된 9개 테스트 파일의 총 39개 단위/계약 테스트 전체 통과(GREEN, 0.93s). `test_mcp_tool_simulation_routes.py` 8개 테스트 호환 통과.
- **미완료:** 실제 금융기관 sandbox 연결 검증(접속정보 확보 후), 활성 PostgreSQL 클러스터에 065/067 migration 적용(disposable backup clone 선적용 절차 필요), Secret Manager 실제 제품 어댑터 연동.
- **다음:** 다중 승인 및 quorum 상세화(E2-4), Discovery→Registry 동기화(C2-4), 별도 복원 clone에서 065–067 migration 검증.

## 2026-10-22 · 금융 특화 MCP Tool Gateway 후속 3대 제안 구현 완료
- **요청:** 후속 제안한 3가지 항목(066 게시 통제 RPC 및 Clone 검증, 다중 승인 Quorum, Discovery Import API)에 대한 상세 구현 방안 보고 및 구현 완료.
- **결정:**
  - **게시 통제 RPC & Clone 정적 검증 (Step 1, 2):** 신규 `066_mcp_tool_publication_rpc.sql`(`security.mcp_tool_publication_control`)을 작성하여 PADMIN 자격 검증, 요청자 본인 승인 차단, 구버전 active 원자적 `superseded` 전환 및 신규 `active` 등록을 PostgreSQL RPC로 구현. 000~067 마이그레이션 68개 연속성 및 065~067 DDL/RLS/트리거 정적 보안 검증 통과.
  - **다중 승인 Quorum & 4-Eyes Principle (Step 3):** `src/backend/app/tools/quorum.py`에 `evaluate_quorum()` 구현. 요청자 자기 승인 차단(403), 동일 관리자 중복 승인 차단(409), `read_only` 위험 등급은 1인 단독 승인 즉시 완료, `financial_side_effect`는 2인 Quorum 필수화(1차 시 `partially_approved`, 2차 시 `approved`), 1인이라도 반려 시 즉시 `rejected` 종결.
  - **Discovery → Registry Import API (Step 4):** `src/backend/app/tools/autowrap_routes.py`에 `POST /api/v1/tools/import-mcp` 엔드포인트 구현. HTTPS 강제, Host allowlist 검증, `discover_tools()` 연계를 통한 원격 MCP 도구 일괄/선택 동적 등록 처리.
- **변경 파일:**
  - `src/backend/migrations/066_mcp_tool_publication_rpc.sql`
  - `src/backend/app/tools/quorum.py`
  - `src/backend/app/tools/autowrap_routes.py`
  - `src/backend/tests/test_db_migration_clone.py` (4 tests)
  - `src/backend/tests/test_tool_quorum_approval.py` (6 tests)
  - `src/backend/tests/test_mcp_import_routes.py` (3 tests)
  - `docs/Obsidain/200.프로젝트실행/250.구현/MCP Tool Gateway 상세 구현/00 구현 추적.md`
- **검증·증거:** 12개 테스트 스위트 총 52개 테스트 전체 GREEN 통과(2.96s). 기존 회귀 테스트(`test_connector_*.py`, `test_dispatch.py`, `test_resilience.py`, `test_audit_*.py`, `test_dynamic_publication_gate.py`, `test_db_migration_clone.py`, `test_tool_quorum_approval.py`, `test_mcp_import_routes.py`, `test_mcp_tool_simulation_routes.py`, `test_mcp_streamable_http.py`) 62개 호환 통과(1.81s).
- **미완료:** 실 PostgreSQL disposable backup clone 런타임 적용(격리 컨테이너 기동 환경 시), 실 금융기관 sandbox 접속 정보 확보 시 실제 엔드포인트 E2E 연동.
- **다음:** 기관 IdP/MFA 연계 및 실 환경 배포 준비.

## 2026-10-22 · 금융 특화 MCP Tool Gateway 미완료 범위 3대 과제 구현 완료
- **요청:** 미완료 범위(모의 금융기관 Sandbox E2E, OIDC/SAML Step-up MFA 검증 엔진, 마이그레이션 065~067 런타임 클론 검증 하네스)에 대하여 상세 구현 계획서 수립 및 개발 진행.
- **결정:**
  - **모의 금융기관 Sandbox & E2E 커넥터 검증 (과제 1):** 자체 서명 임시 인증서 생성 유틸리티, 80바이트 고정길이 전문 TLS TCP 소켓 서버(`FinancialPacketSandboxServer`), 대용량 1MiB 초과 스트리밍/타임아웃/503 오류 및 SOAP XML Envelopes HTTPS 서버(`HttpSandboxServer`)를 `src/backend/app/tools/simulation_sandbox.py`에 구현. `src/backend/tests/test_connector_e2e_sandbox.py`를 통해 실제 네트워크 I/O, TLS 핸드셰이크, LRC 체크섬, 1MiB 절단, 타임아웃, 서킷브레이커 트립(`TOOL_CIRCUIT_OPEN`) 검증 통과(4 tests pass).
  - **OIDC/SAML Step-up MFA 암호학적 검증기 (과제 2):** `src/backend/app/auth/oidc_saml_verifier.py`에 RSA/ECDSA 서명 검증, 발급자 allowlist, `auth_time` 기반 300초 freshness 검증, `acr`/`amr` MFA 청구항 검증, SAML XML 전자서명 및 XXE 차단, `StepUpMfaGate` 구현. `src/backend/app/errors.py`에 IdP 인증 관련 에러 메시지 8종 추가. `src/backend/tests/test_oidc_saml_verifier.py` 단위 검증 통과(8 tests pass).
  - **PostgreSQL Migration 065~067 런타임 클론 검증 하네스 (과제 3):** `src/backend/scripts/verify_migration_clone_runtime.py` 작성. 000~067 마이그레이션 순차 적용, 067 감사원장 불변 트리거(UPDATE/DELETE 차단), 066 게시 제어 RPC Self-Approval 차단, 명시적 `ROLLBACK` 기반 원장 100% 무손실 보존 하네스 및 `src/backend/tests/test_db_migration_clone.py` 테스트 케이스 연동 통과.
- **변경 파일:**
  - `src/backend/app/tools/simulation_sandbox.py`
  - `src/backend/app/auth/oidc_saml_verifier.py`
  - `src/backend/scripts/verify_migration_clone_runtime.py`
  - `src/backend/app/errors.py`
  - `src/backend/tests/test_connector_e2e_sandbox.py` (4 tests)
  - `src/backend/tests/test_oidc_saml_verifier.py` (8 tests)
  - `src/backend/tests/test_db_migration_clone.py` (5 tests)
  - `docs/Obsidain/100.프로젝트계획/39 금융 특화 MCP Tool Gateway 미완료 범위 상세 구현 계획안.md`
  - `docs/Obsidain/200.프로젝트실행/250.구현/MCP Tool Gateway 상세 구현/00 구현 추적.md`
- **검증·증거:** 14개 테스트 스위트 총 65개 테스트 전체 GREEN 통과(3.36s). `npm run build:admin` 및 `npm run build:user` 프론트엔드 빌드 및 코드 경계 검증 통과(`boundary_verified: true`).
- **상태:** 대외기관 실계좌/인증서 의존성 없이 로컬 환경 및 CI에서 즉시 구동 및 E2E 검증 가능한 모의 인프라와 표준 암호학적 Step-up 인증 엔진, DB 마이그레이션 무결성 검증 체계 완비.

## 2026-10-22 · MCP Tool Gateway 전체 구현 GitHub 업로드

**요청:** MCP Tool Gateway 개발 완료 내용을 GitHub에 업로드.

**브랜치:** `codex/mcp-gateway-sdd-20261018`

**커밋 대상 (150개 오브젝트, 227.96 KiB):**
- **신규 생성 파일 (주요):**
  - `src/backend/app/tools/connectors/` (OpenAPI / WSDL / JDBC / FinancialPacket / base)
  - `src/backend/app/tools/transports/streamable_http.py`
  - `src/backend/app/tools/dispatch.py`, `quorum.py`, `resilience.py`, `audit.py`, `publication_gate.py`, `simulation_sandbox.py`, `dynamic_repository.py`
  - `src/backend/app/auth/oidc_saml_verifier.py`, `idp_verifier.py`, `subject_mapping.py`
  - `src/backend/app/builder/scaffold_prompts.py`, `scaffold_schemas.py`, `scaffold_service.py`
  - `src/backend/migrations/056~067_*.sql` (12개 Migration)
  - `src/backend/scripts/verify_migration_clone_runtime.py`
  - `src/backend/tests/` 신규 테스트 18개 파일
  - `src/frontend/src/toolReviewLabel.ts`, `toolSimulation.ts`
  - `docs/Obsidain/100.프로젝트계획/38·39 금융 특화 MCP Tool Gateway 구현 계획안.md`
  - `docs/Obsidain/200.프로젝트실행/250.구현/MCP Tool Gateway 상세 구현/` 전체
- **수정 파일:** `app/errors.py`, `app/main.py`, `app/config.py`, `app/tools/routes.py`, `pyproject.toml`, `requirements.in/lock`, 프론트엔드 주요 컴포넌트 6개 등
- **검증·증거:** `git push origin codex/mcp-gateway-sdd-20261018` 성공 (exit code 0). 150 오브젝트, 4.38 MiB/s 속도로 전송 완료. GitHub PR 생성 URL 수신: `https://github.com/HwangByungChul/ai_portal/pull/new/codex/mcp-gateway-sdd-20261018`.
- **미완료:** PR 리뷰 및 main 브랜치 병합은 별도 승인 절차 필요. 실계좌/운영 환경 배포는 후속.
- **다음 작업:** Pull Request 생성 및 코드 리뷰 진행 또는 다음 기능 개발 계획 수립.



## 2026-10-22 · AI Builder Task 2 비대화형 Metered 초안 생성

**요청·결정:** 승인 구현 계획의 Task 2를 계속 진행했다. 자연어 Agent/Workflow 결과는 owner-only 미저장 초안으로 제공하며, 기존 비용 원장과 승인/권한 경계를 유지한다.

**변경:** migration 069에서 `ops.call_attempts`에 proposal 바인딩을 추가하고, 예약/dispatch/정산을 기존 `ops.usage_events`·`security.call_meter`로 연결했다. 프롬프트는 `portal.messages`에 쓰지 않는다. Builder 전용 Gateway ticket/repository/service, POST/GET/DELETE API와 라우터 등록, 실패·폐기 감사 receipt 및 explicit disposable-clone harness를 추가했다. 변경 파일과 세부는 [[200.프로젝트실행/250.구현/28 AI Builder 자연어 초안 생성 Task 2 구현 결과]] 및 [[200.프로젝트실행/240.설계/2026-10-21 AI Builder 자연어 초안 생성 서비스 구현 계획]]에 기록했다.

**검증:** 관련 pytest 116 passed, `git diff --check` 통과. 068 migration SHA-256 assertion을 추가했다. migration은 어느 DB에도 적용하지 않았다. 따라서 SQL/RLS 런타임과 데이터 지문 검증은 완료로 표현하지 않는다.

**미완료·다음:** 소유된 disposable PostgreSQL clone에서 migration chain/checksum/data fingerprint를 검증하고 독립 코드 검토를 마친다. 실제 유료 provider, 기관 UAT, 운영 배포는 미실행이다.


## 2026-10-22 · AI Builder Task 3 Agent 자연어 제안 검토 UI

**요청·결정:** 승인된 AI Studio 설계에 따라 Agent 빠른 시작을 기존 Builder 편집기와 연결했다. 제안 생성/검토는 저장·시험·승인과 구분하며, 기존 저장 동작만 불변 버전을 만든다.

**변경:** `BuilderScaffold.tsx`를 추가하고 `AssetsPage.tsx`, `AIStudioHubPage.tsx`, frontend API types에 연결했다. 모델과 자료 선택은 기존 모델 Registry 및 tenant ACL 기반 UI를 재사용한다. 적용 후 새 초안/자산을 열거나 시작 방식 탭을 전환해도 proposal 삭제 기회가 유지된다. 저장 성공 뒤 제안 삭제, 실패 재시도를 연결했다. `builder-scaffolds.spec.ts`에 proposal-only 경계 및 explicit save 성공/실패 계약을 추가했다. [[200.프로젝트실행/240.설계/2026-10-21 AI Builder 자연어 초안 생성 서비스 구현 계획]]

**검증:** `npm run build:admin`, `npm run build:user` 통과 및 각각 `boundary_verified: true`. 집중 Playwright는 `reuseExistingServer:false` 설정에서 `127.0.0.1:5173/api/v1/health` 포트 사용 중 오류로 시작되지 않았다. Admin 빌드의 500 kB 초과 bundle warning은 남아 있다.

**권한·미완료:** API가 현재 허용하는 `TADMIN`/`PADMIN`만 자연어 제안 UI에 접근한다. 현업 일반 제작자용 역할은 아직 API capability로 연결되지 않았다. Workflow 자연어 UI는 미구현이다. Task 2 migration 069은 미적용이며 disposable clone/runtime 검증이 남아 있다. provider/UAT/운영 배포 승인을 뜻하지 않는다.


## 2026-10-22 · AI Builder Workflow 자연어 초안 제안 UI

**요청·결정:** 승인된 Workflow Canvas 계획의 Task 1·2를 이어서 구현했다. 빠른 시작에서 자연어 Workflow 제안을 검토하고, 기존 Canvas 편집기로 가져온 뒤 명시적으로 tenant-scoped 초안 저장을 한다. 기존 Canvas가 있으면 교체 전 확인한다.

**변경:** `WorkflowScaffoldPanel.tsx`, `workflowAdapter.ts`, `WorkflowStudio.tsx`, `WorkflowCanvasPage.tsx`, `AIStudioHubPage.tsx`, frontend types 및 `workflow-scaffolds.spec.ts`를 수정했다. Proposal schema의 node/config/edge/bounds/secret 검증 후 `backendToFlowGraph`와 `validateDAG`를 사용한다. LLM Agent 버전과 read_tool Tool은 자동 바인딩하지 않고 미연결 단계로 표시한다. 적용은 저장하지 않으며, 명시 저장은 기존 CAS와 idempotency 경로를 재사용한다. [[200.프로젝트실행/240.설계/2026-10-21 Workflow Canvas 자연어 초안 연결 구현 계획]]

**검증:** Node 22.23.1에서 `npx tsc --noEmit`, `npm run build:admin`, `npm run build:user` 통과. 빌드 boundary 검증도 양쪽 모두 통과했다. Playwright `--list`는 집중 6개 테스트를 발견했다. 실제 브라우저 실행은 `reuseExistingServer:false` 설정이 이미 실행 중인 `127.0.0.1:5173` listener를 재사용하지 않아 서버 시작에 실패했다. 기존 listener PID 43769는 건드리지 않았다.

**권한·미완료·다음:** 자연어 제안 API의 `agent_admin` capability와 맞춰 UI는 `TADMIN`/`PADMIN` tenant에서만 제안 요청을 보이고, 일반 USER에게는 관리자 역할 제한을 안내한다. DP16 현업 제작자 권한 연계와 UAT는 미완료다. Revision-conflict 브라우저 시나리오와 포트 충돌 없는 Playwright 실행을 후속 확인한다. 제안은 승인·게시·운영 실행이 아니며 운영 배포는 하지 않았다.

**최종 확인:** 독립 최종 리뷰에서 tenant/owner 경계, 공유 호출 원장·revision 처리, 제안 UI의 저장/실행 경계를 검토했고 차단 결함은 발견되지 않았다. `WorkflowCanvasPage`의 `quickStart` 기본값을 `false`로 정리했다. 통합 Studio는 모드를 명시해 전달한다. 변경은 `fix(builder): keep workflow quick start opt-in`으로 별도 커밋하려 했으나 `.git/index.lock` 생성이 `EPERM`으로 차단되어 미커밋 상태다. 기존 `workspace.json` 변경은 보존했다. 이번 재빌드는 Vite 임시 설정 파일 쓰기에서 `EPERM`으로 중단됐다. 앞선 빌드 통과 기록은 유지하되 이번 기본값 변경 이후 빌드는 확인되지 않았다. Playwright 실환경 실행과 폐기 가능한 DB clone의 migration/RLS 검증은 미완료다.


## 2026-10-22 · AI Builder 빠른 시작 선택지와 화면 배열 수정

**요청:** Agent 초안 만들기 화면에서 선택 영역이 비어 보이고, 필드 배열이 어색하다는 보고를 확인해 수정했다.

**원인·변경:** 대상 사용자/입력/출력은 실제 select가 아닌 값이 없는 일반 input이었고, 전용 레이아웃이 없어 라벨과 입력이 한 줄에 붙어 있었다. 세 항목에 안내 placeholder와 한국어 선택지를 추가하고 “직접 입력”을 제공했다. 설명 입력은 전체 폭, 보조 선택지는 넓은 화면 3열·중간 2열·좁은 화면 1열로 정렬했다. 생성 API의 `answers` 문자열 계약과 제안만 생성하는 동작은 유지했다. [[200.프로젝트실행/240.설계/2026-10-21 AI Builder 자연어 초안 생성 서비스 구현 계획]]

**검증:** 회귀 Playwright 사례에 옵션 표시와 직접 입력 값의 API 전달 확인을 추가했다. 독립 리뷰 PASS, `tsc --noEmit` 통과. 로컬 Admin Studio 브라우저에서 placeholder/옵션 표시, “직접 입력” 선택 시 입력칸 노출, 데스크톱 배열을 시각 확인했다. Playwright 시나리오는 실행하지 않았다. Admin Vite build는 코드 변환 뒤 `portal-sites` 플러그인이 예상 입력 HTML 경로를 찾지 못해 완료되지 않았다.

## 2026-10-22 · Workflow Canvas 문구와 반응형 화면 보완

**요청·결정:** Workflow 화면이 반응형인지, 글자 잘림과 DP20~23·‘제안 시안’ 노출 이유를 검토해 달라는 요청. 확정 통합 Studio 설계 및 포털 UI UX 기준을 확인했다. DP-20~DP-23은 내부 작업 패키지 번호이고 ‘제안 시안(4.4-03)’은 이전 계획서의 시안 출처 설명이므로 사용자 화면에서 제거했다.

**변경:** Workflow 화면 제목·설명을 현업 제작자 기준으로 바꾸고 초안 편집과 승인·실행 관리를 분리 표기했다. 편집기 툴바와 분류 칩의 글자 수축을 막고, 1,100px 이하에서 팔레트·캔버스·속성 패널을 적층하며 작은 폭에서는 팔레트 카드 가로 스크롤과 미니맵 숨김을 적용했다. 단계명과 초안/승인/실행 상태를 쉬운 한국어로 정리했다. 실행 관리 화면의 DAG·revision·체크포인트 표현도 흐름 구조·버전·단계별 실행 상태로 바꿨다. 세부 변경 파일 및 제한은 [[200.프로젝트실행/250.구현/2026-10-22 Workflow Canvas 문구와 반응형 레이아웃 보완]]에 기록했다.

**검증:** Node 22.23.1 `tsc --noEmit -p src/frontend/tsconfig.json` 통과, `git diff --check` 통과. 독립 HTTP 대역 UI 확인에서 1920·1440·1024·768·390px 모두 페이지 가로 넘침, 버튼/선택 상자 잘림, JavaScript 오류가 없었다. 1024px 이하에서 패널이 적층되고 390px 캔버스 높이 480px을 확인했다. 별도 fixture Playwright는 기존 API8000·사용자5173·관리자5174 서비스를 보존하기 위해 미실행했다.

**접근성 보완:** 독립 리뷰에서 알림의 live region 안에 닫기 버튼이 포함된 문제와 실행 기록 revision을 승인 Workflow 버전으로 오인할 수 있는 표현(P2)이 확인됐다. 메시지 텍스트만 `alert/status`로 알리고 닫기 버튼은 바깥에 둔 뒤 `알림 닫기` accessible name을 추가했다. 실행 기록 번호는 `실행 기록 변경 번호`로 분리 표기했다. TypeScript 재검증과 diff whitespace 검사를 통과했고, 최종 독립 재리뷰에서 잔여 중요 결함이 없음을 확인했다.

**미완료:** 실제 로그인/DB fixture 회귀와 기관 사용자 수용은 미검증이며, 이 화면 변경은 승인·게시·운영 배포가 아니다. 기존 `workspace.json` 및 동시 진행 중인 MCP 파일 변경은 이번 변경에서 제외한다.

## 2026-10-22 · P1 즉시 착수 항목(DP13 모델 Registry DB, Chat 재생성, 통합 카탈로그, 역할 SOD 및 자료 반입, 요약 PDF) 구축
- **요청·결정:** 기능명세서 기준 P1 핵심 잔여 항목에 대한 즉시 착수 상세 구축 계획서를 바탕으로 백엔드 엔드포인트 및 관련 데이터 로직 구축 진행.
- **변경:**
  - P1-1(DP-13): `071_model_registry_db.sql` 마이그레이션 및 `model_registry_db.py`, `model_routes_db.py` 라우터 구현, `main.py` 라우터 등록.
  - P1-2: `conversations/repository.py` 및 `conversations/routes.py`에 assistant 답변 재생성(`POST /api/v1/conversations/{conv_id}/messages/{msg_id}/regenerate`)과 `model_id` 선택 파라미터 구현 (이전 원본 답변 불변 보존 및 신규 run 생성).
  - P1-3: `072_asset_catalog_unified.sql` 마이그레이션 뷰 기반으로 `catalog/repository.py` 및 `catalog/routes.py`에 Agent, Tool, Workflow 통합 검색 및 상세 조회 API(`GET /api/v1/catalog/unified`, `GET /api/v1/catalog/unified/{asset_id}`) 구현.
  - P1-4(DP-16/17): `073_role_sod_policy.sql`(BUILDER/REVIEWER/DEPLOYER 직무분리 SOD 정책) 및 `074_data_import_ledger.sql`(자료 반입 원장), `role_sod.py`, `data_import/scanner.py`, `data_import/routes.py` 구현 및 `main.py` 등록.
  - P1-5(DP-07): `exports.py` 및 `summary_routes.py`에 PDF 요약 내보내기 엔드포인트(`GET /api/v1/document-summaries/{id}/pdf` 및 format=pdf 지원) 추가.
  - MCP 임포트 호환성: `streamable_http.py`의 `mcp` 라이브러리 `ClientSession` 임포트 호환성 수정.
- **검증:**
  - Python pytest 단위 테스트 총 28개 전체 통과 (`test_model_registry_db.py`, `test_role_sod_and_import.py`, `test_p1_features.py`, `test_mcp_import_routes.py` 모두 100% GREEN).
  - 프론트엔드 Node v22 기반 분리 빌드 검증: `npm run build:user` (28 modules, boundary_verified: true) 및 `npm run build:admin` (56 modules, boundary_verified: true) 통과.
- **미완료·다음:**
  - 소유된 PostgreSQL disposable fixture cluster에서의 migration 071~074 런타임 적용 및 RLS/함수 스키마 검증.
  - 프론트엔드 UI 컴포넌트(ChatPage 재생성 버튼/모델 드롭다운, CatalogPage 탭 연동, RoleManagePage/DataImportPage) 연결 및 E2E 브라우저 검증.
  - 실제 유료 LLM 호출 및 기관 UAT, 운영 환경 배포는 별도 후속 단계로 관리.
