---
title: exact revision 승인 gate OIDC-SAML 설계
created: 2026-10-18
updated: 2026-10-18
status: partial-implementation-provider-contract-pending
tags: [mcp, tool-gateway, exact-revision, approval, oidc, saml, mfa]
---
# exact revision 승인 gate OIDC/SAML 설계

## 요청과 범위
MCP Tool Gateway의 다음 단계로 exact revision 승인, 독립 다중 승인, MFA step-up 및 게시/호출 시점을 분리하는 설계를 작성한다. 사용자 답변에 따라 기관의 기존 OIDC 또는 SAML IdP를 대상으로 한다. 공급자별 claim 값과 metadata는 아직 확인되지 않았으므로 특정 제품을 가정하지 않는다. 이번 회차에서는 설계 기반 fail-closed 저장 계약 migration 059와 subject mapping ledger migration 060을 추가했다. IdP verifier·issuer 설정·활성화·승인 전이 코드는 아직 구현하지 않았다.

## 현재 코드 기준선
- `security.sessions`에는 session/token/user/auth_revision 및 시간·폐기 정보만 있고 IdP issuer/subject, MFA assurance, 재인증 시각이 없다. 로그인 token 발급 경로도 IdP 검증 결과를 저장하지 않는다.
- 기존 Tool 승인 함수는 PADMIN 타인 승인, 자기 승인 방지, expected revision CAS 및 append-only `approval_reviews`를 제공한다. Migration 058은 동적 descriptor의 revision/digest를 서버 계산하며 `registration_review_only`의 승인 전이를 API와 DB trigger에서 막는다.
- 동적 Tool은 실제 connector handler 및 durable execution receipt가 없다. 이 상태에서 일반 approval을 해제하면 게시·실행 허가로 오해될 수 있다.

## 보안 결정
1. 클라이언트가 보내는 `mfa=true`, `acr`, `amr`, AuthnContext 문자열은 인증 근거로 신뢰하지 않는다. 브라우저 값을 그대로 API에 제출하는 방식으로는 gate를 통과할 수 없다.
2. Backend가 OIDC 또는 SAML assertion을 암호학적으로 검증하고 로컬 사용자와 immutable subject를 매핑한 뒤, 서버가 만든 assurance evidence만 승인 RPC가 참조한다. 공급자·claim 매핑이 설정되지 않거나 검증기가 unavailable이면 MFA를 만족하지 않은 것으로 처리한다.
3. 검증 전까지 동적 Tool 승인 scope는 등록 검토 전용이고 `execution_ready=false`를 유지한다. 승인 화면의 정보 표시나 요청 접수는 게시·실행 승인이 아니다.
4. 등록된 Tool 버전 승인과 실제 부작용 호출 승인은 별도 대상이다. 금융 side effect 호출은 인자까지 봉인한 per-call approval을 요구하도록 설계하고, read-only 무승인 경로는 검증된 정책 분류가 있을 때만 별도로 허용한다.

