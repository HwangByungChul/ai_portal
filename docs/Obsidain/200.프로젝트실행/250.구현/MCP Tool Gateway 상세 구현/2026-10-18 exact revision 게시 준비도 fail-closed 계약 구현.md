---
title: exact revision 게시 준비도 fail-closed 계약 구현
created: 2026-10-18
updated: 2026-10-18
status: implemented-reviewed
tags: [mcp, tool-gateway, exact-revision, fail-closed]
---
# exact revision 게시 준비도 fail-closed 계약 구현

## 요청·결정
IdP/MFA 및 실제 게시 승인 workflow가 아직 정해지지 않아 publication/execution 권한은 열지 않는다. 대신 관리자 승인 상세 API가 요청 시점 descriptor와 현재 서버 descriptor의 exact-revision 일치 여부 및 고정 차단 사유를 표시하도록 구현한다. 이 응답은 정보성 상태이며 허가 증거가 아니다.

## 변경
- `src/backend/app/tools/publication_gate.py`: server-owned `tool_id`, `revision_number`, `digest`, `risk_policy_id`, `risk_policy_revision`을 검증·비교하는 side-effect-free helper를 추가했다. malformed/stale 값은 false와 안정된 blocker code를 돌려준다. 어떤 입력에서도 `publishable=false`, `execution_ready=false`를 반환한다.
- `src/backend/app/tools/routes.py`: 동적 등록 검토 전용 approval detail에만 `publication_gate` 객체를 추가했다. descriptor는 현재 tenant-scoped repository에서 다시 읽는다. 정적 Tool 응답 형식은 유지한다.
- `src/backend/tests/test_dynamic_publication_gate.py`: 동일 snapshot, registry revision/digest 변경, risk policy revision 변경, 누락/잘못된 digest, client-supplied status/environment/MFA/readiness 필드 비승격을 검증한다.
- DB schema/migration, 승인 decision, tools/list/call, production routing은 변경하지 않았다.

## 실제 검증
- `PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m pytest -q --noconftest -p no:cacheprovider tests/test_dynamic_publication_gate.py` — `5 passed in 0.15s`.
- 지정 파일 `git diff --check` 통과.
- 독립 구현 리뷰 PASS. 리뷰어는 fail-closed 불변식과 static response compatibility를 확인했다.

## 미완료 범위·한계
승인 상세 HTTP/API 통합 왕복 자체는 테스트하지 않았다. 기관 IdP 검증·MFA evidence, exact-revision quorum/결정/게시 RPC, 실제 connector 및 durable receipt/audit는 미구현이다. 일치 결과는 승인이나 게시가 아니며 실제 production 호출은 계속 차단 상태다. 변경은 미커밋이고 배포하지 않았다.

## 다음 작업
기관 IdP issuer/metadata, immutable subject claim, MFA assurance/freshness/replay, Secret Manager 선택 전까지 positive authorization은 추가하지 않는다. 다음 구현 단계에서 exact-revision request/decision ledger와 게시 transaction의 새 additive migration을 설계하고, 기존 migration을 수정하지 않은 채 별도 백업 clone에서만 검증한다.

## 관련 기록
- [[200.프로젝트실행/250.구현/MCP Tool Gateway 상세 구현/00 구현 추적]]
- [[2026-10-18 동적 production dispatch fail-closed 보강]]
- [[400.프로젝트관리/02 포털 UI UX 작업 기록]]
