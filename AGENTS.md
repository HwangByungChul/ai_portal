# 포털 UI UX와 지속 기록

사용자 지시(2026-10-11): 현재까지 검토 내용과 추후 작업을 Obsidian에 기록한다.

- Vault: `docs/Obsidain`.
- 화면 작업 전에 `200.프로젝트실행/240.설계/23 포털 UI UX 확정과 사이트 분리 검토.md`를 읽는다. 사용자 A안 홈, 관리 A안 홈과 관리 B안 승인·검증 목록·상세 패널이 확정 기준이다. 제품 명칭은 ‘생성형 AI 플랫폼’이다.
- 의미 있는 관련 작업 단위마다 최종 보고 전에 `400.프로젝트관리/02 포털 UI UX 작업 기록.md`에 날짜, 사용자 요청·결정, 변경한 실제 파일, 검증·증거, 미완료 범위, 다음 작업을 남긴다. 설계가 바뀌면 확정 설계 노트도 갱신하고 이전 결정·변경 이유를 보존한다.
- 제안/승인/HTML 시연/실제 앱 구현/운영 배포 상태를 구분한다. 기존 앱의 인증·DB·대화·문서 구현 상태는 실제 코드와 최신 검증 기록을 따른다. 이 UI 시연의 미연결 범위를 기존 앱 전체의 미구현으로 표현하지 않는다.
- 정식 문서는 Vault 단계 폴더에 저장하고 wikilink로 연결한다. CLI가 없으면 허용된 파일 도구로 Markdown을 갱신한다. Vault 쓰기가 막히면 로컬에 보존하고 동기화 여부를 알린다.
- 별도 HTML 시연 원본과 비교·검증 자료는 `/Users/jwpios/antigravity/지능형 차세대 정보시스템 구축/UI_UX_제안_20261011`에 있다. 실제 Unicode 경로는 파일 목록으로 확인한다.

## Codex CLI 프로젝트 작업 원칙

- Codex CLI는 저장소 루트에서 실행해 이 지침을 읽게 한다. 작업 시작 전에 `git status --short`로 기존 변경을 확인하고, 종료 후 변경 파일과 diff를 확인해 기존 사용자 변경과 구분한다.
- 요청은 한 번에 한 기능 흐름으로 좁힌다. 먼저 관련 계획·설계·최신 구현/시험 기록과 코드를 확인하고, 불확실하거나 영향 범위가 넓으면 수정 전에 조사 결과와 실행 계획을 제시한다. 구현 요청에는 허용 범위, 완료 조건, 필요한 검증 및 미완료 보고를 구체적으로 적는다.
- 화면 변경 전 `200.프로젝트실행/240.설계/23 포털 UI UX 확정과 사이트 분리 검토.md`와 해당 화면의 최신 승인 설계를 확인한다. 사용자 A안 홈, 관리 A안 홈, 관리 B안 목록·상세 기준과 제품명 ‘생성형 AI 플랫폼’을 유지한다.
- DB 변경은 기존 migration 파일을 수정하지 않고 새 migration으로 추가한다. 적용 전 백업과 별도 fixture clone 검증, 기존 row/checksum 보존을 확인한다. fixture DB나 로컬 서비스는 공유 상태이므로 DB migration·fixture harness를 병렬 실행하지 않는다.
- 제안·요청 접수·승인·게시·실행·운영 배포 상태를 구분한다. 실제 인증 사용자·PADMIN 왕복, 기관 연동, 업무 품질 또는 운영 검증을 수행하지 않았다면 이를 완료로 쓰지 않는다. 승인 gate, tenant/owner 권한, 감사·비용 원장을 우회하지 않는다.
- 의미 있는 개발 작업은 완료 보고 전에 `400.프로젝트관리/02 포털 UI UX 작업 기록.md` 및 해당 Vault 단계의 구현/시험 문서를 갱신하고 wikilink로 연결한다. 변경 파일, 실제 검증 명령·결과, 증거 위치, 미검증·미완료 범위와 다음 작업을 기록한다.

## 2026-10-11 · 상용화 기반 후속 작업

사용자는 실제 상용화 가능한 구현을 요구했고 첫 승인 대상으로 AI 에이전트 배포를 선택했다. UI 시연 노트23뿐 아니라 `docs/Obsidain/100.프로젝트계획/11 포털 상용화 기반 UI 통합 상세 실행 계획.md`, `12 사용자 관리자 사이트 분리와 상용 이행 설계.md`와 최신 작업 로그를 먼저 확인한다. 현재 실제 앱 통합과 HTML 시연·운영 출시는 서로 다른 상태다. 기존 fixture DB·합성 계정·모의 제공자를 상용 환경으로 표시하지 않는다. Agent 운영 설정 직접 PATCH는 승인 필요409이며 변경안 제출과 타인 PADMIN 승인 API를 사용한다. 기록은 관련 작업 완료 시 같은 Vault에서 계속 갱신한다.

