---
title: 포털 UI UX 정렬 및 화면 일치화 실행 계획
date: 2026-10-12
status: 계획확정
stage: 100.프로젝트계획
tags: [ai-platform, ui-ux, design-alignment, portal, user-home, admin]
---

# 포털 UI UX 정렬 및 화면 일치화 실행 계획
관련: [[23 포털 UI UX 확정과 사이트 분리 검토]], [[13 승인 A안과 실제 React 사용자 화면 차이 검토]], [[14 관리 A 홈과 B 승인 패널 실제 앱 차이 검토]], [[02 포털 UI UX 작업 기록]].

## 1. 개요 및 목적
2026-10-12 사용자는 [[13 승인 A안과 실제 React 사용자 화면 차이 검토]]와 [[14 관리 A 홈과 B 승인 패널 실제 앱 차이 검토]]를 바탕으로, 실제 React 앱의 UI/UX를 기승인된 시안(사용자 A안 업무 허브형, 관리자 A안 운영 현황형 홈 + 관리자 B안 승인·검증 패널)에 맞춰 정렬하는 실행 계획 수립을 요청했다.
본 계획서는 컴포넌트 단위 점진적 리팩토링 방식(접근법 1)을 채택하여, 기존 인증·조직 권한·실제 Agent 카탈로그 및 실행 이력 데이터 계약을 온전히 보존하면서 사용자 및 관리자 화면의 시각 체계와 구조를 승인 시안에 완전히 정렬하는 2단계 추진 방안을 정의한다.

## 2. 추진 범위 및 단계별 접근

