# 금융 특화 MCP Tool Gateway 미완료 범위 상세 구현 계획안

본 문서는 금융 특화 MCP Tool Gateway에서 대외기관/운영 환경 연동 전 단계로 남아 있는 3대 미완료 범위(모의 금융 샌드박스 E2E, OIDC/SAML Step-up MFA 검증 엔진, 마이그레이션 065~067 런타임 클론 검증 하네스)의 상세 구현 계획서입니다.

- **목표:** 외부 기관의 실계좌/인증서/운영 DB 의존성 없이도 완벽한 테스트 및 안전한 보안 경계를 확보하기 위해, 모의 대외기관 샌드박스 서버, 표준 암호학적 IdP Step-up MFA 검증기, PostgreSQL 마이그레이션 런타임 검증 하네스를 구축합니다.
- **기술 스택:** Python 3.13, FastAPI/AnyIO, pytest, cryptography, PyJWT, defusedxml, psycopg 3, PostgreSQL 15.

---

## 1. 세부 과제별 구현 범위

### 과제 1: 금융기관 Mock Sandbox & Connector E2E 시뮬레이터 (Protocol Testing Harness)
- **목적:** 대외기관 실 엔드포인트/mTLS 인증서 없이도 4종 커넥터(OpenAPI, WSDL, JDBC, 고정길이 전문)의 실제 네트워크 I/O, TLS 핸드셰이크, 타임아웃, 대용량 응답 절단, 서킷브레이커 트립을 로컬 루프백 상에서 종단 간(E2E) 검증.
- **담당 파일:**
  - `src/backend/app/tools/simulation_sandbox.py` (루프백 TLS 소켓 및 HTTP/SOAP 모의 서버)
  - `src/backend/tests/test_connector_e2e_sandbox.py` (실제 소켓/HTTP 루프백 E2E 통신 검증)
- **구현 인터페이스:**
  - `FinancialPacketSandboxServer`: TLS TCP 소켓 서버. 80바이트 고정길이 전문 수신, LRC 체크섬 검증, 0000(정상)/9999(오류) 전문 응답.
  - `SoapWsdlSandboxServer`: WSDL 명세 서빙 및 SOAP 1.1/1.2 XML Envelope 처리. XXE 공격 차단 및 오류 SOAP Fault 응답.
  - `OpenApiSandboxServer`: 1 MiB 초과 스트리밍 응답, 지연 응답(타임아웃 유발), 503 에러 응답(서킷브레이커 유발).

### 과제 2: OIDC / SAML Step-up MFA 암호학적 검증기 (Identity & Assurance)
- **목적:** 가상/모의 콜백에 머물던 IdP 검증 경계를 표준 OIDC JWT 및 SAML Response 검증기로 고도화하여, 금융 부작용 도구 실행 및 게시 승인 시 실시간 Step-up MFA(300초 freshness, acr/amr 레벨)를 강제.
- **담당 파일:**
  - `src/backend/app/auth/oidc_saml_verifier.py` (표준 JWT/SAML 서명 검증, acr/amr 평가, replay 방지)
  - `src/backend/app/auth/idp_verifier.py` (`IdpVerifier`에 실제 검증 백엔드 주입 지원)
  - `src/backend/app/tools/publication_gate.py` (Step-up MFA freshness 300초 검증 연계)
  - `src/backend/tests/test_oidc_saml_verifier.py` (서명 검증, 위조 토큰 거부, acr 미달 거부, 만료 토큰 거부)
- **구현 사양:**
  - `OidcJwtVerifier`: JWKS(RSA/EC) 서명 검증, `iss`(발급자) allowlist 검증, `aud` 검증, `auth_time` 기준 freshness 계산, `acr`/`amr` 검증.
  - `SamlResponseVerifier`: XML 디지털 서명 검증, Persistent NameID 추출, AuthnInstant 검증, AuthnContextClassRef 검증.
  - `StepUpMfaGate`: 금융 부작용 도구 실행 전 직전 300초 이내 유효한 MFA evidence가 없을 시 `IDP_ASSURANCE_REQUIRED`(403) 차단.

### 과제 3: PostgreSQL Migration 065~067 런타임 적용 및 Clone 검증 하네스 (DB Integrity)
- **목적:** 파일 파싱에 머물렀던 마이그레이션 검증을 넘어, 실제 PostgreSQL 테스트 인스턴스 상에서 000~067 전체 마이그레이션을 순차 실행하고, 신규 테이블(065, 067) 및 RPC(066)의 런타임 동작(트리거, RLS, Self-Approval 차단)을 자동 검증.
- **담당 파일:**
  - `src/backend/scripts/verify_migration_clone_runtime.py` (임시 클러스터/롤백 트랜잭션 런타임 DDL 적용 하네스)
  - `src/backend/tests/test_db_migration_clone.py` (런타임 DB 연결 시 자동 실행되는 E2E DB 테스트 케이스 추가)
- **검증 항목:**
  - 000~067 순차 마이그레이션 무결성 및 DDL 실행.
  - `portal.mcp_tool_audit_events`: 임의의 `UPDATE` 또는 `DELETE` 실행 시 PostgreSQL `prevent_audit_modification()` 트리거가 에러(SQLSTATE P0001) 발생시키며 차단하는지 검증.
  - `security.mcp_tool_publication_control`: 요청자 본인이 승인자로 호출 시 SQLSTATE `A0403` 차단 및 원자적 상태 전이(`active` -> `superseded`) 확인.
  - RLS 격리: 일반 `ai_web` 역할로 audit_events 직접 조작 시 거부 확인.

---

## 2. 작업 순서
- **Step 1:** 모의 금융기관 샌드박스 서버 구현 (`simulation_sandbox.py`)
- **Step 2:** 커넥터 E2E 네트워크 I/O 검증 (`test_connector_e2e_sandbox.py`)
- **Step 3:** OIDC/SAML Step-up 검증기 구현 (`oidc_saml_verifier.py`, `idp_verifier.py`)
- **Step 4:** 도구 실행 게이트 MFA 연계 (`publication_gate.py`, `dynamic_gateway.py`)
- **Step 5:** DB 마이그레이션 런타임 검증 하네스 (`verify_migration_clone_runtime.py`)
- **Step 6:** Obsidian Vault 기록 및 완료 보고 (`02 작업 기록.md`, `00 구현 추적.md`)
