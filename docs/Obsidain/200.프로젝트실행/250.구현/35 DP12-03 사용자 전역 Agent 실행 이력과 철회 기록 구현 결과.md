---
title: 35 DP12-03 사용자 전역 Agent 실행 이력과 철회 기록 구현 결과
date: 2026-10-12
tags: [portal, history, execution]
status: 실제 앱 구현 · local mock 검증
---
# 사용자 전역 Agent 실행 이력

사용자 “네 진행 바랍니다”에 따라 [[34 DP12-03 사용자 전역 실행 이력과 철회 Agent 기록 탐색 계획]]을 Obsidian에 먼저 저장하고 구현·격리 검증·local 추가 이행을 진행했다. 이전 [[34 DP12-02 이전 게시 버전 복원 승인과 배포 이력 비교 구현 결과]]의 확정 화면·승인/게시·개인 owner·정산 경계를 유지한다.

## 실제 구현

사용자 메뉴와 `/user/agent-history` 직접 진입, AI 업무의 ‘독립 Agent 실행 이력 보기’에서 본인 전역 동적 실행을 탐색한다. 고정 대화·문서 요약·관리자 private 시험과 구분하며 독립 실행을 일반 대화 메시지/memory에 끼워 넣지 않는다. 카탈로그에서 철회 Agent가 사라져도 이력은 독립적으로 남는다. 상태 필터·시간 역순20건/더보기·선택 상세·현재 정산 결과·실행 취소·카탈로그 이동을 제공한다.

`GET /api/v1/published-agent-runs` optional cursor/asset_id/state와 `GET /api/v1/published-agent-runs/{run}/record`는 새 `security.published_run_history` capability를 사용한다. 현재 인증/조직·활성 membership을 검증하고 기존 owner forced RLS 및 명시 owner 조건으로 asset_chat만 조회한다. cursor는 같은 owner/조직/asset/state 범위여야 하며 다른 사용자/조직·builder_trial cursor는404다. query extra/중복/state enum/UUID는422·read window/no-store를 적용한다.

record는 run/asset UUID·실행 당시 버전/게시 revision·상태/revision·시간·실행 모드·종료 여부·현재 상세 허용 여부만 반환한다. exact publication/현재 대상/자신의 자료·출처 권한의 기존 guard를 통과한 경우에만 현재 이름을 제공한다. 철회/버전 변경/대상 회수/자료 회수 시 이름도NULL이며 질문/답변/자료/프롬프트/공개 대상 회원은 제공하지 않는다. 최소 metadata는 상세·실행 권한 부여가 아니다.

실행 답변은 기존 `/published-agent-runs/{run}`에서 매번 현재 guard를 재검사한다. 이전 게시 revision과 달라지는 B0401 오류를 사용자에게 내부 DB 오류로 내보내던 기존 문제는 PublishedRepository에서404로 변환했다. 다른 예상하지 못한 DB 오류는 숨겨 성공 처리하지 않는다. 목록/metadata/detail을 분리하고 active1초/terminal5초·focus/visibility 재검사, scope/selection generation·단일 refresh로 늦은 답변을 무시한다. 권한 실패 시 현재 답변을 숨긴다. 모든 비선택 이력 목록을 실시간 push 갱신하는 기능은 아니다.

진행 중 기록은 상세 조회가 제한된 이후에도 본인 기존 취소 API를 사용할 수 있다. 취소 CSRF/revision/owner 검사는 유지하며 실패/409 시 record 재확인, 추가 모델 발사는 없다. 원장 질문/답변·출처·비용/과거 version과 게시 상태를 변경하지 않고 owner 조회 인덱스·이력 함수와 기존 취소 함수의 동적 응답 분기를 추가했다. 취소 API의 raw runs SELECT 권한 오류와 철회 답변 guard 때문에 취소가 rollback되는 기존 문제를 수정했다. owner record capability로 동적 실행을 먼저 검증하고 run_cancel은 기존 write/row lock/revision/audit/session 검사와 상태 변경을 그대로 수행하되 asset_chat만 최소 record를 반환한다. 일반 대화 취소 응답과 답변 상세 guard는 유지한다. 개인정보/실행 원문을 새 로그나 Vault evidence에 복사하지 않는다.

## 실제 변경 파일

- `/Users/jwpios/antigravity/202610_AI 플랫폼/src/backend/migrations/039_published_run_history.sql`
- `/Users/jwpios/antigravity/202610_AI 플랫폼/src/backend/app/assets/published.py`
- `/Users/jwpios/antigravity/202610_AI 플랫폼/src/backend/tests/test_published_history.py`
- `/Users/jwpios/antigravity/202610_AI 플랫폼/src/backend/tests/test_asset_rollback.py`
- `/Users/jwpios/antigravity/202610_AI 플랫폼/src/backend/tests/support.py`
- `/Users/jwpios/antigravity/202610_AI 플랫폼/src/frontend/src/PublishedRunHistory.tsx`
- `/Users/jwpios/antigravity/202610_AI 플랫폼/src/frontend/src/ChatPage.tsx`
- `/Users/jwpios/antigravity/202610_AI 플랫폼/src/frontend/apps/user-web/src/App.tsx`
- `/Users/jwpios/antigravity/202610_AI 플랫폼/src/frontend/tests/published-history.spec.ts`

## 검증과 local 적용

[[36 DP12-03 실행 이력 소유권 철회와 현재 답변 권한 검증]] 및 evidence/DP12-user-history. 서버 최신52개는 수정 후 별도 실행 집계이며 전체 backend 단일 suite 통과가 아니다. 브라우저 최신12(기존9+최종 신규3 별도 실행), user25/admin32 분리 build·코드 경계·git diff --check를 확인했다. 기존 rollback 이행 테스트는 through038 경계로 고정하고039 신규 보존 테스트를 별도로 두었다. SQL000~038 원본은 바꾸지 않았다.

primary private600 백업 후039만 적용했다. 기존51표 모든 행/열 값과39 migration checksum 보존,51표/40migration/141security함수·재적용 무변화·primary seed/reset/합성 업무/paid0을 확인했다. 격리 fixture·private source/credentials·pool 정리 후 API8000·사용자5173·관리자5174 HTTP200으로 복구했다. SQL000~039 동결·다음040 이상. 실제 앱의 local 모의 제공자 검증이며 실제 모델·Entra·기관 UAT·운영 배포가 아니다.

## 미완료와 다음 작업

이번 단위는 사용자 전역 동적 이력 탐색·철회 최소 기록·현재 허용 답변·독립 대화 화면에서의 이동이다. 모든 고정/요약/동적 실행을 하나의 원장 UI로 합친 것이 아니다. 제목/핀/삭제·내보내기·다회차 memory·이력 비용/토큰 상세·과거 version 답변 재허가와 모든 권한 회수 브라우저 경계는 남아 있다.

다음은 동적 Agent 즐겨찾기/My Agent 연동의 별도 상세 계획이다. 기존 고정 Agent 즐겨찾기와 동적 자산을 혼용하지 않고 개인 선호가 권한을 부여하지 않는 계약을 적용해야 한다. DP11 미완료·secret/다중모델 Registry·tool/workflow·복잡 승인·실 provider/Entra/UAT/운영 배포는 유지한다. 전체F 완료 수를 재산정하지 않는다.
