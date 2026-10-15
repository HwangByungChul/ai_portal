---
title: 시각적 블록 조립형 UI Studio 상세 구현 계획
created: 2026-10-15
status: planned
purpose: 제안 시안(4.4-03) 수준의 완전한 드래그 앤 드롭 노드 기반 Workflow UI Studio 개발
tags: [ai-platform, workflow, visual-studio, react-flow, drag-and-drop]
---

# 시각적 블록 조립형 UI Studio 상세 구현 계획
본 계획서는 제안 시안(`4.4-03_Workflow_Canvas.png`)에 부합하는 시각적 블록 조립형(Drag & Drop) UI Studio의 개발 아키텍처, 컴포넌트 설계, 백엔드 연계 및 단계별 실행 계획을 정의한다.

## 1. 개요 및 추진 목표
- **추진 배경**: 현재 AI 플랫폼 내 워크플로우 화면은 고정 카드 나열 방식의 시각화 프로토타입 단계에 머물러 있어, 직관적인 노드 조립, 속성 설정, 엣지 연결 및 실행 모니터링이 가능한 완전한 비주얼 에디터 도입이 요구됨.
- **개발 목표**:
- 제안 시안(4.4-03)과 일치하는 3-Pane 비주얼 캔버스 레이아웃 구현 (컴포넌트 라이브러리 + 중앙 캔버스 + 노드 인스펙터 + 상단 7단계 위저드 바).
- `@xyflow/react`(React Flow v12) 기반의 안정적인 노드/엣지 드래그 앤 드롭 및 캔버스 상호작용(Pan/Zoom/Minimap/Align).
- 기존 백엔드 워크플로우 DAG 엔진([models.py](file:///Users/jwpios/antigravity/202610_AI%20플랫폼/src/backend/app/workflows/models.py)) 및 API와의 무결한 데이터 매핑 및 실시간 실행 상태 시각화.

## 2. 화면 구성 및 UI/UX 아키텍처 (3-Pane 구조)
- **상단 위저드 및 컨트롤 바**:
- 7단계 위저드 단계 표시: 1.기본정보 → 2.데이터소스 → 3.노드배치 → 4.파라미터설정 → 5.테스트/디버그 → 6.검증/평가 → 7.배포/게시
- 액션 도구모음: 실행(Run), 유효성 검증(Validate), 자동 정렬(Auto-layout), 미니맵 토글, 확대/축소(Zoom In/Out), 전체화면, 저장(Save)
- **좌측 패널 (Component Library / Palette)**:
- 7대 카테고리 아코디언: 입력(Trigger/Input), 프롬프트(Prompt), 모델(LLM), 지식/검색(Knowledge/RAG), 도구(Tool), 로직(Logic/Branch), 출력(Output/Response)
- 드래그 앤 드롭 지원: 팔레트의 노드 아이템을 캔버스 영역으로 Drag & Drop 시 마우스 좌표에 신규 노드 즉시 생성
- **중앙 패널 (Interactive Flow Canvas)**:
- `@xyflow/react` 기반 무한 캔버스 (Grid Background, Controls, MiniMap 지원)
- 커스텀 노드 7종: 헤더 컬러 코딩, 입출력 포트(Handle), 노드 상태 배지(대기/실행/완료/에러), 빠른 액션(복제, 삭제)
- 커스텀 엣지: Bezier / SmoothStep 곡선, 엣지 선택 및 삭제, 데이터 흐름 애니메이션(실행 중 점선 흐름)
- 순환 참조(Cycle) 감지 및 유효하지 않은 포트 간 연결 차단
- **우측 패널 (Node Properties Inspector)**:
- 선택된 노드의 타입별 상세 파라미터 동적 폼 바인딩
- 입력 매핑, 프롬프트 템플릿(변수 치환 지원), 모델 하이퍼파라미터(온도, 토큰 등), Tool 연동 인자 설정
- 노드 단독 테스트(Unit Run) 및 직전 실행 결과/원문 로그 조회 탭

## 3. 데이터 모델 및 백엔드 연동 계약
- **프론트엔드-백엔드 스키마 매핑 (Adapter 계층)**:
- 프론트엔드 React Flow 상태: `nodes: Node[]`, `edges: Edge[]` (위치, 선택 여부, UI 렌더링 상태 포함)
- 백엔드 DAG 정의: `WorkflowDefinition` (id, name, version, nodes, edges)
- `WorkflowNode`: `node_id`, `node_type`, `name`, `config: dict`, `position: {"x": float, "y": float}`
- `WorkflowEdge`: `edge_id`, `source_node_id`, `target_node_id`, `source_handle`, `target_handle`
- **검증 및 안전 레일**:
- 클라이언트 사전 검증: 시작 노드(Trigger) 유무, 미연결 고립 노드 검출, DAG 순환 참조(Cycle) 방지 Topological Sort 적용
- 백엔드 실행 계약: `POST /api/v1/workflows` (저장/갱신), `POST /api/v1/workflows/{id}/run` (실행), `GET /api/v1/workflows/{id}/runs/{run_id}` (상태 폴링 및 결과 조회)
- 실행 이벤트 수신 시 각 노드별 상태(`pending`, `running`, `completed`, `failed`)를 캔버스 노드에 실시간 반영

## 4. 단계별 세부 작업 계획 (Task Breakdown)
- **Task 1: 환경 설정 및 기본 캔버스 레이아웃 구축**
- `src/frontend` 내 `@xyflow/react` 의존성 설치 및 React 19 / Vite 8 빌드 호환성 검증
- 3-Pane 레이아웃 쉘 및 상단 컨트롤/위저드 바 구조화 (`WorkflowStudioPage.tsx` 또는 `WorkflowCanvasPage.tsx` 확장)
- 테마 시스템(Dark/Light)과 일치하는 커스텀 CSS 스타일링 작성
- **Task 2: 드래그 앤 드롭 팔레트 및 커스텀 노드 7종 구현**
- 좌측 컴포넌트 라이브러리 드래그 앤 드롭 핸들러(HTML5 D&D API) 연동
- 노드 타입 7종(Trigger, Prompt, Model, Knowledge, Tool, Branch, Response)의 커스텀 React Flow 노드 컴포넌트 제작
- 노드 포트(Handle) 및 연결 규칙(Connection Validation) 정의
- **Task 3: 속성 인스펙터 패널 및 노드 설정 바인딩**
- 선택된 노드의 `config` 객체를 실시간 갱신하는 속성 편집기 패널 구현
- 변수 치환 프롬프트 에디터 및 모델 파라미터 슬라이더/입력 필드 연동
- 노드 복제, 삭제 및 캔버스 자동 정렬(Dagre / Elk 알고리즘 기반) 지원
- **Task 4: 백엔드 DAG API 연동 및 실행 모니터링 시각화**
- React Flow Graph ↔ 백엔드 `WorkflowDefinition` 간 양방향 변환 유틸리티 작성
- 워크플로우 저장/불러오기 API 연동
- 워크플로우 실행 트리거 및 노드별 실행 상태 펄스 애니메이션/결과 출력 뷰어 연동
- **Task 5: 빌드, 단위 시험 및 브라우저 검증**
- `npm run build:user` 및 `npm run build:admin` 코드 경계 및 타입 검사 통과
- 노드 D&D, 엣지 연결, 속성 수정, 저장 및 실행 흐름 브라우저 기능 검증
- 반응형 뷰포트(1440px, 1024px) 레이아웃 및 성능 검증

## 5. 검증 기준 및 완료 조건
- [ ] `@xyflow/react` 설치 후 빌드(`npm run build:user`, `npm run build:admin`) 정상 통과.
- [ ] 컴포넌트 팔레트에서 캔버스로 노드 Drag & Drop 시 올바른 위치에 커스텀 노드 생성.
- [ ] 노드 간 핸들 드래그를 통한 엣지 연결 및 순환 참조 방지 유효성 검사 작동.
- [ ] 노드 클릭 시 우측 인스펙터에 파라미터가 정상 표출되고 수정 내역이 그래프 상태에 즉시 반영.
- [ ] 그래프 데이터가 백엔드 `WorkflowDefinition` 스키마로 정확히 변환되어 저장/로드/실행 가능.