## 2026-10-12 · 독립 앱 후속 기준

실제 frontend는 `apps/user-web`·`apps/admin-web` 진입과 `packages/api-contract`·`packages/ui` 공통 원본을 가진다. 기존 src re-export는 같은 세션/스코프를 유지하기 위한 호환이며 중복 구현을 넣지 않는다. 작업 전에 계획13·구현22·시험23과 최신 로그를 읽는다. build:user/build:admin의 코드 경계 검사를 유지한다. 현재 같은5173 출처·/user·/manage 산출물이며 SSO/상용 운영 배포 완료로 표시하지 않는다. IdP/운영 계약 확인 후 환경 이행을 진행한다.

## 2026-10-12 · 환경별 설정 후속 기준

공개 환경 원본은 config/environments/{local,dev,tb,prd}.json이며 AI_ENVIRONMENT로 선택한다. 계획14/구현23/시험24와 최신 로그를 확인한다. 현재 local 사용자5173·관리자5174·API8000으로 실행한다. 이전 같은5173 설명은 이력이다. local 공통 개발 세션이며 포트는 쿠키를 격리하지 않는다. dev/tb/prd 미설정은 실행/build 차단, 실제 SSO/BFF·TLS·운영 DB profile/배포는 후속이다. strict validation/CSRF/권한·빌드 코드 경계와 안전한 기록을 유지한다. 비밀을 공개 JSON/번들/증거에 저장하지 않는다.

## 2026-10-12 · 상용화 의미 정정과 기능 우선

사용자가 명확히 정정했다: 상용화 요구는 현재 앱을 바로 운영 환경으로 옮기는 요청이 아니라 전체 기능명세서의 제안 기능을 실제 서비스 오픈 수준으로 구현하는 것이다. 후속 작업 전에 docs/Obsidain/200.프로젝트실행/230.분석/09 전체 기능명세서 기준 개발 완료 여부 검토 보고서.md 및 별첨10/최신로그를 읽는다. 기능 잔여를 SSO/도메인/DB/배포 준비 목록으로 대체하지 않는다. F60 전체완료 인정0/부분31/미구현29, 이전 개발F49는부분31/미구현18(2026-10-12 audit). 좁은 DP03/04/05/파서/요약·고정설정 승인과 원본F전체완료를 구분한다. 도메인 미정이어도 동적 자산/카탈로그/Builder/모델/연계/Workflow 기능 계약과 구현은 진행 가능하다. 실제 연동 미검증은 분리 기록한다. 거버넌스 이전 제외/PPTX·OCR 사용자 보류는 유지하며 검토 보고 요청을 새 범위 개발 승인으로 확대하지 않는다.

## 2026-10-12 · 조사 후 기능 개발 재개와 자산 기반

사용자가 조사 결과의 계획서 작성 후 개발을 승인했다. 계획15/설계24/구현24/시험25를 먼저 확인한다. DP09-01 관리자 AI 자산 관리는 PostgreSQL에 새 Agent 초안/불변 버전/지문·재시도/CAS·audit를 저장하고 fixed2는 읽기 전용 연결 view로 보여준다. 새 draft를 승인·게시·실행 완료로 표현하거나 기존 실행 gate를 우회하지 않는다. migration027은 local 소유DB에 백업 후 적용했다. SQL000~027 checksum을 유지하며 새 변경은 후속 migration으로 추가한다. 실제 동적 실행/카탈로그/Builder/일반 자산 승인은 후속이다. 전체 명세 완료·기관 수용·운영 배포와 좁은 모의 검증을 구분한다.

## 2026-10-12 · DP09-02 실행 출처 후속 기준

계획26/구현25/시험26과 최신 로그를 읽는다. 신규 run은 고정 asset UUID·설정 revision·결정적 legacy version UUID·실효 snapshot SHA256을 봉인하고 과거 run은NULL로 유지한다. optional asset_id는 고정 조직별alias만 수용하고 draft는404다. 등록 view 기본 지문과 실행 기본 지문은 다를 수 있으며 현재 view를 과거 출처로 사용하지 않는다. SQL000~028 checksum 유지·다음 migration029 이상. 신규 draft 동적 실행은DP12 승인/게시 이후, 다음DP10 카탈로그/My Agent 상세 계획부터 진행한다. latest-case 서버집계와 단일 브라우저 실행을 구분하며 기관 수용/운영 배포로 표시하지 않는다.

## 2026-10-12 · DP10-01 카탈로그·개인 선호·이용 대상

