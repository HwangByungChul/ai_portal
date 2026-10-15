# Task3 사용자 UI · 2026-10-15

## 구현 범위
AGENT_03 회의일(초기값 없음), 최대 3개 권한 있는 원문 exact version 선택/페이지 이동/선택 재확인, 예비 합산 분량, 문서만 실행, 전체 메모 보존과 전체 payload UUID 재사용을 구현했다. 결과는 서버 봉인 회의일·검증 source_ref/quote·서버 문서 위치·원표현/기한 미확정 사유를 표시한다. 현재 이용 가능한 완료 결과에서만 사람 품질 검토를 제공한다. 4개 평가 기본값은 미평가이며 필수 의견/append-only 최신20 이력/동일 UUID 재시도/CAS 충돌 후 명시적 새 검토를 제공한다.

사용자 최우선은 **결정사항·액션아이템 정확성**이다. 이를 품질 검토 첫 항목과 설명에 명시했다. 누락/담당자/기한은 각각 유지한다. 구조 검증을 의미 정확성 합격으로 표현하지 않는다. Workflow 승인 지원에는 현재 revision2 계약/schema/digest를 표시하고 새 승인 안내를 제공한다. 다른 9종은 추후 확장이다.

프로덕션 backend 변경 0. `scripts/portal_test_app.py` 수정은 폐기형 browser fixture의 명시적 meeting provider 동작에서 revision2 JSON을 반환하기 위한 테스트 전용이다. 일반 mock/실제 provider의 의미 품질을 증명하지 않는다.

## 검증과 명령
작업 경로: repository `src/frontend`, Node `/Users/jwpios/.nvm/versions/node/v22.23.1/bin`을 PATH 앞에 추가했다.

- `npm run build:user`: exit0, tsc/vite 성공, user28 modules boundary_verified=true. `task3-review/build-user-final.txt`.
- `npm run build:admin`: exit0, tsc/vite 성공, admin43 modules boundary_verified=true. `task3-review/build-admin-final.txt`.
- `npx playwright test tests/meeting-runtime.spec.ts tests/tool-workflow-approvals.spec.ts tests/dynamic-agents.spec.ts tests/chat-operations.spec.ts --grep 'WF_03|WF_04|WF_05|WF_12|WF_10|WF_11|D12_01|B05_32'`: **8 passed, 0 failed**, runner_errors0. `browser-regressions.txt` + `browser-regressions-results.json`.
- 실제 폐기형 DB/API: WF04 Tool 정상 제출→타 PADMIN 승인→사용자 실행→철회, WF05 새 Workflow 정상 승인→문서 업로드→candidate.ready true→선택→문서만 실행→2026-10-15 봉인일→내일=2026-10-16→document 출처 2개→사람 검토 저장, D12_01 동적 Agent 승인/실행/철회. 실제 모델 호출 아님.
- HTTP stub: WF03 비동기 결과 계약, WF12 최대3건/페이지 이동/실행 응답 유실 동일 전체 payload·UUID/폼 회의일 변경 후 결과 봉인일 유지/품질 응답 유실 동일 검토 payload·UUID/CAS 명시 재시작. WF10/11 승인 identity/지연 응답, B05_32 조직 변경 후 늦은 설정 응답 회귀.
- WF05에서 1440/1024/768 각각 document.scrollWidth<=innerWidth 검사 및 full-page screenshot. Tab 대체로 review 저장 버튼 focus 후 Enter 실제 동작 확인. 최종 768 screenshot 육안 확인: 결과/근거/평가 모두 표시, 자료 선택과 평가 입력 접근 가능. 긴 Agent 목록은 제한 높이 안에서 스크롤한다.

## 실패와 수정
기존 `browser-initial.txt`, `browser-corrected.txt` 각각 2pass/1fail을 원본 그대로 보존했다. 원인은 own-source를 게시 완료까지 기다린 테스트 기대값이었다. AGENT_03는 본인 원문이 준비되면 색인/게시 전에도 사용할 수 있으므로 업로드 접수 + 실제 candidate.ready + 선택 상태로 수정했다.

