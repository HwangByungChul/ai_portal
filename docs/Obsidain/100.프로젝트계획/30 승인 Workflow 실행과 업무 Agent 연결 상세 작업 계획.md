---
title: 승인 Workflow 실행과 업무 Agent 연결 상세 작업 계획
date: 2026-10-13
status: W5b 실행 기반 구현 · 업무 연결 잔여
stage: 100.프로젝트계획
tags: [workflow, use-case, approved-runtime]
---
# 승인 Workflow 실행과 업무 Agent 연결 상세 작업 계획

**Goal:** W5의 임의 DAG/모의 완료 경로를 승인 버전·부모 Workflow·자식 Tool/Agent 실행과 영속 checkpoint로 교체한다.

**Architecture:** Workflow 승인 요청과 조직별 head, owner Workflow run/step을 별도 영속화한다. Workflow parent는 무료 orchestration 상태이고 LLM별 published Agent 자식은 기존 RunTicket→ExecutionManager→AiGateway→정산을 그대로 사용한다. Tool은 부모 FK와 현재 Workflow gate를 추가하여 W4 receipt를 재사용한다. Workflow의 config에서 모델/URL/prompt를 받지 않고 승인 Agent asset/version/publication revision과 값 binding만 받는다. 10 업무 Agent는 조직별 승인 Workflow head에 연결되기 전 준비 중이다.

**Spec:** [[28 상세 수정 재검토 F1-F8 잔여 결함 보완 작업 계획서]], [[29 Tool 승인 버전과 영속 실행 상세 작업 계획]], [[2026-10-13 W4 Tool 승인 및 영속 실행 구현 보고서]]. 기존 사용자 승인에 따라 이번 채팅에서 순차 실행한다.

## 공통 제약

생성형 AI 플랫폼·사용자A·관리A/B 확정 방향을 유지한다. SQL000~046을 변경하지 않고 신규047부터 추가한다. 이전 예약046은Tool에사용되었다. 기존primary040checksum문제를우회하지않고시험DB만사용한다. 실제기관connector·실제자료/모델품질·Entra/UAT/운영배포는별도다. 별도프로젝트/backup의결과를혼용하지않는다.

## Task1 승인 버전과 strict DAG

파일: `app/workflows/approved_models.py`, `repository.py`, `migrations/047_approved_workflow_versions.sql`, 신규 backend 시험.

- [x] config는 input/read_tool/llm/validate/output의 각 typed schema만 받는다. input/output 각1, node20/edge30/max_steps20이내, duplicate/self/cycle/단절/중복edge/미도달·미선행 참조를 거부한다. deterministic order로 동일 승인 버전을 재현한다.
- [x] read_tool은tool_id+승인digest+strictargs, llm은published asset/version/publication revision+values bindings다. arbitrary model/prompt/URL은422다. binding은문자열literal 또는선행node의제한된JSONpath다. 입력키·값과bound결과길이를제한한다.
- [x] admin제출→다른PADMIN승인/반려→head CAS/revoke를 구현한다. 실행모드·실행코드SHA·현재자산/Tool권한을 확인하고 원자audit를 남긴다.

## Task2 부모·checkpoint·자식 실행

파일: `app/workflows/service.py`, `repository.py`, `routes.py`, `app/tools/repository.py`, `execution.py`, `app/main.py`, 신규 시험.

- [x] public실행은version_id/client_request_id UUID/inputs만 받는다. tenant/user/client ID와bodyhash를영속화하고동일요청재생·다른body409·queue한도를확인한다.
- [x] 부모claim/lease/token·node checkpoint를DB에저장한다. public은node상태·자식참조·최종허용결과만반환하며inputs/context_snapshot/예외원문/worker token은반환하지않는다.
- [x] LLMnode admission과checkpoint child FK를같은트랜잭션에저장한다. 모델별자식의기존정산과취소/자료현재ACL을재사용한다. 생성된모의문자열로대체하지않는다.
- [x] Tooladmission과부모FK를원자저장하고현재부모상태/승인/취소를dispatch·finish에도검사한다. 동일node요청ID는자식receipt를재생한다.
- [x] 노드별입출력검사후checkpoint저장/최종공개한다. requirednode실패면downstream0이다. 취소는부모·진행중자식에전파한다.
- [ ] 재시작시완료checkpoint는재사용하고발사여부불명Tool/중단LLM은자동재발사하지않는다. 진행중부모의lease만료는interrupted/확인필요로봉인한다. accepted/replayed요청과조회가복구알림을제공한다. 완전자동분산재시작복구를완료했다고표현하지않는다.