설계27/구현26/시험27과 최신 로그를 읽는다. 고정 운영 Agent2종만 사용자 카탈로그에 제공하며 새 draft는 숨긴다. 개인 선호는 권한을 부여하지 않고, 회수 시 숨김·재허가 시 보존 선호 복원이다. 관리 이용 후보는 활성 account와 membership의 교집합이다. rules_rag 정책은 현재 문서 요약 제출·재시도·worker에도 적용한다. 키/자산UUID/진행 중 실행·stream에 현재 gate를 적용하고 이미 발사된 비용과 본인 이력·문서 ACL을 유지한다. SQL000~029 checksum 유지·새 migration030 이상. local40표/30migration/112security함수, 최신 사례 server421/browser77과 user23/admin22 분리 빌드 pass는 여러 실행의 최신 사례 집계다. 전체 suite 단일 성공/기관 수용/운영 배포로 확대하지 않는다. 동적 공개 자산·다른 자산 유형·태그/랭킹·복제/구독·부서/만료/권한 신청/계열사 공유는 후속. 다음 DP13 상세 계획부터 진행하며 Entra ID는 실제 테스트 환경 준비 후 검증한다.

## 2026-10-12 · 사용자 요청으로 Builder 우선

이전 DP13 다음 지시는 이력이다. 사용자 최신 요청으로 설계28/구현27/시험28을 읽고 DP11을 우선한다. 첫DP11-01은 기존 immutable초안 저장/변수조합 preview·선택자료현재ACL만 실제구현했다. 모델/검색 호출과 운영게시가 아니다. 다음Task2 구조화prompt/복제/RAG검색시험, 이어최소모델계약포함trial/증적이다. 새migration0·000~029checksum유지. 일반운영run은draft404를유지하고시험실행을우회연결하지않는다. latestcasebackend52/browser9·분리build와local복구는좁은검증이다.

## 2026-10-12 · DP11-02a 구조화 profile 후속 기준

설계28 최신보완/구현28/시험29를 읽는다. profile은불변 assetversion과원자 저장하며 role별prompt/default model_ref/명시docs만지원한다. 과거simple버전은read-only derived, clone lineage는수정후에도보존. oldassetappend로profile유실을허용하지않고 privateasset_registry_v029는ai_web실행금지. savedprofile/preview/clone replay에도현재자료권한을확인한다. SQL000~031동결·후속032이상. local42표/32migration/116securityfunc와전행/체크섬보존,모의검증·세서비스복구는실제모델/기관수용/운영배포와구분한다. 다음Task2b actualRAGsearch+Task3 최소trial/정산/취소,이어증적·승인이다. secrets참조/다중모델Registry/일반제작자역할은미완료다.

## 2026-10-12 · DP11-03a private trial

설계28/구현29/시험30 최신 내용을 읽는다. private builder_trial은 본인 현재 manage와 저장 버전/자료 ACL을 봉인·재검사하며 일반 운영 draft404를 유지한다. 기존 gateway/예산/dispatch/meter/cancel/recover 사용, 사용자 대화/메시지에서 숨김. SQL000~032 동결·후속033 이상. local43표/33migration/123security함수 및 기존42표 전행/32checksum 보존. 서버 latest292·브라우저단일10·user23/admin25 build pass는 모의 검증이다. SSE 중간출력 대신 final-only polling이며 증적 목록/평가비교/DP12/secret·다중모델·제작자/실제 제공자는 미완료. 다음DP11-04 증적부터 진행한다. 병렬 fixture migration은 공용 roles를 갱신하므로 pytest/브라우저 harness는 순차 실행한다.


## 2026-10-12 · DP11-04 evidence

설계29/구현30/시험31을 읽는다. 본인 asset trial 이력·append-only manual-v1 평가·동일자산두시험비교는 실제API/DB/React 구현이며 현재관리/owner/자료ACL을 재검사한다. 이력최소metadata와상세권한을구분하고mock품질·배포승인으로표현하지않는다. SQL000~033동결·후속034이상. local44표/34migration/127security함수, 이전43표전행/33checksum보존. 서버최신122(74/63별도실행)/브라우저단일13/user23admin26buildpass·세서비스복구. 다음DP11업무평가셋/정확한승인증적공유계약→DP12동적승인게시. 원문저장소재변조조회수용·상세비용토큰비교·전체평가내보내기·secret/다중모델/실제제공자/Entra/기관수용/운영배포는미완료.


## 2026-10-12 · DP11-05 evaluation cases

