---
title: 관리 B안 Tool Workflow 승인 화면 확장 상세 작업 계획
date: 2026-10-14
status: 현재 범위 구현·선별 수용·최종 코드 검토 완료
stage: 100.프로젝트계획
tags: [admin, approvals, workflow, tool, implementation-plan]
---
# 관리 B안 Tool Workflow 승인 화면 확장 상세 작업 계획

**Goal:** 기존 관리A기본홈·승인B목록/상세흐름에Tool/Workflow승인요청·검증·비교·결정·철회·업무연결을추가한다.

**Architecture:** 공통승인쉘과선택/필터를유지하고요청유형별상세컴포넌트를분리한다. 기존Tool/Workflow승인RPC의타인결정·CAS·원자audit를재사용하며부족한상세/페이지/검토의견API는신규migration으로추가한다. UI의버튼비활성은보조이고최종권한/현재의존성검사는항상서버에서수행한다.

**Tech Stack:** 기존React/TypeScript/CSS tokens, FastAPI/Pydantic/PostgreSQL, Node22.23.1, pytest/Playwright.

**Spec:** [[23 포털 UI UX 확정과 사이트 분리 검토]], [[28 상세 수정 재검토 F1-F8 잔여 결함 보완 작업 계획서]], [[31 업무 Agent 10종 승인 연결 상세 작업 계획]], [[30 승인 Workflow 실행과 업무 Agent 연결 상세 작업 계획]].

**실행 방식:** 기존사용자범위안에서현재채팅의순차단위로구현/검증/기록한다. 이번작업은계획작성이고앱수정/새승인/primary이행을하지않는다.

## 기준선·제약

- 현재ApprovalsPage유형:운영설정/settings·시험증적/evidence·동적배포/dynamic. App.tsx/approvalLaunch.ts deep link는settings/dynamic만지원한다. Tool/Workflow유형은신규다.
- Tool·Workflow는list/submit/decision/revoke API가있지만목록이최근50개고정이며독립상세/검토의견/완전한이력은부족하다. 일반설정/동적배포에있는comment계약을자동으로Tool/Workflow에도있다고가정하지않는다.
- pending/approved/rejected는승인요청상태이고enabled/currenthead/철회는현재활성상태다. 과거approved요청을철회했다고rejected로덮어쓰지않는다.
- requester본인결정금지·현재조직PADMIN결정·TADMIN신청/관리범위·USER접근거부·CSRF/currentmembership·CAS409·audit실패rollback 유지.
- 신규번호050은예약이며착수때마지막migration을재확인한다.000~048을수정하지않고계획31의049와순차이행한다. primary040문제를우회하지않는다.
- 제품명과공통공간/색상/관리A/B기준유지. 확인되지않은정상상태·승인수/통과badge를생성하지않는다.

## 1. 화면 구성

```text
승인·검증
  요청 유형: 운영 설정 | 시험 증적 | 동적 Agent 배포 | Tool 승인 | Workflow 승인
  좌측: 상태/유형 필터 + 요청 검색 + 요청일순 목록 + 더 보기
  우측: 선택 요청 제목 / 상태 / 요청자 / 요청일 / 검토 가능 여부
        검증 결과 | 변경 사항 | 처리 이력
        검토 의견 / 승인·반려 / 적용 결과
```

넓은화면은목록·상세2패널,좁은화면은목록→상세순서로전환하고뒤로가기시선택/필터를유지한다. 조직변경/로그아웃은상세/선택/의견/확인단계를즉시초기화한다. ‘요청검색’은서버title/id의허용범위검색이며50개만클라이언트에서찾고전체결과로표시하지않는다.

### Tool 상세

- 어떤읽기도구를누가어느대상에게허용하려는지:이름·용도·read-only·argument schema·timeout·mode·connector현재상태·공개대상.
- 검증:현재도구descriptor/승인base head·스키마·권한·연결준비와현재버전일치. 품질/보안심사통과를기술검증과구분한다.
- 변경:현재활성승인과요청의도구version·허용arguments·timeout·공개대상차이. API key/DSN/endpoint비밀은표시하지않는다. exactdigest는접힌기술상세에서필요시확인한다.
- 이력:신청·검토의견·승인/반려·현재head변경/철회시점. 승인과기관connector연결완료는별도표시.

### Workflow 상세

