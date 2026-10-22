---
title: AI Builder 자연어 초안 생성 Task 2 구현 결과
created: 2026-10-22
updated: 2026-10-22
status: implementation-complete-runtime-validation-pending
tags: [ai-platform, builder, implementation, backend]
---

# AI Builder 자연어 초안 생성 Task 2 구현 결과

## 요청·결정

승인된 구현 계획의 Task 2를 진행했다. 제안 생성은 owner/tenant 범위에서 비공개 초안으로 저장한다. 비용·예약·감사는 기존 AI call/usage ledger만 사용하며 `portal.messages`에 프롬프트를 적재하지 않는다. Agent/Workflow 실행, Tool 호출, 자산 저장·승인·게시를 이 경로에서 수행하지 않는다.

## 변경 파일

- `src/backend/migrations/069_builder_scaffold_shared_meter.sql`: `ops.call_attempts`의 제안 바인딩, 예약/디스패치/실패·완료·폐기 RPC, 공유 원장·감사 경계
- `src/backend/app/builder/scaffold_repository.py`, `scaffold_service.py`, `scaffold_routes.py`: `call_meter` 정산을 쓰는 비대화형 생성 경로와 POST/GET/DELETE API
- `src/backend/app/ai/gateway.py`, `src/backend/app/main.py`: trace-aware guardrail, 서비스 및 라우터 등록
- `src/backend/tests/test_builder_scaffold_repository.py`, `test_builder_scaffold_migration.py`, `test_builder_scaffolds.py`, `test_db_migration_clone.py`: focused contract/clone guard tests
- `src/backend/scripts/verify_builder_scaffold_clone.py`: 명시적 `_builder_clone` DB에만 실행하고 rollback하는 검증 harness

## 실제 검증

- Focused pytest 116 passed. `git diff --check` 통과.
- migration 068의 SHA-256 `d70eb773d2e252c4336dcf6d3ff3e0671ab509a774c47e32681567ac04fbda1b` 확인 및 테스트 assertion 추가. 기존 migration은 수정하지 않았다.
- DB에는 migration을 적용하지 않았다. 따라서 SQL/RLS의 실제 런타임, 기존 데이터 보존, disposable clone 검증 결과는 아직 없다.

## 남은 범위·다음

별도 disposable clone을 준비한 뒤 전 migration checksum과 기존 데이터 지문을 보존하는지 확인하고, `AI_BUILDER_DISPOSABLE_CLONE_DSN`으로 Builder clone harness를 실행해야 한다. 완료 후 독립 코드 검토가 필요하다. 실제 유료 provider, 기관 UAT, 운영 배포, 생성 제안의 자산 저장·실행은 이번 결과에 포함하지 않는다.

## 관련 문서

- 계획: [[240.설계/2026-10-21 AI Builder 자연어 초안 생성 서비스 구현 계획]]
- 작업 기록: [[400.프로젝트관리/02 포털 UI UX 작업 기록]]
