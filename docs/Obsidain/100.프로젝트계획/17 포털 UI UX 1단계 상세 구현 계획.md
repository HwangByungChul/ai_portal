---
title: 포털 UI UX 1단계 상세 구현 계획
date: 2026-10-12
status: 계획작성
stage: 100.프로젝트계획
tags: [ai-platform, ui-ux, implementation-plan, portal-shell, user-home]
---

# 포털 UI UX 1단계 상세 구현 계획 (공통 쉘 및 사용자 홈 A안 정렬)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 사용자 승인 A안에 맞춰 공통 디자인 토큰, 좌측 사이드바-상단 헤더 분리형 쉘([PortalShell.tsx](file:///Users/jwpios/antigravity/202610_AI%20%ED%94%8C%EB%9E%AB%ED%8F%BC/src/frontend/packages/ui/src/PortalShell.tsx)), 그리고 사용자 홈 4단 레이아웃([HomePage.tsx](file:///Users/jwpios/antigravity/202610_AI%20%ED%94%8C%EB%9E%AB%ED%8F%BC/src/frontend/src/HomePage.tsx))을 실제 React 앱에 정렬 구현한다.

**Architecture:** `packages/ui`에서 틸 주색(`#12635C`)과 본문(`#182E32`), 배경(`#F3F6F6`) CSS 변수 및 분리형 쉘 레이아웃을 정립하고, `HomePage.tsx`를 환영 배너, 분할 질문 카드, 4열 가로 Agent 카드, 최근 업무/공지 4단으로 개편하며 실제 인증 및 Agent 카탈로그/이력 데이터 계약을 유지한다.

**Tech Stack:** React 18, TypeScript, Vanilla CSS (Design Tokens), Vite, Node.js

## Global Constraints
- 제품 명칭은 ‘생성형 AI 플랫폼’으로 표기하며 특정 기관명이나 붉은색 브랜드 요소를 제거한다.
- All responses and artifacts must be written in Korean.
- 마크다운 문법: 글머리 기호는 단일 하이픈(-)과 공백을 사용하며, 각 헤더 뒤에는 빈 행을 두지 않는다.
- 기존 조직 권한 선택(`onOrganizationChange`), 역할 뱃지, 세션 검증, Agent 실행 계약, 대화 이력 API 계약을 훼손하거나 모의 데이터로 대체하지 않는다.
- 두 앱의 독립 빌드(`npm run build:user`, `npm run build:admin`) 및 코드 경계 검사를 통과해야 한다.

---

### Task 1: 공통 디자인 토큰 및 시각 체계 CSS 확장

**Files:**
- Modify: `src/frontend/packages/ui/src/styles.css`
- Modify: `src/frontend/packages/ui/src/portal.css`

**Interfaces:**
- Produces: CSS 토큰 변수 (`--color-brand-primary: #12635C`, `--color-brand-dark: #0D4A45`, `--color-text-main: #182E32`, `--color-text-muted: #64748B`, `--color-bg-subtle: #F3F6F6`, `--color-bg-card: #FFFFFF`, `--color-border: #E2E8F0`), 분리형 쉘 클래스 (`.portal-layout`, `.sidebar-brand`, `.top-header`, `.nav-icon`), A안 4단 클래스 (`.home-greeting`, `.home-split-hero`, `.home-agent-grid-4col`, `.home-bottom-columns`)

