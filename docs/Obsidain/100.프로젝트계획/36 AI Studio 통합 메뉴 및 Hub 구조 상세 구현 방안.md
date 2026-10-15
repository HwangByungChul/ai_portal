---
title: AI Studio 통합 메뉴 및 Hub 구조 상세 구현 방안
created: 2026-10-15
status: planned
purpose: Agent Builder와 Workflow Canvas의 단일 Hub 통합 및 메뉴 체계 개편
tags: [ai-platform, ai-studio, menu-integration, agent-builder, workflow-canvas]
---

# AI Studio 통합 메뉴 및 Hub 구조 상세 구현 방안
본 문서는 관리자 콘솔 내 분산되어 있던 단일 Agent 제작(Agent Builder)과 다단계 업무 파이프라인 조립(Workflow Canvas)을 단일 진입점인 `AI Studio` Hub로 통합하여 사용자 인지 혼선을 해소하고 유기적인 제작 흐름을 제공하기 위한 상세 구현 방안을 정의한다.

## 1. 개요 및 추진 배경
- **현상 및 문제점**:
- 현재 관리자 사이드바에 `Agent 관리`, `AI 자산 관리`, `Agent Builder`, `Workflow 오케스트레이션`이 서로 별개 메뉴로 나열되어 있음.
- 사용자는 "에이전트 제작"과 "워크플로우 조립" 간의 관계(부품과 완성품 조립 관계)를 직관적으로 파악하기 어렵고, 어디서 시작해야 하는지 혼선이 발생함.
- **추진 목표**:
- 사이드바 메뉴를 직관적인 **`AI Studio (제작)`** 단일 대분류로 통합.
- AI Studio 진입 시 상단 서브 탭을 통해 **[ 🤖 단일 Agent 제작 (Builder) ]**과 **[ ⚡ 다단계 Workflow 조립 (Canvas) ]**을 자유롭게 전환할 수 있는 통합 Hub UI 구축.
- 기존 URL 경로(`/manage/admin/builder`, `/manage/admin/workflows`) 및 북마크에 대한 하위 호환성 100% 보장.

## 2. 통합 UI/UX 아키텍처 및 화면 구조
- **사이드바 메뉴 개편 (관리자 콘솔)**:
- 기존: `Agent 관리`, `AI 자산 관리`, `Agent Builder`, `Workflow 오케스트레이션` 분산
- 변경:
  - `AI Studio` (통합 제작 허브 — 상단 탭으로 Agent와 Workflow 제공)
  - `AI 모델 관리` (제공자 및 모델 레지스트리)
  - `문서 관리` (RAG 지식베이스 데이터 소스)
  - `보호 정책` (가드레일 및 보안)
  - `승인·검증` (결재 및 배포 심사)
  - `운영 관리` (사용자 관리, 조직 사용량, 답변 평가, 운영 현황)
- **AI Studio Hub 컨테이너 구조 (`AIStudioHubPage.tsx`)**:
- **상단 글로벌 서브 탭 바**:
  - `[ 🤖 단일 Agent 빌더 ]`: 단일 챗봇 페르소나, 지시문, 모델 바인딩 및 Trial 시험
  - `[ ⚡ 다단계 Workflow 캔버스 ]`: 3-Pane 드래그 앤 드롭 캔버스, 기간계 Tool 및 다단계 로직 조립
- **상태 및 라우팅 제어**:
  - URL 경로: `/manage/admin/studio` (기본)
  - 쿼리 파라미터 또는 탭 상태: `?tab=agent` | `?tab=workflow`
  - `/manage/admin/builder` 접근 시 `?tab=agent`로 자동 정렬 매핑
  - `/manage/admin/workflows` 접근 시 `?tab=workflow`로 자동 정렬 매핑
- **상호 연계 안내 배너 (Contextual Bridge)**:
  - Agent Builder 상단: *"제작한 에이전트를 기간계 시스템(API)과 결합하여 다단계 자동화 업무를 만들고 싶으신가요? → [Workflow 캔버스로 조립하기]"* 버튼 배치.
  - Workflow Studio 팔레트 상단: *"새로운 전담 에이전트가 필요하신가요? → [단일 Agent 빌더에서 추가]"* 버튼 배치.

## 3. 세부 컴포넌트 설계 및 코드 수정 계획
- **1) 신규 통합 Hub 컴포넌트: `src/frontend/src/AIStudioHubPage.tsx`**:
- `AssetsPage(builder 모드)`와 `WorkflowCanvasPage`를 하위 뷰로 수용.
- `activeTab` 상태 및 브라우저 히스토리(`history.pushState`) 동기화.
- 테마 시스템 및 포털 공통 CSS 스타일 규격 준수.
- **2) 관리자 앱 라우팅 수정: `src/frontend/apps/admin-web/src/App.tsx`**:
- `paths` 객체에 `studio: '/manage/admin/studio'` 추가 및 메뉴 목록 정리.
- `labels.studio = 'AI Studio (제작)'`.
- 기존 `builder` 및 `workflows` 뷰 요청 시 `studio` 뷰의 해당 탭으로 자연스럽게 안내.
- **3) 사용자/관리자 빌드 경계 검증 유지**:
- `apps/user-web`, `apps/admin-web`, `packages/api-contract`, `packages/ui`의 코드 경계 및 빌드 스크립트 무결성 보존.

## 4. 단계별 세부 작업 계획 (Task Breakdown)
- **Task 1: 통합 Hub 컴포넌트 `AIStudioHubPage.tsx` 제작**
- 서브 탭 헤더 및 뷰 전환 쉘 구조화
- 탭 전환 시 URL 쿼리 파라미터 동기화 및 뒤로가기/앞으로가기(PopState) 지원
- **Task 2: 관리자 앱 사이드바 및 네비게이션 라우팅 개편**
- `apps/admin-web/src/App.tsx` 내 메뉴 항목 통합 및 라우트 리다이렉트 처리
- 하위 호환성을 위해 기존 `/builder`, `/workflows` 경로 진입 시 해당 탭 자동 활성화
- **Task 3: 안내 브릿지 배너 및 연계 액션 버튼 추가**
- Agent Builder와 Workflow Canvas 간 원클릭 상호 이동 버튼 연동
- **Task 4: 포털 빌드 및 브라우저 검증**
- `npm run build:admin` 및 `npm run build:user` 빌드 경계 검증
- 실제 브라우저 포털에서 사이드바 `AI Studio` 클릭 시 탭 전환 및 각 캔버스/빌더 렌더링 검수

## 5. 완료 기준 (Definition of Done)
- [ ] 관리자 사이드바에 `AI Studio` 메뉴가 정상 노출되고, 분산된 메뉴가 깔끔하게 정돈됨.
- [ ] AI Studio 진입 시 상단 탭을 통해 Agent Builder와 Workflow Canvas를 즉시 전환 가능.
- [ ] 기존 북마크나 URL(`/manage/admin/builder`, `/manage/admin/workflows`)로 진입해도 올바른 탭으로 자동 연결됨.
- [ ] 포털 전체 빌드(`npm run build`) 통과 및 브라우저 검증 증적 보존.
