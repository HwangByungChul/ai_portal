---
title: Registry clone 검증 및 056 적용 결과
created: 2026-10-18
updated: 2026-10-18
status: applied-development-fixture
tags: [mcp, tool-gateway, migration, verification]
---
# Registry clone 검증 및 056 적용 결과

## 기준선
활성 개발 fixture는 migration 055까지 적용됐고, 052 및 전체 적용 source checksum 불일치가 없었다. MCP definitions/versions/profiles/audit 테이블은 모두 0행이었다. AI_WEB/METER/INDEX DSN이 같은 active fixture를 가리키는지도 비밀정보를 출력하지 않고 확인했다.

## 백업 및 복원
- Private custom dump를 `.runtime/backups/mcp-gateway-20261018/active-fixture.dump`에 보관했다. mode 0600, 1,184,629 bytes, SHA-256 `c37c30c444f5e9bb543134aaf2aad7f0d297bd732836dcf28c57a51957ac4b62`.
- 별도 소유 marker DB에 restore하고 security/portal/rag/ops 업무 테이블 전체 row count와 정렬 JSON digest를 대조했다. 기존 migration checksum과 함께 원본과 일치했다.

## 056 clone 검증
- 복원 clone에 신규 `056_mcp_tool_registry_control.sql`만 적용했다. 기존 업무 테이블 행 지문과 055까지 migration checksum이 보존됐다.
- `ai_web` 연결로 registry 등록, 목록, 모의 재조회, version 1→2 append를 확인했다. 일반 USER 등록은 `A0403` 거부, 타 tenant 조회는 `A0404` not-found를 반환했다. ai_web의 직접 version table UPDATE 권한은 없다.
- 초기 시도에서 중첩 집계 SQL 오류가 발견되어 profile 존재 여부를 `EXISTS`로 고친 뒤 전체 검증이 통과했다.

## 활성 개발 fixture 결과
별도 복원·검증 후 활성 fixture에 056만 적용했다. 적용 후 기존 업무 테이블 지문과 055까지 checksum이 그대로 보존됐고, 최신 migration은 056, 적용 source checksum 불일치는 0건이다. MCP 테이블은 여전히 각각 0행이다.

## 코드 및 시험
- `src/backend/app/tools/dynamic_repository.py`, `src/backend/app/tools/autowrap_routes.py`, `src/backend/migrations/056_mcp_tool_registry_control.sql`.
- `pytest src/backend/tests/test_mcp_tool_autowrap.py -q`: 9 passed(캐시 경로 권한 경고 1건). Python 구문 검사 및 `git diff --check` 통과.

## 범위 및 다음 단계
이 결과는 개발 fixture의 영속 registry 기반 준비를 뜻한다. 승인된 exact revision으로 production route를 만들거나 실제 MCP/금융 connector를 호출하지 않았다. 다음은 기존 타인 승인·게시·receipt 원장에 동적 Tool의 exact revision digest를 연결하고 회수/권한 재검사를 설계하는 단계다. Secret Manager/IdP, HITL, egress/SSRF, metadata integrity, 불변 audit/circuit breaker, 기관 sandbox/UAT 및 운영 배포는 별도 미완료다.

관련 기록: [[200.프로젝트실행/250.구현/MCP Tool Gateway 상세 구현/00 구현 추적]], [[2026-10-18 영속 Registry RPC 연결 구현 결과]]


## 관리자 화면 및 API 프로세스 후속
- 등록 확인 문구를 테넌트별 영속 Registry 저장과 개발 profile fixture 모의 실행으로 구분해 수정했다. 확정 UI의 배치/탐색 흐름은 바꾸지 않았다.
- `npm run build:admin` 통과: TypeScript 검사, 227 modules, `boundary_verified: true`. 기존 500kB chunk 경고가 남는다.
- API 서비스는 `uvicorn ...`이며 `--reload` 없이 실행 중이다. PID 56265 실행 경로는 프로젝트를 가리키지만 `scripts/service_control.py`와 일치하는 소유 process 기록이 없어 이번 작업에서 중지/재시작하지 않았다. 따라서 API 프로세스의 새 route 로드와 브라우저 왕복은 아직 확인하지 않았다.