## Task3 업무 Agent와 실제 화면

파일: `app/use_cases/service.py`, `routes.py`, `catalog.py`, frontend API types/WorkflowCanvasPage/UseCaseWorkspacePage, 신규 시험.

- [ ] optional use_case_id는10종실제manifest키만허용한다. requiredtools·허용역할·자동결정금지/전문가확인 조건을승인된profile과함께검사한다. 연결전execution_ready=false/approved_version=null이다.
- [ ] 실제tenant승인workflow version을조회해실행/조회/취소한다. run_id·poll·같은clientUUID재생을연결한다. 실제업무의의미품질/출처검증은별도수용이다.
- [x] 기존client-DAG /run gate는유지한다. 화면은승인된버전을선택하고state/사용모드/자식이력/안전최종결과를표시한다. 준비중/결과불명과실제완료를구분한다.

## Task4 순차 검증과 기록

- [ ] strictschema와모든10manifest binding검사, actualDB타인승인/멱등성/권한회수/현재자료권한/부모취소/중간실패/downstream0/동시·lease·정산중복0을검증한다.
- [ ] 047이행은이전59표의기존열/행·47checksum보존과재적용무변화를검증한다. Toolreceipt새FK열은기존행NULL로두며백필하지않는다.
- [x] 변경된사용자/관리자Node22분리build·필요브라우저검증을실행한다. 전체suite/기관UAT상태와구분한다.
- [x] 실제파일·시험증거·실패와수정·미완료를설계23/진행02와새구현보고서에기록한다. primary미적용과유료호출0을명시한다.


## 2026-10-13 · W5a 승인 버전 기반 부분 구현

[[2026-10-13 W5a 승인 Workflow 버전 및 승인 API 부분 구현 결과]]에 실제 파일·테스트·한계를 기록했다. 047 신규 migration, strict 정의 저장 및 승인/카탈로그 API를 추가했고 임의 DAG 실행은 계속 409다. W5a 테스트와 migration 20개 통과, 관련 W4/W5 회귀 73개 통과(이후 승인 CAS revision 분리 변경 후 관련 20개 재통과), 관리자 build와 Canvas 브라우저 1건 통과. primary DB 미적용·전체 suite/운영 미검증. reject/revoke 및 Tool 참조 경계 일부 검증, Workflow parent/step ledger·Agent child 실행·10개 업무 연결이 남아 있으므로 계획 상태는 부분 구현이다.


## W5b 실행 원장 구현 순서 · 2026-10-13

기존 승인에 따라 이 채팅에서 순차 구현한다. 047은 보존하고 048에 parent run/step 및 기존 자식 capability wrapper를 추가한다. `workflow_versions`에 실행 mode/code digest를 추가하며 과거 NULL은 승인으로 소급 봉인하지 않는다. 서버 code digest와 현재 mode가 일치하는 승인만 실행한다.

- [x] 048: 불변 정의 보호 trigger, version gate, owner parent/step RLS, 승인 코드 지문, 기존 published/tool guard wrapper, atomic child admission/FK, cancel/lease/recovery 원장을 추가한다.
- [x] `app/workflows/identity.py`·`bindings.py`: 코드 지문과 제한 JSON 경로 binding을 구현한다. `repository.py`는 runtime/child/tool/recovery RPC를 제공한다. Tool 서비스에는 parent-bound repository를 주입하여 기존 검사·receipt를 재사용한다.
- [x] `service.py`: accepted→claim→strict 순서→node checkpoint→completed를 실행한다. heartbeat 10초·parent lease60초·최대1200초, Agent 노드180초, 안전 오류 코드, cancel 전파, 불명/실패 downstream0을 유지한다.
- [x] `routes.py`·`main.py`: 승인 version 실행 202/replay200, 본인 run 조회·CAS 취소, factory 시작/종료·복구를 연결한다. client DAG는409를 유지한다.
- [x] disposable DB에서 실제 Agent run/call/settle와 Tool receipt를 확인하며 동일client body 충돌·타인조회·승인회수·노드실패·부모취소·lease/recovery를 순차 시험한다. 기존000~047 checksum과 기존행/열을 보존한다.
- [x] 변경과 검증을 구현 보고서·진행02에 기록한다. primary040 문제·기관모델/UAT/운영배포는 이전과 구분한다. 업무10종/UI 승인 편집·상세패널 연결은 Task3로 이어진다.


