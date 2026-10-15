---
title: T-035 MCP 및 외부 Tool 연동 노코딩 자동변환 구현 결과
created: 2026-10-15
updated: 2026-10-15
status: completed
purpose: T-035 필수 기술요건(MCP 및 외부 Tool 연동, 배포 승인 상태별 동적 전환, 노코딩 Auto-Wrapping)의 실제 구현 및 검증 결과 보고
tags: [mcp, tool, auto-wrapping, openapi, wsdl, jdbc, financial-packet, dynamic-routing, implementation-result]
---
# T-035 MCP 및 외부 Tool 연동 노코딩 자동변환 구현 결과
본 문서는 기능명세서 상의 필수 기술요건 **T-035(MCP 및 Tool 연동)** 및 연관 기능(**F-011, F-021, F-048**)에 대한 실제 백엔드/프론트엔드 구현 및 검증 완료 결과를 보고합니다.

## 1. 구현 개요
- **배포 승인 상태 기반 Dev ↔ Prd 동적 라우팅 게이트웨이**:
  - 에이전트의 현재 배포 승인 상태(`publication_status`: 'draft' vs 'approved_published')에 따라 호출 대상을 개발계(Dev)와 운영계(Prd) 엔드포인트로 런타임에 동적 스위칭하는 중앙 게이트웨이를 구현했습니다.
  - 미승인/Draft 상태 에이전트가 운영계 엔드포인트로 접근하는 것을 원천 차단하고, 자격증명(Credential)을 대칭키 기반으로 암호화 보관하여 프론트엔드 및 로그 유출을 방지했습니다.
- **수동 코딩 없는 4대 인터페이스 Auto-Wrapping 엔진**:
  - OpenAPI 3.0 / Swagger 2.0 (REST JSON)
  - WSDL (SOAP XML)
  - JDBC (RDB 가상화 뷰 및 DML 뮤테이션 차단)
  - 금융 전문 (ISO 8583, EAI, FEP 고정길이 전문 바이트 패킹/언패킹)
- **관리자 전용 포털 화면**:
  - 노코딩 마법사 모달(명세 입력 → 실시간 스키마 파싱 → Dev/Prd 엔드포인트 분리 설정 → 即時 모의 테스트 → 최종 등록)을 탑재한 `ToolAdminPage`를 구현하고 관리자 사이드바에 연동했습니다.

## 2. 변경 및 생성된 실제 파일 목록
- **데이터베이스 스키마 마이그레이션**:
  - `src/backend/migrations/052_mcp_tool_autowrap_and_dynamic_routing.sql`:
    - `portal.mcp_tool_definitions`, `portal.mcp_tool_versions`, `portal.mcp_tool_endpoint_profiles`, `portal.mcp_tool_audit_logs`
- **백엔드 핵심 모듈**:
  - `src/backend/app/tools/credentials.py`: 표준 라이브러리(HMAC-SHA256 Keystream) 기반 인증 암호화 자격증명 볼트
  - `src/backend/app/tools/parsers/openapi_parser.py`: Swagger/OpenAPI 파서 및 MCP Tool 자동 변환
  - `src/backend/app/tools/parsers/wsdl_parser.py`: WSDL SOAP XML 파서 및 Envelope 템플릿 생성기
  - `src/backend/app/tools/parsers/jdbc_parser.py`: JDBC 테이블 가상화 및 DML(`DROP`, `INSERT` 등) 엄격 차단기
  - `src/backend/app/tools/parsers/packet_parser.py`: 금융 전문 레이아웃 파서 및 고정길이 바이트 Pack/Unpack 직렬화기
  - `src/backend/app/tools/dynamic_gateway.py`: 배포 승인 상태 연동 동적 라우팅 게이트웨이 및 보안 가드레일
  - `src/backend/app/tools/autowrap_routes.py`: 노코딩 스펙 파싱, 등록, 동적 도구 목록 및 라우팅 호출 API
  - `src/backend/app/main.py`: `autowrap_tools_router` 등록
- **프론트엔드 관리 화면 및 라우팅**:
  - `src/frontend/src/ToolAdminPage.tsx`: 연계 Connector & MCP Tool 관리 및 노코딩 마법사 페이지
  - `src/frontend/apps/admin-web/src/App.tsx`: `🔌 연계 Tool & MCP` 사이드바 메뉴 및 `/manage/admin/tools` 라우트 연결
- **자동화 테스트 스위트**:
  - `src/backend/tests/test_mcp_tool_autowrap.py`: 7개 핵심 단위/통합 테스트 케이스

## 3. 검증 결과
- **백엔드 자동화 테스트 (`pytest tests/test_mcp_tool_autowrap.py`)**:
  - `test_credential_encryption_and_decryption`: **PASSED** (민감 자격증명 암·복호화 무결성)
  - `test_openapi_auto_wrap_parsing`: **PASSED** (REST API 엔드포인트 및 inputSchema 추출)
  - `test_wsdl_auto_wrap_parsing`: **PASSED** (SOAP Action 및 XML Envelope 템플릿 생성)
  - `test_jdbc_auto_wrap_parsing_and_security`: **PASSED** (Read-Only 생성 및 SQL DML 인젝션 422 차단)
  - `test_financial_packet_auto_wrap_and_pack_unpack`: **PASSED** (29바이트 고정길이 전문 패킹/언패킹 일치)
  - `test_dynamic_environment_routing_draft_vs_approved`: **PASSED** (Draft는 Dev로, Approved는 Prd로 자동 분기)
  - `test_tool_argument_safety_and_idempotency`: **PASSED** (경로조작/SQLi 차단 및 동일 요청ID 409 충돌 검증)
  - **결과**: `7 passed in 0.53s` (100% 통과)
- **프론트엔드 빌드 경계 검증**:
  - `npm run build:admin`: 통과 (`modules: 51, boundary_verified: true`)
  - `npm run build:user`: 통과 (`modules: 28, boundary_verified: true`)
  - `npm run build`: 통합 빌드 전원 통과 (오류 0건)