### 단계 분리 원칙
- **1단계 (최우선)**: 공통 디자인 토큰 정립, 분리형 좌측 사이드바/상단 헤더 쉘([PortalShell.tsx](file:///Users/jwpios/antigravity/202610_AI%20%ED%94%8C%EB%9E%AB%ED%8F%BC/src/frontend/packages/ui/src/PortalShell.tsx)) 구축, 사용자 홈 A안([HomePage.tsx](file:///Users/jwpios/antigravity/202610_AI%20%ED%94%8C%EB%9E%AB%ED%8F%BC/src/frontend/src/HomePage.tsx)) 4단 레이아웃 및 실제 데이터 바인딩 완성.
- **2단계 (후속)**: 관리자 홈 A안([AdminHomePage.tsx](file:///Users/jwpios/antigravity/202610_AI%20%ED%94%8C%EB%9E%AB%ED%8F%BC/src/frontend/src/AdminHomePage.tsx)) 핵심 4대 지표/추이 카드 정렬, 관리자 B안 승인 패널([ApprovalsPage.tsx](file:///Users/jwpios/antigravity/202610_AI%20%ED%94%8C%EB%9E%AB%ED%8F%BC/src/frontend/src/ApprovalsPage.tsx)) 2열 목록-상세 및 3탭(검증/변경/이력) 일관화.

### 상태 구분 기준
- **승인 시안**: HTML 및 PNG 시안에 정의된 UI/UX 이상형 구조.
- **실제 앱 구현**: 본 계획을 통해 React 컴포넌트에 반영되는 프론트엔드 코드.
- **운영 데이터 계약**: 가짜 예시 데이터(홍길동, 가짜 10개 Agent 등)를 복제하지 않고, 실제 서버 API([`/api/user/agent-history`](file:///Users/jwpios/antigravity/202610_AI%20%ED%94%8C%EB%9E%AB%ED%8F%BC/src/frontend/src/ChatPage.tsx), `/api/catalog/agents`, `/admin/agent-deployments` 등)와 연결된 정합성을 유지.

## 3. 1단계 상세 설계: 공통 디자인 쉘 및 사용자 홈 A안

### 3.1 공통 디자인 토큰 정립 ([packages/ui/src/styles.css](file:///Users/jwpios/antigravity/202610_AI%20%ED%94%8C%EB%9E%AB%ED%8F%BC/src/frontend/packages/ui/src/styles.css), [portal.css](file:///Users/jwpios/antigravity/202610_AI%20%ED%94%8C%EB%9E%AB%ED%8F%BC/src/frontend/packages/ui/src/portal.css))
- **컬러 팔레트**:
  - 브랜드 주색: `--color-brand-primary: #12635C`
  - 브랜드 딥 틸: `--color-brand-dark: #0D4A45`
  - 본문 텍스트: `--color-text-main: #182E32`
  - 보조 텍스트: `--color-text-muted: #64748B`
  - 페이지 배경: `--color-bg-subtle: #F3F6F6`
  - 카드 배경: `--color-bg-card: #FFFFFF`
  - 테두리: `--color-border: #E2E8F0`
- **타이포그래피 및 간격**:
  - 대제목(H1/H2): 20px / font-weight 700
  - 카드 제목: 16px / font-weight 600
  - 본문: 14px / line-height 1.5
  - 섹션 간격(gap/margin): 24px, 32px
- **아이콘 시스템**:
  - 유니코드 문자(예: ⚙️, 🔍 등)를 인라인 SVG 규격 아이콘 컴포넌트로 일원화.

### 3.2 분리형 공통 쉘 구조 ([packages/ui/src/PortalShell.tsx](file:///Users/jwpios/antigravity/202610_AI%20%ED%94%8C%EB%9E%AB%ED%8F%BC/src/frontend/packages/ui/src/PortalShell.tsx))
- **좌측 사이드바 (Navigation Sidebar)**:
  - 상단: 제품명 ‘생성형 AI 플랫폼’ 텍스트/심볼 로고 (기관 명칭 없음)
  - 중단: 홈, AI 채팅, 에이전트 탐색, 내 워크스페이스 등 주요 메뉴 (현재 경로 활성화 강조)
  - 하단: 이용 가이드, 지원 센터 바로가기
  - 너비: 240px 고정 (모바일 390px에서는 드로어 메뉴 또는 하단 바 반응형 전환)
- **상단 헤더 (Header Bar)**:
  - 좌측: 현재 페이지 브레드크럼 및 화면 타이틀
  - 중앙: 전역 통합 검색 바 (검색 안내 플레이스홀더 및 검색 모달 연결)
  - 우측: 필수 비즈니스 컨트롤 보존
    - 현재 조직 선택 드롭다운 (`onOrganizationChange` 계약 보존)
    - 알림 아이콘 뱃지
    - 사용자 프로필 요약(이름, 역할 뱃지) 및 로그아웃 버튼
- **본문 영역**:
  - 배경 `#F3F6F6`, 중앙 정렬 최대 너비(1440px), 좌우 반응형 패딩.

### 3.3 사용자 홈 A안 4단 레이아웃 ([src/frontend/src/HomePage.tsx](file:///Users/jwpios/antigravity/202610_AI%20%ED%94%8C%EB%9E%AB%ED%8F%BC/src/frontend/src/HomePage.tsx))
- **1단 (환영 배너)**:
  - `"안녕하세요, {user.name}님. 오늘 어떤 업무를 도와드릴까요?"` 인사말
  - 오늘 날짜(예: 2026년 10월 12일 월요일) 표시
- **2단 (분할 업무 시작 카드 - 7:3 비율)**:
  - 좌측 카드 (질문 입력 및 업무 추천):
    - Textarea 프롬프트 입력창 + '질문하기' 버튼 (클릭 시 입력값을 지닌 채 [ChatPage.tsx](file:///Users/jwpios/antigravity/202610_AI%20%ED%94%8C%EB%9E%AB%ED%8F%BC/src/frontend/src/ChatPage.tsx)로 이동)
    - 파일 첨부 안내/동선 (문서 요약 및 내 자료실 연계)
    - 주요 업무 추천 칩(예: "사내 규정 질의", "업무 보고서 초안", "공문 작성") 클릭 시 입력창 자동 채움
  - 우측 카드 (처음 사용 안내):
    - 플랫폼 사용 팁 3가지 및 상세 이용 가이드 링크
- **3단 (업무별 AI 도우미 가로 카드 그리드 - 4열)**:
  - 상단 타이틀 `"업무별 AI 도우미"` 및 `"전체 보기 →"` (카탈로그 이동 링크)
  - 실제 권한이 있는 Agent 목록 바인딩: 고정 2종(규정 검색 도우미, 일반 업무 어시스턴트) 및 승인된 동적 Agent
  - 카드 요소: 카테고리 뱃지, SVG 아이콘, Agent명, 설명, 상태 태그, 시작 버튼
- **4단 (하단 정보 2열 분할)**:
  - 좌측 (최근 업무 내역): 실제 최근 실행 이력 API 연동(Agent명, 요약, 일시, '이어하기' 링크), 이력 없을 시 빈 상태 카드
  - 우측 (공지사항 및 리소스): 플랫폼 공지사항 영역(API 미연동 상태 투명 표기) 및 내 자료실/사용량 바로가기 링크

## 4. 2단계 연계 설계: 관리자 화면 정렬 (개요)

### 4.1 관리자 홈 A안 정렬 ([AdminHomePage.tsx](file:///Users/jwpios/antigravity/202610_AI%20%ED%94%8C%EB%9E%AB%ED%8F%BC/src/frontend/src/AdminHomePage.tsx))
- 공통 사이드바 및 상단 헤더 쉘 적용 (관리자 메뉴: 운영 현황, 승인·검증, AI 자산 관리, 설정 등)
- 4대 주요 지표 카드 정렬: 호출 건수, 정산 비용(예약/불명 금액 안전 보존), 승인 대기 요청 수, 게시 자산 수
- 운영 알림 및 호출 추이 섹션 레이아웃 복원
- 승인 대기 목록 테이블 배치 및 승인 상세 딥링크(유형+ID) 지원

### 4.2 관리자 B안 승인 패널 통일 ([ApprovalsPage.tsx](file:///Users/jwpios/antigravity/202610_AI%20%ED%94%8C%EB%9E%AB%ED%8F%BC/src/frontend/src/ApprovalsPage.tsx))
- 운영설정 배포, 증적 공유 검토, 동적 배포 요청 3종에 대한 2열 패널(목록 320px + 상세 영역) 통일
- 상태 필터(대기, 승인, 반려) 및 요청 검색 바 일관화
- 상세 화면의 3개 탭 구성 (검증 결과 / 변경 사항 / 처리 이력) 일원화
- 타인 승인, CAS 동시성, 자료 ACL RLS 보호 계약 철저 유지

## 5. 영향 파일 및 수정 명세

| 구분 | 파일 경로 | 주요 변경 내용 |
|---|---|---|
| 공통 디자인 | [packages/ui/src/styles.css](file:///Users/jwpios/antigravity/202610_AI%20%ED%94%8C%EB%9E%AB%ED%8F%BC/src/frontend/packages/ui/src/styles.css) | 틸(#12635C)/배경(#F3F6F6) 토큰, 타이포그래피 스케일 추가 |
| 공통 디자인 | [packages/ui/src/portal.css](file:///Users/jwpios/antigravity/202610_AI%20%ED%94%8C%EB%9E%AB%ED%8F%BC/src/frontend/packages/ui/src/portal.css) | 사이드바, 상단 헤더, 분할 카드, 4열 그리드 전용 스타일 정의 |
| 공통 쉘 | [packages/ui/src/PortalShell.tsx](file:///Users/jwpios/antigravity/202610_AI%20%ED%94%8C%EB%9E%AB%ED%8F%BC/src/frontend/packages/ui/src/PortalShell.tsx) | 좌측 브랜드/아이콘 내비게이션 + 상단 헤더 분리 구조로 재구성 |
| 사용자 홈 | [src/frontend/src/HomePage.tsx](file:///Users/jwpios/antigravity/202610_AI%20%ED%94%8C%EB%9E%AB%ED%8F%BC/src/frontend/src/HomePage.tsx) | 환영문구, 분할카드, 4열 Agent 카드, 최근업무/공지 4단 구조 구현 |
| 사용자 앱 진입 | [apps/user-web/src/App.tsx](file:///Users/jwpios/antigravity/202610_AI%20%ED%94%8C%EB%9E%AB%ED%8F%BC/src/frontend/apps/user-web/src/App.tsx) | 개편된 쉘 및 홈 페이지와의 라우팅/조직 전달 정합성 확인 |
| 관리자 앱 (2단계) | [AdminHomePage.tsx](file:///Users/jwpios/antigravity/202610_AI%20%ED%94%8C%EB%9E%AB%ED%8F%BC/src/frontend/src/AdminHomePage.tsx), [ApprovalsPage.tsx](file:///Users/jwpios/antigravity/202610_AI%20%ED%94%8C%EB%9E%AB%ED%8F%BC/src/frontend/src/ApprovalsPage.tsx) | 관리 A 홈 지표 정렬 및 B 승인 패널 2열/3탭 구조 통일 |

## 6. 검증 계획 및 완료 기준

### 6.1 시각 및 반응형 검증
- **데스크톱 (1440px / 1600px / 1920px)**:
  - 수평 스크롤(overflow) 없음
  - 좌측 사이드바 240px 고정, 상단 헤더 상단 고정, 본문 카드 정렬 확인
  - 4열 Agent 카드 및 분할 카드가 왜곡 없이 균등 배치됨을 확인
- **모바일 (390px)**:
  - 분할 카드 및 4열 카드가 수직 1열로 유연하게 줄바꿈
  - 사이드바 메뉴의 모바일 토글/드로어 정상 동작

### 6.2 데이터 및 비즈니스 계약 검증
- **조직 전환 및 세션**: 상단 헤더의 조직 드롭다운 변경 시 해당 조직 권한 데이터가 올바르게 갱신되는지 확인
- **Agent 실행 연결**: 카드에서 '시작하기' 클릭 시 해당 Agent 식별자를 유지한 채 채팅 페이지로 정상 진입
- **실행 이력 표시**: 실제 API의 본인 실행 내역만 최근 업무에 표시되며 타인의 실행 내역은 격리됨 확인
- **빌드 및 타입 무결성**: `npm run build:user` 및 `npm run build:admin` 경계 검사 및 빌드 통과

## 7. 기록 및 후속 절차
- 본 계획서는 `docs/Obsidain/100.프로젝트계획/`에 정식 보존한다.
- 세부 구현 착수 및 단계별 검증 완료 시 [[02 포털 UI UX 작업 기록]] 및 [[23 포털 UI UX 확정과 사이트 분리 검토]]에 실제 변경 파일, 정적/브라우저 검증 증거, 미완료 사항을 지속 누적 기록한다.
