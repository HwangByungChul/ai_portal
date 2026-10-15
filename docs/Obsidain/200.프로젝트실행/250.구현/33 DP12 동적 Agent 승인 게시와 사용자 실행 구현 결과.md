---
title: 33 DP12 동적 Agent 승인 게시와 사용자 실행 구현 결과
date: 2026-10-12
tags: [portal, agents, approval]
status: 실제 앱 구현 · local mock 검증
---
# 동적 Agent 승인·게시와 사용자 실행

사용자의 “네 진행 바랍니다”에 따라 [[32 DP12 동적 Agent 승인 게시와 사용자 실행 상세 계획]]을 먼저 Vault에 저장하고 구현·격리 검증·소유 local 이행을 수행했다. 실제 서비스 기능을 구현하라는 지시이며 즉시 상용 배포 요청으로 해석하지 않는다. 사용자 A 업무 허브·관리 A 운영 현황·승인 B 목록/상세와 ‘생성형 AI 플랫폼’ 명칭은 유지한다.

## 실제 구현된 범위

- 본인 명시 공유된 exact Builder trial/evaluation/version 증적에서 게시 목적·전체/선택 사용자 공개 대상·현재 게시 revision을 함께 제출한다. 회원은 현재 조직의 활성 계정/소속만 수용하며 최대200명, 요청자는 대기20건·목록20건이다. 같은 client_request_id와 같은 body는 receipt 재확인, 다른 body는409이다. 제출 대기 한도는 요청자 단위 잠금으로 경쟁을 직렬화한다.
- 현재 조직 PADMIN 중 요청자와 다른 사람이 결정한다. 승인에는 공유 상태/현재 latest version/profile/모드/고정 실행 정책/검토자 자신의 자료 ACL, generate 시험의 자동 조건 충족과 품질·보안 별도 검토 확인을 요구한다. 자동 통과 자체를 업무 품질 판정으로 취급하지 않는다. 실패/철회/자료 접근 불가 시 승인 불가, 반려는 가능하다. 반려 사유를 보존하고 새 client ID로 재요청할 수 있다.
- 승인 결정과 사용자 게시 snapshot을 같은 transaction에 기록한다. approved 버전·immutable config/profile/hash·공개 대상·모드를 봉인한다. 서로 다른 요청의 동일 게시 revision 승인은 한 건만 성공하며, 같은 요청의 동시 결정은 한 번 저장하고 같은 receipt를 반환한다. 요청 원장은 수정/삭제가 제한되고 raw ai_web/index/meter 권한은 없다.
- 관리자 승인·검증에 ‘동적 Agent 배포’ B안 목록/상세를 추가했다. 증적과 저장 prompt/profile을 검토하고 의견·품질/보안 체크·승인/반려·현재 게시 상태를 확인한다. 기존 운영 설정 승인과 Builder 증적 메뉴는 유지한다. 증적 확인 실패 시 승인 버튼을 막고 원문 질문/답변·기대조건·개인 평가를 추가 공유하지 않는다. 5초 상세 재검사는 권한 실패 시 기존 상세를 숨긴다.
- 게시 철회는 PADMIN의 현재 publication revision CAS로 저장하며 신규/진행 실행의 guard를 제한한다. 동일 철회 receipt 재확인과 audit1회, 과거 승인 receipt 조회가 다시 게시하지 않음을 검증했다. 이미 dispatch된 요청의 영수증/unknown 비용은 버리지 않고 결과 저장과 공개를 막는다. 호출 중 철회는 진행 중 네트워크 호출을 원격 취소했다는 뜻이 아니다.
- 사용자 AI 카탈로그에 현재 공개 대상·회원·고정 Agent 이용 대상·모드·자신의 자료 ACL을 통과한 게시 Agent 목록과 상세를 추가했다. 변수명과 안전한 이름/설명만 반환하며 입력→실행→최종 결과 polling→취소→본인 실행 이력을 실제 API에 연결했다. 접수 응답 유실은 같은 client_send_id로 확인한다. 각 실행은 독립적이며 다회차 대화 memory는 이번 범위가 아니다.
- 새 asset_chat은 정확한 publication revision/version/profile/composition/roles/messages/자료 version/index를 DB에 봉인한다. 일반 사용자 자신의 세션/조직·owner RLS로 실행하며 작성자/승인자를 대행하지 않는다. admission/capacity/중지/예산/dispatch/Gateway/meter/recovery를 재사용한다. RAG는 승인된 선택 자료만 검색하고 빈 범위는 embedding/generation 호출0·근거 부족으로 종료한다. private 자료는 승인자가 읽을 수 있어도 일반 사용자에 자동 전이되지 않는다.
- 고정 /runs admission은 미게시 Builder draft404를 유지하고, 동적 실행은 별도 /published-agents/{asset}/runs로만 연결했다. 요청 때와 SQL 안에서 version/publication CAS를 확인하고 worker dispatch/finish와 읽기에서 현재 공개 상태/자료를 재검사한다. 같은 조직의 타 사용자 결과404. 철회·자료 회수 뒤 최소 본인 history API metadata는 보존하며 상세 답변은 차단한다.
- published 결과는 기존 직접 대화 메시지와 분리한 원장에 저장한다. 전용 사용자 화면에서 본인 결과와 현재 접근 가능한 근거를 읽는다. 독립 실행의 대화 컨테이너와 기존 일반 대화 화면 사이의 탐색 통합, 철회된 Agent 이력의 별도 전역 목록, SSE 중간 답변은 후속 UX 작업이다.

