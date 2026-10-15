---
title: DP12 동적 Agent 승인 게시와 사용자 실행 상세 계획
date: 2026-10-12
tags: [portal, approval, agents]
status: 해당 구현 단위 완료 · 후속 남음
---
# DP12 동적 Agent 승인 게시와 사용자 실행 상세 계획

**Goal:** 명시 공유된 정확한 Builder 버전의 승인 요청→타인 승인/반려→공개 대상별 게시→일반 사용자 실행을 실제 DB/API/React로 연결한다.

**Architecture:** 개인 trial/case와 공유 원장은 유지한다. SQL036에 요청·현재 게시 원장, SQL037에 사용자 동적 실행 binding을 추가한다. 승인 시 exact shared evidence와 현재 버전/정책/모드/자료·검토자 역할을 검증하여 immutable config/profile과 공개 대상을 게시 원장에 봉인한다. 사용자 실행은 그 게시 snapshot만 사용하고 기존 admission/capacity/중지/예산·Gateway/원장을 재사용한다. raw 개인 입력 접근이나 관리 권한 대행은 하지 않는다.

**Tech Stack:** PostgreSQL forced RLS·security RPC, FastAPI/Pydantic, React/TypeScript, pytest/Playwright.

**Spec:** [[31 DP11-06 승인용 시험 증적 공유 상세 계획]], [[32 DP11-06 승인용 시험 증적 공유 구현 결과]], [[33 DP11-06 증적 공유 독립 자료 권한과 철회 검증]], [[23 포털 UI UX 확정과 사이트 분리 검토]], [[15 전체 기능명세서 잔여 기능 개발 실행 계획]].

사용자의 다음 작업 진행 승인을 설계·직접 순차 실행 승인으로 적용한다. 사용자 지정 Vault·기존 변경 보존을 스킬의 추가 승인/commit/기본 경로보다 우선한다. 하위 에이전트를 사용하지 않는다.

## 검토한 구현 선택

1. 선택: 별도 동적 게시 binding과 실행 task를 기존 중앙 원장에 연결한다. 개인 owner RLS와 고정 Agent 계약을 보존하고 게시된 snapshot만 일반 사용자에게 적용할 수 있다.
2. 미선택: 고정 general/rules_rag 설정에 동적 prompt를 덮어쓴다. 같은 조직의 다른 Agent와 실행 지문을 혼용하게 된다.
3. 미선택: 별도 제공자 실행기를 만든다. 기존 예산/dispatch/정산·취소/사용량 누락 위험이 있다.

## 이번 단위의 계약

- 제품명/사용자A·관리A·승인B 유지. SQL000~035 동결. primary47표/36migration/132함수에서036/037만 추가, backup600·기존 전행/checksum 보존. 합성 업무 primary 쓰기/유료 호출0.
- submit: client_request_id, share_id, expected_publication_revision(첫0), reason, audience all|restricted, member_ids 최대200. restricted 대상은 활성 계정·현재 조직 membership의 교집합, 중복/NULL 거부. 본인 공유만 요청 가능하며 share submitted·현재버전/profile/모드/정책·자료 검사. 동일 ID/body receipt, 변경409. 반려 뒤 새ID·새 증적/버전으로 재신청, 기존 요청 보존.
- decide: pending revision CAS, approve|reject, 의견1~500자. 승인자는 현재 조직 PADMIN이며 요청자와 달라야 한다. approve에는 quality_reviewed/security_reviewed 명시 true, 조건충족 evaluation·generate 시험, current conditions 모두 일치, share 미철회·검토자 현재 ACL·최신 asset·현재 publication_revision을 확인한다. mock 승인은 local mock 게시이며 real 실행에는 real 시험/게시가 필요하다. reject는 자료 회수/구버전에서도 가능하며 게시를 바꾸지 않는다. 같은 결정 replay·다른결정409. 승인과 publication 저장은 같은 transaction; 현재 fixed runtime 설정/예산/중지는 변경하지 않는다.
- 게시 원장은 정확한 asset/version/revision/config hash/profile hash·공개 대상·운영 모드·요청/결정자를 보존한다. 새 승인 게시의 CAS revision을 별도로 증가시키며 과거 요청은 immutable snapshot으로 보존한다. 새 초안 버전 저장만으로 현재 게시를 바꾸지 않는다. 운영 철회(retire)는 PADMIN·CAS로 신규/진행 실행을 차단하고 사용량/요청 이력은 보존한다. 이전 버전 복귀는 별도 승인 이력이 필요한 후속 rollback 단위로 남긴다.
- 사용자 published catalog는 현재 membership·게시 대상·publication mode와 현재 fixed Agent 이용 정책을 모두 적용한다. prompt 원문/개인 시험을 catalog에 노출하지 않는다. 실행 form 변수명만 제공하고 모든 required values로 one-pass compose; default_general/default_rules_rag만 사용한다. 임의 모델/secret/tool 호출 미지원.
- 실행은 새 task_kind asset_chat, exact publication revision/version/profile/messages/sources를 owner run에 봉인한다. asset prompt와 정책 config_revision은 별개이며 claim이 봉인한 binding을 사용한다. 기존 capacity/rate/중지/예산/예약/dispatch/settle/timeout/cancel/recovery를 유지한다. dynamic asset임을 fixed alias로 위장하거나 관리자의 identity를 대행하지 않는다.
- RAG는 승인 profile의 명시 자료 범위만 사용한다. 빈 scope는 검색/생성 호출0·부족근거. 실행 사용자의 현재 자료권한·정확한index/mode를 admission/claim/heartbeat/dispatch/finish/read에 재검사한다. 다른 자료를 자동 확장하지 않는다. 게시 철회/교체·공개 대상 회수·fixed 정책 변경 시 진행 실행은 fence하며 발사된 비용을 보존한다.
- 동적 사용자 작업은 전용 변수 입력·완료 출력 polling·본인 실행 이력·취소로 제공한다. 매 요청은 독립 run/conversation으로 저장하며 이번 단위의 다회차 대화 memory는 추가하지 않는다. 기존 사용자 chat/카탈로그/고정 승인/개인 Builder는 유지한다. 일반 /runs의 미게시 draft404 유지.

