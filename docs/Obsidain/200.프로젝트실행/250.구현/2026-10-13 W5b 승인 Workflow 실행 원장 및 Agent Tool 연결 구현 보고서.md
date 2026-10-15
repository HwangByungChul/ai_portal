---
title: W5b 승인 Workflow 실행 원장 및 Agent Tool 연결 구현 보고서
date: 2026-10-13
status: 실행 기반 구현 및 선별 검증 완료 · 업무 연결 잔여
stage: 200.프로젝트실행/250.구현
tags: [workflow, execution-ledger, approval, agent, tool]
---
# W5b 승인 Workflow 실행 원장 및 Agent Tool 연결 구현 보고서

## 요청과 판정

사용자의 계속 진행 승인에 따라 [[30 승인 Workflow 실행과 업무 Agent 연결 상세 작업 계획|계획30]]의 실행 원장 단위를 구현했다. 작업 중 상태 문의에 진행 상황을 안내하고 검증·기록까지 이어갔다. 이 보고서의 W5b는 계획30의 실행 원장 보완 단위이며, [[28 상세 수정 재검토 F1-F8 잔여 결함 보완 작업 계획서|계획28]]의 업무 Agent 10종 완료를 의미하지 않는다.

**실제 코드·API·PostgreSQL 원장·React 실행 화면은 구현했으며 disposable DB와 모의 provider/Tool로 검증했다.** 기존 primary DB에는 적용하지 않았고 운영 배포·기관 업무 수용·전체 명세 완료 상태가 아니다. 이전 [[2026-10-13 W5a 승인 Workflow 버전 및 승인 API 부분 구현 결과|W5a]]의 runtime409 설명은 당시 이력으로 보존한다. 실행 서비스와 현재 승인 버전이 준비된 시험 환경에서는 이번 코드로 실행202/재생200이 가능하다.

제품명 ‘생성형 AI 플랫폼’, 사용자 홈 A·관리 홈 A·승인 B 목록/상세 방향은 유지한다. 예시 DAG와 승인 버전 실행은 별도 구획으로 표시한다.

## 구현 내용

| 영역 | 실제 동작 | 주요 파일 |
|---|---|---|
| 승인 버전 | 실행 mode와 interpreter 코드 SHA-256 봉인, 불변 정의 보호, 타인 승인·반려 및 CAS/replay, 현재 공개 대상·Agent·Tool·문서 권한 재검사 | `migrations/048_workflow_execution_ledger.sql`, `app/workflows/identity.py`, `repository.py` |
| 부모 원장 | owner/tenant/client UUID/body hash, 사용자3·조직20 대기/실행 한도, parent run/step FORCE RLS, claim/worker token/lease/CAS와 안전 metadata | 같은 048, `repository.py` |
| Agent 자식 | 정확한 게시 asset/version/publication revision, SQL이 계산한 값 binding, admission과 child FK 원자 저장, 기존 ExecutionManager/Gateway/예산/정산 사용 | `app/workflows/bindings.py`, `repository.py`, `service.py` |
| Tool 자식 | 기존 Tool 서비스에 부모 capability repository 주입, admit/FK 원자 저장, dispatch/finish의 현재 부모·승인·취소 검사, 독립 Tool API로 bound receipt 구동 불가 | 같은 repository/service 및 048 wrapper |
| 실행·취소 | strict 순서 실행, 노드별 입출력 검사와 private checkpoint, 실패 시 후속 실행0, 부모 fence 먼저 commit한 뒤 자식 취소 전달 | `app/workflows/service.py`, 048 |
| 중단 처리 | lease60초·heartbeat10초·부모 최대1200초·Agent 노드180초, 중단 부모 interrupted, 발사한 Tool unknown, 완료 checkpoint 보존, 자동 재발사 없음 | 같은 service 및 048 recovery/read |
| HTTP 조립 | version UUID/request UUID/inputs만 실행202 또는 재생200, 본인 조회·CAS 취소·CSRF, 32KB 요청 상한, 서비스 startup recovery/close | `app/workflows/routes.py`, `app/main.py`, `app/errors.py` |
| React | 승인 버전/모드 선택, 실제 tenant·CSRF 요청, polling·취소·단계 상태/자식 참조·허용 최종 결과, 수신 실패 재시도 UUID 보존 | `src/frontend/src/WorkflowCanvasPage.tsx`, `packages/api-contract/src/types.ts`, `api.ts` |

