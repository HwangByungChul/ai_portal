---
title: 업무 Agent 10종 승인 연결 상세 작업 계획
date: 2026-10-14
status: 사용자 승인 · 회의록 1종 및 관리 B안 우선 개발
stage: 100.프로젝트계획
tags: [use-case, workflow, agent, implementation-plan]
---
# 업무 Agent 10종 승인 연결 상세 작업 계획

**Goal:** 10종 업무 카탈로그를 조직별 실제 승인 Workflow와 게시 Agent·허용 Tool·현재 자료 권한에 연결하고, 실행/조회/취소/안전 결과를 사용자 화면에서 제공한다.

**Architecture:** 기존 Workflow parent/step과 Agent RunTicket/Gateway/예산/정산·Tool receipt를 재사용한다. 업무 manifest와 승인 버전의 연결은 제출 시 봉인하고 타인 승인 시 활성 head를 원자 갱신한다. 업무 전용 API는 이 승인 head를 서버에서 선택하며 클라이언트가 prompt/model/Tool/임의 context를 바꿔 실행하지 못하게 한다.

**Tech Stack:** 기존 FastAPI/Pydantic/PostgreSQL FORCE RLS, React/TypeScript, Node22.23.1, pytest/Playwright.

**Spec:** [[25 DP24 표준 업무 Agent 10종 상세 구현 계획]], [[30 승인 Workflow 실행과 업무 Agent 연결 상세 작업 계획]], [[2026-10-13 W5b 승인 Workflow 실행 원장 및 Agent Tool 연결 구현 보고서]], [[32 관리 B안 Tool Workflow 승인 화면 확장 상세 작업 계획]].

**실행 방식:** 기존 사용자 지시에 맞춰 현재 채팅에서 작업 단위별 순차 구현·검증·기록한다. 이번 요청은 상세 범위 설명과 문서 작성이며 아래 체크박스는 신규 작업을 완료했다는 뜻이 아니다. 별도 subagent/commit/배포를 이 계획만으로 실행하지 않는다.

## 공통 제약과 확인된 기준선

- 제품명·사용자A·관리A/B 탐색 흐름 유지. local/dev/tb/prd 설정 및 비밀 참조 분리 유지.
- 현재 source migration 마지막은048. 새 migration 번호049·050은 계획 예약이며 구현 시작 시 충돌을 재확인한다. 기존000~048/과거 checksum을 수정하지 않는다.
- primary040 체크섬 불일치를 우회하지 않는다. 이번 후속 기능 개발은 소유 disposable DB에서 먼저 검증하고 기존 DB 이행은 별도 처리한다.
- 실행 mode/code/manifest 변경은 새 승인 버전을 필요로 한다. 이전 승인과 NULL metadata를 업무 승인으로 소급 연결하지 않는다.
- 실제 기관 connector·업무 자료·모델 품질 수용과 local/mock 앱 구현 완료를 구분한다. 승인과 시험 실행만으로 실제 업무 정확성을 통과했다고 표시하지 않는다.
- DB fixture pytest와 browser harness는 순차 실행한다. 기존 working tree의 다른 개발을 임의 덮어쓰거나 묶어 commit하지 않는다.

2026-10-14 source 확인: `app/use_cases/catalog.py`에10manifest, `routes.py`는모두execution_ready=false이며 main에use_case_execution조립이없다. `app/use_cases/service.py`는아직없다. `UseCaseWorkspacePage.tsx`는 raw fetch에tenant/scope가없고 ‘승인 Agent10종/DP24준수’ 표시가 실제 승인 상태와 다르다. 기본 Tool은 fixture이며 real adapter 세 메서드는 endpoint/key가 있어도409다. `_configured()`도real을차단한다. 따라서 flag만true로바꾸는작업은완료기준이아니다.

## 1. 업무10종의 산출물·필요 자료·개별 수용

