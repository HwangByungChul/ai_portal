---
title: Streamable HTTP 누적 응답 한도 보강
created: 2026-10-21
updated: 2026-10-21
status: contract-implemented
tags: [mcp, tool-gateway, streamable-http, security]
---
# Streamable HTTP 누적 응답 한도 보강

## 요청·결정
T035-C Streamable HTTP discovery adapter의 전체 응답 크기 제한 공백을 닫는다. 한 번의 discovery 작업에서 MCP SDK 협상 응답과 모든 `tools/list` 페이지의 JSON/SSE 응답 바이트를 합산한다. 압축 확장으로 한도를 우회하지 않도록 `Accept-Encoding: identity`를 보내고, identity 외 `Content-Encoding`은 본문을 읽기 전에 거부한다. 실제 금융 endpoint·DB·기관 서비스에는 연결하지 않는다.

## 구현
- `src/backend/app/tools/transports/streamable_http.py`: 호출 단위 누적 2 MiB 응답 예산으로 negotiation 및 모든 응답 스트림을 감싼다. 초과하는 chunk는 애플리케이션 parser로 전달하지 않고 고정된 discovery 오류로 실패한다. 취소·시간초과·읽기 오류·초과·encoding 거부에서 하위 스트림을 shielded close한다.
- SDK의 동시 GET stream 오류가 내부 reconnect 경로로 흡수될 수 있음을 독립 리뷰가 재현했다. 따라서 SDK와 HTTP client 정리가 끝난 뒤 공유 rejection 상태를 다시 검사하고, background GET의 overflow/encoding 거부가 있어도 성공 catalog를 반환하지 않도록 했다.
- `src/backend/tests/test_mcp_streamable_http.py`: JSON/SSE 누적한도, 협상·pagination 합산, 정확 한도 경계, 호출 간 새 budget, 다섯 encoding 거부, 오류·취소 정리와 동시 GET overflow/encoding 우회를 주입형 `MockTransport`로 검증한다.

## 실제 검증
- 명령: `PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m pytest --noconftest -p no:cacheprovider tests/test_mcp_streamable_http.py -q` (`src/backend` 기준)
- 최종 결과: `53 passed in 1.52s`.
- 독립 task review에서 초기 Important finding(동시 GET의 rejection flag가 성공 반환을 막지 못함)을 수정 후 재검토하여 Spec PASS, Quality PASS, 미해결 Critical/Important/Minor 없음.
- 모든 시험은 메모리 안의 mock transport를 사용했다. DB, 실제 endpoint, fixture, credential, connector, `tools/call`, 배포는 건드리지 않았다. 변경은 미커밋 상태다.

## 미완료 범위·다음 단계
전체 byte cap은 응답 크기 확대를 제한하지만 hostname allowlist만으로 DNS rebinding/SSRF를 해결하지 않는다. CPU-bound schema parsing의 별도 자원 한도, 기관 승인 endpoint/egress·DNS pinning, 인증/Secret Manager, registry API 연결, 실제 sandbox, approval/audit/cost gate를 갖춘 별도 `tools/call` 경로는 미구현이다. IdP/MFA는 미설정이고 production dispatch는 계속 fail-closed다. 다음 단계는 실제 endpoint 통합 전에 기관과 egress·DNS pinning 및 auth delegation 계약을 확정하는 것이다.

## 연결
- [[00 구현 추적]]
- [[2026-10-20 Streamable HTTP 도구 탐색 어댑터 구현]]
- [[400.프로젝트관리/02 포털 UI UX 작업 기록]]
