---
title: native DB pool 경계 단위 검증
date: 2026-10-18
tags: [mcp, tool-gateway, database-boundary, verification]
status: unit-verified
---
# Native DB pool 포트·소유 마커 경계 단위 검증

## 요청과 범위
이전 Gateway HTTP 왕복 검증은 테스트 전용 pool adapter를 주입해 native pool의 DSN 포트 검사와 PostgreSQL database ownership marker 검사를 우회했다. 해당 경계만 별도 단위 검증했다. 활성 devdb나 fixture를 기동·수정하지 않았고, production DB 호출도 하지 않았다.

## 변경
- `src/backend/tests/test_db_native_boundary.py` 추가.
- 유효한 나머지 설정을 가진 port 55433 DSN이 `WEB_CONFIGURATION_REJECTED`로 거절되고 `AsyncConnectionPool`을 생성하지 않는지 확인한다.
- 역할·권한·port 조건은 유효하지만 database marker만 다른 async stub이 `WEB_DATABASE_REJECTED`로 거절되며 오류 메시지에 marker/host/port 세부값이 노출되지 않는지 확인한다.
- production code와 migration은 변경하지 않았다.

## 검증 결과
- 실행: `PYTHONDONTWRITEBYTECODE=1 .venv/bin/pytest -q -p no:cacheprovider tests/test_db_native_boundary.py`
- 결과: `2 passed in 0.05s`.
- Test reviewer: Spec compliant / Task quality Approved; Critical·Important·Minor 지적 없음.
- Whole-change reviewer: clean verdict, concrete finding 없음.
- 격리 구현 copy에서 subagent가 만든 첫 작업 결과는 `9d969f8`였으나 임시 실행 환경이 handoff 후 정리되어 사라졌다. 동일한 단일 테스트 파일만 현재 backend working tree에 복원하고 다시 검증·검토했다. 현재 repository 변경은 미커밋이며, 기존 main의 다른 미커밋 변경을 포함하지 않도록 커밋하지 않았다.
- 테스트는 PostgreSQL service 또는 DB fixture를 사용하지 않는다.

## 미완료 범위
실제 native pool startup과 live PostgreSQL marker 검증은 본 단위 테스트로 확인하지 않았다. 외부 MCP connector, 승인 후 production call, 기관 sandbox, 운영 배포도 미수행이다. MFA/IdP·publication gate와 connector 준비 전까지 외부 호출은 계속 차단 상태다.

## 다음 작업
기관 issuer/metadata, immutable subject claim, MFA assurance allowlist/freshness/replay 및 key rotation 계약을 확보한다. 미정 상태에서는 실제 verifier/evidence issuer를 활성화하지 않는다.

관련: [[00 구현 추적]], [[400.프로젝트관리/02 포털 UI UX 작업 기록]], [[2026-10-18 062 backup clone 검증 결과]].
