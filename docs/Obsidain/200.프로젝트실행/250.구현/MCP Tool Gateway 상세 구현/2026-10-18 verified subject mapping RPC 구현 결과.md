---
title: Verified subject mapping RPC 구현 결과
date: 2026-10-18
tags: [mcp, tool-gateway, oidc, saml, security]
status: database-clone-verified-api-unverified
---
# Verified subject mapping RPC 구현 결과

## 요청과 결정

- 요청: 기관 IdP 준비 전에도 가능한 다음 단계로 verified subject mapping 서버 RPC를 구현한다.
- 경계: 현재 mock SSO callback은 신원/MFA 증거로 인정하지 않는다. real verifier, issuer 설정, policy head 및 assurance evidence가 없으면 매핑 변경은 실패해야 한다.
- 매핑은 현재 로그인 계정 본인에 대한 link/revoke만 허용한다. 클라이언트 입력으로 subject, issuer, digest 또는 대상 user를 받지 않는다.

## 구현

- 새 additive migration `src/backend/migrations/061_verified_idp_subject_mapping_rpc.sql`을 추가했다.
- RPC 입력은 session/tenant/action/evidence UUID/request UUID/기대 revision이며, identity와 digest는 server-verified session evidence에서만 읽는다.
- AAL2/AAL3, 유효시간, verifier policy digest, issuer, tenant/session/user 일치 및 활성 policy head를 검사한다.
- 이벤트는 subject 원문 없이 append-only ledger에 저장한다. key version 기록, 요청 idempotency, expected revision CAS, 동일 subject 직렬화, mapping collision/revoke 상태 검사와 감사 이벤트를 포함한다.
- policy head는 기본 행이 없고 `enabled=false`만 허용되도록 제약했다. 별도 verifier 및 활성화 계약이 추가되기 전에는 호출이 항상 fail-closed다.
- `ai_web` 직접 테이블 DML/조회 권한은 추가하지 않고 RPC 실행만 부여한다. self-scoped RLS를 추가해 타 사용자 계정 연결을 막는다.

## 검증과 제한

- private backup `active-fixture.dump` (head 055)를 두 개의 disposable DB로 복원해 비교 baseline과 적용 clone을 분리했다. clone에서 migrations 056–061을 적용했고 head 061, migration entries 62, source checksum mismatch 0을 확인했다.
- baseline의 기존 74개 테이블/322행 JSONB 지문이 모두 동일했고, 신규 assurance/evidence/mapping/policy-head 테이블 4개는 비어 있었다. 네 테이블 모두 ENABLE/FORCE RLS, `ai_web` 직접 SELECT/INSERT 권한 없음, RPC EXECUTE는 `ai_web`만 있고 PUBLIC은 거부, self-scoped evidence INSERT policy 1개와 immutable trigger 3개를 확인했다.
- 첫 적용 시 migration 선택 스크립트 오류는 첫 트랜잭션에서 중단되어 반영되지 않았다. 수정된 migration 선택으로 fresh restore clone에서 전체 적용·검증을 완료했다. 임시 cluster를 종료·삭제했고 port 55433 해제를 확인했다. regular devdb는 stopped 상태이며 적용하지 않았다.
- `POST /api/v1/auth/idp/subject-mapping` 및 tenant-scoped repository를 연결했다. 기존 세션 cookie, CSRF, `X-Tenant-ID` 검증을 재사용하며 요청은 action/evidence UUID/request UUID/expected revision만 받고 여분 속성 및 query를 거부한다. DB 오류를 고정된 API 오류코드로 번역하고 원문 subject/digest를 반환하지 않는다. `git diff --check` 통과. HTTP 왕복/pytest는 실행하지 않았다.
- 실제 assertion evidence가 없어 RPC 정상 경로/부작용 행 생성은 호출하지 않았다. IdP verifier, assurance provenance, HMAC 생성·회전, live idempotent retry는 미검증·미구현이다. 운영 준비/기관 수용 완료로 표현하지 않는다.

## 다음 작업

1. 기본 fixture를 건드리지 않고 private backup 기반 disposable clone에서 migrations 059–061을 적용하고 checksum/기존 행 fingerprint를 검증한다.
2. 전용 clone에서 비활성 정책, evidence 부재, tenant/session/user 불일치, stale revision, replay, link/revoke 및 collision 경계를 확인한다.
3. 이후 real verifier와 keyed digest service를 별도 구현하고, 기관 issuer/metadata 및 claim assurance 계약이 준비되기 전에는 활성화하지 않는다.

관련: [[00 구현 추적]], [[2026-10-18 exact revision 승인 gate OIDC-SAML 설계]]
