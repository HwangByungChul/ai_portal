---
title: 포털 High-End UI UX 전면 개편 및 듀얼 아이덴티티 상세 구현 계획
created: 2026-10-13
status: completed
purpose: 방안 1(A/B 시안 100% 정밀 구현 및 사용자·관리자 듀얼 아이덴티티 분리) 상세 구현 및 검증 계획
tags: [ai-platform, ui-ux, design-system, plan]
---
# 포털 High-End UI UX 전면 개편 및 듀얼 아이덴티티 상세 구현 계획
사용자 확정(2026-10-13): 제안 시안 A안(사용자 업무 허브형)과 B안(관리자 다크 슬레이트 콘솔)을 100% 정밀 구현하는 **방안 1**을 승인함. 사용자 포털과 관리자 포털의 디자인을 시각적으로 명확히 분리하고, 엔터프라이즈 High-End 완성도를 달성한다.

## 1. 개요 및 설계 원칙
- **사용자 포털 (5173 - Modern AI Workspace)**: 화이트/소프트 세이지(`--user-soft: #e6f1ee`) + 딥 틸(`--user-accent: #12635c`) 악센트. 248px 정규 사이드바, 메뉴별 SVG 라인 아이콘, 2컬럼 컴포저(좌측 프롬프트·가드레일 뱃지·추천 칩 4종·자료 범위 안내·딥 틸 CTA "대화 시작 →"/우측 3분 이용 가이드 배너), 10대 표준 업무 Agent 배너, 카테고리 태그 4열 에이전트 카드.
- **관리자 포털 (5174 - Enterprise Ops Console)**: **다크 슬레이트 차콜 (`#1a2e30`)** 사이드바, 방패 심볼, 민트 하이라이트(`active: #2a4d52` / `#34d399`), 상단 `OPERATIONS` 뱃지, 실시간 관제 정상 펄스 뱃지, 실시간 메트릭 카드 및 관제 테이블.
- **공통 기반**: `Pretendard` 웹폰트 전면 도입, 1px 보더 라인(`--line: #dce5e5`), 일관된 SVG 라인 아이콘 시스템, 완벽한 반응형.

## 2. 파일 수정 및 신규 구성 맵
| 구분 | 파일 경로 | 변경 및 역할 |
|---|---|---|
| **스타일/폰트** | `packages/ui/src/portal.css` | Pretendard 웹폰트 전면 import, 시안 A/B 색상 토큰, 사이드바·탑바·컴포저·카드 전면 리팩토링 |
| **사이드바 & 셸** | `packages/ui/src/PortalShell.tsx` | 사용자(화이트/틸) vs 관리자(다크 슬레이트/민트) 듀얼 브랜딩 및 100% 라인 SVG 아이콘 매핑 |
| **탑바** | `packages/ui/src/TenantHeader.tsx` | 브레드크럼 계층화, 둥근 검색바, 관제 시스템 정상 펄스 뱃지, 원형 아바타 뱃지, 관리자 전용 뱃지 |
| **사용자 홈** | `src/frontend/src/HomePage.tsx` | 2컬럼 컴포저 히어로, 가드레일 뱃지, 추천 칩 4종, 3분 이용 가이드, 10대 Agent 배너, 카테고리 태그 4열 카드 |
| **관리자 홈** | `src/frontend/src/AdminHomePage.tsx` | 다크 테마와 조화로운 고대비 카드 및 지표, 실측 Overview 차트 연동 유지 |

## 3. 세부 작업 단계 (Bite-Sized Tasks)
### Task 1: 디자인 시스템 및 Pretendard 웹폰트 토큰 정비
- [x] `packages/ui/src/portal.css` 상단에 Pretendard 다이내믹 서브셋 웹폰트 import 및 기본 글꼴 적용 완료.
- [x] 사용자 포털용 토큰: `--user-accent: #12635c`, `--user-soft: #e6f1ee`, `--user-text-main: #142a27`, `--user-border: #dbe7e4`.
- [x] 관리자 포털용 다크 토큰: `--admin-sidebar-bg: #1a2e30`, `--admin-sidebar-border: #233e42`, `--admin-sidebar-active-bg: #2a4d52`, `--admin-mint: #34d399`, `--admin-sidebar-text: #dce7e4`.
- [x] 버튼, 카드, 뱃지, 컴포저 섀도우 및 마이크로 인터랙션 클래스 정의 완료.