- 이름·정의version·연결업무Agent·mode·현재head·공개대상과node/edge diagram.
- 노드:입력계약→허용Tool→게시Agent→출력조건검사→최종결과. 각Agent의exact게시version/공개범위,Tool승인version,자료접근가능여부를최소범위로표시한다.
- 검증:cycle/도달성/선행binding·필수Tool·입출력/manifest정합성·현재code/mode·의존성회수·자기승인금지. schema검사성공은업무정확성통과가아니다.
- 변경:현재승인과요청version의노드추가/삭제·Agent/Toolversion·binding·입출력조건·공개대상·검토필수여부비교. 임의JSON만던져주는UI를완성으로보지않는다.
- 이력:신청·타인결정/의견·업무head활성화·철회. private질문/개인trial원문·남의실행결과를승인상세에혼합하지않는다.

## Task1. 상세·검증·이력 API를 먼저 완성

**Create:** `src/backend/app/approval_reviews/models.py`, `repository.py`, `src/backend/migrations/050_tool_workflow_approval_reviews.sql`, `tests/test_tool_workflow_review_http.py`, `tests/test_approval_review_migration.py`.
**Modify:** `tools/routes.py`, `repository.py`, `workflows/routes.py`, `repository.py`, `errors.py`, `tests/support.py`.

- [ ] 목록에status/query/cursor/limit(최대50·기본20)을추가하고tenant/kind/filter에결합된keysetcursor를검증한다. 항목ID로별도상세를조회해최근50개에없는deep link도처리한다.
- [ ] 상세는요청snapshot·current head·현재dependency검사·can_decide와safe reason을반환한다. 권한없는자료명/원문은숨기고접근불가검증상태만표시한다. 존재하지않는필드는추정하지않는다.
- [ ] 반려/승인의견은trim후1~500자UTF8/NUL거부로검증한다. 신규append-only FORCE RLS review원장에tenant/kind/target/version/actor/decision/CAS revision/의견/시각을저장한다. 기존승인결정+review+audit를한트랜잭션으로처리하고유실/부분결정을허용하지않는다.
- [ ] 기존comment없는과거결정은‘의견미기록’으로표시한다. 결정재생은same actor/decision/revision/comment만동일결정으로확인한다. 다른의견을이미처리된요청에덮어쓰지않는다.
- [ ] 철회는head CAS·사유·최소이력으로저장한다. historicalapproved요청status를변경하지않는다. 관련업무head/부모실행현재gate도같은규칙으로회수한다.
- [ ] currentversion대비diff는서버가두개의exactsnapshot에서계산한다. 없는기존snapshot에는‘기존승인없음’을표시한다. 존재하지않는이력을현재상태로꾸며내지않는다.
- [ ] 타조직목록/상세·USER접근·자기승인·타PADMIN·staleCAS·중복결정/의견충돌·audit/review저장실패rollback·과거의견NULL·cursor위조를실제DB/API에서검증한다.

예정상세API(현재없음):

```text
GET /api/v1/admin/tool-approvals/{request_id}
GET /api/v1/admin/workflow-approvals/{version_id}
# 각각 list,status/query/cursor 및 detail의 validation/diff/history를 추가
POST /api/v1/admin/{tool|workflow}-approvals/{id}/decision
     {decision: approve|reject, expected_revision: integer, comment: string}
```

기존revoke경로는유지하며comment/safe history를확장한다. 일반설정·동적배포의의견은해당기존원장을그대로사용한다.

## Task2. 요청 제출 UI와 정확한 version 선택

**Create:** `src/frontend/src/ToolApprovalRequest.tsx`, `WorkflowApprovalRequest.tsx`.
**Modify:** `WorkflowCanvasPage.tsx`, `packages/api-contract/src/types.ts`, `api.ts`; 관련Tool관리진입은현재페이지구조에서추가한다.

- [ ] Tool신청은서버카탈로그에서만선택·공개대상회원선택·현재head revision을사용한다. client가descriptor/digest/임의URL을작성하지못한다. 제출UUID는receipt실패재시도때유지한다.
- [ ] Workflow신청은업무template또는엄격노드편집으로input/Tool/Agent/binding/output을작성한다. 현재실제게시Agent/승인Tool만선택하고변수명·reference·requiredtools를검증한다. JSON고급보기는구조화폼과동일typed schema의검토용이다.
- [ ] 업무10종용신청은caseID와서버manifest계약을함께 표시하고자동결정금지/필수자료를사용자가해제하지못하게한다. 계획31의현재업무head CAS를제출한다.
- [ ] 제출전검증은서버ApprovedWorkflow schema와동일 검증 함수를사용한다. 현재 기존 `/workflows/validate`는예시구조용이므로실제 승인 schema 검증 API를 별도로 추가해 구분한다.
- [ ] 제출성공은‘승인요청접수/미승인’이며즉시현재운영version/실행ready로바꾸지않는다. 요청ID/versionID로승인B상세에연결한다.

