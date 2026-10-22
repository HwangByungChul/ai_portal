---
title: 영속 Registry RPC 연결 구현 결과
created: 2026-10-18
updated: 2026-10-18
status: partial
tags: [mcp, tool-gateway, registry, database]
---
# 영속 Registry RPC 연결 구현 결과

## 요청과 범위
금융 특화 MCP Tool Gateway 상세 계획의 T035-B를 진행했다. 기존 migration 052의 테이블을 사용하고 새 `056_mcp_tool_registry_control.sql` SECURITY DEFINER RPC와 서버 저장소를 추가했다. 활성 DB 적용은 수행하지 않았다.

## 기준선 확인
- 활성 개발 fixture 적용 이력: 055까지, 056 미적용.
- migration 052 적용 확인. 적용된 migration의 소스 checksum 불일치: 0건.
- `mcp_tool_definitions`, `mcp_tool_versions`, `mcp_tool_endpoint_profiles`, `mcp_tool_audit_logs` 행 수: 각각 0.
- DB inspection은 읽기 전용으로 수행했다. 이후 fixture PostgreSQL이 중지 상태여서 별도 fixture clone 및 RPC 검증을 시작하지 않았다.

## 구현 변경
- `src/backend/app/tools/dynamic_repository.py`: 등록/목록/모의 실행 재수화 기능을 RPC 경유 저장소로 추가했다.
- `src/backend/app/tools/autowrap_routes.py`: 등록/목록은 tenant-scoped repository를 사용하고 모의 invoke 전 영속 정의/profile을 재조회하게 변경했다.
- `src/backend/migrations/056_mcp_tool_registry_control.sql`: additive migration. 서버에서 인증된 tenant admin만 등록/목록/모의용 profile 조회를 할 수 있게 제한하고, schema revision을 append한다. 클라이언트 직렬 SQL 권한이나 credential 입력을 허용하지 않는다.

## 확인 결과와 한계
- Python 변경 파일 `py_compile` 통과(캐시 경로 `/private/tmp` 사용), `git diff --check` 통과.
- 이번 Registry/RPC 코드의 fixture DB 테스트는 실행하지 못했다. 실행 시도는 소유 PostgreSQL이 중지되어 `CLUSTER_NOT_RUNNING`으로 종료됐다.
- 056은 미적용이므로 현재 활성 앱에서 영속 Registry 기능을 사용할 수 있는 상태로 보지 않는다. 활성 DB를 변경하지 않았다.
- profile은 비밀정보 없이 endpoint/protocol 메타데이터만 저장한다. RPC 입력 URL의 HTTPS 형태 확인은 SSRF/egress allowlist 검증을 대체하지 않는다. 외부 호출은 계속 fixture simulation이며 실 connector, approval/receipt gate, Secret Manager, 불변 audit 구현은 미완료다.

## 다음 작업
1. 소유 fixture DB의 서비스 복구 여부와 운영자 지시를 확인하고, 별도 fixture clone에서 056 적용·기존 checksum/행 보존·정상 및 비인가 RPC 시나리오를 순차 검증한다.
2. 검증 후 backup/restore 계획에 따라 활성 개발 fixture 적용 필요성을 판단한다.
3. 승인·게시 exact revision과 실행 receipt를 연결하기 전까지 production route를 만들지 않는다.

관련 추적: [[200.프로젝트실행/250.구현/MCP Tool Gateway 상세 구현/00 구현 추적]]


## 2026-10-18 검증 및 적용 후속 기록

- 056 migration의 초기 clone 시도에서 `list` 응답 쿼리의 중첩 집계 오류를 발견했다. 프로파일 여부를 `EXISTS`로 검사하도록 migration SQL을 수정한 후 재검증했다.
- 055 기준으로 구성한 disposable fixture clone에 056만 적용했다. 055 이전의 모든 business table row/digest와 migration checksum이 일치했다. 등록·목록·revision 1→2 append·simulation profile 재조회가 통과했고, 일반 USER 등록은 거부됐으며 타 tenant의 정의 조회는 not-found로 차단됐다. `ai_web`의 version table 직접 UPDATE 권한은 부여되지 않았다.
- 활성 개발 fixture는 사설 custom dump로 백업한 뒤 새 marker DB에 복원했다. 복원본의 전체 대상 business table row/digest와 기존 migration checksum이 원본과 일치했다. 검증 완료 후 활성 fixture에 056만 적용했으며 기존 행 지문과 기존 checksum은 보존됐다. 최종 migration은 056, source checksum mismatch 0건, registry/versions/profiles/audit 초기 행 수는 각각 0이다.
- 비공개 backup: `.runtime/backups/mcp-gateway-20261018/active-fixture.dump`, 1,184,629 bytes, SHA-256 `c37c30c444f5e9bb543134aaf2aad7f0d297bd732836dcf28c57a51957ac4b62`.
- `pytest src/backend/tests/test_mcp_tool_autowrap.py -q`: 9 passed. `.pytest_cache` 쓰기 경고 1건(권한 제한)이 있었으나 시험 결과에는 영향이 없었다. Python `py_compile` 및 `git diff --check`도 통과했다.
- 기존 fixture PostgreSQL은 이 작업 시작 당시 중지 상태였고, 작업 중 프로젝트 소유 확인 후 기동했다. 기존 서비스 포트는 중지하지 않았다.

**적용 범위 주의:** 056 활성 적용은 영속 metadata registry를 준비한 것이다. 실제 connector 실행, 자동생성 Tool의 금융 승인·게시·receipt 연계, 자격증명 저장/전달, 불변 감사 완성, 사용자 브라우저 수용 및 운영기관 연결은 구현 완료가 아니다.
