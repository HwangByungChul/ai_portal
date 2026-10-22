---
title: 동적 production dispatch fail-closed 보강
created: 2026-10-18
updated: 2026-10-18
status: implemented-reviewed
tags: [mcp, gateway, security, fail-closed]
---
# 동적 production dispatch fail-closed 보강

## 요청과 결정
기관 IdP·MFA와 exact-revision 게시 승인 gate가 준비되지 않은 상태에서 동적 MCP Tool의 `approved_published` 상태만으로 production endpoint에 도달할 수 있는 경로를 닫는다. 현재 게시·실행 gate가 완성될 때까지 dynamic tool 실제 dispatch는 허용하지 않는다.

## 변경
- `src/backend/app/tools/dynamic_gateway.py`: `invoke_routed` 진입 시 `publication_status="approved_published"`를 `TOOL_DYNAMIC_REVIEW_ONLY` / HTTP 409로 거부한다. 거부는 tool 조회, 인자 처리, idempotency 변경, profile 선택, protocol dispatch, audit 기록 전에 발생한다. 미게시 호출의 개발 simulation 경로는 유지한다.
- `src/backend/tests/test_mcp_tool_autowrap.py`: 기존 published→production 성공 기대를 fail-closed 회귀 검증으로 바꿨다. 개발 simulation 지속 동작과 profile/dispatch/audit/idempotency 부작용 부재를 확인한다.
- 공개 invoke route는 기존대로 서버가 `draft`를 전달하며 변경하지 않았다.

## 실제 검증
- 회귀 테스트 사전 RED: 기존 동작에서 production dispatcher에 진입했고, 테스트는 고정 409 대신 `TOOL_EXECUTION_FAILED`를 받아 실패했다.
- 사후 focused 검증: `PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m pytest tests/test_mcp_tool_autowrap.py --noconftest -p no:cacheprovider -q` — `9 passed in 0.58s`.
- `git diff --check -- app/tools/dynamic_gateway.py tests/test_mcp_tool_autowrap.py` 통과.
- 독립 task review: PASS. guard 선행성, side effect 부재 검증, 개발 simulation 유지 확인.

## 미완료 범위와 한계
IdP 실제 서명 검증·MFA evidence, Secret Manager, exact-revision 다중 승인·게시·호출 권한 gate, 실제 MCP transport/connector, 영속 audit는 미구현이다. 테스트는 PostgreSQL 비의존 focused 단위 테스트이며 기관 수용·운영 배포 증거가 아니다. 운영 dispatch는 계속 차단 상태다. 변경은 미커밋 작업 트리에 있으며 commit/deploy하지 않았다.

## 다음 작업
기관 IdP issuer/metadata, subject claim, MFA assurance/freshness/replay, Secret Manager 정책 결정 전까지 verifier는 비활성 fail-closed로 유지한다. 이후 exact-revision 승인/call gate의 데이터 계약과 승인자·상태 전이를 구체화하고 disposable clone에서만 검증한다.

## 관련 기록
- [[200.프로젝트실행/250.구현/MCP Tool Gateway 상세 구현/00 구현 추적]]
- [[400.프로젝트관리/02 포털 UI UX 작업 기록]]