| ID / 명칭 | 입력·연결 | 결과 계약 / 필수 수용 |
|---|---|---|
| 03 회의록 및 액션아이템 | 회의 메모 또는 현재 허용 자료, 선택 회의일 / 외부Tool없음 | 결정·미정·담당자·기한·근거문장. 원문에 없는 담당자/날짜는 ‘미정’, 잘못 생성하지 않음 |
| 01 규정 책무 관리 | 질문·업무분류 / kb_rule_query + 허용 RAG 규정·책무자료 | 조항·문서버전·개정일·관련책무 출처. 현재 유효 규정 구분, 근거 없으면 불충분 |
| 04 공문 및 보고서 작성 | 문서유형·수신/발신·목적·본문자료 / kb_rule_query + 승인서식 | 발신·수신·제목·본문·붙임 초안과 서식 출처. 입력하지 않은 사실·결재번호 생성 금지 |
| 10 영업점 단말 내비게이션 | 업무명·채널·시스템 버전 / kb_rule_query + 단말매뉴얼 | 현재 화면번호·거래코드·단계·서류. 근거 없는 코드/거래 실행 금지 |
| 06 광고 심의 점검 | 광고문안·채널·상품유형 / kb_rule_query + 승인 심의기준 | 문구별 체크리스트·근거·수정안. 사전점검 결과이며 최종 심의필/통과 확정 아님 |
| 09 외환 업무 가이드 | 거래사유·통화·국가 등 허용 조건 / kb_rule_query + 유효 외환기준 | 적용 조건·신고/증빙 체크리스트·확인할 항목·기준일. 근거 없으면 판단 보류, 자동 승인 없음 |
| 02 그룹웨어 문서 요약 | 승인 범위의 문서 식별자·질문 / data_view_reader의 문서 읽기 계약 또는 정식 문서connector | 목적·핵심사항·예산/인력 영향·일정·결재 쟁점 5영역. 원문에 없는 수치/일정은 미확인 |
| 07 금융 상품 비교 안내 | 상품군·기간·비교조건 / financial_product_lookup | 동일 조회 기준일의 금리·우대·가입조건·유의사항·원문. 만료/불일치 조건은 비교 제외/표시 |
| 05 고객 민원 응대 보조 | 비식별 민원내용·상품참조 / kb_rule_query + financial_product_lookup | 요구분류·사실확인 목록·관련기준·회신초안. 담당자 검토 필수, 고객 자동 발송 없음 |
| 08 여신 심사 보조 | 승인된 차주자료 참조·수치/기간·정책버전 / data_view_reader + kb_rule_query | 누락/모순·계산근거·리스크·심사의견 초안. 승인/거절 자동결정 없음. 수치 산식은 LLM 아닌 승인된 서버 계산 |

기존 manifest의required_tools는 임의 제거하지 않는다. 자료 연결 방식을 바꾸면 manifest 버전·변경 이유·새 승인으로 반영한다. 그룹웨어 문서/차주자료를 기존 `branch_daily_stats` 시험통계로 대신하지 않는다. 상품fixture가 금리 숫자를 반환한다고 기관 상품 비교 기능이 완료된 것은 아니다.

## Task1. 업무 계약과 승인 연결을 원자 저장

**Create:** `src/backend/app/use_cases/models.py`, `repository.py`, `templates.py`, `src/backend/migrations/049_use_case_workflow_bindings.sql`, `tests/test_use_case_bindings.py`, `tests/test_use_case_binding_migration.py`.
**Modify:** `use_cases/catalog.py`, `workflows/routes.py`, `repository.py`, `identity.py`, `main.py`, `tests/support.py`.