## 신뢰 경계와 IdP 검증 계약
### OIDC adapter
- Authorization Code + PKCE 기반 step-up을 사용하고 기존 로그인 세션에 묶인 `state`, `nonce`, issuer, client/audience, redirect URI를 검증한다. access token 자체를 앱 session token으로 사용하지 않는다.
- 서명 알고리즘 allowlist, `iss`, `aud`/`azp`, `exp`, `iat`, nonce, JWKS key id 및 key rotation을 검증한다. 허용되지 않은 issuer, 알고리즘, redirect/host, 오래된 assertion은 거부한다.
- 사용자 연결은 검증된 `(issuer, sub)`를 사전 등록된 로컬 사용자 계정에 매핑한다. email/display name은 식별 키로 사용하지 않는다.
- MFA는 기관이 확정한 `acr` 값 목록과 필요 시 `amr` 정책을 서버 설정에 명시적으로 매핑한다. `auth_time` freshness 상한을 검사한다. 미확인 claim 조합은 만족으로 추론하지 않는다.
### SAML adapter
- IdP metadata의 issuer/entity ID, signing certificate rollover, 허용 서명 알고리즘을 신뢰 앵커로 사용한다. Response/Assertion 서명, issuer, audience, recipient, destination, `InResponseTo`, 시간 조건 및 replay 방지를 검증한다.
- 사용자 연결은 검증된 `(issuer, persistent NameID)` 또는 기관이 승인한 불변 subject attribute를 로컬 계정에 사전 매핑한다. transient NameID/email은 허용하지 않는다.
- MFA는 기관이 지정한 `AuthnContextClassRef` allowlist와 `AuthnInstant` freshness를 검사한다. `SessionNotOnOrAfter`도 넘으면 step-up 증거가 만료된 것으로 처리한다. 알 수 없는 context는 통과시키지 않는다.
### 공통 assurance evidence
- 원본 ID token/SAML assertion은 approval row·audit·브라우저 저장소에 기록하지 않는다. 검증 뒤 서버가 최소 증거만 저장한다: `session_id`, `user_id`, issuer 식별자, subject mapping 식별자, 정규화된 assurance level, `auth_time`, `verified_at`, `expires_at`, verifier/policy revision, assertion replay 식별자의 일방향 digest. 원본 token/Assertion은 응답·로그에서 제외한다.
- 이 evidence는 step-up 세션에 결합하고 계정 전환, session revoke, issuer/config revision 변경 시 무효화한다. MFA 요구 정책·claim allowlist 변경은 새 immutable policy revision으로 남긴다.

## Exact revision 승인 계약
### Tool publication request
서버가 계산한 다음 tuple을 canonical JSON으로 정규화하고 digest를 계산해 승인 요청에 고정한다: `tenant_id`, `tool_id`, `registry_revision`, `descriptor_digest`, `risk_policy_id/revision`, `mode`, `target_environment`, `requested_scope`, `audience/member_ids`, `created_by`, `expires_at`. endpoint credential 값은 포함하지 않으며 필요 시 secret reference의 비밀 아닌 immutable version ID만 포함한다.
- 기존 동적 등록 review request와 운영 publication request를 분리한다. 등록 review는 metadata 확인만 뜻하고 head를 활성화하지 않는다.
- 승인 요청 상태는 `requested → pending → approved | rejected | expired | cancelled`로 제한한다. `published`는 publication transaction이 성공한 뒤 별도 기록하며 승인 상태와 합치지 않는다.
- risk policy가 요구하는 서로 다른 승인자 수와 역할을 서버가 계산한다. requester는 승인할 수 없고, 승인자 ID는 tenant membership 및 PADMIN 상태를 결정 시 다시 확인한다. 고위험 기본값은 서로 다른 2명의 PADMIN과 각자 유효한 step-up evidence다. 실제 역할·조직 기준은 정책 revision으로 고정한다.
- 각 결정은 target request + exact digest + expected state revision에 CAS로 묶고 append-only review ledger에 남긴다. 재시도는 동일 actor/action/revision/result만 idempotent replay한다.
### 승인 시점과 게시 시점
- 모든 승인 직전 DB 함수가 exact tuple 재계산을 요청하고 현재 registry revision, descriptor digest, policy revision, tenant/member 상태, requester, reviewer MFA evidence 만료/assurance를 확인한다. 하나라도 달라지면 `REVISION_CONFLICT` 또는 `APPROVAL_DENIED`로 거부한다.
- 승인 완료가 곧 publication은 아니다. 별도 publish RPC가 승인 quorum, 승인 digest, 현재 Tool revision, 목적 환경, secret reference 상태를 재검증하고 immutable publication record/head를 한 트랜잭션으로 만든다. 중간 변경이면 새 request가 필요하다.
- dynamic `tools/list`는 호출 주체 권한과 현재 published exact digest가 일치할 때만 노출한다. `tools/call`도 같은 조건을 다시 검사하며 list filtering은 보안 경계로 간주하지 않는다.
### 부작용 호출 승인
- 부작용 Tool call은 canonical arguments digest, tool/publication digest, tenant/user/agent, target environment, policy revision, client request ID 및 만료를 봉인한 call approval request를 생성한다. 승인 UI와 알림에는 마스킹된 최소정보와 승인 참조만 표시한다.
- 실행 직전에 사용자 권한·publication·arguments digest·승인 quorum·step-up freshness·정책·멱등성 상태를 다시 검사한다. 단 하나라도 변하면 upstream packet을 보내지 않는다. 승인 후 timeout/불명 결과는 receipt에 `unknown`으로 남기며 side-effect call을 자동 재시도하지 않는다.
- 실행 dispatch 전의 승인과 실행 완료는 distinct states/records다. durable receipt에 upstream correlation, 결과 분류 및 audit reference를 묶되 원문 금융정보·credential은 불필요하게 저장하지 않는다.