설계30/구현31/시험32를읽는다. 본인불변case/version/profile/values/purpose와literal-v1필수/금지문구·answer_kind·실제출처조건검증을실제API/React에연결했다. 자동조건충족은semantic품질·운영승인아니다. case trial도기존admission/gateway/원장사용, evaluate는provider0·samecase/run1행replay·현재ACL. 과거출처없는검색후보는source검사실패·소급수정금지. SQL000~034동결·후속035이상. local46표/35migration/131security함수·기존44표전행/34checksum보존, 서버최신118(92/45/1별도실행)/브라우저단일16/user23admin27buildpass·세서비스복구. 다음승인용정확한증적공유계약→DP12동적승인게시. batch평가/semanticjudge·실제업무품질·원문재변조조회전체수용·상세비용토큰/전체평가export·secret/다중모델/Entra/실제제공자/UAT/운영배포미완료. fixture DB harness 순차원칙유지.


## 2026-10-12 · DP11-06 evidence sharing

설계31/구현32/시험33을읽는다. 본인 exact완료run/evaluation/version/hash의최소snapshot만명시동의후현재조직PADMIN과공유하고, 개인trial/case/eval ownerRLS는유지한다. reviewer 자신의현재자료ACL을재검사·원문/messages/values/기대문구/개인평가의견미공유,본인CAS철회후snapshot비노출. 공유원장의submitted는승인/게시아니다. 고정설정승인흐름과구분한B목록상세를승인메뉴에연결했다. SQL000~035동결·후속036이상. local47표/36migration/132security함수·기존46표전행/35checksum보존·새공유0행·primary합성/paid0. 서버73최신(신규12/기존61별도)·브라우저단일19·user23/admin29build·세서비스복구. 다음DP12타인결정/반려/재신청/공개대상·동적실행/폐기/rollback이다. 추가상세증적동의/업무검토기준·실provider/Entra/UAT/운영배포·이전DP11잔여미완료. fixture harness는순차실행하고primary서비스포트충돌없이중지/복구한다.

## 2026-10-12 · DP12 동적 Agent 첫 실행 단위

설계32/구현33/시험34 최신내용을 읽는다. 본인 exact shared generate 증적→타인PADMIN 결정→immutable publication+공개대상→일반 USER asset_chat을 별도API/React로 실제연결했다. 고정 /runs draft404·개인 ownerRLS 유지, 사용자 own 자료ACL·central admission/Gateway/예산/dispatch/meter 사용, publication CAS/retire fence·늦은답변 비저장/비용보존. SQL000~037동결·후속038이상. local50표/38migration/138security함수·이전47표전행/36checksum보존·신규3표0행·primary합성/paid0. 서버166최신(기존144+신규22별도)·브라우저27단일·user24/admin31build·세서비스복구. 다음 이전게시버전 복원 승인/rollback·이력비교/사용자이력탐색. 다회차memory/즐겨찾기/복잡승인·실 provider/Entra/UAT/운영 배포/동적native crash전경계·이전DP11잔여미완료. fixture harness순차원칙·기존시점미구현기록보존.

## 2026-10-12 · DP12-02 복원 승인·배포 이력

설계33/구현34/시험35를읽는다. historical approved exact 버전을 별도 타인PADMIN 승인으로 복원하며 현재 audience/member목록 유지·shared status/정책/모드/current자료ACL/회원활성/publicationCAS 재검사, 자기승인금지/반려/replay. 일반 승인 publicwrapper는rollback을새capability로전달·internalv1 web직접실행revoke. 이벤트append-only forcedRLS·backfill은과거승인/관찰현재 구분·누락철회/actor추정금지·comparisoncurrentACL. SQL000~038동결·039이상. local51표/39migration/140함수·이전50표기존행/열+38checksum보존·primary합성/paid0·서비스복구. 이번서버35최신(34/1별도)·브라우저28최신별도집계·user24/admin32build. 다음 사용자전역동적실행이력·철회metadata 탐색/기존대화탐색통합. 실제provider/Entra/UAT/운영배포·복잡승인/모델/secret/tool/workflow/이전DP11미완료. fixture순차원칙유지.

## 2026-10-12 · DP12-03 사용자 전역 실행 이력

설계34/구현35/시험36을읽는다. user/agent-history·AI 업무 이동, 본인asset_chat keyset20·state/assetfilter·cursorowner/조직범위. 최소record와currentanswer분리, exactpublication/ownsourceguard실패시이름NULL·답변숨김·철회최소record보존. B0401은PublishedRepository404·unexpectedDBerror는성공으로삼키지않음. recordowner취소/CSRF 유지·metadata권한부여아님. SQL000~039동결·040이상·primary51표전행/39checksum보존·51표/40migration/141함수·합성/paid0·세서비스복구. 서버52최신별도집계/브라우저12최신별도집계/user25admin32build. 다음동적즐겨찾기/MyAgent별도계획·이전DP11/secret/다중모델/tool/workflow/복잡승인/실provider·Entra·UAT·운영배포미완료. fixtureharness순차원칙유지.
