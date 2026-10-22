---
title: MCP Tool Gateway 서비스 적용 전 위험 점검
created: 2026-10-21
updated: 2026-10-21
status: review-recorded
tags: [mcp, tool-gateway, service-readiness, risk-review]
---
# MCP Tool Gateway 서비스 적용 전 위험 점검

## 점검 요청과 범위
현재까지 구현한 MCP Tools 기능을 현 서비스에 적용할 때 장애나 호환성 문제가 생길 수 있는지 코드·최신 구현 기록 기준으로 점검했다. 이는 정적 소스 및 기존 테스트/clone 증거 검토이며, 실행 중인 서비스의 배포 버전·실 DB 상태·운영 로그를 확인한 장애 조사나 운영 수용 시험은 아니다.

## 결론
현재 확인한 내용으로 즉시 발생 중인 운영 장애를 확인하지 못했다. 하지만 변경사항은 미커밋·미배포 상태이며, 이 결과만으로 현재 서비스에 적용해도 무문제라고 보증할 수 없다. 기존 MCP 기능은 일부 계약·모의 구현이며 실제 원격 MCP/금융 connector 실행 기능은 연결돼 있지 않다.

## 적용 전에 처리할 항목

### P0 — 애플리케이션과 DB 배포 버전 일치
- 동적 Tool 목록 API는 `security.mcp_tool_registry_list`를 호출한다. 해당 함수는 migration 063에서 추가됐고, 063/064는 백업 복원 clone에서 검증됐으나 활성 DB 적용 기록은 확인되지 않았다.
- 현재 코드만 먼저 반영하면 DB 함수 부재 시 동적 Tool 목록 경로가 실패할 수 있다. 등록 및 simulation도 관련 Registry RPC/migration 의존성이 있다.
- 작업: 배포 대상 DB의 실제 migration manifest/checksum을 읽기 전용으로 확인하고, 승인된 백업·복구 절차 및 disposable clone을 거친 배포 순서를 확정한다. 활성/공유 DB에 검증 없이 migration을 적용하지 않는다.
- 증거: [[2026-10-20 063-064 백업 클론 검증 결과]], `src/backend/app/tools/dynamic_repository.py`의 register/list/simulation query.

### P1 — 사용자 역할 및 API 소비자 호환성
- 등록·동적 목록·호출은 `TADMIN` 또는 `PADMIN` effective role을 요구한다. 현 서비스의 관리자 계정/조직별 role mapping이 이 값들로 정규화되는지 배포 전에 확인해야 한다.
- endpoint profile 입력에서 credential 객체를 제거했고 스키마는 추가 필드를 거부한다. 예전 API client가 `credential` 필드를 보내면 422가 될 수 있다.
- 작업: frontend 외부의 API client·스크립트·운영 절차 소비자를 조사하고, 역할별 및 이전 payload 호환 계약을 staging에서 확인한다. Secret 전달 경로는 복원하지 않는다.

### P1 — 명세 파싱 자원·권한 경계
- `/api/v1/tools/auto-wrap/parse`는 인증 세션을 확인하지만 TADMIN/PADMIN 검사를 호출 경로에서 수행하지 않는다. 확인한 요청 모델에는 원본 명세의 명시적인 최대 바이트/깊이/복잡도 제한도 보이지 않는다.
- 작업: 서비스 접근정책에 맞는 허용 역할, request body 크기, XML/JSON 파서 자원 제한, rate limit 및 오류 노출 경계를 정하고 테스트한다. 외부 URL fetch를 허용하지 않도록 유지한다.

### P2 — SSO 시연 경로의 의미 변경
- 현재 SSO callback은 합성 identity를 반환하고 `verified=false`, `assurance_evidence_created=false`로 표시한다. 실제 IdP 서명/issuer/nonce/MFA 검증은 수행하지 않는다.
- 작업: UI/운영 안내가 이를 로그인 성공이나 기관 인증으로 표시하지 않는지 확인한다. 기존 시연이 가짜 `verified=true`/`external_sub` 응답에 의존했다면 callback 소비자 호환을 수정한다. 실제 IdP는 기관 설정 확정 후 별도 연결한다.

### 릴리스 전 확인
- 작업 트리에 MCP 외 변경도 다수 미커밋 상태로 보인다. 배포에는 검토된 변경 집합만 포함하고, 기존 작업을 임의로 되돌리거나 섞지 않는다.
- 활성 DB migration 상태 확인 후 별도 staging 환경에서 로그인, 관리자 권한, 명세 parse, 등록, 목록, 모의 실행, tenant 분리, 실패 응답을 확인한다.
- 관리자 TypeScript/Vite build는 로컬 통과 기록이 있으나 실제 서비스 배포·브라우저 UAT 증거는 아니다. 작업 후 실제 대상으로 검증한 결과를 별도로 기록한다.

## MCP 기능 자체의 현재 직접 위험 범위
- Streamable HTTP adapter는 `discover_tools()` 모듈과 계약 테스트로 구현돼 있다. 현재 backend app 코드에서 이 함수를 부르는 route/service 통합 호출처를 찾지 못했다. 그러므로 이 adapter는 현재 일반 요청에서 원격 MCP endpoint로 나가는 경로가 아니다.
- `tools/call`, 운영 dispatch, 승인 후 금융 side effect는 연결돼 있지 않으며 production dispatch는 fail-closed다. mock simulation은 외부 endpoint 호출로 간주하지 않는다.
- 향후 실제 연결 때는 hostname allowlist만으로 충분하지 않으므로 기관 승인 endpoint, DNS pinning/egress 정책, TLS·인증 위임 및 Secret Manager 계약, 승인·감사·비용 gate가 필요하다. 실제 대상 선정은 추후로 미룬다.

## 실제 확인 근거와 한계
- `tests/test_mcp_streamable_http.py`: Task 8 수정 후 53 passed (injected in-process MockTransport만 사용).
- `npm run build:admin`: TypeScript, Vite 및 admin boundary 검사 통과 기록(229 modules, 큰 chunk 경고 1건).
- migrations 056–064: 별도 disposable PostgreSQL backup clone 검증 완료. 이는 활성 DB migration 적용을 뜻하지 않는다.
- 실제 서비스 버전/활성 DB 상태/고객 API 소비자/로그인 브라우저/UAT는 이번 점검에서 확인하지 않았다. 따라서 항목은 적용 전 점검 목록이며 확인된 운영 사고 보고가 아니다.

## 연결
- [[00 구현 추적]]
- [[2026-10-21 Streamable HTTP 누적 응답 한도 보강]]
- [[2026-10-20 063-064 백업 클론 검증 결과]]
- [[400.프로젝트관리/02 포털 UI UX 작업 기록]]