파일 경로의 `app/`·`migrations/`는 `src/backend/` 기준이다. public 응답에는 원본 inputs, worker token, private checkpoint 결과, context_snapshot을 포함하지 않는다. 완료 결과도 조회 시 현재 승인/자료 권한·출력 정책을 다시 확인한다. literal binding이 system/developer 역할에 포함될 때도 구성된 모든 메시지의 입력 정책을 child admission 전에 검사한다.

부모가 무료 orchestration 상태라고 해서 LLM 비용이 사라지는 것은 아니다. 각 LLM 자식은 기존 호출 원장/정산을 사용한다. 동일 요청의 정상 재생 시험에서 provider1·Tool1·settled call1·parent1을 확인했다. 취소 및 정책 차단 이후 새로운 결과를 공개하지 않는 경계와 이미 발사된 호출의 기존 정산 흐름을 유지한다.

## 실패 발견과 수정

1. 신규 SQL 구문에서 CASE 표현 괄호가 누락되어 migration 시험이 실패했다. 수정 후 신규 이행/관련 검증을 통과했다.
2. browser case reset이 새 Workflow FK 때문에 실패했다. `src/backend/scripts/portal_test_control.py`의 소유 임시 DB 전용 명시적 초기화 목록에 Workflow/Tool 표를 추가했다. primary 배제/소유 marker 검사와 CASCADE 없는 초기화를 유지했다.
3. 출력 PII 차단을 실제 Agent 자식에 적용하자 기존 `security.execution_fail`이 새 safe code를 허용하지 않아 자식이 running에 남았다. 과거 SQL을 수정하지 않고 048 wrapper로 제한된 새 코드만 추가했다. 기존 코드와 NULL 처리는 과거 함수에 위임하고 worker/epoch fence를 유지했다. mask/block 둘 다 재검증했다.
4. 이전 완료 실행 후 다음 요청의 receipt 수신 실패를 재시도할 때 새 UUID가 생성될 수 있었다. POST 전에 이전 run 표시를 비우고 동일 version/input의 미수신 요청 UUID를 유지했다. WF02에서 신규 요청은 새 UUID, 실패 후 재시도는 같은 UUID임을 확인했다.
5. admission과 claim 사이 승인 회수 시 부모가 accepted에 남을 수 있었다. 미claim 본인 부모의 안전한 fail을 허용하고 running 부모의 worker/session fence는 유지했다. 회수 전에 자식 호출0·부모 blocked를 확인했다. 미claim 부모의1200초 만료도 조회 시 interrupted/미실행 step skipped로 봉인한다.

## 검증과 증거

증거 폴더: `200.프로젝트실행/260.테스트/evidence/W5-Workflow-20261013/`.

| 검증 | 결과 | 해석 |
|---|---|---|
| 관련 넓은 서버 회귀 | 157 passed / 229.02초 | Workflow·Tool·Agent 승인/게시/이력·schema·migration 등 선별 suite. 마지막 시작 전 경계 보완 이전 실행 |
| 최종 서버 재검증 | 40 passed / 55.47초 | 마지막 보완 포함 runtime·migration·승인·strict schema·기존 migration 검증. 157과 중복되므로 합산하지 않음 |
| Node22.23.1 분리 build | user26/admin37, boundary_verified=true | TypeScript와 사용자/관리자 번들 코드 경계. preliminary Node24 build도 통과했으나 최종은 지정 Node22 기준 |
| WF01 browser | passed | 실제 임시 인증/API의 catalog200·빈 목록 실행 비활성·tenant/CSRF DAG validate200 |
| WF02 browser | passed | 실제 React 화면의 HTTP 계약 대역. version-only POST·poll 완료 표시·receipt 실패 후 같은 UUID 재시도. 실제 DB runtime 성공 증거는 서버 시험 |
| 048 단독 이행 | passed | 이전62표 기존행/열 및48개 DB migration checksum 보존, 결과64표/49migration/166security함수/34보호표, NULL legacy seal 유지, 재적용 변경0 |
| 이전 source baseline | 000~046의47파일 변경0 | W4 보관 SHA와 대조. 047은 신규 이행 시험에서 이전 DB checksum 보존 |
| browser 정리 | passed | API pool 연결0, fixture DB·합성 자격증명·소유 source store 제거 |