## Task1 승인/게시 DB·API·관리 UI

파일: migrations/036_asset_deployments.sql, app/assets/deployments.py, app/main.py, frontend/src/AssetDeployments.tsx, SharedEvidenceReview.tsx, ApprovalsPage.tsx, 관련 tests.

security.asset_deployment(session,tenant,action,id,body,mode) actions submit/list/detail/decide/retire. 공유 proof는 security.builder_evidence_share(detail)로 검토자의 own-context에서 확인한다. SQL이 반려·조건미충족·자기승인을 실패시킨다. request/publication forced RLS·capability only·snapshot trigger seal. API /admin/asset-deployments GET/POST, /{id} GET, /{id}/decision POST, /publications/{asset}/retire POST. strict query/extra·CSRF·32KiB/no-store·rate window 적용.

- [ ] 격리 서버: exactshare/version/조건/모드/본인/타인/타조직, submit receipt·변경409, 타인 승인/CAS/replay/자기승인거부/반려, source회수·shared철회·정책변경·게시 대상 current membership·원자성 검증.
- [x] 실제 UI: 본인 공유 상세에서 공개 대상·목적을 입력해 승인 요청, B 목록/상세에서 승인 검토 체크/의견/결정·반려·현재 상태 확인·게시 철회.

## Task2 중앙 실행 연결·사용자 UI

파일: migrations/037_published_agent_execution.sql, app/assets/published.py, app/ai/repository.py, app/builder/execution.py, app/execution/manager.py, app/execution/rag.py, app/main.py, frontend/src/PublishedAgents.tsx, CatalogPage.tsx, build 경계 검사·fixture 지원·tests.

SQL capabilities published_asset_guard, published_run_guard, published_agent_admit, published_agent_read, published_agent_finish. 현재 publication RLS와 공개 대상·owner scope를 분리한다. 기존032 admission/claim/guard의 고정 운영 정책·원장 부분을 재사용하며 새 exact binding 분기만 추가한다. TrialExecutor는 asset_chat에서 개인 TrialRepository 대신 published run을 읽고 전용 finish를 사용한다. run_view의 asset_chat 결과는 own-context/current source guard를 통과한 sealed result만 제공한다. 대화 history에 개인시험이 나타나지 않는 기존 restrictive policy는 유지한다.

핵심 검증 예:
```python
assert requester_decision.status == 403
assert approved.publication_revision == 1
assert ordinary_user_run.asset_binding.version_id == approved.version_id
assert reattempt_same_send.run_id == first_run.run_id
assert unpublished_draft_run.status == 404
assert retired_execution_is_fenced
```

- [ ] 서버: 일반 USER general/RAG 실행·exact roles/messages/출처/정산, restricted 거부·자료거부/삭제/빈scope·stale publication/retire/CAS·중지/한도/취소/unknown 비용·재시작·owner 이력과 raw 권한.
- [ ] 브라우저: Builder 증적→요청→타인 승인→사용자 catalog→변수 실행→정확한 모의 결과·이력/취소→철회·접수유실 같은ID 복구, 기존 Builder/고정 승인 회귀.

## Task3 local·지속 기록

- [x] fixture harness 순차 실행, 포트 충돌 전 소유 서비스 중지. user/admin 분리 build와 admin 구현 user번들 누출 검사.
- [x] private600 backup→036/037 적용→기존47표 전행·36checksum 보존·신규표0행·재적용 무변화→세 서비스 HTTP200 복구. primary seed/reset/합성업무·유료 호출0.
- [x] 구현33/시험34·설계23·로그02·master15/DP11계획28·잔여11·AGENTS 갱신, 실패/미검증/실제파일·안전 증거와 다음 작업 기록.

## 수용 경계·후속

핵심 승인/반려/게시/공개대상/일반 USER 실행과 게시 철회가 이번 단위다. 전체 DP12·기관승인·상용 배포 완료는 아니다. 별도 승인 rollback·복잡 승인자 배정/부서·기간별 공개·다회차 memory·dynamic 즐겨찾기/구독/권한신청·추가 원문 증적 동의·semantic 품질·실제업무/제공자/Entra/UAT/운영 배포·다중모델/도구/Workflow는 후속이다. 기존 F완료수는 재산정하지 않는다.

## 2026-10-12 실행 결과

[[33 DP12 동적 Agent 승인 게시와 사용자 실행 구현 결과]] 참조. 승인/게시/일반 사용자 실행/철회 단위는 local mock 구현과 검증을 완료했다. 기존 체크리스트는 전체 경계 검증 목표를 보존하며 아직 검증하지 않은 native crash/조직 이동 등의 항목까지 일괄 완료 표시하지 않는다. 서버166 최신 별도집계·브라우저27 단일·build 및 local 이행은 [[34 DP12 동적 승인 공개 대상 실행과 정산 검증]]에 기록했다. 다음 별도 rollback 승인/이력 UX, 실제 제공자/Entra/UAT는 후속이다.