후속 4개 중 3pass/1fail은 1024px 가로 overflow였다. 긴 refs wrap/min-width와 meeting route에 한정한 user header wrap, Agent 목록 스크롤을 수정해 3개 크기 모두 통과했다. `browser-layout-failure.txt` 보존. 수정 명령 1회 cwd 오지정으로 FileNotFoundError가 나서 파일을 변경하지 못했고 올바른 repo cwd에서 즉시 수정했다.

추가 문서 삭제 검증 초안은 optional title 및 `/documents` 게시목록에서 own source를 찾으려 하여 undefined 오류였다. 현재 server candidate.document_id와 `/documents/mine` 소유 목록으로 revision을 얻도록 수정했다. 삭제 응답은 기존 API 계약 HTTP200을 사용한다. 최종 결과는 아래 추가 기록을 따른다.

## 합성 fixture 정답과 한계
입력 원문: “자료를 검토하기로 했다. 김검토는 내일 자료를 확인한다.” 회의일 2026-10-15. 기대 결정 자료 검토, action 김검토/자료 확인, 원표현 내일, 정규기한 2026-10-16, 인용은 원문 그대로, source_ref는 선택한 exact version이다. 이는 합성 기술 계약 정답이며 실제 요약 적절성/누락률/담당자 문맥의 의미 정확성 검증이 아니다. 실제 provider 호출/유료 호출 0. 실제 업무자료·정답·승인 provider를 준비한 사람 의미 UAT 미완료.

미완료: UI 진행 중 source 철회 후 취소는 신규 browser 케이스로 재실행하지 않았다(Backend Task2의 71개 runtime 검증에서 철회 후 안전 취소 검증 완료). 모든 날짜 표현의 실제 모델 생성 결과, 실기관 자료, OCR/전사, 나머지9종, 운영 배포는 미완료다. 최종 리뷰/051 운영 적용/백업/서비스 복원/Obsidian 기록은 root가 담당한다.

## 변경 증적
`task3-review/paths.json`의 10개 파일. 기존 pre snapshot/manifest를 덮어쓰지 않고 각 sha256 일치를 검증했다. `post/`, `post-manifest.json`, `scoped.diff`, `capture-checks.json`, `meeting-1440.png`/`meeting-1024.png`/`meeting-768.png`로 최종 상태를 보존한다. 테스트 시도는 중복 합산하지 않으며 고유 최종 regression 8개와 확장 WF05 재검증을 구분한다.

## 최종 확장 검증과 인계
`npx playwright test tests/tool-workflow-approvals.spec.ts --grep 'WF_05'`: **1 passed / 0 failed, runner_errors0**. `browser-source-withdrawal.txt` 및 `browser-source-withdrawal-results.json`. 실제 source DELETE200 후 동일 실행 receipt 재확인에서 현재 원문 사용 불가, 초안/품질 패널 숨김, 봉인된 회의일 유지, 자료 새로고침 후 삭제된 선택 제거를 검증했다. 이 1개는 기존 WF05의 확장 재검증이며 고유 시험수를 9개로 합산하지 않는다.

최종 source package pre10/10 hash 검증, post10/10 capture, scoped.diff 완료. 폐기형 fixture 정리 및 loopback 서비스 종료는 `cleanup.json` 참조. exclusive DB/browser 소유권을 root에 반환한다. 운영 서비스는 시작하지 않았다.

## Task3 리뷰 수정 · 2026-10-15
Important/Minor 4개 모두 수정. 자료 새로고침은 선택이 있으면 권한 있는 목록의 모든 페이지를 끝까지 확인한 뒤 exact document/version을 재검증한다. 페이지 누락은 권한 회수로 간주하지 않는다. 중간 네트워크/목록 실패·반복 cursor는 선택을 유지하며 확인 미완료를 알린다. 삭제·권한 회수·ready=false로 확인된 선택은 제외 사유를 명시한다. 공통 세션/권한 invalidation은 기존 useScope 정책으로 숨긴다. 확인 중 선택 변경은 막는다.