최종 서버 명령:

```sh
src/backend/.venv/bin/python -m pytest src/backend/tests/test_workflow_runtime.py src/backend/tests/test_workflow_runtime_migration.py src/backend/tests/test_workflow_approvals.py src/backend/tests/test_workflow_approved_schema.py src/backend/tests/test_migrations.py -q -x
```

브라우저는 DB 시험과 순차 실행했다. `PATH`에 프로젝트 Node22.23.1 경로를 먼저 두고 frontend에서 `npm run build`, `npm run test:e2e -- tests/workflow-orchestration.spec.ts`를 실행했다. 회귀의 정확한 범위/상태는 `selected-verification-summary.json`, 각 source SHA는 `source-files.json`/`source-migration-hashes.json`, 이행 증거는 `migration-preservation.json`, browser case는 `browser-contract-results.json`, 정리는 `browser-cleanup.json`에 저장했다. 계정 비밀번호·토큰·DSN·질문 원문·답변은 증거에 저장하지 않았다.

통합 시험은 실제 PostgreSQL의 승인, 동시 동일요청, body 충돌, 타인조회 차단, 철회 후 답변 숨김, child admission/audit 실패 원자 rollback, Tool/Agent 취소·중단, lease/recovery와 모의 provider 호출 수를 확인한다. 전체 backend/browser suite·실제 provider/기관자료 업무 품질·다중 폭 시각 검수·Obsidian 앱 렌더는 이번 단위에서 검증하지 않았다.

## 미완료와 다음 작업 순서

1. **업무 Agent10종 연결:** 현재 use-case API는 여전히 execution_ready=false다. 조직별 실제 승인 Workflow head/manifest를 연결하고 역할·필수 Tool·전문가 확인 조건·입력/출처·업무별 성공/불충분/차단 시험을 하나씩 수행한다. 임의 UUID/더미 승인으로 준비 상태를 해제하지 않는다.
2. **관리 B 승인 화면:** Workflow/Tool 제출·요청 목록·정확한 버전 상세·타인 승인/반려·철회 API는 있으나 해당 React 편집/검토 UI는 남아 있다. 현재 Canvas의 실행 selector는 승인 요청 화면을 대신하지 않는다.
3. **복구 운영 수용:** 완료 checkpoint는 보존·조회하며 unknown/interrupted는 자동 재발사하지 않는다. 중단 run의 수동 확인/재개 API 및 UI, 다중 worker/분산 복구·모든 crash 경계·실시간 제한값 부하 시험은 미완료다. 조회하지 않는 만료 accepted parent의 백그라운드 정리도 후속이다.
4. **계획28 W6→W9:** 실제 관측·집계 수용, 승인 유형 진입, 지원 UI 동작과 화면 일치, 통합 회귀를 순차 진행한다. 이번 좁은 회귀를 전체 기능 완료 판정으로 대체하지 않는다.
5. **기존 DB 이행/외부 수용:** primary040 원본 바이트/이력 SHA 불일치가 해결되지 않아041~048 미적용이다. 이력 수정·checksum bypass·primary seed·유료 호출은 하지 않았다. 기관 connector/실제 RAG Workflow 종합 수용·Entra ID·운영 배포는 별도다.

관련 결정과 진행은 [[23 포털 UI UX 확정과 사이트 분리 검토]], [[02 포털 UI UX 작업 기록]]에도 기록했다. 기존 working tree의 다른 추가개발 파일을 이번 단위의 변경으로 묶거나 임의 commit/서비스 배포하지 않았다.