- [ ] **Step 1: CSS 토큰 및 신규 클래스 정의 작성**
[portal.css](file:///Users/jwpios/antigravity/202610_AI%20%ED%94%8C%EB%9E%AB%ED%8F%BC/src/frontend/packages/ui/src/portal.css)에 A안 시각 규격(틸 주색, 밝은 슬레이트 배경, 4열 그리드, 분할 히어로 카드, 좌측 사이드바 및 상단 헤더) 스타일을 추가한다.

- [ ] **Step 2: 사용자 웹 및 관리자 웹 빌드 영향 확인**
Run: `npm --prefix src/frontend run build:user`
Expected: 기존 빌드 통과 및 CSS 번들링 정상 완료

---

### Task 2: 분리형 공통 쉘 구조 리팩토링 ([PortalShell.tsx](file:///Users/jwpios/antigravity/202610_AI%20%ED%94%8C%EB%9E%AB%ED%8F%BC/src/frontend/packages/ui/src/PortalShell.tsx), [TenantHeader.tsx](file:///Users/jwpios/antigravity/202610_AI%20%ED%94%8C%EB%9E%AB%ED%8F%BC/src/frontend/packages/ui/src/TenantHeader.tsx))

**Files:**
- Modify: `src/frontend/packages/ui/src/TenantHeader.tsx`
- Modify: `src/frontend/packages/ui/src/PortalShell.tsx`

**Interfaces:**
- Consumes: `session.getSnapshot()`, `Tenant`, `User`, `items`
- Produces: 개편된 `PortalShell` (좌측 브랜드/아이콘 사이드바 + 상단 헤더 분리형 쉘), `TenantHeader` (상단 헤더 전용 우측 컨트롤)

- [ ] **Step 1: TenantHeader를 상단 헤더 바로 개편**
좌측 브랜드 로고를 사이드바로 이전하고, [TenantHeader.tsx](file:///Users/jwpios/antigravity/202610_AI%20%ED%94%8C%EB%9E%AB%ED%8F%BC/src/frontend/packages/ui/src/TenantHeader.tsx)를 페이지 타이틀/검색창/조직선택/프로필이 배치되는 깔끔한 상단 바로 재구성한다.

- [ ] **Step 2: PortalShell 레이아웃 구조 개편**
[PortalShell.tsx](file:///Users/jwpios/antigravity/202610_AI%20%ED%94%8C%EB%9E%AB%ED%8F%BC/src/frontend/packages/ui/src/PortalShell.tsx)의 사이드바 최상단에 ‘생성형 AI 플랫폼’ 브랜드 로고를 배치하고, 본문 상단에 `TenantHeader`를 렌더링하며 아래에 `portal-main` 콘텐츠가 오도록 구조를 정렬한다.

- [ ] **Step 3: 타입 체크 및 빌드 검증**
Run: `npm --prefix src/frontend run typecheck`
Expected: TypeScript 컴파일 오류 없음

---

### Task 3: 사용자 홈 A안 4단 레이아웃 및 실제 데이터 연동 개편 ([HomePage.tsx](file:///Users/jwpios/antigravity/202610_AI%20%ED%94%8C%EB%9E%AB%ED%8F%BC/src/frontend/src/HomePage.tsx))

**Files:**
- Modify: `src/frontend/src/HomePage.tsx`

**Interfaces:**
- Consumes: `tenant`, `user`, `onChat`, `onDocuments`, `onSummary`, `onCatalog`, `onMine`, `/agents`, `/conversations?limit=5`
- Produces: A안 4단 업무 허브 사용자 홈 화면

- [ ] **Step 1: 1단 환영 인사 및 날짜 섹션 구현**
사용자 실제 세션명과 오늘 날짜(한글 포맷)를 헤더 배너로 구성한다.

- [ ] **Step 2: 2단 분할 업무 시작 카드 구현**
좌측(Textarea 프롬프트 입력 + 업무 추천 칩 3종 + 문서등록/채팅시작 버튼)과 우측(처음 사용 안내 팁 + 가이드 링크)을 7:3 비율 분할 카드로 배치한다.

- [ ] **Step 3: 3단 가로 4열 Agent 카드 그리드 구현**
`useRemote('/agents')`의 실제 Agent 목록을 매핑하여 카테고리, SVG 아이콘, 이름, 설명, 상태 태그, 시작 버튼을 지닌 4열 반응형 카드로 렌더링한다.

- [ ] **Step 4: 4단 하단 분할 영역 (최근 업무 + 공지/안내) 구현**
좌측에 최근 대화 5건 이력 목록 및 빈 상태, 우측에 공지사항 카드(준비 중 표기) 및 워크스페이스 바로가기 버튼들을 배치한다.

- [ ] **Step 5: 정적 타입 검증 및 사용자 웹 빌드**
Run: `npm --prefix src/frontend run build:user`
Expected: 빌드 성공 및 청크 정상 생성

---

### Task 4: 통합 시스템 검증 및 회귀 테스트

**Files:**
- Verify: `apps/user-web/src/App.tsx`
- Verify: `apps/admin-web/src/App.tsx`
- Document: `docs/Obsidain/400.프로젝트관리/02 포털 UI UX 작업 기록.md`
- Document: `docs/Obsidain/200.프로젝트실행/240.설계/23 포털 UI UX 확정과 사이트 분리 검토.md`

- [ ] **Step 1: 두 앱 빌드 및 코드 경계 검사 실행**
Run: `npm --prefix src/frontend run build:user && npm --prefix src/frontend run build:admin`
Expected: 사용자/관리자 앱 모두 빌드 성공 및 번들 경계 위반 없음

- [ ] **Step 2: 브라우저 뷰포트(데스크톱 1440px / 모바일 390px) 반응형 확인**
좌측 사이드바 및 분할 카드, 4열 카드가 너비에 맞춰 정상 배치되고 수평 넘침이 없음을 확인한다.

- [ ] **Step 3: Obsidian 작업 기록 및 설계 문서 갱신**
[02 포털 UI UX 작업 기록.md](file:///Users/jwpios/antigravity/202610_AI%20%ED%94%8C%EB%9E%AB%ED%8F%BC/docs/Obsidain/400.%ED%94%84%EB%A1%9C%EC%A0%9D%ED%8A%B8%EA%B4%80%EB%A6%AC/02%20%ED%8F%AC%ED%84%B8%20UI%20UX%20%EC%9E%91%EC%97%85%20%EA%B8%B0%EB%A1%9D.md)과 [23 포털 UI UX 확정과 사이트 분리 검토.md](file:///Users/jwpios/antigravity/202610_AI%20%ED%94%8C%EB%9E%AB%ED%8F%BC/docs/Obsidain/200.%ED%94%84%EB%A1%9C%EC%A0%9D%ED%8A%B8%EC%8B%A4%ED%96%89/240.%EC%84%A4%EA%B3%84/23%20%ED%8F%AC%ED%84%B8%20UI%20UX%20%ED%99%95%EC%A0%95%EA%B3%BC%20%EC%82%AC%EC%9D%B4%ED%8A%B8%20%EB%B6%84%EB%A6%AC%20%EA%B2%80%ED%86%A0.md)에 실제 변경 파일과 검증 결과를 기록한다.
