---
title: 동적 Tool revision digest 불변성 migration 구현안
created: 2026-10-18
updated: 2026-10-18
status: source-added-clone-validation-pending
tags: [mcp, tool-gateway, metadata-integrity, migration]
---
# 동적 Tool revision digest 불변성 migration 구현안

## 요청과 결정
Secret Manager 제품이 미정이어서 특정 SDK를 선택하지 않는다. exact-revision 승인에 앞서, 공급자에 종속되지 않는 동적 Tool registry revision의 schema/source metadata 무결성 기반을 추가한다. 기존 migration은 수정하지 않으며 새 `062` migration만 추가한다.

## 구현
`src/backend/migrations/062_mcp_tool_version_integrity.sql`은 다음을 수행한다.
- tenant, tool ID, revision number, `mcp_tool_spec`, `raw_source_spec`를 canonical JSONB로 묶어 SHA-256 digest를 저장한다.
- 기존 버전이 있으면 digest를 채우고, digest 길이 32 byte 제약을 적용한다.
- 신규 revision insert 시 DB가 digest를 계산한다. 명시적 digest가 내용과 다르면 거부한다.
- version row의 UPDATE/DELETE를 immutable violation으로 거부한다.
- 기존 API와 registry write RPC는 바꾸지 않는다. `integrity_digest`는 DB trigger가 채워준다.

## 경계
이 migration은 metadata를 등록 검토에 묶는 무결성 기반이며, tool poisoning을 완전히 탐지하거나 publish/call을 승인하지 않는다. `tools/list`/`tools/call`은 계속 fail-closed이고 동적 Tool 승인 scope도 `registration_review_only`다. 현재 DB에는 적용하지 않았다.

## 확인과 미완료
`git diff --check`와 SQL 변경의 수동 구조 검토만 수행한다. 별도 backup clone에서 migration 전/후 row fingerprint, checksum, role/RLS 및 insert-digest/update-delete denial을 확인하기 전에는 적용하지 않는다. 이번 회차에는 DB·fixture·API 프로세스·migration ledger를 변경하지 않았다.

## 다음
폐기 가능한 backup clone에서 062 적용·검증을 수행한다. 그 뒤 stored digest를 review descriptor에 포함해 exact revision 승인 계약과 묶고, MFA evidence가 없는 동안 승인·게시 전이는 계속 닫아 둔다. Secret Manager 제품 결정 시 vendor adapter는 별도로 추가한다.

관련: [[00 구현 추적]], [[2026-10-18 동적 Tool 승인 gate 계약 조사 결과]], [[2026-10-18 동적 Tool 보수적 위험정책 구현 결과]], [[100.프로젝트계획/38 금융 특화 MCP Tool Gateway 상세 구현 계획안]], [[400.프로젝트관리/02 포털 UI UX 작업 기록]]
