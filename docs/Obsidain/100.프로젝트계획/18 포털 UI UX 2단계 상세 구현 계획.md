---
title: 포털 UI UX 2단계 상세 구현 계획
date: 2026-10-12
status: 계획작성
stage: 100.프로젝트계획
tags: [ai-platform, ui-ux, implementation-plan, admin-home, admin-approvals]
---

# 포털 UI UX 2단계 상세 구현 계획 (관리 A 홈 및 B 승인 패널 정렬)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 관리 A안 운영 현황형 홈([AdminHomePage.tsx](file:///Users/jwpios/antigravity/202610_AI%20%ED%94%8C%EB%9E%AB%ED%8F%BC/src/frontend/src/AdminHomePage.tsx))과 관리 B안 승인·검증 패널([ApprovalsPage.tsx](file:///Users/jwpios/antigravity/202610_AI%20%ED%94%8C%EB%9E%AB%ED%8F%BC/src/frontend/src/ApprovalsPage.tsx))을 실제 React 관리자 앱에 정렬 구현한다.

**Architecture:** 관리 A 홈에 조회 기준 안내 바, 상단 운영 알림, 4대 핵심 지표 카드, 호출 추이 시계열 및 서비스 운영 상태 구획을 복원하고, 관리 B 승인 패널의 2열(목록 320px + 상세) 구조와 3개 탭(검증 결과 / 변경 사항 / 처리 이력)을 일관되게 정렬하며 실제 API 계약(정산 금액 안전 보존, 타인 승인, CAS, RLS)을 철저히 유지한다.

**Tech Stack:** React 18, TypeScript, Vanilla CSS (Design Tokens), Vite, Node.js

## Global Constraints
- All responses and artifacts must be written in Korean.
- 마크다운 문법: 글머리 기호는 단일 하이픈(-)과 공백을 사용하며, 각 헤더 뒤에는 빈 행을 두지 않는다.
- 정산 지표의 예약 금액(`reserved_krw`)과 불명 사용량(`unknown_count`)은 안전 계약이므로 임의 삭제하거나 0원으로 처리하지 않고 보존한다.
- 타인 PADMIN 승인 권한 검사, CAS 버전 일치, 자료 ACL 및 RLS 격리 계약을 반드시 유지한다.
- 두 앱의 독립 빌드(`npm run build:user`, `npm run build:admin`) 및 코드 경계 검사를 통과해야 한다.

---

### Task 1: 관리자 홈 및 승인 패널 전용 CSS 확장

**Files:**
- Modify: `src/frontend/packages/ui/src/portal.css`

**Interfaces:**
- Produces: `.admin-overview-header`, `.admin-metrics-grid`, `.admin-trend-card`, `.admin-service-status`, `.approval-v2-container`, `.approval-tabs-pill`

