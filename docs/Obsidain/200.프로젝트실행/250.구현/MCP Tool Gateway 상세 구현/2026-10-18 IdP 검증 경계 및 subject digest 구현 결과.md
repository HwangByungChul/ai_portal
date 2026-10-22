---
title: IdP 검증 경계 및 subject digest 구현 결과
created: 2026-10-18
updated: 2026-10-18
status: partial-implementation-provider-contract-pending
tags: [mcp, tool-gateway, oidc, saml, hmac, security]
---
# IdP 검증 경계 및 subject digest 구현 결과

## 요청과 범위
기관 서비스 연결 정보가 아직 없는 상태에서 서버 측 OIDC/SAML verifier 준비 작업과 keyed subject digest 처리를 진행한다. 실제 issuer·metadata·claim 정책이 정해지지 않았으므로 기관 로그인 검증이나 MFA evidence 발급을 활성화하지 않는다.

## 변경
- `src/backend/app/auth/idp_verifier.py`: OIDC/SAML verifier backend 경계, 최소 `VerifiedIdentity` 타입, fail-closed dispatcher, HMAC-SHA256 subject pseudonymization 및 versioned `SubjectDigestKeyring`을 추가했다. Provider protocol을 통해 활성·보존 키 버전을 서버에서만 읽을 수 있고, 누락/미확인 버전은 거부한다. backend가 주입되지 않으면 두 프로토콜 모두 `IDP_VERIFIER_NOT_CONFIGURED`로 거부한다.
- `src/backend/app/config.py`: 선택 설정 `AI_IDP_SUBJECT_HMAC_KEY`, `AI_IDP_SUBJECT_HMAC_KEY_VERSION`을 추가했다. 함께 설정해야 하며 키는 UTF-8 기준 32 byte 이상이어야 한다. secret 값은 저장소와 이 문서에 기록하지 않는다.
- `src/backend/app/main.py`: 앱 lifespan에서 verifier는 항상 비활성으로 만들고, digest 설정이 완비된 경우에만 서버 프로세스 내 digest service를 준비한다. `create_app`은 `SubjectKeyProvider` 주입 경계를 제공하며 설정된 버전 목록/활성 버전으로 keyring을 구성한다. 버전 정책이 있는데 provider가 없거나 provider와 환경 key가 동시에 들어오면 시작을 거부한다. verifier와 digest는 별도 기능이며 HMAC 키만으로 인증이 승인되지 않는다.
- `src/backend/app/auth/sso.py`: 기존 모의 callback 결과를 `identity_kind=synthetic`, `verified=false`, `assurance_evidence_created=false`로 바꿨다. raw subject를 흉내 낸 외부 식별자는 반환하지 않는다.
- `src/backend/app/errors.py`: verifier 비활성 고정 오류 메시지를 추가했다.

## 보안 경계와 미완료 범위
암호학적 OIDC/SAML 파싱·서명 검증 backend, issuer/metadata 신뢰 검증, nonce/state/audience/replay 처리, claim allowlist, IdP policy 관리, evidence 발급·저장, HMAC key rotation/Secret Manager, subject mapping resolver는 구현되지 않았다. 현재 설치 의존성에 검증된 OIDC/SAML 암호 검증 라이브러리가 확인되지 않아 토큰/Assertion을 임의로 파싱하지 않았다. 따라서 실제 IdP verifier는 아직 제공되지 않으며 mapping RPC는 계속 fail-closed다. 현재 앱에는 실제 Secret Manager 제품 adapter가 주입되지 않았다. 단일 HMAC key 환경설정 경로는 유지되며, versioned provider 경로는 injection seam까지만 구현했다. 따라서 회전 키의 공급·DB mapping digest 재계산·이전 키 폐기 절차는 아직 운영 가능하지 않다.

## 검증
변경 Python 파일 7개 컴파일 통과, `git diff --check` 통과. pytest·HTTP/DB·기관 IdP 검증은 실행하지 않았다. 활성 DB migration이나 API 프로세스 재기동은 하지 않았다.

## 다음
기관 보안팀이 issuer/metadata, subject claim, MFA assurance allowlist, freshness, replay 및 키 회전 정책을 확정한 뒤 검증된 crypto backend와 evidence writer를 별도 단계로 구현한다. 그 전까지 verifier, policy, evidence 생성은 비활성으로 유지한다.

관련: [[00 구현 추적]], [[2026-10-18 verified subject mapping RPC 구현 결과]], [[2026-10-18 exact revision 승인 gate OIDC-SAML 설계]], [[400.프로젝트관리/02 포털 UI UX 작업 기록]]


## 키 회전 기반 보강 (2026-10-18)
`SubjectKeyProvider` protocol과 immutable `SubjectDigestKeyring`을 추가했다. 다중 키 버전을 서버 메모리에 로드하고 지정된 활성 버전으로 새 digest를 만들며 보존 중인 버전으로 기존 subject digest를 재현할 수 있다. 키 누락·버전 오류는 fail-closed다. 실제 Secret Manager adapter와 rotation 운영 절차는 미구현이며 현재 앱은 기존 단일 설정 key만 사용한다.


## Secret provider 주입 경계 (2026-10-18)
`create_app(..., subject_key_provider=...)`에 Secret Manager adapter를 주입할 수 있도록 연결했다. `AI_IDP_SUBJECT_HMAC_KEY_VERSIONS`와 `AI_IDP_SUBJECT_HMAC_KEY_VERSION`으로 읽을 버전 집합과 활성 버전을 지정한다. provider 오류, 누락 키, 중복/잘못된 버전, provider와 환경 key 동시 사용은 fail-closed다. 현재 조직 문서에는 실제 Secret Manager 제품이 정해져 있지 않아 AWS/Azure/GCP/Vault 중 특정 SDK를 추가하거나 운영 연동했다고 주장하지 않는다.
