---
created: 2026-10-12
updated: 2026-10-12
status: provider-selected-design-proposed
scope: DP16-SSO
---
# Microsoft Entra ID 선정과 SSO 연동 검토

## 사용자 결정과 현재 상태

2026-10-12, “다음 SSO 연동에 사용할 IdP가 정해져 있는가”라는 질문에 사용자가 **Microsoft Entra ID**로 답했다. 제품 선정은 확정이며 테스트 테넌트/앱 등록 사용 가능 여부는 아직 답변받지 못했다. 이 답변으로 실제 테넌트 접근·앱 등록 생성·정책 변경·SSO 구현/연동 시험 완료를 추정하지 않는다.

현재 앱은 local 사용자5173·관리자5174·API8000, 공통 개발 세션이다. auth 설정/router와 공개 local 환경에 Entra OIDC 구현·설정은 없다. 이번 작업은 제품 결정과 연동 검토를 기록하며 제품 코드·환경 JSON·DB·Entra 설정은 변경하지 않는다. [[15 전체 기능명세서 잔여 기능 개발 실행 계획]]의 기능 우선 순서를 유지하고 이 자료를 DP16 인증 설계에 연결한다. 동적 자산/카탈로그/Builder의 기능 개발을 실제 IdP 테스트 환경 대기로 멈추지 않는다.

## 연동 설계안 — 구현 전 상세 계약으로 확정할 항목

기존 [[12 사용자 관리자 사이트 분리와 상용 이행 설계]]의 사용자/관리자 별 OIDC 클라이언트·서버 세션/BFF 원칙을 Entra에 적용하는 안이다. 현재 포트와 도메인 미정 상태를 지원하되 포트만으로 쿠키 격리가 이루어졌다고 판단하지 않는다. 사이트별 client ID/redirect/세션 수신자를 서버에서 묶고 관리 권한을 매 업무 API에서 다시 확인한다. 이는 프로젝트 설계안이며 Microsoft가 두 앱 등록을 의무화한다는 뜻이 아니다.

인증 프로토콜은 OIDC Authorization Code + PKCE(S256)를 기본안으로 한다. callback에서 state/nonce와 단일 사용/유효시간을 검증하며 토큰의 서명·issuer·audience·만료를 서버에서 확인한 뒤 내부 세션을 만든다. 토큰/credential은 브라우저 localStorage·공개 환경 JSON·번들·공개 시험 증거에 넣지 않는다. Microsoft는 해당 흐름과 지원 인증 라이브러리 사용을 안내한다. 라이브러리 선택은 현재 Python 런타임/검증 책임을 확인한 상세 구현 계획에서 고정한다. [Microsoft Authorization Code Flow](https://learn.microsoft.com/en-us/entra/identity-platform/v2-oauth2-auth-code-flow).

Entra의 디렉터리 tenant(`tid`)와 플랫폼의 업무 조직 tenant_id를 구분한다. 검증된 외부 주체를 내부 account와 연결하고, 계열사/부서·USER/TADMIN/PADMIN·승인 capability는 내부 membership/운영 권한으로 판정한다. 로그인 email/표시명이나 미검증 role/group claim을 내부 관리자 권한으로 자동 승격하지 않는다. 외부 식별 키는 검증된 issuer 및 tid/oid를 기본 검토 대상으로 하고, 앱별 subject 차이와 guest 계정을 테스트한다. 승인 대상 Entra tenant 목록과 한 디렉터리/복수 디렉터리 모델은 실제 계열사 구성을 확인한 뒤 결정한다. [ID Token Claims](https://learn.microsoft.com/en-us/entra/identity-platform/id-token-claims-reference), [Claims Validation](https://learn.microsoft.com/en-us/entra/identity-platform/claims-validation).

관리자 MFA/Conditional Access 정책·재인증 요구, 로그인 취소·IdP 장애·서명키 갱신, 내부 권한 회수/세션 폐기·사이트별 logout 및 IdP logout의 범위도 실제 테넌트 정책과 함께 수용한다. 현재 local 개발 세션을 자동으로 Entra 세션으로 바꾸지 않는다.

## 필요한 설정과 확인 사항

| 항목 | 용도 | 상태/보관 |
|---|---|---|
| 테스트 테넌트와 앱 등록 사용 가능 여부 | 실제 인증 시험 착수 여부 | 질문 중, 미확인 |
| Entra tenant ID·허용 issuer | 신뢰할 디렉터리 경계 | 미수령, 검증된 환경별 공개 설정 대상 |
| 사용자/관리자 Application client ID | 사이트별 인증 수신자 | 미수령, 환경별 설정 대상 |
| callback/logout 주소 | 정확한 앱 등록·복귀 경로 allowlist | 미확정, 실제 등록 규칙 검토 후 local/dev/tb/prd로 관리 |
| 서버 credential 참조 | confidential client code 교환 | 미확정, 서버 비밀 설정/저장소 참조로 관리 |
| 내부 account·조직 mapping 및 테스트 역할 | 계열사 분리·관리자 승인 검증 | 기존 membership 유지, 테스트 대상 매핑 미확정 |
| MFA·Conditional Access·테스트 guest 정책 | 관리자 인증 강도·외부 주체 수용 | 기관 정책 미확인 |

최초 로그인용 scope는 openid/profile 최소안을 검토한다. Graph 접근이나 디렉터리 전체 읽기 권한을 제품명 선택만으로 요청하지 않는다. 실제 조직 동기화가 필요한 기능에서 별도 연동 계약으로 범위를 정한다.

## 검증·미완료·다음 작업

- 수행: 현재 auth/환경/계획 대조, Microsoft 공식 프로토콜·claim 검증 문서 확인, 제품 선택과 제안/미확정 구분.
- 미수행: 코드 구현·외부 앱 등록/테넌트 수정·토큰 교환·로그인/로그아웃·MFA·기관 SSO 수용. 이번 검토에 제품 통합 시험은 필요하지 않아 실행하지 않았다.
- 후속: 테스트 환경 답변과 tenant/client/주소·사용자 매핑을 확보하고 DP16 SSO 상세 실행 계획을 작성한다. mock IdP 음성시험과 실제 Entra 수용 증적을 별도로 기록한다. 기능 개발은 계획15 순서로 계속 관리한다.

관련 기록: [[23 포털 UI UX 확정과 사이트 분리 검토]], [[02 포털 UI UX 작업 기록]]. Obsidian Vault Markdown 직접 저장이며 GUI 렌더링은 미검증이다.

## 2026-10-12 · 테스트 환경 준비 상태 응답

사용자가 테스트 테넌트·앱 등록 가용성 선택지에 “2”라고 응답했다. 직전 선택지의 2번 **준비 예정**으로 해석해 기록한다. 실제 테넌트/앱 등록 접근 가능 또는 연동 검증 완료를 의미하지 않는다. 테스트 환경 준비 후 식별자·callback/logout 주소·내부 계정 매핑을 확인한다. 기존 기능 개발 계획의 순서는 유지한다.
