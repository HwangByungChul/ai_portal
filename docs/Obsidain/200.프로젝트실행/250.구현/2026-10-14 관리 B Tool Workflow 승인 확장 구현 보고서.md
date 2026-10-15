---
title: 관리 B Tool Workflow 승인 확장 구현 보고서
date: 2026-10-14
status: 현재 범위 실제 앱 구현·선별 검증·최종 코드 검토 완료
stage: 250.구현
tags: [approval, tool, workflow, implementation]
---
# 관리 B Tool Workflow 승인 확장 구현 보고서

[[32 관리 B안 Tool Workflow 승인 화면 확장 상세 작업 계획]]과 사용자의 진행 승인에 따른 실제 앱 개발 기록이다. 사용자 홈 A·관리 홈 A·승인 B 및 생성형 AI 플랫폼 명칭을 유지한다. 업무는 AGENT_03 회의록 한 종이며 나머지 9종은 추후 확장한다.

## 서버 단위 완료

050 신규 마이그레이션과 `app/approval_reviews/{models,repository}.py`, Tool·Workflow routes/repository, Workflow identity를 변경했다. 검토 의견 원장·현재 검증·정확한 UUID 상세·서버 검색/페이지·서명 cursor·현재 head 비교·처리 이력·신청 지원 정보·별도 엄격 Workflow 검증 API를 구현했다. 신규 회의록 요청에는 서버 계약 전체 snapshot을 불변 저장한다. 기존 과거 요청의 의견과 snapshot을 소급 생성하지 않는다.

승인/반려/철회 의견은 trim 후 1~500자, UTF8/NUL 검사이며 결정·의견·감사 이력을 원자 저장한다. 신청자 본인 결정 금지·현재 PADMIN·CAS·조직 권한 검사를 유지한다. 승인 상태와 현재 활성 head를 구분한다. 서버 코드 검토에서 현재 Tool 모드 전달 및 공개 대상 회원 재검사 누락 2건을 찾아 수정했고 재검토가 통과했다.

## 시험·증거

실제 임시 PostgreSQL/API의 최종 보완 후 `test_tool_workflow_review_http.py`, `test_approval_review_migration.py`, `test_tool_persistent_execution.py`, `test_workflow_approvals.py` 46건 통과(72.48초). 이전 단계의 46건/8건 시험과 중복 합산하지 않는다. 더 넓은 선행 시험은 65통과/1fixture 오류였고 후속 시험에서 수정 확인했다. strict validate HTTP의 정상/변수/순환/USER/CSRF 및 현재모드·회원비활성화 차단/반려 가능·감사/의견 rollback 등을 확인했다.

050 시험은 기존 행/열·이력 checksum·NULL 과거의견/manifest·직접 web SELECT 차단·append-only를 확인했다. 시험 schema 66표/51migration/172security 함수이며 primary에 적용한 결과가 아니다. 소스 변경 전 원본 일부는 캡처하지 못해 task review의 기존 변경 귀속에 한계가 있다. 재구성 비교본과 실제 post snapshot을 구분하여 검토했다. 시험 결과는 실행 보고, 코드 검토는 읽기 전용 판정이다.

증거: `260.테스트/evidence/B-Approval-20261014/approval-backend-report.md`, `approval-backend-review-report.md`, `approval-ui-contract.md`.

## 진행 중·미완료

Tool·Workflow 신청폼과 관리 B 목록·상세·deep link·홈 집계·브라우저 검증은 현재 구현 중이며 완료로 표시하지 않는다. 전체 suite, 실제 기관 connector/모델의 업무품질·Entra 시험·UAT·운영 배포는 미검증이다. 기본 DB의 040 checksum 경계는 유지하며 이력 우회/기본 DB 이행/seed/유료 호출/배포를 수행하지 않았다. Obsidian Markdown 파일 기록은 완료했으나 앱 reading view는 미검증이다.

다음: 화면 구현→실제 임시 API 브라우저 종단·기존 3유형 회귀·1440/1024/768 화면 검수→최종 코드 검토·보고서 갱신.

## 2026-10-14 · 마지막 작업 재확인 및 서버 보완

사용자가 마지막 작업 확인과 계속 진행을 승인했다. 이전 임시 보고서 일부는 지워졌으나 실제 source와 Obsidian 기록은 유지되어 현재 코드를 다시 확인했다. 화면 구현은 존재하지만 최종 수용 완료로 보지 않는다. 사용자·관리자 Node22 build와 경계 검사 user26/admin43을 재확인했다.