## Task3. 관리 B 목록·상세와 deep link 확장

**Create:** `src/frontend/src/ToolApprovals.tsx`, `WorkflowApprovals.tsx`, `ApprovalReviewPanel.tsx`, `tests/tool-workflow-approvals.spec.ts`.
**Modify:** `src/frontend/src/ApprovalsPage.tsx`, `approvalLaunch.ts`, `apps/admin-web/src/App.tsx`, `AdminHomePage.tsx`, `packages/api-contract/src/types.ts`, `packages/ui/src/portal.css`.

- [ ] ApprovalKind를 settings/evidence/dynamic/tool/workflow로 정의한다. 기존 3유형 동작을 유지하고 유형별 adapter/component에서 신규 2유형을 표시한다.
- [ ] deep link의 kind·UUID·중복 query 검사를 유지한다. Workflow는 request_id 표시 키에 version UUID를 전달하고 Tool은 request UUID를 전달한다. 조직 변경 후 이전 tenant의 요청을 자동 선택하지 않는다.
- [ ] 목록filter/상태/더보기·선택·loading/empty/error를제공한다. 상세검증/변경/이력탭은동일B스타일로제공하며keyboardfocus/선택행aria/currentbadge와조회시점표시를갖는다.
- [ ] 검토의견→승인/반려확인→저장응답→재조회순서로수행한다. 클릭중복을막고CAS409면최신요청을재조회해기존의견을검토후다시결정하게한다. 자동재승인을하지않는다.
- [ ] 결정권한이없으면사유를표시하고동작을제한한다. 의존성회수/버전변경시승인은차단하되반려는현재정책상가능한경로를유지한다. 최종권한확인은API가수행한다.
- [ ] 철회는현재활성head만별도동작으로제공하고기존진행중실행/업무영향을보여준다. 완료정산취소/과거승인이력삭제를철회동작에포함하지않는다.
- [ ] 관리자A홈승인수/바로가기/요청선택을새유형과연결한다. 집계기간·자기승인불가·현재조회권한에맞춘서버count를사용하고고정상수/화면목록길이로전체대기건수를대체하지않는다.

## Task4. 기술·시각 수용과 기록

- [ ] 실제임시DB/API의Tool신청→다른PADMIN승인→USER허용,Workflow신청→타인승인→업무head활성화→실제Workflow실행을browser종단검증한다. HTTP대역시험과DB종단시험을분리기록한다.
- [ ] 기존settings/evidence/dynamic 진입·상세·결정·철회,승인홈링크회귀를유지한다. wrongkind/ID·staleUUID·잘못된query·조직전환중늦은응답과CSRF누락을검증한다.
- [ ] 1440·1024·768폭에서목록/상세/긴한국어제목/DAG/의견칸이잘리지않는지캡처하고keyboard로선택/결정/뒤로가기를검증한다. 캡처에 비밀·개인 trial 원문을 포함하지 않는다.
- [ ] Node22user/admin분리build와코드경계검증을실행한다. 신규 review/binding 및 기존 Tool/Workflow/Agent 승인 pytest를 순차 실행하고 그 뒤 Playwright 시험을 실행한다.
- [ ] 050 migration은 기존 행/열/checksum·과거 의견 NULL·append-only/RLS·직접 web SELECT 거부·재적용0을 검증한다. schema 기대값은 실제 새 migration을 확인하여 갱신한다.
- [ ] 실제 파일/증거/실패·미검증·다음 작업을 새 구현 보고서, [[02 포털 UI UX 작업 기록]], [[23 포털 UI UX 확정과 사이트 분리 검토]]에 기록한다. primary 이행/실제 기관 연결/업무 품질/운영 배포는 별도로 판정한다.

## 완료 판정과 의존 순서