- [ ] 10개ID/manifest_revision·역할·required_tools·review_required·input/output규칙을 서버 계약으로 정의하고 canonical digest를 계산한다. 지금의 `v1.0.0-std`는 실제 승인 version 표시에서 분리한다.
- [ ] Workflow 승인 버전에 nullable `use_case_id`, `manifest_digest`, `use_case_contract`를 추가한다. legacy는NULL로두며 새 업무버전만 제출시봉인한다. immutable trigger에서 이 필드도 보호한다.
- [ ] `portal.use_case_heads`는 tenant/use_case별1개 approved version·CAS revision·enabled를 가진다. 타인 Workflow 승인과 기존 Workflow head·업무head 변경을 같은 트랜잭션/audit에서 처리한다. 반려는 업무head를 변경하지 않는다. 동일업무다른Workflow 승인 경합도 CAS409다.
- [ ] `/admin/workflow-approvals` 제출에 optional use_case_id/expected_use_case_revision를 추가한다. manifest 계약/지문·안내문은 서버가 정하며 client 임의 system_prompt/required_tools/역할을 받지 않는다. 일반 Workflow 요청은 기존 계약을 유지한다.
- [ ] `workflow_version_guard`에 업무버전일 때 현재 업무head·manifest/code/mode·역할 검사도 추가한다. 일반 `/workflows/run`을 직접 호출해 업무 계약을 우회하는 경우도 차단한다. 철회/새head는 기존 실행/저장/조회에도 적용한다.
- [ ] 입력/출력의 업무 검증 함수를 runtime digest에 포함한다. 기존 code seal과 다른 interpreter를 종전 승인으로 실행하지 않는다.
- [ ] fixture에서 타인승인·자기승인거부·조직격리·동일UUID재생/변경body409·업무head경합·manifest변경차단·원자audit 실패rollback을 시험한다. 이행은 기존64표 전행/열·49checksum 보존·새업무metadata NULL·재적용0을 확인한다.

예정 내부 호출 계약(현재 없는 계약):

```text
UseCaseRepository.resolve(ctx, use_case_id: str) -> UseCaseBinding
UseCaseBinding:
  version_id: UUID | null
  head_revision: integer
  manifest_digest: string
  input_contract: 업무별 허용 필드와 타입/길이
  execution_ready: boolean
  readiness_reason: string | null
  execution_mode: mock | real
```

resolve는SQL public capability만 호출하며 web role의 직접 표 SELECT를 허용하지 않는다. prompt/private inputs는반환하지않는다. 업무가 미연결이면version_id=null/readiness_reason=unbound다.

## Task2. 입력·Tool·출처 계약을 실제 자료와 맞추기

**Create:** `src/backend/app/use_cases/inputs.py`, `outputs.py`, `calculations.py`, `tests/test_use_case_contracts.py`, `tests/test_use_case_source_access.py`.
**Modify:** `workflows/approved_models.py`, `bindings.py`, `service.py`, `repository.py`, `tools/adapters.py`, `registry.py`, `execution.py`, `execution/rag.py`; 필요한 새 SQL은049에 포함하거나 다음 신규 번호로 분리한다.