승인 후 자체 head/case revision 증가를 실패로 표시하던050 상세 검증은 pending에만 base CAS를 적용하고, approved는 exact 현재 활성 요청/version과 실제 계약·의존성으로 검사하도록 보완했다. PublishedRun이 expected_publication_revision을 받지 못해 실행422였던 결함은 required bounded StrictInt 계약으로 수정했다. 변경 파일은050 SQL, app/assets/published.py, tests/test_tool_workflow_review_http.py, tests/test_published_agents.py다. 변경 전/후를 이번에는 정확히 캡처했다. 최종 실제 임시 DB/API 지정23pass(50.34초), 앞선 넓은54pass/1 신규fixture호출 오류는 수정 후 확인했으며 합산하지 않는다. 신규 접수202/동일재조회200/변경충돌409/잘못된revision422와 정상 승인·superseded·철회 검증을 확인했고 읽기전용 코드 검토 Spec/Quality PASS다.

화면 정적 검토에서 Tool 선택 순서에 따른 노드ID 재사용으로 변수 연결 대상이 바뀔 수 있는 문제와 게시 Agent 새로고침이 이전 exactversion을 유지하는 문제를 찾아 보완 중이다. 현재 scope는 AGENT_03과 Tool/Workflow 승인 B이며 나머지9종은 후속이다. primary040 경계·실제기관연결/품질/UAT/배포 미검증 유지. 증거 resume-backend-report/review-result 및 resume-ui-review는 B-Approval-20261014에 보존했다. 다음은 화면 수정→현재실제 browser검증→최종검토/기록 갱신이다.

## 2026-10-14 · 화면 보완·브라우저 선별 수용 완료

실제 React 관리 B에 Tool·Workflow 2유형과 신청/검증/비교/처리 이력/필수 의견/승인·반려/현재head 철회, 검색·페이지·정확한 UUID deep link를 연결했다. 기존 운영설정·Builder 증적·동적 Agent 배포 3유형과 관리 A 홈 이동을 유지한다. 홈은 서버의 전체 대기와 Tool·Workflow 처리 가능 대기를 별도로 표시하며, 기존 API가 제공하지 않는 전체 처리가능 건수를 만들어 표시하지 않는다.

실제 화면 파일은 ApprovalReviewPanel.tsx, ToolApprovals.tsx, WorkflowApprovals.tsx, ApprovalAudience.tsx, ToolApprovalRequest.tsx, WorkflowApprovalRequest.tsx, ApprovalsPage.tsx, approvalLaunch.ts, AdminHomePage.tsx, WorkflowCanvasPage.tsx, apps/admin-web/src/App.tsx 및 공통 types/CSS다. 이전 초기 변경의 귀속 비교본 일부는 지워졌으므로 재개 corrective 수정은 정확한 pre/post를 영속 캡처하고, 초기 전체 UI는 현재 scoped source 검토로 확인했다. 서버 카탈로그/실제 게시 Agent 변수와 exact version을 읽고, generated definition은 읽기 전용이며 서버 엄격 검증 뒤 접수한다. 회의록만 업무 template이고 나머지9종은 추후다.

WorkflowApprovalRequest.tsx의 Tool 노드ID를 선택 순서와 분리해 제거된 source가 다른 Tool로 바뀌지 않도록 했고, 선택 해제 시 해당 binding을 무효화한다. 지원 정보 새로고침은 선택한 게시 Agent exact 상세를 다시 읽어 새 버전/변수·검증 상태를 갱신하며, 늦은 selection/겹치는 refresh 응답을 무시한다. 수정 후 이전 접수 표시 초기화와 홈의 빈 목록 문구 범위도 보완했다. 변경 파일은 이 신청폼, AdminHomePage.tsx, tests/tool-workflow-approvals.spec.ts다. 읽기전용 재검토 Spec/Quality PASS이며 initial Important2/Minor2는 모두 종료됐다.

### 재개 후 확인한 시험

