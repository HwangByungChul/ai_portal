---
title: MCP Streamable HTTP 도구 탐색 어댑터 구현
created: 2026-10-20
updated: 2026-10-20
status: contract-implemented
tags: [mcp, tool-gateway, streamable-http, discovery]
---
# MCP Streamable HTTP 도구 탐색 어댑터 구현

## 요청·결정
MCP Gateway T035-C의 다음 단계를 진행한다. 공식 MCP Python SDK를 고정하고, 외부 시스템에 연결하지 않는 Streamable HTTP `tools/list` 탐색 계약을 구현한다. 현 단계는 discovery module과 검증까지만 포함한다. public API route, registry 영속화, `tools/call`, OAuth·IdP·Secret Manager, 실제 금융 connector는 연결하지 않는다.

공식 Python SDK v2.3.0을 고정했다. 공식 SDK는 Streamable HTTP client, 프로토콜 자동 협상, 이전 프로토콜 호환을 제공한다. `httpx2` 클라이언트는 environment proxy를 신뢰하지 않고 redirect를 차단한다. 계획상 redirect 금지 또는 허용 목록 제한을 허용하므로 이번 구현은 HTTPS와 정확 hostname allowlist를 강제하고, SDK redirect 제한도 함께 적용한다. 앱 자체 재시도는 추가하지 않았다. SDK negotiation/reconnect 동작은 멱등 읽기 전용 목록 탐색 범위에서만 남기고, 도구 실행은 구현하지 않는다.

## 구현
- `src/backend/app/tools/transports/streamable_http.py`: HTTPS·hostname allowlist 검증, URL credentials/query/fragment 거부, 제한된 discovery timeout·SSE 이벤트 크기·page/catalog 수, JSON Schema 확인, 중복/잘못된 이름 거부, 결정적 이름 정렬, 고정 안전 오류, 응답 metadata 축소를 구현했다.
- `src/backend/tests/test_mcp_streamable_http.py`: 공식 SDK와 injected `httpx2.MockTransport`를 사용해 modern `2026-07-28` 및 legacy `2025-06-18` protocol 협상, 빈/복수 목록, pagination, sanitization, malformed response, redirect 차단, 타임아웃 및 안전 오류를 검증한다. 예약한 `.example` 이름만 사용하며 socket이나 외부 endpoint는 없다.
- `requirements.in`에 `mcp==2.3.0`을 추가하고 hash lock을 재생성했다. lock은 총 55 distributions이며 11개 신규 distributions를 추가했고 기존 pin 버전은 변경하지 않았다. `pip check` 통과.

## 실제 검증 결과
- focused backend 테스트 35 passed. `--noconftest` 적용으로 DB/fixture setup을 건너뛰었다.
- `pip check`: No broken requirements found. 전체 dependency 해석 및 hash 검증 설치 성공.
- `git diff --check`: 통과. lock 55개 pin 각각 SHA-256 hash 확인.
- 독립 SDD task review: Spec Compliance PASS, Task quality PASS. 경미한 lock 개수 보고 오기를 수정해 55 total/11 added로 정정했다.
- 변경 범위 확인: DB/migration/fixture/service/browser/real MCP endpoint/배포 접촉 없음. 변경은 미커밋 상태.

## 보안 제한·미완료
Hostname allowlist는 DNS rebinding/pinning이나 완전한 SSRF 보호가 아니다. SSE event cap은 전체 JSON body 크기를 제한하지 않으며, async deadline은 CPU-bound schema parsing을 선점하지 않는다. SDK logging을 application integration 전에 검토해야 한다. 실제 자격증명/OAuth, stored endpoint profile, egress policy, route registration, approval/call execution, external connector/sandbox/UAT, 운영 배포는 미구현이다. 기존 fail-closed production dispatch와 IdP 미설정 상태는 유지한다.

## 공식 참고
- [MCP Python SDK v2.3.0 release](https://github.com/modelcontextprotocol/python-sdk/releases)
- [MCP Python SDK client API](https://py.sdk.modelcontextprotocol.io/api/mcp/)
- [MCP Python SDK client transport guide](https://github.com/modelcontextprotocol/python-sdk/blob/main/docs/client/transports.md)

## 연결 기록
- [[00 구현 추적]]
- [[400.프로젝트관리/02 포털 UI UX 작업 기록]]
- [[2026-10-20 최종 리뷰 수정 및 검증 결과]]