- [ ] 현재 input노드1개/string질문 계약을 업무별 이름 있는 필드로 확장한다. 텍스트4000자·strict문자열/숫자/식별자·필드allowlist·총요청32KB를 검증한다. input node는1개를 유지하며 필드 경로 binding을 SQL과Python이 동일하게 계산한다. 임의 context_data/원본 prompt/URL/SQL을 받지 않는다.
- [ ] 문서/차주참조는 존재·조직·owner/현재자료ACL·버전·게시Agent 승인자료범위 교집합을 확인한다. 요청 자료가 게시profile범위를 넓히지 못하게 admission/dispatch/save/read 모두 검사한다. ‘전 조직 문서검색’으로 전환하지 않는다.
- [ ] Tool adapter에 서버가 만든 사용자/조직·read scope·mode·승인참조 context를 전달한다. client arguments에tenant_id/자격증명을 받지 않는다. registry method·descriptor·실행mode 검사를 함께 변경하여 coroutine/sync adapter경로와timeout을 통일한다.
- [ ] 내부 규정은 기존 권한형 SearchRepository/RAG 출처 계약으로 읽는다. 외부 그룹웨어/상품/차주 connector는 고정 allowlist·인증참조·timeout·응답schema·기준일을 가진다. 현재 real stub을 실제 connector로 대체하되, 설정값 존재만으로 연결 완료를 판정하지 않는다. 미연결은409와사유를 유지한다.
- [ ] Tool 응답→Agent prompt에는 허용된 결과 필드만 binding한다. 객체 결과는 승인된 필드 projection과 길이 제한 canonical JSON 문자열로 변환하고, 자유로운 객체/role 지시문을 prompt 변수로 전달하지 않는다. 규정/상품 provenance는 Tool이 제공한 실제source/version/time에서 검증하며 LLM이 작성한 인용을 authoritative source로 채택하지 않는다.
- [ ] ‘validate’가 비어있지않은문자열만검사하는현재상태를 업무output계약검사로 보강한다. 최종 parent완료/일반Workflow결과공개 전에도 적용하여 use-case화면만의 후처리로 우회되지 않게 한다. 필수근거없음은insufficient_evidence, 형식불일치는failed/검증사유이며 임의보충답변을 만들지 않는다.
- [ ] 여신의 계산은 정책version·단위·기간·반올림·누락/0/불일치 수치를 검증하는 결정적서버함수로 처리한다. 산식변경은 승인계약변경이다. 실제여신조건/승인판정은 업무검토자수용이 필요하다.
- [ ] 자료권한회수·출처변조·기준일만료·connector timeout/unknown·PII mask/block·예산차단·취소와정산보존을 actualDB/승인profile과 연계시험한다.

기관 연결 정보가 없어도 typed adapter·서버권한·timeout/schema·오류처리와 계약대역 시험은 개발할 수 있다. 실제 기관 endpoint·허용뷰·문서·기준버전·테스트 접근은 준비되는 항목부터 실연동 수용하며 미제공 항목을 완료로 표시하지 않는다.

## Task3. 실행 서비스와 비동기 API

**Create:** `src/backend/app/use_cases/service.py`, `tests/test_use_case_execution_http.py`.
**Modify:** `use_cases/routes.py`, `main.py`, `errors.py`, `workflows/service.py`.

- [ ] UseCaseExecutionService를 main factory에 조립한다. 중앙 WorkflowExecutionService에 위임하며 provider/Tool을 use-case route에서 직접 발사하지 않는다. 입력부터DB GuardrailService를 사용한다.
- [ ] 실행요청에 필수 client_request_id UUID와strict parameters를 추가한다. 서버가현재승인version을확정하여202/같은내용재생200을반환한다. retry는처음수락된 exactversion/body를동일부모로재생하고 승인변경과 겹치면 새버전에자동재실행하지않는다.
- [ ] catalog/detail은 execution_ready·safe readiness_reason·approved_version_id·mode·업무안내를 현재사용자별반환한다. 서버/사용자권한별ready 판정과source가없는카탈로그설명을 구분한다.
- [ ] 본인 run조회/CAS취소를 제공한다. 다른업무ID로본인run을조회하거나 타인/조직run을조회하면404다. child참조·최종안전결과만 공개하며 원문inputs/Toolrawrows/worker token은 숨긴다.
- [ ] 중단/unknown을 완료로 치환하지 않는다. 사용자가 새 실행을 명시하지 않는 한 자동재발사하지 않는다. 종료/취소/revocation은 기존 parent/child fence·정산 경계를 유지한다.

예정 공개 API:

```text
GET  /api/v1/use-cases
GET  /api/v1/use-cases/{id}
POST /api/v1/use-cases/{id}/execute
     {client_request_id: UUID, prompt: string, parameters: 업무별 strict object}
GET  /api/v1/use-cases/{id}/runs/{run_id}
POST /api/v1/use-cases/{id}/runs/{run_id}/cancel
     {expected_revision: integer}
```

예정 수용 시험의 최소 HTTP 회귀(현재routes에서clientUUID extra가422이므로 신규 계약 구현 전 실패하는 시험):