## 데이터/API/UI 변경 후보
- 새 additive migration으로 immutable IdP assurance/policy revision 및 dynamic publication/call approval decision ledger를 추가한다. 기존 migrations 001~058은 수정하지 않는다. RLS tenant/owner 조건, `ai_web` 직접 테이블 접근 차단, `ai_policy_executor` SECURITY DEFINER RPC만 허용한다.
- backend에 OIDC/SAML verifier adapter, step-up endpoint, server-side assurance repository, exact-revision approve/publish/call RPC wrapper를 둔다. IdP issuer/metadata/key, audience/client ID, claim mapping은 secret-free configuration reference로 관리한다.
- 관리자 B 상세 패널에는 등록검토, 승인대기(승인자 수/요건), 게시, 실행 가능, 실행 receipt를 별도 상태로 표시한다. MFA 미충족 시 사용자 제공 값 입력 폼이 아니라 IdP 재인증 경로와 차단 이유를 표시한다.
- request/approval alert에는 approval reference와 최소 식별 정보만 포함한다. prompt, 금융 인자 원문, token은 Slack/email/문서에 싣지 않는다.

## 수용 기준 및 회귀 행렬
1. IdP 서명 오류, 잘못된 issuer/audience/recipient, nonce/state/`InResponseTo` 불일치, replay, 만료, key rotation 실패는 모두 거부된다.
2. 매핑되지 않은 subject, 다른 로컬 계정 subject, step-up을 하지 않은 세션, 낮은/미확인 assurance, freshness 초과는 승인 거부되고 audit에는 안전한 사유 코드만 남는다.
3. 두 PADMIN은 서로 다른 계정이어야 하며 requester/self approval, 비활성 membership, 타 tenant, 중복 결정, stale CAS를 거부한다.
4. 승인 후 descriptor/schema/registry revision/risk policy/environment/audience 변경은 publish/call 전부를 거부하고 새 승인 요청을 요구한다.
5. MFA verifier/approval service 장애 시 고위험 요청은 fail-closed, upstream packet 0건이다. timeout/중복 제출/replay에서도 receipt와 audit가 일관된다.
6. `ai_web` 직접 ledger 조회·수정은 거부되고 approved RPC만 tenant 경계를 통과한다. DB clone 적용 전후 기존 row fingerprint·migration checksum 보존을 확인한다.
7. mock/fixture 결과는 실제 IdP 또는 기관 금융시스템 수용으로 표시하지 않는다. 실제 IdP 시험은 비밀을 노출하지 않는 기관 sandbox evidence가 있을 때 별도 수용 단계로 기록한다.

## 착수 gate와 미결 항목
Verified subject-mapping RPC, verifier 및 policy activation 코드 구현 전 기관에서 아래 값을 확정한다. IdP의 discovery/metadata endpoint·issuer, OIDC 또는 SAML 사용 경로, immutable 사용자 식별 claim/attribute 매핑, MFA assurance allowlist, freshness 최대값, 서명 키 rollover 담당, sandbox/test 계정 및 callback 주소. 현재 값은 미확정이므로 migration 059는 policy/evidence 저장 계약만 제공하고 adapter 활성화 및 MFA 통과 정책은 비활성 상태로 둔다.