기한 상태/사유의 현재 known code와 평가 이력 known rating을 한국어로 표시하며 알 수 없는 값은 원문을 노출하지 않고 확인 필요로 표시한다. 근거는 문서 제목·짧은 버전 식별자·페이지·위치를 먼저 표시하고 메모는 회의 메모로 표시한다. 전체 exact source_ref/version은 disclosure 안에서 확인한다. 관련 없는 ResponseFeedbackValue/AgentAccess의 meeting_context를 제거했다. 기존 child step 표시는 변경하지 않았다.

검증 명령(working directory src/frontend, PATH 앞 Node22.23.1):
- `npm run build:user`, `npm run build:admin`: 최종 corrected 로그 둘 다 exit0; tsc/vite 및 user28/admin43 boundary_verified=true.
- `npx playwright test tests/meeting-runtime.spec.ts tests/tool-workflow-approvals.spec.ts --grep 'WF_03|WF_12|WF_05'`; 후속은 동일 인자를 `./node_modules/.bin/playwright test`로 실행. WF03/WF12는 HTTP stub, WF05는 실제 폐기형 DB/API + structured mock이다. paid/real provider0, 의미 UAT 미완료 유지.
- WF12에 페이지2 선택→새로고침 유지, 목록 실패→선택 유지와 명시 안내, 성공 재확인, 삭제/회수 대역→선택 제거와 명시 안내를 추가했다. WF05는 읽기 쉬운 제목과 펼친 exact ref, 기존 상대기한/품질/삭제/1440·1024·768/keyboard를 검증한다.

실패 기록: 최초 편집 명령 `python /tmp/meeting_fix.py`는 python 명령 없음 exit127(편집 없음); `python3`로 수행. 최초 focused는 2pass/1fail: WF05의 기존 raw 출처 기대값이 변경 UI와 달랐다(`fix-browser.txt`, `fix-browser-initial-results.json`). 제목+disclosure 검증으로 변경한 두 번째 시도는 test-only candidate 변수 오타로 2pass/1fail, 같은 시점 두 build는 TS2552 exit2 (`fix-build-user.txt`, `fix-build-admin.txt`, `fix-browser-reference-failure*`). candidates로 수정 후 corrected build 둘 다 성공했다. 세 번째 focused는 WF05/WF03 pass, WF12 strict alert 2개 모호성으로 fail(`fix-browser-alert-failure*`): 의도한 목록 실패 안내를 다음 실행 실패 검사 전에 성공 새로고침으로 복구하도록 test를 수정했다. read-only ps 확인은 sandbox operation not permitted였으며 소유권 판단에 사용하지 않았다. raw private failure 파일은 보고서로 복사하지 않았다.

증적은 원래 pre/manifest를 유지하고 원래 리뷰 post/manifest/scoped.diff를 `original-post/`, `original-post-manifest.json`, `original-scoped.diff`에 보존했다. 최종 post/manifest/scoped.diff를 갱신하고 수정분만 `fix.diff`, 변경경로/hash는 `fix-changed-paths.json`, 무결성은 `fix-capture-checks.json`에 남긴다. 운영 DB/051/서비스/env/backend production/commit/Obsidian 변경 없음. 최종 통합·live 적용·문서 기록은 root 담당이다.

최종 focused 결과: **3 passed / 0 failed / runner_errors0**, `fix-browser-final.txt` + `fix-browser-final-results.json`. 이전 시도와 중복 합산하지 않는다. `fix-meeting-1440.png`/1024/768은 최종 WF05의 제목·펼친 exact ref·한국어 기한 상태 화면이다. `fix-cleanup.json`: API pool0, fixture/자격 파일/owned source store 제거=true, cluster stopped. DB/browser fixture exclusive 소유권을 root에 반환한다. 최종 hash 검증은 pre 불변/post 일치/original post 보존 모두 true.