- [ ] **Step 1: 관리 A 홈 지표 카드, 추이 바, 서비스 상태 CSS 정의 작성**
[portal.css](file:///Users/jwpios/antigravity/202610_AI%20%ED%94%8C%EB%9E%AB%ED%8F%BC/src/frontend/packages/ui/src/portal.css)에 4대 핵심 지표 카드 룩앤필, 시계열 호출 추이 막대 그래프 스타일, 서비스 상태 신호등 뱃지 스타일을 추가한다.

- [ ] **Step 2: 관리 B 승인 패널 2열 목록-상세 및 3탭 스타일 보강**
좌측 요청 카드 선택 상태 및 상세 검증/변경/이력 탭 전용 스타일을 보강한다.

- [ ] **Step 3: 관리자 웹 빌드 영향 확인**
Run: `export PATH="$HOME/.nvm/versions/node/v22.23.1/bin:$PATH" && npm --prefix src/frontend run build:admin`
Expected: CSS 번들링 및 빌드 통과

---

### Task 2: 관리 A 홈 지표 및 구조 정렬 ([AdminHomePage.tsx](file:///Users/jwpios/antigravity/202610_AI%20%ED%94%8C%EB%9E%AB%ED%8F%BC/src/frontend/src/AdminHomePage.tsx))

**Files:**
- Modify: `src/frontend/src/AdminHomePage.tsx`

**Interfaces:**
- Consumes: `tenant`, `onApprovals`, `onUsage`, `onAssets`, `onMembers`, `useRemote('/admin/usage')`, `useRemote('/admin/agent-deployments')`
- Produces: 관리 A안 운영 현황 홈 컴포넌트

- [ ] **Step 1: 조회 기준 안내 및 운영 알림 배너 구현**
집계 기간, 실행 모드, 집계 기준 시각과 함께 호출 제한 알림(`blocked-note`)을 상단에 정렬한다.

- [ ] **Step 2: 4대 핵심 지표 카드 정렬**
AI 호출 건수(`call_count`), 추정 사용 금액(`estimated_accounted_krw` + 예약금액 `reserved_krw`), 승인 대기 요청 수, 불명 사용량/자산 상태를 4열 카드로 배치한다.

- [ ] **Step 3: 중간 영역 (호출 추이 + 우선 승인 대기 요청) 구현**
좌측에 주간 AI 호출 추이 시계열 차트 영역, 우측에 최근 대기 중인 배포 요청 목록 테이블 및 승인 상세 딥링크 버튼을 배치한다.

- [ ] **Step 4: 하단 영역 (서비스 운영 상태 + 관리 바로가기) 구현**
공통 AI 플랫폼 서비스 상태(API 게이트웨이, 서빙 모델, DB) 및 관리 업무 퀵 링크를 배치한다.

- [ ] **Step 5: 정적 타입 검증 및 관리자 빌드 확인**
Run: `export PATH="$HOME/.nvm/versions/node/v22.23.1/bin:$PATH" && npm --prefix src/frontend run build:admin`
Expected: 빌드 성공

---

### Task 3: 관리 B 승인 패널 UI 및 탭 구조 일관화 ([ApprovalsPage.tsx](file:///Users/jwpios/antigravity/202610_AI%20%ED%94%8C%EB%9E%AB%ED%8F%BC/src/frontend/src/ApprovalsPage.tsx))

**Files:**
- Modify: `src/frontend/src/ApprovalsPage.tsx`

**Interfaces:**
- Consumes: `tenant`, `user`, `initialId`, `/admin/agent-deployments`
- Produces: B안 목록-상세 및 3탭 일관화 승인 화면

- [ ] **Step 1: 상단 요청 유형 탭 및 검색 바 레이아웃 정돈**
'운영 설정 요청', 'Builder 시험 증적', '동적 Agent 배포' 3종 탭 및 목록 검색 필터의 시각적 위계를 정리한다.

- [ ] **Step 2: 2열 목록-상세 레이아웃 및 3개 탭(검증/변경/이력) 스타일 일관화**
좌측 320px 목록 패널의 상태 뱃지와 시각, 우측 상세의 3개 탭 전환 및 검토 의견 입력/승인 액션 바를 정돈한다.

- [ ] **Step 3: 관리자 빌드 및 경계 검사 실행**
Run: `export PATH="$HOME/.nvm/versions/node/v22.23.1/bin:$PATH" && npm --prefix src/frontend run build:admin`
Expected: 빌드 성공 및 청크 정상 생성

---

### Task 4: 통합 시스템 검증 및 Obsidian 작업 기록/설계 문서 갱신

**Files:**
- Verify: `apps/user-web/src/App.tsx`
- Verify: `apps/admin-web/src/App.tsx`
- Document: `docs/Obsidain/400.프로젝트관리/02 포털 UI UX 작업 기록.md`
- Document: `docs/Obsidain/200.프로젝트실행/240.설계/23 포털 UI UX 확정과 사이트 분리 검토.md`

- [ ] **Step 1: 두 앱 빌드 및 코드 경계 검사 실행**
Run: `export PATH="$HOME/.nvm/versions/node/v22.23.1/bin:$PATH" && npm --prefix src/frontend run build:user && npm --prefix src/frontend run build:admin`
Expected: 사용자/관리자 앱 모두 빌드 성공 및 번들 경계 위반 없음

- [ ] **Step 2: 로컬 서버 HTTP 응답 및 정적 무결성 확인**
Run: `curl -s -I http://127.0.0.1:5173/ | head -n 3 && curl -s -I http://127.0.0.1:5174/ | head -n 3`
Expected: 사용자/관리자 서버 정상 응답 확인

- [ ] **Step 3: Obsidian 작업 기록 및 확정 설계 문서 최종 갱신**
[02 포털 UI UX 작업 기록.md](file:///Users/jwpios/antigravity/202610_AI%20%ED%94%8C%EB%9E%AB%ED%8F%BC/docs/Obsidain/400.%ED%94%84%EB%A1%9C%EC%A0%9D%ED%8A%B8%EA%B4%80%EB%A6%AC/02%20%ED%8F%AC%ED%84%B8%20UI%20UX%20%EC%9E%91%EC%97%85%20%EA%B8%B0%EB%A1%9D.md)과 [23 포털 UI UX 확정과 사이트 분리 검토.md](file:///Users/jwpios/antigravity/202610_AI%20%ED%94%8C%EB%9E%AB%ED%8F%BC/docs/Obsidain/200.%ED%94%84%EB%A1%9C%EC%A0%9D%ED%8A%B8%EC%8B%A4%ED%96%89/240.%EC%84%A4%EA%B3%84/23%20%ED%8F%AC%ED%84%B8%20UI%20UX%20%ED%99%95%EC%A0%95%EA%B3%BC%20%EC%82%AC%EC%9D%B4%ED%8A%B8%20%EB%B6%84%EB%A6%AC%20%EA%B2%80%ED%86%A0.md)에 2단계 변경 파일과 검증 결과를 기록한다.