```python
from uuid import uuid4
from test_operations import headers

def test_unbound_case_does_not_execute(client, login, db_fixture):
    csrf = login(client, 'A-U1')['csrf_token']
    reply = client.post('/api/v1/use-cases/AGENT_03/execute',
        headers=headers(db_fixture, csrf=csrf),
        json={'client_request_id':str(uuid4()),'prompt':'회의 메모','parameters':{}})
    assert reply.status_code == 409
    assert reply.json()['error']['code'] == 'EXECUTION_NOT_READY'
```

## Task4. 사용자 화면과 단일 업무 종단 완료

**Modify:** `src/frontend/src/UseCaseWorkspacePage.tsx`, `packages/api-contract/src/types.ts`, `api.ts`, `apps/user-web/src/App.tsx`, `packages/ui/src/portal.css`.
**Create:** `src/frontend/tests/use-case-runtime.spec.ts`.

- [ ] rawfetch를공통api/useScope로교체하고모든요청에tenant/CSRF/AbortSignal을전달한다. 조직변경/로그아웃때선택·질문·결과·진행중응답을정리한다.
- [ ] 목록은정의10종/현재이용가능승인종수를각각표시한다. ‘승인10종/DP24준수’ 고정문구를제거하고준비중·승인대기·권한없음·연결미설정·사용가능을사실대로표시한다.
- [ ] 오른쪽패널에업무별필수입력·허용자료선택·승인version/mode·안내문을제공한다. 질문예시chip은입력보조이며실행/승인증거가아니다.
- [ ] run_id·poll·취소·단계/자식상태·최종draft/근거/자료기준일을연결한다. requestreceipt실패재시도UUID를보존한다. 자동결정금지4종은서버정책과일치하는담당자검토표시를유지한다.
- [ ] 근거와최종초안은현재권한을재검사하여공개한다. arbitrarytool_resultsJSON을사용자결과로직접펼치는기존경로를제거하고최소허용필드만표시한다.
- [ ] AGENT03의실제시험게시Agent→타인Workflow승인→사용자실행→조회/취소/정산·조직전환종단을가장먼저완성한다. 이름만바꾼같은prompt10개를업무10종완료로표시하지않는다.

## Task5. 나머지 업무 묶음과 평가

- [ ] 규정기반묶음: 01→04→10. 승인문서·서식·단말매뉴얼·Tool/RAG현재자료권한과수용출처를완성한다.
- [ ] 심의/외환: 06→09. 업무별체크리스트·조건미확인·전문가확인강제·유효근거수용을완성한다.
- [ ] 연결자료묶음: 02→07. 실제문서connector/허용뷰와상품정보schema·기준일을확정하고개별권한및동일기준비교를수용한다.
- [ ] 복합업무: 05→08. 둘이상의Tool결과→실제초안·근거·모순/불충분과독립서버계산을검증한다. 자동발송/거래/승인실행경로를추가하지않는다.
- [ ] 각업무는정상입력·누락·불충분근거·출처/정책만료·타조직/타인·회수·취소·동일UUID/변경body·예산/정산·receipt단절을검증한다. 추가로회의담당자미정/공문필수서식/상품단위비교/여신반올림·0·오류수치의개별case를갖는다.
- [ ] ‘모의workflow기술성공’, ‘실제자료연결’, ‘담당자업무품질수용’, ‘운영DB이행/배포’를종별표에서분리한다. 기술조건통과만으로의미품질/기관수용을PASS로올리지않는다.

## 실행 순서·완료 기준·기록

권장순서: Task1공통승인연결→Task2/3최소계약→Task4의03단일종단→[[32 관리 B안 Tool Workflow 승인 화면 확장 상세 작업 계획|관리B승인UI]]→Task2자료connector확장/Task5나머지9종→통합회귀. 이전계획30의‘10종후B안’보다승인UI를앞당기는제안이다. 첫1종으로계약을검증한뒤나머지9종을실제UI에서검토/승인할수있도록하려는이유이며,확정된A/A/B디자인은변경하지않는다.

