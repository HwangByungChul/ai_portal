---
title: Workflow Canvas 문구와 반응형 레이아웃 보완
date: 2026-10-22
status: 실제 React 화면 수정 · HTTP 대역 레이아웃 검증 완료 · fixture 회귀 미실행
tags: [workflow, studio, ui, responsive]
---

# Workflow Canvas 문구와 반응형 레이아웃 보완

## 요청과 기준

Workflow 화면의 내부 개발 단계 번호·과거 제안 시안 문구, 압축되는 도구 모음·분류 칩과 세 패널의 가로 넘침을 수정했다. [[2026-10-21 AI Builder 고도화 통합 Studio 설계]]와 [[23 포털 UI UX 확정과 사이트 분리 검토]]의 통합 Studio 탭, 초안·승인 요청·승인 버전 실행 구분을 기준으로 삼았다. 이전 통합 Studio 설계 결정은 유지한다.

## 변경

- `src/frontend/src/WorkflowCanvasPage.tsx`: 제목을 Workflow Canvas로 정리하고 내부 DP 번호·제안 시안 규격을 제거했다. 초안 편집과 승인·실행 관리로 탭의 실제 기능을 설명한다.
- `src/frontend/src/workflow/WorkflowStudio.tsx`: 단계 이름을 사용자 용어로 정리하고 구성 검증→실행 결과 확인→승인 요청 순서로 안내한다. 개인 초안 저장·별도 승인 요청·선택한 승인 버전 실행을 명시하고 이름 입력의 접근성 라벨과 알림 역할을 추가했다.
- `src/frontend/src/workflow/WorkflowPalette.tsx`: 분류 칩용 클래스와 검색 라벨을 적용했다.
- `src/frontend/src/workflow/workflowStudio.css`: 도구 모음은 줄바꿈하고 버튼·칩은 수축하지 않는다. 페이지 편집 영역의 컨테이너 폭이 1,100px 이하이면 팔레트→캔버스→속성을 세로로 쌓는다. 팔레트는 분류별 카드를 가로 스크롤하며 최대 높이260px, 캔버스는480px, 속성은 최대480px 내부 스크롤을 사용한다. 넓은 화면은 세 패널과560px 캔버스를 유지한다. 모바일에서는 미니맵을 숨기며 기본 확대·축소·전체 보기 도구는 제공한다.
- `src/frontend/tests/workflow-orchestration.spec.ts`: 오래된 화면 계약을 현재 Studio 제목·도구·상태 안내로 갱신했다. 1440·1024·768·390px 가로 넘침·버튼 잘림·캔버스 높이·패널 순서·팔레트 스크롤·입력 동기화 검사를 추가했다. 승인 버전 실행 계약은 해당 관리 탭을 명시적으로 연다.

## 실제 검증과 근거

1. Node22.23.1로 `node src/frontend/node_modules/typescript/bin/tsc --noEmit -p src/frontend/tsconfig.json`: 종료0.
2. `git diff --check`: 종료0.
3. 독립 컴포넌트 HTTP 대역 브라우저 검사: `node src/frontend/.runtime/workflow-layout-check.cjs` (저장소 루트, 기존 Vite5173 필요), 종료0. 이 스크립트는 실제 WorkflowCanvasPage 및 공통 CSS를 임시 진입 화면에서 마운트한다. 모든 `/api/v1/**` 요청을 Playwright에서 대역 처리하며 합성 사용자·조직 props를 사용한다. 실제 세션·API·DB 연결 검증은 아니다. 임시 HTML/TSX 진입 파일은 실행 후 제거한다.
4. 1920·1440·1024·768·390px 모두 문서 가로 넘침0, 버튼/select 잘림0, 분류 칩 수축0, JavaScript 오류0. 독립 리뷰에서 알림 live region에 닫기 버튼을 넣지 말라는 P2 지적을 반영해 메시지 텍스트와 닫기 조작을 분리했으며, 관련 assertion을 회귀 테스트에 추가했다. Node22 TypeScript와 `git diff --check` 재통과. 캔버스 높이는1920/1440에서560px, 1024/768/390에서480px였다. 아래3폭에서 패널 적층, 팔레트 가로 스크롤 및 속성 입력→제목 동기화, 콘솔 질문 입력 유지를 확인했다. 390·1440px 스크린샷을 시각 확인했다.

증거(로컬, Git 제외):

- `src/frontend/.runtime/workflow-responsive-check.json`
- `src/frontend/.runtime/workflow-responsive-390.png`
- `src/frontend/.runtime/workflow-responsive-1440.png`
- 같은 경로의1920·1024·768 이미지 및 `workflow-layout-check.cjs` 재현 스크립트

## 미실행과 다음 작업

`playwright test tests/workflow-orchestration.spec.ts`의 공유 fixture harness는 실행하지 않았다. 사전 확인에서 기존 API8000·user5173·admin5174가 실행 중이었고 A05 fixture 표식은 없었다. 이 harness는 세 포트가 비어 있어야 하므로 기존 서비스를 보존했다. 변경된 계약 테스트의 실제 로그인·fixture 통합 회귀, 승인 요청/실행 API, 기관 업무 품질·외부 제공자·운영 배포는 이번 검증 범위가 아니다. 다음 작업은 공유 서비스 중단이 승인된 별도 시험 시간에 해당2개 계약 테스트를 순차 실행하는 것이다. 독립 최종 재리뷰: PASS, 추가 critical/important 발견 없음.

관련 기록: [[400.프로젝트관리/02 포털 UI UX 작업 기록]], [[2026-10-21 AI Studio 공통 제작 흐름 구현 계획]], [[2026-10-21 Workflow Canvas 자연어 초안 연결 구현 계획]].