완료기준은실제요청접수→목록/상세조회→현재검증/비교→타인결정/의견영속저장→운영head변경→USER실행/철회차단이연결되고기존3유형이유지되는것이다. 승인 UI만 완성한 상태를 미연결 connector나 업무10종 완료로 확대하지 않는다.

순서는 계획31의 공통 API·03 단일 종단 이후 이 계획 Task1→2→3→4를 진행하고 남은9종을 확장한다. 상세 API와 현재 검증이 선행하므로 화면에 가상의 합격 판정을 넣지 않는다. 이번에는 source 대조/문서 작성만 수행했으며 테스트/DB/앱 변경·외부 승인 실행은0이다. Obsidian 앱 reading view는 미검증이다.


## 예정 HTTP 권한 회귀 예시

신규 상세 경로는 현재 없어 아래 일반사용자403 기대 시험이 먼저 실패한다. 경로 추가 후 currenttenant관리권한을 검사하여 통과시킨다. ID 존재 여부를 일반사용자에게 먼저 노출하지 않는다.

```python
from uuid import uuid4
from test_operations import headers

def test_user_cannot_open_tool_approval_detail(client, login, db_fixture):
    login(client, 'A-U1')
    reply = client.get('/api/v1/admin/tool-approvals/' + str(uuid4()),
        headers=headers(db_fixture))
    assert reply.status_code == 403
```


## 2026-10-14 · 사용자 범위 확정

사용자가 나머지9종은 추후 확장하고 다음 작업을 진행하도록 승인했다. 이번 개발 범위는 공통 승인 연결·회의록 및 액션아이템 AGENT_03 한 종의 실행/조회/취소/결과 검증, 관리B Tool/Workflow 승인 화면이다. 계획31 Task5의 나머지9종과 이들을 위한 기관 connector/여신 계산 확장은 후속 범위로 보류한다. 먼저 typed 회의록 입력/출력·manifest 봉인 계약을 검증하고 승인 head·실행 API·화면을 연결한다. A/A/B 결정·기존 migration 보존·시험DB 우선 원칙은 유지한다.


## 2026-10-14 · 회의록 실행 선행 완료

[[2026-10-14 회의록 Agent 승인 연결 및 실행 API 화면 구현 보고서]]에서 회의록 승인 연결/API/사용자 UI의 선별검증을 완료했다. 다음은 이 계획의 Task1 상세·현재검증·head revision·불변manifest snapshot 및 검토의견/이력 계약, 이어 요청폼과 관리B 목록/상세 UI다. 나머지9종은 사용자 지시로 후속 확장이다. primary/실제 모델업무수용/운영배포는 완료가 아니다.

## 2026-10-14 · 승인 B 확장 실행 결과

[[2026-10-14 관리 B Tool Workflow 승인 확장 구현 보고서]]에서 현재범위 Task1 서버와 Task2/3 신청·승인B UI 구현/검토, Task4 선별수용을마쳤다. 신규050원장/의견/현재검증·목록cursor/정확상세·manifest snapshot, 5유형탐색/신청/비교/이력/타인결정/철회/관리A홈집계/deep link/폭별화면을연결했다. 재개과정에서기술검증의승인후자체head증가와PublishedRun필드누락·Toolbindingretarget·stalepublicationrefresh를수정했다.

최종서버지정23pass, Node22user26/admin43경계pass, 고유browser15pass(실제임시DB/API6·HTTP대역9), 1440/1024/768visual/keyboard선별검수와최종Spec/QualityPASS다. 반복실행수합산·전체suite완료·실모델품질/기관connector개통·기본DB이행/운영배포완료로표현하지않는다. 초기tempbaseline귀속한계·040기본DB경계·미검증상용/UAT와나머지9종후속범위는보고서에유지한다. 상세체크리스트의기관수용/전체경로추가검증은실제환경후속수용조건으로남긴다.


## 2026-10-15 · 현재 개발 DB 상태 갱신

[[2026-10-15 기존 계정 데이터 보존 및 040 개발 보류 해소 보고서]]에서기존계정/비밀번호/52업무표데이터를보존한새개발DB전환을완료했다. 현재SQL51/source51일치·040포함불일치0/pending0·서비스3개200이다. 위이전기록의040보류/primary미이행은보존된옛DB의원본직접이행이력이며현재개발DB를막는사항이아니다. 옛040원본발견/복원으로표현하지않고원본DB/이력을따로보존한다.