검증명령은backend프로젝트venv로신규test_use_case_*와기존test_workflow_runtime/approval·Tool·publishedAgent·DP24를순차실행한다. Node22 `npm run build`, browser `npm run test:e2e -- tests/use-case-runtime.spec.ts tests/workflow-orchestration.spec.ts`를DB시험뒤실행한다. 기본DB이행전시험이므로현재primary포트/계정/데이터를변경하지않는다.

이번문서확인은소스읽기·파일존재·계획상호링크검증이다. 앱/DB/정책/외부연동/테스트실행·운영배포변경없음. 실제연결에필요한기관자료와승인자는후속개발의가용항목부터계약을검증하며계획만으로확정된것으로취급하지않는다.


## 2026-10-14 · 사용자 범위 확정

사용자가 나머지9종은 추후 확장하고 다음 작업을 진행하도록 승인했다. 이번 개발 범위는 공통 승인 연결·회의록 및 액션아이템 AGENT_03 한 종의 실행/조회/취소/결과 검증, 관리B Tool/Workflow 승인 화면이다. 계획31 Task5의 나머지9종과 이들을 위한 기관 connector/여신 계산 확장은 후속 범위로 보류한다. 먼저 typed 회의록 입력/출력·manifest 봉인 계약을 검증하고 승인 head·실행 API·화면을 연결한다. A/A/B 결정·기존 migration 보존·시험DB 우선 원칙은 유지한다.


## 2026-10-14 · 회의록 승인 연결·메모 실행 API·사용자 UI

사용자의 다음 작업 승인에 따라 [[2026-10-14 회의록 Agent 승인 연결 및 실행 API 화면 구현 보고서]]에실제파일·시험·실패/보완·잔여를기록했다. 신규049의caseID/계약digest/기반revision·불변seal·조직업무head FORCE RLS/타인승인/CAS, workflows approval/repository/identity/service와use_cases service/routes·main, 사용자화면/API types·순차시험/전용fixture를변경했다. 입력→LLM과최종LLM text binding을강제하고일반Workflow실행에도같은원문근거검사를적용한다. 실제인증HTTP202/poll/재생200·CSRF/타인조회차단·철회/취소를시험했다.

넓은관련132pass(최종binding보완이전), 최종39pass(이행강화포함), browser4pass(실제API2·HTTP계약대역2), Node22 user26/admin37코드경계pass. 기존64표의과거행/열·49checksum/sourceSHA보존→fixture65표/50migration/169함수/35보호표·재적용0·개인fixture/자격증명제거·연결0. 안전증거는`260.테스트/evidence/Meeting-runtime-20261014`다. 테스트수를중복합산하지않는다.

회의록텍스트메모4000자 실행 연결은실제코드에서완료했으나기본DB041~049는040경계로미적용·유료호출/primaryseed/배포0. 구조화mock출력과실제모델/회의품질수용은구분한다. 관리B의Tool/Workflow신청·상세/검증/비교·검토의견/이력·결정/철회는다음작업이다. 전체manifest snapshot/자료선택·회의일/상대날짜·수동재개·다중폭검수는후속이며나머지9종추후확장과A/A/B방향을유지한다. 전체계획/운영완료는아니다.

## 2026-10-14 · 관리 B 신청·검토 UI 및 신규 회의록 전체 snapshot 연결

[[2026-10-14 관리 B Tool Workflow 승인 확장 구현 보고서]]에서AGENT_03신규신청의서버전체계약snapshot봉인과B안Workflow신청→타인승인→USER회의록mock실행→철회흐름을임시DB/API브라우저에서확인했다. 과거snapshotNULL을소급생성하지않고현재head/실제게시version/권한검사를유지한다. 나머지9종은추후확장이라는사용자범위를변경하지않았다. 실제모델/기관자료/회의업무품질·UAT·기본DB041~050이행과운영배포는남아있다.