## 이번 회차 결과
- 구현 상태: fail-closed 저장 계약의 additive migration 059를 추가했다. IdP 연결/정책 활성화 및 MFA 승인 전이는 미구현이며 dynamic approval은 기존처럼 차단된다.
- 변경: `src/backend/migrations/059_idp_assurance_evidence_contract.sql`, `src/backend/migrations/060_idp_subject_mapping_contract.sql`, 본 설계 문서, 추적표, 작업 이력. 기존 migration과 active fixture는 변경하지 않았다.
- 059는 tenant-scoped OIDC/SAML policy revision과 최소 session assurance evidence를, 060은 원본 subject 대신 digest/key version을 저장하는 append-only account mapping event ledger를 정의한다. 모두 RLS/FORCE RLS, `ai_web` 직접 접근 revoke 및 immutable trigger를 둔다. 데이터는 저장하지 않았다.
- private backup을 두 disposable DB에 복원해 055 baseline과 059/060 적용 clone을 비교했다. Clone은 migration head 060, migration entries 61, source checksum mismatch 0; 기존 테이블 74개·322행의 모든 table fingerprint 일치, 추가된 3개 테이블은 0행이었다. 세 테이블 FORCE RLS 및 trigger 활성, `ai_web` 직접 SELECT 권한 없음과 세 테이블 read 거부를 확인했다. 검증 후 DB와 임시 cluster를 종료·삭제했다.
- API/pytest/IdP 왕복 검증은 미수행. immutable trigger는 catalog 활성 상태까지 확인했으며 직접 UPDATE 실행은 검증하지 않았다.

연결: [[MCP Tool Gateway 상세 구현 추적]], [[2026-10-18 동적 Tool 보수적 위험정책 구현 결과]], [[2026-10-18 동적 Tool 승인 gate 계약 조사 결과]], [[400.프로젝트관리/02 포털 UI UX 작업 기록]]

## 기관 IdP 설정값 수집 및 입력 가이드

### 기관 IdP 관리자에게 요청할 자료
1. 사용할 프로토콜 하나: OIDC 또는 SAML.
2. OIDC면 discovery URL과 discovery 문서의 `issuer`, 등록된 `client_id`, redirect URI, signing JWKS 경로. SAML이면 IdP Entity ID, 서명된 metadata 및 metadata 서명 확인 방법/인증서 rollover 담당자. Metadata URL은 신뢰할 수 있는 관리 경로로 받아야 하며, 임의 URL을 사용자 입력으로 받아 서버가 fetch하지 않는다.
3. assertion에서 반환되는 불변 사용자 식별자와 테스트 사용자 2명(승인자/다른 계정)의 redacted claim/assertion 예시. 이메일·표시명은 subject 매핑 근거로 쓰지 않는다.
4. step-up을 강제했을 때 반환될 MFA assurance 값의 정확한 문자열, IdP 문서의 의미, 인증 시각 claim, prompt/RequestedAuthnContext 지원 여부. 비밀번호 로그인과 MFA가 모두 성공한 후 실제로 무엇이 내려오는지 확인한다.
5. 기관 보안 담당자가 정한 assurance 수준, step-up 최대 경과 시간, 금융 승인별 요구 factor, 기기/인증수단 조건, 실패 시 정책.
6. sandbox/테스트 tenant, callback/ACS 등록 절차, assertion signing key 교체 주기 및 담당자. 비밀키나 client secret은 문서·채팅에 넣지 말고 승인된 secret manager reference만 전달한다.

