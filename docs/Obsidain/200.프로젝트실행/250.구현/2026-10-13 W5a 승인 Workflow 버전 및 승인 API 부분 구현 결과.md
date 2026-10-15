---
title: W5a 승인 Workflow 버전 및 승인 API 부분 구현 결과
date: 2026-10-13
status: 부분 구현
stage: 200.프로젝트실행/250.구현
tags: [workflow, approval, immutable-version]
---
# W5a 승인 Workflow 버전 및 승인 API 부분 구현 결과

## 범위와 판정

사용자 진행 지시에 따라 [[100.프로젝트계획/30 승인 Workflow 실행과 업무 Agent 연결 상세 작업 계획|W5 계획]]의 첫 단계 중 서버 검증형 Workflow 정의 저장, 승인 요청/결정 API, 현재 승인 head 카탈로그를 구현했다. 이 작업은 실제 앱 코드와 disposable fixture PostgreSQL에서 검증한 local mock 단계다. 상용 배포나 기관 업무 수용이 아니다.

기존 사용자 A안·관리자 A안·승인 B안 결정은 변경하지 않았다. 047 migration만 추가했으며 기존 000~046 파일, 특히 040의 원본/체크섬은 수정하지 않았다.

## 구현 파일과 동작

- `src/backend/migrations/047_approved_workflow_versions.sql`: tenant별 Workflow·정의 버전·승인 head를 분리 저장한다. RLS FORCE, `ai_policy_executor` 제한 권한, owner 권한과 감사 정책을 둔다. 정의 revision과 승인 요청의 CAS revision을 분리해 승인 상태 변경으로 불변 정의 버전 번호가 바뀌지 않게 했다.
- `src/backend/app/workflows/approved_models.py`: 기존 typed strict DAG schema를 승인 등록에도 사용한다. input/read_tool/llm/validate/output의 설정, node/edge 크기, cycle·도달성·선행 참조, 임의 모델·prompt 설정을 검증한다.
- `src/backend/app/workflows/repository.py`, `routes.py`, `main.py`: canonical JSON SHA-256 저장, `/api/v1/admin/workflow-approvals` 제출/목록/결정/철회 API, `/api/v1/workflows/catalog`을 연결한다. 자산 및 Tool의 현재 승인·버전·공개 범위를 제출과 승인 시 재검사한다. 현재 실행 `/api/v1/workflows/run`은 승인 version ID 기반 요청 형식만 허용하며 runtime ledger가 준비되지 않아 409를 반환한다. 구형 client DAG도 실행되지 않고 409로 차단한다.
- `src/backend/tests/support.py`, `tests/test_workflow_approvals.py`, `tests/test_tool_persistent_execution.py`: 047 스키마 기대값, 승인 통합, 격리 범위, strict payload, 버전 불변성, W4 보존 검증을 보강했다.
- `src/frontend/src/WorkflowCanvasPage.tsx`, `src/frontend/tests/workflow-orchestration.spec.ts`: Workflow 실행이 이미 지원되는 것처럼 보이지 않게 상태 문구를 바꾸고 실행 버튼을 비활성화했다. DAG 구조 검증과 예시 시각화는 유지했다.

## 검증 결과

- 최종 W5a 관련 테스트 및 migration 검증: `20 passed` (workflow approval, strict schema, migrations). positive 경로에서 실제 게시 Agent 버전을 Workflow에 연결해 제출, 같은 요청 재생, 자기 승인 거부, 타 PADMIN 승인, 사용자 카탈로그 노출, 승인 후 정의 revision 불변/decision revision 증가를 확인했다.
- 최종 W4·W5 종합 관련 회귀: 73 passed in 73.61s. 불변 revision·decision CAS 분리 및 권한 수정 이후 실행한 결과다. 전체 backend suite 완료로 확대 해석하지 않는다.
- `npm run build:admin`: TypeScript 및 관리자 독립 번들 경계 검증 통과(37 modules, `boundary_verified: true`).
- Playwright `WF_01_workflow_canvas_page_view_and_dag_nodes`: 1 passed. 준비 중 안내 및 실행 버튼 비활성 상태 확인.
- 첫 Python 시스템 인터프리터 실행은 lockfile 종속성 `httpx2` 미설치로 테스트 수집에 실패했다. 프로젝트 `.venv/bin/python`으로 다시 실행해 위 결과를 얻었다.
- migration 검증 fixture에서 기존 migration 이력/체크섬과 기존 fingerprint를 보존하고 047 재적용 무변화를 확인했다. 모든 검증 DB는 disposable fixture다. primary DB에 047을 적용하지 않았다.

## 미완료 및 다음 순서

1. W5a의 reject/revoke/stale head, restricted member, Tool 참조 성공/회수, 동일 client UUID의 변경 body 거부를 추가 검증하고 runtime/code identity seal을 마무리한다.
2. 계획 Task2의 parent run/step checkpoint/lease/CAS/취소 원장을 신규 migration으로 구현한다. 승인 Workflow run은 현재 409이며 Tool 또는 LLM 자식이 실행되지 않는다.
3. published Agent child run을 기존 admission→Gateway→정산 흐름에 연결하고 불명·취소·재시작 시 재발사 방지와 현재 권한 재검사를 추가한다.
4. Task3에서 Workflow Canvas·업무 Agent 화면을 승인 version 선택, run 조회/취소, 안전한 node 상태로 연결하고 10개 업무 manifest를 하나씩 검증한다.

실제 provider/기관자료/Entra ID/UAT, 전체 기능명세서 완료, 운영 DB 적용·배포는 검증하지 않았다. 040 checksum 불일치에 대한 기존 안전 경계는 그대로 유지한다.
