---
title: IdP verifier fail-closed 단위 검증
date: 2026-10-18
tags: [mcp, tool-gateway, idp, verification]
status: unit-verified
---
# IdP verifier fail-closed 경계 단위 검증

## 요청과 범위
기관 issuer/metadata, immutable subject claim, MFA assurance freshness/replay 정책 및 Secret Manager가 아직 결정되지 않았다. 실제 verifier를 활성화하지 않은 상태에서 현재 코드의 fail-closed 계약과 subject digest keyring 동작을 테스트했다.

## 변경
- `src/backend/tests/test_idp_verifier_boundary.py` 추가.
- 기본 `IdpVerifier`의 OIDC/SAML 미설정 거부, 합성 backend 입력 전달, `VerifiedIdentity` 동일 반환을 검증한다.
- versioned keyring의 활성 key 선택, retained-version digest 재현, protocol/issuer/subject 도메인 분리와 모호한 문자열 결합 방지를 검증한다.
- unknown/missing key, Secret provider 누락 및 예외에서 고정 오류만 노출되고 secret-bearing exception context가 억제되는지 검증한다.
- production 코드, migration, 설정, DB 및 외부 서비스는 변경·호출하지 않았다.

## 검증 결과
- 실행: `.venv/bin/python -m pytest --noconftest -p no:cacheprovider tests/test_idp_verifier_boundary.py -q`
- 결과: `10 passed in 0.45s`; pytest cache 경고 없이 종료.
- Task reviewer: Spec PASS / Quality PASS, actionable finding 없음.
- 검증 입력과 backend/provider는 전부 합성값이며 실제 IdP 검증으로 간주하지 않는다.

## 미완료 범위
OIDC/SAML crypto backend, issuer metadata와 claim policy, MFA evidence 발급, 실제 Secret Manager adapter/key rotation, mapping RPC의 live DB 검증 및 기관 수용은 미완료다. 현재 verifier는 기관 정책과 backend가 준비되지 않으면 비활성 상태로 유지한다.

## 다음 작업
기관이 issuer/metadata, immutable subject claim, MFA assurance allowlist/freshness/replay, key rollover 및 Secret Manager 선택을 확정하기 전에는 실제 verifier를 활성화하지 않는다.

관련: [[00 구현 추적]], [[2026-10-18 native DB pool 경계 단위 검증]], [[400.프로젝트관리/02 포털 UI UX 작업 기록]].