API: admin/asset-deployments 제출/목록/상세/decision/publications/retire, published-agents 목록/상세/runs, published-agent-runs 상세/cancel. strict UUID/int/bool·extra/중복 query/CSRF·no-store/read window/32KiB body 경계를 적용했다. cancellation은 본인 동적 run만 수용하고 게시 철회 뒤에도 현재 본인 실행을 취소할 수 있다.

## 변경한 실제 파일

- `/Users/jwpios/antigravity/202610_AI 플랫폼/src/backend/migrations/036_asset_deployments.sql`
- `/Users/jwpios/antigravity/202610_AI 플랫폼/src/backend/migrations/037_published_agent_execution.sql`
- `/Users/jwpios/antigravity/202610_AI 플랫폼/src/backend/app/assets/deployments.py`
- `/Users/jwpios/antigravity/202610_AI 플랫폼/src/backend/app/assets/published.py`
- `/Users/jwpios/antigravity/202610_AI 플랫폼/src/backend/app/main.py`
- `/Users/jwpios/antigravity/202610_AI 플랫폼/src/backend/app/ai/repository.py`
- `/Users/jwpios/antigravity/202610_AI 플랫폼/src/backend/app/builder/execution.py`
- `/Users/jwpios/antigravity/202610_AI 플랫폼/src/backend/app/execution/manager.py`
- `/Users/jwpios/antigravity/202610_AI 플랫폼/src/backend/app/execution/rag.py`
- `/Users/jwpios/antigravity/202610_AI 플랫폼/src/backend/tests/support.py`
- `/Users/jwpios/antigravity/202610_AI 플랫폼/src/backend/scripts/portal_test_control.py`
- `/Users/jwpios/antigravity/202610_AI 플랫폼/src/backend/tests/test_asset_deployments.py`
- `/Users/jwpios/antigravity/202610_AI 플랫폼/src/backend/tests/test_published_agents.py`
- `/Users/jwpios/antigravity/202610_AI 플랫폼/src/backend/tests/test_dynamic_extended.py`
- `/Users/jwpios/antigravity/202610_AI 플랫폼/src/frontend/src/AssetDeploymentRequest.tsx`
- `/Users/jwpios/antigravity/202610_AI 플랫폼/src/frontend/src/AssetDeployments.tsx`
- `/Users/jwpios/antigravity/202610_AI 플랫폼/src/frontend/src/PublishedAgents.tsx`
- `/Users/jwpios/antigravity/202610_AI 플랫폼/src/frontend/src/ApprovalsPage.tsx`
- `/Users/jwpios/antigravity/202610_AI 플랫폼/src/frontend/src/SharedEvidenceReview.tsx`
- `/Users/jwpios/antigravity/202610_AI 플랫폼/src/frontend/src/CatalogPage.tsx`
- `/Users/jwpios/antigravity/202610_AI 플랫폼/src/frontend/scripts/verify-portal-builds.mjs`
- `/Users/jwpios/antigravity/202610_AI 플랫폼/src/frontend/tests/dynamic-agents.spec.ts`
- `/Users/jwpios/antigravity/202610_AI 플랫폼/src/frontend/tests/safe-reporter.ts`

## 검증과 local 반영

[[34 DP12 동적 승인 공개 대상 실행과 정산 검증]] 및 evidence/DP12-dynamic-agents에 안전 증거를 기록했다. 서버 최신166사례는 기존 회귀144 + 최종 신규22의 별도 실행 집계로 전체 suite 단일 pass가 아니다. 브라우저27 단일pass, 분리 build user24/admin31·경계pass, git diff --check pass. 모의 제공자·합성 업무 입력 검증이며 실제 모델 품질/기관 UAT가 아니다.

private600 backup 뒤 SQL036/037을 추가했다. 기존47표 모든 행 fingerprint·36 migration checksum을 보존했다. 현재50표/38migration/138security함수, 신규3표0행·재적용 무변화, primary seed/reset·합성 자산/요청/실행·정책 변경·유료 호출0. disposable DB/credentials/source/pool을 정리하고 API8000·사용자5173·관리자5174를 복구했다. 세 공개 HTTP200은 접속 확인이며 primary 인증 사용자 업무 수용시험은 아니다. SQL000~037 동결·후속038 이상.

## 미완료와 다음

이번 단위는 승인/반려/기본 재요청/공개 대상/동적 사용자 실행/게시 철회다. 전체 DP12·원본 F 전체 개발·운영 배포 완료로 확대하지 않는다. 다음은 이전 게시 버전 복원 승인·rollback 및 배포 이력 비교/상태 탐색을 먼저 설계하고 구현한다. 현재 다시 승인한 버전으로 교체하는 기능은 있지만 별도 rollback API/화면은 없다.

추가 상세 답변 공유 동의/실업무 검토 기준·승인자 배정/다단계·부서/기간별 공개·제작자 역할·동적 즐겨찾기/구독/권한신청/계열사 공유·다회차 memory·비용/토큰 상세 비교/export·batch/semantic 평가·다중 모델/secret/tool/workflow·실제 제공자/Entra ID/UAT/운영 배포는 후속이다. DP11 원문 저장소 재변조 전체 수용과 PPTX/OCR 보류·거버넌스 F050~060 제외는 유지한다. 동적 run 전용 native-process crash/재시작 및 경계별 조직 이동 브라우저 수용은 추가 검증 대상이며 기존 중앙 실행 회귀와 혼용하지 않는다. 과거 F 완료 수는 재산정하지 않았다.