### Task 2: 듀얼 사이드바 및 아이콘 시스템 적용 (`PortalShell.tsx`)
- [x] 사용자 뷰: Sparkle SVG 로고, `생성형 AI 플랫폼` / `WORK`, 메뉴별 라인 SVG 아이콘, 하단 녹색 닷("보안 RAG 연계 가동 중").
- [x] 관리자 뷰: 다크 슬레이트 배경, Shield SVG 로고, `관리자 콘솔` / `OPERATIONS` 뱃지, 관리자 14개 메뉴별 라인 SVG 아이콘, 하단 녹색 닷("플랫폼 관제 가동 중").
- [x] 활성 상태 시각적 피드백: 사용자는 부드러운 세이지 배경, 관리자는 다크 틸 배경 + 좌측 민트 인디케이터 바.

### Task 3: 상단바 헤더 (`TenantHeader.tsx`) 리팩토링
- [x] 사용자 사이트: `생성형 AI 플랫폼 / 나의 업무 시작점` 브레드크럼, 둥근 검색바, 원형 아바타 + 사용자명 + 조직 선택기.
- [x] 관리자 사이트: `관리 포털 / 운영 현황 모니터링` + `OPERATIONS` 뱃지, 초록 펄스 `관제 시스템 정상` 뱃지, 조직 선택기, 관리자 롤 뱃지.

### Task 4: 사용자 홈 화면 (`HomePage.tsx`) 시안 A안 100% 일치화
- [x] 인사말: `안녕하세요, {user.display_name}님. 오늘 어떤 업무를 도와드릴까요?` + 날짜 뱃지.
- [x] 2컬럼 컴포저 히어로: 좌측 독립 프롬프트 카드(가드레일 뱃지, 문서 첨부, 사내 승인 문서 범위, 딥 틸 CTA "대화 시작 →", 4개 퀵 칩) + 우측 `3분 이용 가이드` 카드.
- [x] 10대 표준 업무 Agent(DP-24) 배너 카드 정돈.
- [x] 업무별 AI 도우미: 4열 카드에 카테고리 태그, 라인 SVG 아이콘, 운영 중 뱃지, `시작하기` 버튼.

### Task 5: 관리자 홈 화면 (`AdminHomePage.tsx`) 고대비 디자인 정돈
- [x] 4대 메트릭 카드: 상단 다크 슬레이트 포인트 바, 고대비 수치 표시(Pretendard 800), 호버 모션.
- [x] 기간별 AI 호출 추이 및 관제 현황 카드 일치화.

### Task 6: 빌드 및 브라우저 실증 검증
- [x] `npm run build:user` & `npm run build:admin` 모듈 경계 검증 PASS 확인.
- [x] `npm run test:config` 19/19 PASS 확인.
- [x] 브라우저 서브에이전트로 5173 사용자 포털 및 5174 관리자 포털 실제 화면 캡처 및 시각적 분리 검증 완료.

## 4. 수용 검증 결과
- **사용자 포털(5173)과 관리자 포털(5174)의 즉각적인 시각적 분리 달성**: 라이트 틸/화이트 세이지 vs 다크 슬레이트 차콜/민트 사이드바로 인해 1초 만에 역할 구별 가능.
- **Pretendard 웹폰트 적용으로 심미성 대폭 제고**: 타이포그래피 품격과 가독성 완성.
- **모듈 경계 및 비즈니스 로직 불변 유지**: `build:user` 및 `build:admin` 통과.