### OIDC 입력 예시
- `protocol`: `oidc`
- `issuer`: discovery JSON의 `issuer` 값을 그대로 사용한다. OIDC Core는 issuer 식별자와 ID Token의 `iss` 일치, client ID가 `aud`에 포함됨을 검증하도록 규정하며 값은 case-sensitive다. [`sub`는 issuer 범위에서 유일하고 재할당되지 않는 주체 식별자](https://www.openid.net/specs/openid-connect-core-1_0.html)로 문서화되어 있으므로 `subject_claim`은 통상 `sub`다.
- `client_identifier`: 등록된 RP client ID. 인증 요청과 callback URI는 서버 설정으로 고정한다.
- `metadata_reference`: 승인된 discovery 문서 URL 또는 내부 설정 식별자. 서버가 allowlist issuer에 한해 discovery/JWKS를 가져오며 redirect/임의 host를 허용하지 않도록 한다.
- `assurance_claim`: `acr`를 우선 기준으로 삼고, `amr`는 허용된 인증 수단의 보조 점검으로 쓴다. OIDC Core상 `acr` 의미는 상호 합의가 필요하고 `amr` 값도 기관/상대방 의미 합의가 필요하므로 `mfa`, `otp` 같은 문자열을 보편적 증거로 추정하지 않는다.
- `accepted_assurance_values`: 테스트 결과와 IdP 문서로 뜻을 확인한 정확한 `acr` 값만 입력한다. 현재 저장 schema의 내부 `aal1/aal2/aal3`는 서버가 검증 결과를 정규화해 기록하는 값이며 claim 문자열과 동일시하지 않는다.
- `max_auth_age_seconds`: 인증 요청에 `max_age`를 넣고 반환 `auth_time`이 정책의 freshness 이내인지 서버 검증한다. OIDC Core는 `max_age` 요청 시 `auth_time` 검증을 요구하며, 너무 오래되면 재인증 요청을 해야 한다.

### SAML 입력 예시
- `protocol`: `saml`
- `issuer`: 검증된 Assertion/Response의 Issuer(Entity ID)와 신뢰된 metadata의 Entity ID. 둘이 정확히 일치해야 한다.
- `client_identifier`: 서비스 제공자(SP) Entity ID. `metadata_reference`에는 version 관리되는 신뢰된 IdP metadata 식별자를 사용한다. Metadata signing certificate는 별도 승인 경로로 fingerprint/유효기간을 확인하고 키 교체 이력을 관리한다.
- `subject_claim`: persistent NameID (`urn:oasis:names:tc:SAML:2.0:nameid-format:persistent`) 또는 기관이 합의한 불변 subject attribute. transient NameID는 계정 매핑에 쓰지 않는다. OASIS는 persistent NameID를 IdP와 SP pair 범위의 opaque identifier로 정의한다. [SAML Core](https://docs.oasis-open.org/security/saml/v2.0/saml-core-2.0-os.pdf)
- `assurance_claim`: `AuthnContextClassRef`; `accepted_assurance_values`는 기관 IdP가 실제 MFA step-up 후 발행한 명시적 context URI 목록이다. `AuthnStatement.AuthnInstant`를 freshness 검사에 쓰고 Assertion Conditions, AudienceRestriction, Recipient/Destination, `InResponseTo`, signature, replay도 함께 검증한다. AuthnInstant와 SessionNotOnOrAfter는 SAML Core의 AuthnStatement에 정의돼 있다.

### 로컬 사용자 계정 매핑
매핑 키는 `(issuer, protocol, subject)`로 하고 값은 기존 `security.accounts.user_id` UUID로 연결한다. OIDC `sub`는 case-sensitive이므로 소문자화·trim·email 변환을 하지 않는다. SAML은 Entity ID와 persistent NameID 조건을 함께 보존한다. 최초 연결은 HR/IAM에서 승인한 계정 대조 자료로 관리자 2인 검토 후 등록하고, 계정 이전·재발급 시 기존 연결을 자동 재사용하지 않는다.

> [!warning] migration 059의 범위
> 059는 assurance policy revision과 evidence 저장 계약, 060은 `(issuer, protocol, subject_digest) → user_id` append-only mapping event ledger를 추가했다. 다만 IdP 검증 subject-to-account 매핑을 기록·조회하는 검증 RPC, HMAC subject digest 계산, 충돌/재매핑 전이 검사 및 OIDC/SAML signature verifier는 아직 없다. migration 060 테이블은 `ai_web` 직접 접근이 차단돼 있고 trusted RPC가 추가되기 전까지 비어 있다. email/login ID 자동 연결을 구현하지 않는다.

### 유효시간 권고와 승인
- 유효시간은 기관 보안정책/위험평가의 값으로 결정한다. 표준의 전체 로그인 세션 수명과 step-up freshness는 다른 기준이다. NIST는 재인증 기한을 AAL 및 환경/보호 대상/기기 상황과 함께 문서화하도록 한다. [NIST SP 800-63B §4](https://pages.nist.gov/800-63-4/sp800-63b.html)
- 프로젝트 초안 권고: 금융 부작용 또는 고위험 Tool 승인에서는 각 승인자가 결정 직전에 별도 step-up을 거치고, 유효시간을 **최대 5분(300초)**으로 시작한다. 기관 정책이 더 엄격하면 더 짧게 하고, 정책 책임자 승인 없이는 늘리지 않는다. 이 값은 표준이 정한 수치가 아니라 검토용 기본안이다.
- OIDC `exp`/SAML `NotOnOrAfter`의 assertion 유효성과 step-up `auth_time` freshness를 둘 다 검사한다. 짧은 assertion 만료만으로 새 MFA 인증을 증명하지 않는다.
- 추가로 다중 승인의 두 번째 승인자는 다른 계정이어야 하고 요청자와도 달라야 한다. 각자 MFA freshness를 독립 검사한다.

### 설정표 (기관과 채워 넣을 항목)
| 항목 | 기관 제공/결정 값 | 확인 방법 |
|---|---|---|
| 프로토콜 | OIDC 또는 SAML | IdP 운영자 확인 |
| Issuer / Entity ID | 정확한 식별자 | Discovery 또는 서명 검증된 metadata와 실제 assertion 비교 |
| Client ID / SP Entity ID | 등록된 RP/SP 식별자 | IdP 앱 등록 정보 |
| Discovery / Metadata ref | 승인된 URL 또는 내부 ref | 인프라 보안팀 검토 |
| Subject field/format | OIDC `sub` / SAML persistent NameID 또는 승인된 immutable attr | 테스트 사용자 claim + HR/IAM 매핑 검증 |
| MFA assurance allowlist | 정확한 ACR/AuthnContext URI | MFA 강제 전후 assertion 비교 및 IdP 문서 |
| Freshness | max auth age 초 | 기관 위험정책 승인; 고위험 제안은 300초 |
| Key rollover | 일정/책임자 | IdP 운영 runbook |
| Test identities | requester + 독립 approver | sandbox에서 실제 step-up 확인 |

외부 표준: [OpenID Connect Core 1.0](https://www.openid.net/specs/openid-connect-core-1_0.html), [OASIS SAML 2.0 Core](https://docs.oasis-open.org/security/saml/v2.0/saml-core-2.0-os.pdf), [NIST SP 800-63B](https://pages.nist.gov/800-63-4/sp800-63b.html).


## 구현 업데이트: verifier 경계 및 keyed digest (2026-10-18)
인증 설정값이 아직 제공되지 않은 상태에서 `IdpVerifier`의 비활성 fail-closed 경계와 keyed HMAC subject digest 구현을 추가했다. mock callback은 synthetic 결과로 명시하고 assurance evidence를 만들지 않는다. 실제 JWT/SAML cryptographic verifier, issuer 검증, claim 정책, evidence 발급은 아직 구현·활성화하지 않았다. 변경과 정적 검증 결과는 [[2026-10-18 IdP 검증 경계 및 subject digest 구현 결과]]에 기록했다.
