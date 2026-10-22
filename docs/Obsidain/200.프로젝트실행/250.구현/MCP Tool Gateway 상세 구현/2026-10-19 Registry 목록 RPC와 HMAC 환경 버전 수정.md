---
title: Registry 목록 RPC와 HMAC 환경 버전 수정
created: 2026-10-19
updated: 2026-10-19
status: source-ready-clone-blocked
tags: [mcp, tool-gateway, settings, unit-test]
---
# Registry 목록 RPC와 HMAC 환경 버전 수정

## 요청과 결정
전체 변경 리뷰에서 확인한 목록 집계와 단일 HMAC 키 버전 환경값 처리를 한 번의 수정 작업으로 보강했다. 기존 056 파일은 수정하지 않고 새 063에 읽기 전용 tenant-authorized RPC를 추가했다. 기존 repository는 Python list를 반환하고 route는 `items`와 `total`로 감싸므로 이 계약을 유지했다.

## 변경 파일
- `src/backend/migrations/063_mcp_tool_registry_list_rpc.sql`: `security.mcp_tool_registry_list(uuid,uuid)`. `operations_authorize(...,'agent_admin',false)` 후 기존 FORCE RLS 아래 현재 tenant의 enabled Tool을 조회한다. 최신 revision lateral join과 profile EXISTS로 행을 늘리지 않으며 단일 `jsonb_agg`에 이름/Tool ID 순서를 지정한다. 반환은 빈 목록을 포함한 하나의 `{'items': [...]}`다. 함수 owner/search_path/EXECUTE ACL 및 직접 table 접근 금지를 유지한다.
- `src/backend/app/tools/dynamic_repository.py`: 목록만 전용 RPC로 변경하고 기존 error translation을 유지했다.
- `src/backend/app/config.py`: 단일 버전 환경값의 ASCII 숫자 문자열을 명시적으로 정수 변환한다. 직접 생성값에는 StrictInt를 유지하여 bool/float/string을 거부하며, 양수 1..32767과 기존 tuple 검증을 보존했다.
- `src/backend/tests/test_dynamic_registry_list.py`, `src/backend/tests/test_idp_subject_settings.py`: DB 비의존 회귀 검증.

## 실제 검증
backend 디렉터리에서 실행했다.

```text
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m pytest --noconftest -p no:cacheprovider tests/test_dynamic_registry_list.py tests/test_idp_subject_settings.py -q
RED: 3 failed, 26 passed in 1.06s
```

두 목록 케이스가 기존 RPC 호출로 실패했고, 잘못된 공백 포함 환경 버전이 거부되지 않아 실패했다. 설치된 pydantic-settings는 이미 정상 환경 문자열 `1`을 변환하고 있었으므로 그 정상 케이스는 RED에서도 통과했다. 명시적 변환은 이 라이브러리의 암묵적 처리 의존을 없애고 malformed 입력을 거부한다.

```text
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m pytest --noconftest -p no:cacheprovider tests/test_dynamic_registry_list.py tests/test_idp_subject_settings.py tests/test_config.py tests/test_idp_verifier_boundary.py -q
GREEN: 47 passed in 0.75s
```

scoped `git diff --check`와 새 파일의 `git diff --no-index --check /dev/null <file>`를 수행했으며 공백 오류가 없었다(no-index의 exit 1은 /dev/null과의 차이 표시다). 056 SHA-256은 전후 `3c6c2ea2d59d1936d8a08571719f6e043e7ec3ac021ad917353381698486ded0`으로 동일했다.

## 미완료와 다음 작업
`.runtime/backups/mcp-gateway-20261018/active-fixture.dump`는 존재 여부만 확인했으며 결과는 false였다. clone 검증은 **BLOCKED**다. 063은 소스만 추가했고 migration 적용·복원·DB/fixture/service 실행은 하지 않았다. SQL 실행, 다중 Tool 집계/빈 목록/권한/RLS의 실제 DB 검증과 기존 행/checksum 보존은 미검증이다. 실행 중 DB의 목록 결함이 해결됐다고 주장하지 않는다. 검증된 백업을 확보한 뒤 disposable clone에서 이 범위를 확인해야 한다. 승인·게시·실행 및 기관 수용·운영 배포의 완료 상태는 아니다. 변경은 staging/commit하지 않았다.

관련: [[200.프로젝트실행/250.구현/MCP Tool Gateway 상세 구현/00 구현 추적]], [[400.프로젝트관리/02 포털 UI UX 작업 기록]], [[2026-10-18 Registry clone 검증 및 056 적용 결과]].
