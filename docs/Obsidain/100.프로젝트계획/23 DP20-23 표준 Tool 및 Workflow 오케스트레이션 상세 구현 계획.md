---
title: DP20-23 표준 Tool 및 Workflow 오케스트레이션 상세 구현 계획
created: 2026-10-13
status: in_progress
purpose: 표준 도구(Tool/MCP) 레지스트리, 게이트웨이 및 다단계 DAG Workflow 실행 엔진 구현 계획
tags: [ai-platform, tool-gateway, mcp, workflow, dag, orchestration, dp20, dp21, dp22, dp23]
---
# DP20-23 표준 Tool 및 Workflow 오케스트레이션 상세 구현 계획
본 계획서는 전체 기능명세서 잔여 기능 개발 실행 계획([[15 전체 기능명세서 잔여 기능 개발 실행 계획]])의 순서 9-10에 따라, 표준 외부 API/읽기 도구(Tool/MCP) Gateway(DP-20/21/22) 및 다단계 DAG 기반 Workflow 오케스트레이션 실행 엔진과 시각화 Canvas(DP-23)를 구현하기 위한 상세 계획입니다.

## 1. 배경 및 핵심 목표
- **안전한 읽기 Tool / MCP Gateway (DP-20/21/22)**:
  - 모델이나 에이전트가 호출할 수 있는 도구를 서버 Allowlist로 통제하고 인자 스키마(`JSONSchema`)를 엄격히 검증합니다.
  - Shell 명령이나 임의 URL 호출을 원천 차단하며, 사전 승인된 커넥터(합성 상품 조회, 규정 쿼리, 데이터 가상화 읽기 뷰)만 허용합니다.
  - 동일한 `client_operation_id` 재전송 시 멱등성을 보장하고, 타임아웃 및 자격증명(`credential_ref`) 은닉을 유지합니다.
- **다단계 Workflow 오케스트레이션 엔진 (DP-23)**:
  - 선형 또는 분기형 DAG(Directed Acyclic Graph) 구조의 워크플로우 파이프라인을 지원합니다.
  - 노드 유형: `input`(사용자 입력) → `read_tool`(도구 호출) → `llm`(AI 모델 추론) → `validate`(결과 검증) → `output`(최종 출력).
  - 순환(Cycle) 참조 및 연결되지 않은 고립 노드를 사전 검증(`WORKFLOW_CYCLE_DETECTED`, `WORKFLOW_GRAPH_INVALID`) 단계에서 즉시 차단합니다.
  - 각 단계의 실행 상태와 중간 산출물(`NodeResult`)을 스냅샷으로 보존하며, 중간 취소 요청 시 즉시 다음 노드 실행을 중단합니다.
- **Workflow 시각화 Canvas (프론트엔드)**:
  - 관리자/개발자가 워크플로우의 노드와 연결선(Edge)을 확인하고, 실시간 단계별 실행 흐름(성공/진행/실패 신호등)을 확인할 수 있는 직관적인 콘솔을 제공합니다.

## 2. 인터페이스 및 계약 설계
- **Tool 인터페이스 DTO (`ToolDefinition`)**:
  - `tool_id`: 도구 식별자 (예: `financial_product_lookup`, `kb_rule_query`, `data_view_reader`)
  - `name`: 표시 명칭
  - `description`: LLM/사용자 설명
  - `arg_schema`: 입력 인자 검증 스키마
  - `timeout_seconds`: 최대 실행 시간
  - `enabled`: 활성화 여부
- **Workflow 인터페이스 DTO (`WorkflowDefinition`)**:
  - `workflow_id`: 식별자
  - `name`: 워크플로우 명칭
  - `nodes`: `list[WorkflowNode]` (`node_id`, `node_type`, `config`, `dependencies`)
  - `edges`: `list[WorkflowEdge]` (`source_node`, `target_node`)
  - `max_steps`: 최대 허용 단계 (기본 20)
- **API 엔드포인트 계약**:
  - `GET /api/v1/tools`: 등록된 활성 표준 도구 목록 조회
  - `POST /api/v1/tools/{tool_id}/invoke`: 지정된 도구 안전 실행 (CSRF 검증)
  - `POST /api/v1/workflows/validate`: 워크플로우 DAG 순환 여부 및 유효성 검증
  - `POST /api/v1/workflows/run`: 다단계 워크플로우 실행 및 단계별 체크포인트 반환
- **수용 검증 케이스**:
  - `C01`: 등록된 승인 도구 정상 호출 및 결과 스키마 반환
  - `C02`: 미등록 도구 호출 시 404 및 인자 유효성 위반 시 422 거부
  - `C03`: 순환(Cycle)이 존재하는 워크플로우 검증 시 `WORKFLOW_CYCLE_DETECTED` 거부
  - `C04`: 다단계 파이프라인(`input` → `read_tool` → `llm` → `output`) 순차 실행 및 스냅샷 보존
  - `C05`: 프론트엔드 분리 빌드(`build:user`, `build:admin`) 통과 및 화면 렌더링 확인

## 3. 작업 대상 파일 목록
- **백엔드**:
  - 생성: `src/backend/app/tools/registry.py` (도구 레지스트리, 승인 도구 정의, 실행 핸들러)
  - 생성: `src/backend/app/tools/routes.py` (도구 조회 및 호출 API 라우터)
  - 생성: `src/backend/app/workflows/models.py` (워크플로우 DAG 노드/엣지 DTO 및 순환 검출기)
  - 생성: `src/backend/app/workflows/runner.py` (다단계 워크플로우 오케스트레이션 실행기)
  - 생성: `src/backend/app/workflows/routes.py` (워크플로우 검증 및 실행 API 라우터)
  - 수정: `src/backend/app/main.py` (도구 및 워크플로우 라우터 등록)
  - 생성: `src/backend/tests/test_dp20_dp23_acceptance.py` (도구 안전 호출 및 워크플로우 DAG 수용 테스트)
- **프론트엔드**:
  - 생성: `src/frontend/src/WorkflowCanvasPage.tsx` (다단계 워크플로우 파이프라인 시각화 및 실행 콘솔)
  - 수정: `src/frontend/apps/admin-web/src/App.tsx` (관리자 네비게이션에 워크플로우 오케스트레이션 메뉴 등록)
  - 생성: `src/frontend/tests/workflow-orchestration.spec.ts` (E2E 화면 검증)
- **문서**:
  - 기록: `docs/Obsidain/400.프로젝트관리/02 포털 UI UX 작업 기록.md`

## 4. 단계별 실행 계획
1. **1단계**: 표준 도구 레지스트리(`app/tools/registry.py`, `routes.py`) 구현
2. **2단계**: 다단계 DAG 워크플로우 모델 및 순환 검증기(`app/workflows/models.py`) 구현
3. **3단계**: 워크플로우 오케스트레이션 실행기(`app/workflows/runner.py`, `routes.py`) 구현
4. **4단계**: 백엔드 수용 테스트 `test_dp20_dp23_acceptance.py` 작성 및 C01~C04 통과 검증
5. **5단계**: 프론트엔드 `WorkflowCanvasPage.tsx` 시각화 컴포넌트 구현 및 관리자 메뉴 연결
6. **6단계**: 프론트엔드 분리 빌드(`build:user`, `build:admin`) 및 전체 회귀 검증
7. **7단계**: Obsidian 작업 기록 및 결과 보고
