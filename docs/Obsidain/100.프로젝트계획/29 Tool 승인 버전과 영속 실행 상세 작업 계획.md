---
title: Tool 승인 버전과 영속 실행 상세 작업 계획
date: 2026-10-13
status: 독립읽기도구-API및DB검증완료-화면기관연계미완료
stage: 100.프로젝트계획
tags: [tools, durable-execution, implementation-plan]
---
# Tool 승인 버전과 영속 실행 상세 작업 계획

**Goal:** W4의 조직별 승인과 영속 receipt를 구현하여 같은 요청의 중복 handler 호출을 방지한다.

**Architecture:** server registry의 Tool/인자 schema/adapter revision/mode/timeout을 지문으로 묶어 변경 불가능한 승인 요청을 만든다. 제작 관리자는 요청하고 다른 PADMIN이 승인한다. 조직별 현재 승인 head와 사용자 audience를 매번 확인한다. 영속 accepted→dispatched→succeeded/failed/unknown receipt를 PostgreSQL SECURITY DEFINER RPC와 CAS로 변경한다. API는 원문 인자를 저장하지 않고 지문만 저장하며 출력 검사 후 허용 결과만 보존한다.

**Tech Stack:** 기존 FastAPI/Psycopg/PostgreSQL/pytest. 새 외부 라이브러리는 추가하지 않는다.

**Spec:** [[28 상세 수정 재검토 F1-F8 잔여 결함 보완 작업 계획서]], [[2026-10-13 F1-F8 1차 보완 구현 및 040 원본 검증 보고서]]. 기존 사용자 승인에 따른 순차 개발이며 새 운영 배포 요청이 아니다.

## 제약과 설계 결정

- 000~045 기존 migration은 수정하지 않는다. 계획28의 예약045는 이미 관측 경계에 사용했으므로 신규046을 사용한다.
- 기존 primary 040 불일치는 우회하지 않는다. 별도 폐기 가능한 시험 DB에만 migration·합성 fixture를 적용한다.
- 승인 head는 tenant/tool별이고 receipt 요청 키는 tenant/user/client UUID이다. 같은 ID를 다른 tool/version/args에 쓰면409다. 다른 tenant/user는 독립이다.
- 승인 요청에는 server descriptor와 expected head revision, audience all/restricted, member UUID 목록을 저장한다. 자기 승인403, 승인자는 PADMIN, stale head409. 타인 승인 후 head CAS. revoke는 현재 head revision을 요구한다.
- 처음에는 독립 읽기 Tool3종만 지원한다. parent RunTicket/Workflow 연결·자료 ACL/실제 서비스계정 connector는 W5/기관 연계 단계다. 현재 Tool은 자료 참조를 받지 않는다.
- mock만 FixtureToolAdapter를 명시 주입하고 실제 데이터로 표현하지 않는다. real은 connector 구현 전409이며 fixture로 대체하지 않는다.
- accepted 상태는 안전하게 dispatch할 수 있다. dispatched 이후 timeout/취소/과정 오류/프로세스 중단은 결과 불명 unknown으로 보존하고 같은 ID 재호출 시 handler를 다시 실행하지 않는다. 외부 effect exactly-once를 보장한다고 표현하지 않는다.
- body/result 최대 UTF-8 32KiB, 현재 strict schema type/required/enum/maxLength/additionalProperties를 검사한다. 원문 args는 receipt/audit에 저장하지 않는다.
- DB 권한 회수·승인 변경 시 replay/dispatch/finish도 거부한다. input/output GuardrailService를 연결한다. 저장 실패 후 raw handler 결과를 반환하지 않는다.

## Task1 승인과 영속 원장

파일: `src/backend/migrations/046_tool_approvals_and_receipts.sql`, `app/tools/repository.py`, `tests/test_tool_persistent_execution.py`, `tests/support.py`.

- [x] 승인 요청·현재 head·receipt3표를 FORCE RLS, web 직접 DML 금지로 생성한다.
- [x] `security.tool_approval_control(session,tenant,action,id,body,trace)`에서 list/submit/approve/reject/revoke 및 원자 audit를 제공한다.
- [x] `security.tool_execution_control(session,tenant,action,tool,digest,mode,client,args,token,result,error,trace)`에서 ready/admit/dispatch/finish/read를 제공한다. dispatch token과 CAS를 검사하고 DB 시각 lease 만료는 unknown이다.
- [x] 새 fixture에서 같은 요청 재시도/다른 args409/자기 승인403/잘못된 audience403/회수 후 재생 거부/직접 DML 거부/행 보존을 검증한다.

## Task2 실행 서비스와 HTTP

파일: `app/tools/execution.py`, `app/tools/registry.py`, `app/tools/routes.py`, `app/main.py`, 신규 시험파일.

- [x] `ToolExecutionService.invoke(ctx,tool_id,args,client UUID)`와 `ready(ctx)`를 제공한다. registry는 검증/명시적인 handler 실행 역할만 맡고 서비스는 DB receipt를 사용한다.
- [x] 관리자 `/api/v1/admin/tool-approvals` 목록·제출/타인 승인·반려, `/api/v1/admin/tools/{tool_id}/revoke`를 추가한다. 사용자 invoke는 필수 UUID와 strict dict이며 상태 조회는 본인 요청 ID만 허용한다.
- [x] main에서 pool·mode·DB guardrails·명시 mock registry를 주입한다. execution_enabled 미설정과 real 기관 connector 미구현은409를 유지한다.
- [x] 두 서비스 instance와 동시 요청에서 handler합계1, 결과 보존, lease 만료/timeout unknown, 저장 실패시 원문 반환0을 검증한다.

## Task3 회귀와 기록

- [x] DB 시험은 순차 실행한다. 단위 schema, actual DB/auth HTTP, checksum 변경 거부를 확인한다.
- [x] 기존 표의 행·열 및000~045 checksum 보존, 재적용 변화 없음, 공통 schema 개수·권한 검사를 확인한다.
- [x] 검증 결과와 미완료를 [[02 포털 UI UX 작업 기록]], [[23 포털 UI UX 확정과 사이트 분리 검토]]와 구현 보고서에 기록한다.

기관 connector, Workflow parent run, 관리자 React Tool 승인 UI, 실제 제공자·Entra/UAT·primary 이행/운영 배포는 이 독립 Tool 작업의 완료로 표현하지 않는다.


## 2026-10-13 실행 결과 및 추가 경계

위 체크는 독립 읽기 API/DB 작업 범위다. actual parent RunTicket·기관 connector·관리자 React 화면을 완료한 것은 아니다. 최종57건 순차 시험 통과. 설정 period/mode의 플랫폼 중지·stop latch, 재생 출력 검사 후 permit 재확인, schema·adapter/registry 코드 지문, queue20건 제한과 관리자 current_head_revision을 추가했다. 처음예약045는이미사용되어046으로구현했다. 상세파일·실패수정·증거·미완료는 [[2026-10-13 W4 Tool 승인 및 영속 실행 구현 보고서]]를 따른다. 기존primary는040문제로반영하지않았고초기화·이력변경·유료호출은없다.