- 서버 지정 최종 시험23pass(50.34초) — 실제 임시 PostgreSQL/API, 정상 승인/철회/superseded·필수 publication revision 계약.
- Node22 `npm run build`: user26/admin43 코드 경계 통과. 현재 변경 후 빌드 결과이며 기존 보고와 중복 합산하지 않는다.
- 브라우저 covering14pass(86.77초), focused2pass(26.20초), 강화 race1pass(10.92초). 실행 간 중복을 제외해 고유15건이며 **실제 임시 DB/API 경로6건·HTTP 대역 경로9건**이다. 전체 suite 완료가 아니다.
- 실제 경로: D12_01/02 동적 배포·USER 실행·동일 접수 재조회200·철회/반려, WF_01 카탈로그·Canvas 구조 검증, WF_04 Tool 신청→다른 PADMIN 승인→USER 실행→철회 차단, WF_05 회의록 Workflow 신청→불변 계약 저장→다른 PADMIN 승인→USER mock 결과→철회, U11_02 운영설정 승인. 실제 경로의 외부 AI 응답은 시험 전용 mock이며 업무품질이나 기관connector 수용이 아니다.
- HTTP 대역: D12_07 홈 요청 선택/reload, WF_02/03 실행·회의록 UI 계약, WF_06~11 검색·cursor·CAS/응답유실·접수UUID·잘못된link·조직전환·집계/popstate·Tool binding·새게시version/늦은응답. 인증/시험DB가 실제라도 업무응답을 대체한 시험은 대역으로 분류했다.
- 실제 안정된 승인 상세 캡처1440/1024/768과 긴 제목 대역 캡처를 저장했다. 각 폭에서 가로 넘침 없음을 시험했고 코디네이터도 실제 캡처를 확인했다. 768px 헤더 줄바꿈·목록 복귀 keyboard focus·승인 후 현재 기술 조건 충족 표시를 확인했다. 품질/보안/업무 심사 통과와 기술 검증은 구분한다.

증거: `resume-covering-browser.json`, `resume-focused-browser.json`, `resume-race-browser.json`, `B-Approval-workflow-{1440,1024,768}.png`, 별도 long-workflow 대역 PNG 및 resume-frontend-report/ui-review. 비밀번호/개인 trial/비공개 trace는 증거로 내보내지 않았다. 시험 harness가 종료됐고5173/5174시험포트닫힘을 확인했다. 기존서비스 강제 종료 없이 시험 소유권을 해제했다.

### 미완료 범위와 다음 작업

현재 앱 구현·선별 수용과 기본 DB 이행/실제 상용 서비스 수용은 별개다. primary040 checksum 경계는 그대로이며041~050을 기본 DB에 적용하거나 이력 우회/seed/유료호출/배포하지 않았다. 실제 기관 Tool·모델·자료·Entra 연결, 업무품질/보안심사·UAT, 전체suite·분산복구/수동재개·문서자료선택/상대날짜 지원, 나머지9종은 남아 있다. Obsidian 파일 기록과 앱 reading view 검증도 구분한다. 현재 최종 교차 코드검토 진행 중이며 결과 뒤 계획32/설계23/진행02를 갱신한다. 다음 개발 범위는 기존 계획28 잔여와 회의록 업무 수용 조건을 근거로 정하며 나머지9종은 사용자 확장 결정 전 개발 범위에 복귀시키지 않는다.

## 2026-10-14 · 최종 통합 검토 및 기록 종료

현재 승인 B 확장과 재개 보완에 대해 최종 읽기전용 교차 코드검토 Spec PASS / Quality PASS, 확인된 Critical·Important·Minor 미해결0이다. 필수 의견/재조회/CAS/현재head·안정된 binding/늦은 응답·PublishedRun revision 및 임시 mock fixture격리를 대조했다. 이 검토에서 시험을 반복하거나 source·DB·배포를 변경하지 않았다. 원래 초기 baseline 귀속 한계는 유지한다. 증거 `resume-final-review.md`를 저장했다.

계획32 Task1 서버·Task2/3 신청/승인 화면은 현재 범위 구현·검토 완료이며 Task4는 위에 열거한 선별 수용을 마쳤다. 전체 서비스 개통·전체 suite·실제 기관 업무 수용으로 표시하지 않는다. 설계23·진행02·계획31/32에도 현재 결과와 잔여 범위를 기록했다. Markdown 저장은 확인했고 Obsidian 앱 reading view는 미검증이다. 이후 작업은 현재 운영 DB 이력 확인과 별도 기관 시험/UAT 등 남은 범위를 구분해 진행해야 한다. 나머지9종은 사용자 지시대로 후속 확장으로 유지한다.


## 2026-10-15 · 현재 개발 DB 상태 갱신

[[2026-10-15 기존 계정 데이터 보존 및 040 개발 보류 해소 보고서]]에서기존계정/비밀번호/52업무표데이터를보존한새개발DB전환을완료했다. 현재SQL51/source51일치·040포함불일치0/pending0·서비스3개200이다. 위이전기록의040보류/primary미이행은보존된옛DB의원본직접이행이력이며현재개발DB를막는사항이아니다. 옛040원본발견/복원으로표현하지않고원본DB/이력을따로보존한다.
