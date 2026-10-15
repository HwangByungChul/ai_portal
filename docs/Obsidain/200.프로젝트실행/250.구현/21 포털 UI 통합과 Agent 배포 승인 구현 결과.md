---
title: 포털 UI 통합과 Agent 배포 승인 구현 결과
created: 2026-10-11
updated: 2026-10-11
status: local-implemented
production_deployed: false
tags: [ai-platform, portal, approval, implementation]
---

# 포털 UI 통합과 Agent 배포 승인 구현 결과

사용자 지시에 따라 상세 계획을 먼저 저장하고 실제 앱의 UI·승인 API·DB를 순차 적용했다. 기준은 [[100.프로젝트계획/11 포털 상용화 기반 UI 통합 상세 실행 계획]], 상용 전환은 [[100.프로젝트계획/12 사용자 관리자 사이트 분리와 상용 이행 설계]]다. HTML 시연과 별개인 실제 React/FastAPI/PostgreSQL 구현이며 현재 상용 운영 배포는 아니다.

## 적용된 화면과 동선

- 제품 명칭: 생성형 AI 플랫폼. `/`·`/home`은 사용자 A 업무 허브, `/workspace`는 기존 실제 대화다. 질문/Agent/최근 대화를 전달하고 질문 보내기 전 AI를 자동 호출하지 않는다.
- `/admin`은 관리 A 운영 홈이다. 현재 조직의 실제 집계 기간·mock/real 모드·호출·추정 금액·예약·불명 사용량과 실제 승인 요청을 사용한다. 예시 그래프·가짜 공지·인기 순위는 넣지 않았다.
- `/admin/approvals`는 관리 B 목록·상세 패널이다. 상태·불러온 목록 검색·cursor 더 보기·검증/변경/이력·의견·처리 확인을 제공한다.
- 사용자와 관리자 메뉴·기본 홈을 분리했다. 직접 URL과 조직/세션 변경에도 현재 권한을 확인하고 개인 입력·옛 조직 데이터를 정리한다. 현재는 단일 빌드·단일 출처다.
- 모바일 메뉴·입력 라벨·키보드 동선을 적용했다. 기능별 기존 대화·문서·요약·사용량·권한 화면을 유지한다.

## 실제 Agent 배포 승인

현재 지원하는 배포는 고정 Agent `general`/`rules_rag`의 이름·설명·기본 지시문 변경이다. 코드·모델·도구·MCP·인프라 신규 배포는 별도 확장 대상이다.

1. 조직 TADMIN/PADMIN이 Agent 관리에서 변경안·사유를 제출한다. UUID와 기반 버전, 이전·제안 스냅샷을 DB에 봉인하며 운영 설정은 바꾸지 않는다.
2. 해당 조직을 관리하는 다른 PADMIN이 승인·반려한다. 본인 처리·다른 조직·권한 회수·오래된 기반 버전은 거부한다.
3. 승인 결정·버전 CAS·실제 설정 반영·감사 이력을 한 transaction으로 처리한다. 승인으로 운영 중지를 해제하거나 비용·예약·한도를 변경하지 않는다.
4. 동일 제출 UUID/내용과 동일 처리자/결정/의견의 재전송은 기존 결과를 반환한다. 응답 불명 시 동일 제출 확인만 가능하며 새 변경 자동 재시도는 하지 않는다.
5. 기존 설정 직접 PATCH/RPC는 승인 필요 409로 차단했다. 긴급 중지·재개는 기존 운영 제어로 유지한다. 설정 롤백은 이전 내용의 새 요청·타인 승인으로 진행한다.

검증 탭은 입력 구조·현재 권한·버전 일치를 표시한다. 모델 품질·보안 심사·평가 근거를 자동으로 통과했다고 표시하지 않는다. 업무별 승인 체크리스트·평가셋·별도 승인 역할은 상용 후속 범위다.

## 실제 파일

| 책임 | 파일 |
|---|---|
| 사용자·관리자 홈 | `src/frontend/src/HomePage.tsx`, `AdminHomePage.tsx` |
| 승인 목록·상세 | `src/frontend/src/ApprovalsPage.tsx` |
| 라우팅·메뉴·표현 | `App.tsx`, `portal.css`, `main.tsx`, `TenantHeader.tsx`, `LoginPage.tsx`, `index.html` |
| 기존 대화 연결·설정 요청 | `ChatPage.tsx`, `AgentSettingsPage.tsx`, `api.ts`, `types.ts` |
| 승인 API·권한 오류 | `src/backend/app/approvals/`, `app/main.py`, `app/errors.py`, `app/operations/repository.py` |
| DB·우회 차단 | `src/backend/migrations/026_agent_deployment_approval.sql` |
| 검증·시험 도구 | `tests/test_agent_approvals.py`, 기존 운영/이행/스키마 시험, `portal_test_control.py`, frontend `portal-ui.spec.ts`와 기존 회귀의 명시적 메뉴 이동 |

전체 변경 목록과 최종 SHA는 [[200.프로젝트실행/280.통합시스템테스트/evidence/UI11-portal/source-manifest.json]]에 남겼다. 기존 000~025 SQL·런타임 의존성 버전은 변경하지 않았다. 관련 README에 승인 계약과 현재 사이트 경계를 기록했다. Git 커밋·원격 PR·외부 배포는 만들지 않았다.

## 이행·검증과 실행 상태

[[200.프로젝트실행/280.통합시스템테스트/22 포털 UI와 Agent 승인 통합 검증 결과]]에 실행·실패·수정·재시험 증거를 기록했다. 관련 backend 149개와 기존/추가 browser 108개 시나리오의 최종 결과가 통과했다. 전체 backend 전수 시험이나 단일 browser 108개 일괄 실행을 의미하지 않는다. build/typecheck·기존 개발 DB 백업/별도 DB 복원·026 이행·기존 데이터 지문 대조를 확인했다.

원래 소유한 개발 서비스를 복구했다. [사용자 홈](http://127.0.0.1:5173/home), [관리자 홈](http://127.0.0.1:5173/admin), [승인·검증](http://127.0.0.1:5173/admin/approvals). 로그인·현재 조직 권한을 사용한다.

## 다음 순서

독립 앱/공통 UI·API 계약 분리 → 실제 IdP와 사이트별 세션/BFF → 운영 DB profile·비밀관리·도메인/TLS/CI → 승인 역할·평가 근거 → 복구·부하·격리·관측 수용 시험. 환경이 필요한 항목은 설계 상태로 남긴다. 현재 mock·fixture·합성 계정을 상용 운영 환경으로 표시하지 않는다. 후속 작업은 [[400.프로젝트관리/02 포털 UI UX 작업 기록]]에 지속 기록한다.