## 2026-10-13 · 실행 원장 단위 완료 및 잔여 구분

[[2026-10-13 W5b 승인 Workflow 실행 원장 및 Agent Tool 연결 구현 보고서]]에 실제 변경 파일·실패/수정·검증·다음 순서를 기록했다. Task1 승인 code/mode seal, Task2 영속 parent/step·실제 published Agent/Tool child·정산/취소 gate와 Task3 Canvas 실행 화면을 구현했다. 최종40건·넓은회귀157건은 별도 실행이며 중복 합산하지 않는다. browser2건(1실제API/1HTTP계약대역), Node22 user26/admin37 분리build도 통과했다. 048 이행은 이전62표/48checksum 보존→64표/49migration/166함수다. primary 미적용·유료 호출0.

Task2의 재시작 항목은 **완료 checkpoint 보존·불명/중단 자동재발사 금지까지 완료, 중단 run 재개는 미구현**이므로 원래 항목을 부분 상태로 남긴다. Task3의 실제10manifest 승인 head 연결/use-case 실행 API와 Task4의 모든10binding 수용은 아직 미완료다. Canvas와 generic runtime를 업무10종 완료로 확대하지 않는다. 다음 순서는 실제10종 binding/업무별 시험→관리B Tool/Workflow 승인UI→계획28 W6~W9다. 자세한 잔여/외부 수용과 primary040 경계는 구현 보고서를 따른다.


## 2026-10-14 · 업무10종 연결과 관리B 승인 확장 상세 계획 제안

사용자의 상세 작업 문의에 따라 [[31 업무 Agent 10종 승인 연결 상세 작업 계획]], [[32 관리 B안 Tool Workflow 승인 화면 확장 상세 작업 계획]]을 작성했다. 현재 source에서 업무execution_ready=false/use_case_execution미조립·service.py부재, rawfetch tenant/scope누락과고정‘승인10종’표시, realToolstub409, 승인settings/evidence/dynamic3유형과Tool/Workflow50개목록·상세/의견계약부족을확인했다.

제안범위는업무manifest/strictinput-output·조직별승인head/code/mode/자료권한·실제Workflow/Agent/Tool원장연결·poll/취소/안전출처와10종별업무수용, 관리B의Tool/Workflow신청·목록/상세/현재검증/diff/검토의견/타인결정/철회·deep link/반응형수용이다. 기존A/A/B디자인결정은변경없음. genericWorkflow직접API에서도업무정책을검사하고manifest/code변경은새승인을필요로한다.

이전계획30의‘10종→B안’보다공통계약→외부Tool없는회의록03의1종종단→관리B확장→나머지9종순서를권장하는새제안이다. 1종으로공통계약을검증하고나머지9종을실제승인UI에서검토하도록하는이유이며사용자확정/개발완료로표시하지않는다. 실제connector/기관자료없는항목은시험연결·실연동·업무품질·운영DB이행을각각구분한다. primary040경계/000~048보존을유지하고049/050은번호예약뿐이다.

변경한실제파일은계획31·32와이기록·설계23·계획30의연계문단뿐이다. source대조/10종ID·역할/Tool명·문서상호링크/한글문서검사만수행했으며새앱/DB/정책/테스트/외부승인/배포변경없음. Obsidian앱렌더미검증. 다음착수단위는계획31 Task1공통승인연결이며실제기관자료·업무검토자는후속수용조건이다.
