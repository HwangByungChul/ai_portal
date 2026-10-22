# 금융 특화 MCP Tool Gateway 상세 구현 계획안

> 실행 시 각 작업은 현재 저장소 규칙과 본 계획의 보안·승인 gate를 유지하고, 작은 검증 단위로 진행한다.

**목표:** 기존 MCP Tool 자동 생성 기반을 영속 레지스트리, 표준 MCP 원격 전송, 실제 connector 실행, 금융 업무 승인, 최소 권한 통제, 감사·복원력까지 갖춘 단계적 금융용 MCP Gateway로 발전시킨다.

**아키텍처:** OpenAPI/WSDL/JDBC/금융 전문 파서는 connector onboarding 계층으로 유지하고, 외부 MCP 서버 연결은 별도 MCP backend adapter로 다룬다. 모든 `tools/list` 및 `tools/call`은 tenant·owner·사용자·agent 권한, 게시된 도구 버전, 위험정책을 평가하는 중앙 Gateway를 통과한다. 자격증명은 서버 측 Secret Manager/KMS에 두며, 쓰기·거래 도구는 불변 버전·payload에 결속된 별도 승인 gate를 거친 후에만 backend로 전달한다.

**기술 기준:** 현재 FastAPI/Pydantic 백엔드, React/TypeScript 관리자 포털, PostgreSQL 기반 tenant/RLS·승인·감사 원장 패턴을 우선 재사용한다. 원격 MCP는 공식 호환성을 확인한 Streamable HTTP를 기본으로 하고 stdio는 로컬 개발 어댑터로 한정한다. WebSocket은 MCP 표준 전송으로 가정하지 않고 별도 제품 요구가 입증될 때 추가 검토한다.

**기준 문서:** `docs/Obsidain/200.프로젝트실행/250.구현/36 T-035 MCP 및 외부 Tool 연동 노코딩 자동변환 구현 결과.md`; `docs/Obsidain/200.프로젝트실행/250.구현/2026-10-18 노코딩 MCP Tool 자동 생성 화면 기능 설명 및 구현 범위.md`; `docs/Obsidain/100.프로젝트계획/37 미완료 기능 잔여 개발 통합 상세 계획.md`; `AGENTS.md`.

## 공통 제약

- 현재 구현은 파서·화면·일부 라우팅 코드의 기반이다. `_execute_protocol`은 모의 응답을 반환하고 동적 등록/감사 데이터는 메모리 구조체에 있으므로 실제 금융 시스템 연동·영속성·기관 수용 완료로 표현하지 않는다.
- 제안·등록 요청·타인 승인·게시·실행·실기관 검증·운영 배포를 서로 다른 상태로 기록한다.
- 기존 승인 gate, tenant/owner 범위, exact asset/tool version, 감사·비용 원장, 취소·unknown 결과 보존을 우회하지 않는다.
- 기존 migration 파일을 수정하지 않는다. 적용 전 활성 DB 상태 확인, 백업·복구 가능성 확인, 별도 fixture clone 적용, 기존 행 및 checksum 보존을 증명한다. DB/fixture 작업은 직렬 실행한다.
- 사용자 credential은 브라우저·공개 설정·번들·로그·검증 증거에 두지 않는다. 기존 커스텀 암호화 코드는 운영 보안 검토 전까지 안전한 Vault 대용으로 취급하지 않는다.
- 실제 외부 연결은 기관 소유자·보안담당자가 승인한 sandbox, 제한 자격증명, 합성 데이터로만 시험한다. 접속정보가 없으면 contract/mock 시험만 수행했다고 기록한다.
- 생성형 AI 플랫폼 명칭을 사용한다. 제품 화면에서 BNK 브랜드를 새로 넣지 않는다.

---

## 목표 처리 흐름과 계약

1. 관리자가 OpenAPI/WSDL/JDBC/금융전문 명세 또는 원격 MCP server를 등록 요청한다.
2. 서버가 출처·스키마·호스트·인증방식·데이터 등급·위험 분류를 검사하고 도구 버전을 draft로 저장한다. 변경된 description/schema/annotation은 새 revision으로 취급한다.
3. 권한 있는 검토자가 도구별 노출범위·입출력 정책·승인 조건·환경 프로파일을 검토하고 승인한다. 게시 시 승인된 exact revision과 설정 지문을 봉인한다.
4. 실행 시 Gateway가 현재 사용자·agent·tenant·asset publication·tool revision·문서/데이터 ACL·위험 정책을 다시 확인한다. 목록 단계에서 비노출 도구를 제외하고 호출 단계에서 동일 정책을 재검사한다.
5. 읽기 전용 허용 도구는 직접 실행한다. 금융거래/민감 변경 도구는 실행 의도와 canonicalized arguments의 해시를 가진 `pending_approval` 요청으로 보류한다. 다른 승인자와 요구된 MFA/IdP assurance가 확인되기 전 upstream 요청을 발송하지 않는다.
6. 승인 후 실행 결과/오류/비용/시간을 trace와 append-only audit 원장에 연결한다. 외부 side effect 결과가 불명확하면 자동 재시도하지 않고 `unknown`으로 남겨 수동 조정한다.

제안 API 계약(기존 route와 충돌 여부 확인 후 확정):

- `POST /api/v1/admin/tools/onboarding/parse`: spec source 및 원본 지문 수신, 도구 초안/진단 반환. 입력 크기 제한, 안전한 parser, SSRF 차단.
- `POST /api/v1/admin/tools`: draft revision 저장 및 idempotent receipt 반환. Endpoint credential은 Secret Manager reference만 저장.
- `GET /api/v1/admin/tools` 및 `GET /api/v1/admin/tools/{tool_id}/versions/{version_id}`: 현재 관리자 범위 안의 목록/버전 상세.
- `POST /api/v1/admin/tools/{tool_id}/approval-requests`, `GET/POST /api/v1/admin/tool-approvals/{request_id}`: 기존 승인 B 흐름/승인 원장과 연결. 신청자 자기승인 금지.
- `GET /api/v1/mcp/{server_id}/tools` 및 `POST /api/v1/mcp/{server_id}/tools/{tool_name}/calls`: MCP 클라이언트 호출용 정책 집행면. 실제 구현 시 선택된 공식 MCP SDK 및 표준 JSON-RPC envelope를 따른다.
- 모든 변경 요청은 CSRF 보호, 엄격한 Pydantic schema, 요청 ID/idempotency, no-store, tenant scope를 적용한다. list 응답에 민감한 backend URL/credential을 포함하지 않는다.

## 구현 작업 패키지

### T035-A: 기준선·데이터 계약·위협 모델 확정

**대상 파일:** `docs/Obsidain/200.프로젝트실행/240.설계/35 MCP 및 외부 Tool 연동 노코딩 자동변환 상세 구현 계획서.md`, `docs/Obsidain/100.프로젝트계획/37 미완료 기능 잔여 개발 통합 상세 계획.md`, `src/backend/app/tools/*`, `src/backend/migrations/*`, 승인·실행 원장 관련 모듈.

- [ ] 최신 DB migration manifest, 실제 DB 적용 상태, T-035 코드와 승인/게시/실행 원장을 대조해 현재 기준선을 별도 조사 기록으로 확정한다. migration 번호를 계획 문서에서 임의로 고정하지 않는다.
- [ ] 도구 인벤토리 계약에 `tenant_id`, `owner_id`, `tool_id`, immutable `version_id`, source type, source digest, schema/metadata digest, risk class, data classification, approval state, publication state, owner, protocol/capability, timeout, rate limit, retention, endpoint secret reference를 정의한다.
- [ ] 위협 모델에 tool poisoning, 간접 prompt injection, confused deputy, credential exfiltration, SSRF/DNS rebinding, tenant crossover, replay/double execution, approval race, oversized/malformed payload, malicious response, audit tampering을 포함한다.
- [ ] T-035 parser/모의 실행의 현재 완료 범위와 미완료를 계획·기록에 명확히 분리한다.

**완료 기준:** 현재 DB와 원장 연결 지점이 확인되고, 모델/권한/승인/실행 상태 전이와 위협 완화 담당 모듈이 검토 가능한 표로 정리된다. 이 작업은 코드 구현이나 외부 연동 완료로 세지 않는다.

### T035-B: 영속 Registry와 immutable Tool revision

**예상 코드:** `src/backend/app/tools/repository.py`, `service.py`, `schemas.py`, `routes.py`(기존 `autowrap_routes.py`는 호환 route 이관 전까지 얇은 facade로 유지), 신규 migration, `src/backend/tests/test_tool_registry.py`.

- [ ] 현재 migration/RLS/RPC 작성 관례에 맞춰 tool definition, immutable versions, endpoint profile(Secret Manager reference만), approvals/publications, registry audit event의 관계를 설계한다.
- [ ] 신규 migration을 추가하고 필요한 FORCE RLS/tenant·owner 정책, FK·유일 revision, append-only 이력, CAS·idempotency 처리 함수를 정의한다. 기존 정의 테이블의 명칭/컬럼과 충돌하면 기존 스키마를 보존하는 점진 변경안을 택한다.
- [ ] application이 전역 in-memory dict를 source of truth로 쓰지 않도록 repository를 구현한다. cache는 DB revision/fence와 일치 검증 후 보조 용도로만 둔다.
- [ ] 생성/갱신은 revision 증가와 source/schema digest 봉인을 수행한다. 기존 revision은 수정하지 않고 metadata 또는 endpoint 정책 변경도 새 revision 또는 독립 불변 policy revision으로 기록한다.
- [ ] tenant 소유자 외 상세 접근, 타 tenant ID 추측, stale revision, 동일 요청 재전송, disable/revoke 동시성, 읽기/쓰기 권한 분리를 시험한다.

**완료 기준:** 별도 fixture clone에서 migration 및 RLS 검증 통과, 기존 데이터/checksum 보존, 별도 계정 권한 시험 통과. fixture rows 결과는 운영 데이터와 혼동하지 않는다.

### T035-C: 표준 MCP 연결·발견·실제 connector dispatcher

**예상 코드:** `src/backend/app/tools/transports/streamable_http.py`, `mcp_client.py`, `connectors/{openapi,wsdl,jdbc,financial_packet}.py`, `dispatch.py`; parser/route/gateway의 모의 dispatch 대체; `src/backend/tests/test_tool_transports.py`, `test_tool_connectors.py`.

- [ ] 공식 MCP SDK 및 프로젝트 지원 Python 버전을 확인해 의존성을 고정한다. MCP 2026 최신 버전 호환 여부와 레거시 버전 협상, Streamable HTTP·stdio 지원 범위를 문서화한다.
- [ ] 원격 Streamable HTTP 연결 시 TLS, Host/Origin 정책, redirect 금지 또는 allowlist, timeout, 연결/응답 크기 제한, server identity 및 JSON-RPC 오류 처리를 구현한다. stateless 운용을 우선하고 표준 사양상 필요한 상태만 명시적으로 둔다.
- [ ] `tools/list` 결과를 정규화하고 도구명 충돌 namespace, JSON Schema 검증, deterministic ordering, upstream metadata source/version/hash를 보존한다. 클라이언트가 제시한 `publication_status`를 신뢰하지 않고 서버가 승인 원장으로 계산한다.
- [ ] OpenAPI connector는 HTTPS method/path/query/header/body binding과 response schema 제한을 구현한다. 자유 URL 구성 금지.
- [ ] WSDL connector는 허용 SOAP binding/version/action과 XML parser hardening(외부 entity/DTD 금지)을 구현한다.
- [ ] JDBC connector는 사전 승인 view와 bind parameter만 허용하는 read-only DB role을 사용한다. 문자열 블랙리스트만으로 안전성을 주장하지 않는다.
- [ ] 금융전문 connector는 기관 승인 layout/version, encoding, length, checksum/validation 및 제한 endpoint를 구현한다. 전송 형식/응답이 확인되지 않은 부분은 지원하지 않는다고 명시한다.
- [ ] 실패·429·5xx·TLS 오류·잘못된 응답·timeout·늦은 응답·취소·중복 호출을 contract adapter로 재현한다. side effect 요청은 receipt 미확인 상태에서 자동 재발사하지 않는다.

**완료 기준:** parser 생성 스키마와 `tools/list` 계약이 맞고, mock/contract 시험이 pass한다. 허가된 sandbox 시험은 connector별 별도 결과로 기록한다.

### T035-D: 중앙 정책 집행, RBAC, 인증·Secret lifecycle

**예상 코드:** `src/backend/app/tools/policy.py`, `authorization.py`, `credentials.py` 및 `src/backend/app/tools/autowrap_routes.py`; 관련 security functions/migration; `src/backend/tests/test_tool_authorization.py`, `test_tool_credentials.py`.

- [ ] `tools/list`와 `tools/call` 양쪽에 공통 policy evaluator를 적용한다. tenant, user, agent identity, asset exact publication, tool revision, 역할/그룹, data class, 업무 scope, 목적, 위험 등급을 서버 컨텍스트에서 계산한다.
- [ ] list filtering은 노출 최소화 UX일 뿐 보안 경계가 아니므로 call 시 같은 정책을 다시 검사한다. client가 넘기는 user_id/tenant_id/publication_status/environment는 authorization 근거로 사용하지 않는다.
- [ ] Gateway↔upstream 인증은 사용자 위임 OAuth, client credentials, managed identity 중 connector별 최소권한 방식으로 정의한다. identity pass-through는 기본 차단하고 승인된 delegation contract가 있을 때만 제한 허용한다.
- [ ] 자격증명 입력 UI를 secret value 입력에서 Vault 등록/참조 흐름으로 바꾼다. 암호화 키 관리, envelope encryption, rotation, revocation, 접근 감사, 복구를 KMS/Secret Manager와 연계한다. 현재 커스텀 keystream 구현을 운영 수준 암호화로 간주하지 않는다.
- [ ] MFA/step-up은 IdP assurance claim과 정책으로 검증한다. 화면의 임의 MFA 완료 flag로 대체하지 않는다.
- [ ] 회수/사용자 disable/그룹 변경/게시 철회/secret rotation이 `tools/list`, 신규 call, 승인 후 실제 dispatch 전에서 반영되도록 race 시험한다.

**완료 기준:** 양 사용자·양 tenant 권한 matrix, 비노출/호출 차단, 회수 경합, secret 값이 응답/로그/UI에 없는 테스트 통과. 실제 IdP가 없으면 IdP 통합은 미검증으로 둔다.

### T035-E: 금융 Human-in-the-loop 승인 및 exact execution gate

**예상 코드:** 기존 approval domain/service를 재사용하고 필요 시 `src/backend/app/tools/approval.py`, `src/backend/app/tools/execution.py`, 기존 관리자 승인 API/화면, `src/backend/tests/test_tool_approval.py`를 추가한다.

- [ ] 도구 등록 시 read-only / sensitive-read / reversible-write / financial-side-effect 등 위험 분류와 요구 승인 단계·승인자 역할·MFA level·금액/건수·조직 scope·운영환경 조건을 지정한다.
- [ ] 호출 전에 canonical arguments, tool version digest, user/agent/tenant, asset publication version, target environment, policy revision, 만료시간을 봉인한 approval request를 만든다.
- [ ] 상태 전이를 `requested → pending → approved | rejected | expired | cancelled → dispatched → succeeded | failed | unknown`으로 기록하고 불가능한 전이를 거부한다. requester self-approval 금지, 고위험 작업 다중 승인 정책은 2인 독립 계정으로 검사한다.
- [ ] 승인 후 실행 직전에 current authorization, approval expiry, payload hash, tool/asset publication digest, environment policy를 재확인한다. 하나라도 바뀌면 실행 거부 후 재신청한다.
- [ ] 승인 대상 호출 인자나 결과에 민감값이 포함되면 검토 화면은 최소 필요 정보/마스킹만 표시한다. 알림 채널은 승인 reference만 전달하고 자격증명/전체 금융 인자를 보내지 않는다.
- [ ] list/read 도구의 무승인 경로와 변경/거래 도구의 fail-closed 경로를 분리 검증한다. approval-service 장애 시 고위험 호출은 실행하지 않는다.

**완료 기준:** 승인 전 upstream packet 0건, 승인자·MFA·payload/version 변경·만료·취소·중복 제출 시나리오 통과, 승인 이벤트가 기존 관리자 B 요청 목록/상세 흐름에서 조회된다. 승인 접수와 실제 실행/게시 완료는 따로 표시한다.

### T035-F: Tool metadata·입출력 가드레일과 hybrid routing

**예상 코드:** `src/backend/app/tools/validation.py`, `metadata_integrity.py`, `routing.py`, parser/adapters, `src/backend/tests/test_tool_guardrails.py`.

- [ ] onboarding 시 명세 원본 digest, 생성 schema digest, 공급자/소유자/버전/검토자/승인 시점을 기록한다. 기존 승인 revision의 description/schema/annotation 변경은 새 revision과 재검토 없이는 게시되지 않는다.
- [ ] 도구 설명은 신뢰되지 않은 입력으로 분류하고 HTML/Markdown/Unicode 혼동 및 prompt instruction 표시를 탐지·검토한다. 메타데이터 탐지 결과를 완전한 injection 방어로 주장하지 않는다.
- [ ] JSON Schema 타입/크기/정규화 검증, SQL bind 변수, path segment encoding, command/SQL interpreter 미호출 원칙, 개인정보/기밀 분류·마스킹 정책을 connector별로 적용한다.
- [ ] upstream result도 untrusted content로 취급한다. 모델에 전달 전 allowlisted schema·크기·PII·정책 검사를 하고, 원문·비밀을 불필요하게 trace에 기록하지 않는다.
- [ ] data classification/policy가 on-prem route를 요구하면 승인된 사내 모델/connector만 허용한다. 외부 cloud로 전달되는 데이터는 기본 차단하고 명시된 정책·DLP 결과와 route decision을 남긴다.
- [ ] 차단·정책엔진 장애·분류 unknown은 fail-closed 대상과 제한적 read-only fallback 대상을 사전에 구분한다.

**완료 기준:** metadata 변조로 인한 재승인 누락이 없고, malicious input/output, 잘못된 MIME/schema, 초대형 payload, 외부 route 차단을 검증한다. injection 탐지는 완화 수단으로만 표기한다.

### T035-G: 감사 추적·불변성·운영 복원력

**예상 코드:** 기존 audit/ledger 원장 확장, `src/backend/app/tools/audit.py`, `resilience.py`, `src/backend/tests/test_tool_audit_resilience.py`.

- [ ] trace에는 correlation/trace ID, user·agent·tenant·asset/tool exact version, metadata/policy digest, approval ID, route decision, secret reference ID(값 제외), redacted argument digest, dispatch/receipt status, latency/error category, usage/cost를 최소 필요로 연계한다.
- [ ] 전체 프롬프트·민감 arguments·금융 응답을 무조건 복제하지 않는다. 법무/보안 승인된 보존기간·마스킹·암호화·접근통제에 따라 필요 데이터만 보관한다.
- [ ] append-only DB 정책과 별도 보안 저장/서명 또는 hash-chain 검증으로 tamper-evident 체계를 구성한다. 해시만으로 물리적 불변이라고 주장하지 않는다.
- [ ] endpoint/tool별 timeout, concurrency limit, token bucket rate limit, circuit breaker, bounded retry를 둔다. 쓰기/금융 side effect는 강한 idempotency 계약 또는 기관 receipt 없이는 retry 금지.
- [ ] circuit open/half-open, quota exceeded, audit store 장애, 늦은 성공 receipt, 취소 경합은 안전한 상태로 기록하고 관리자 운영 현황/알림으로 노출한다.

**완료 기준:** audit 조회가 현재 권한을 적용하고 trace 단계가 승인·실행 원장과 맞는다. 실패/정책 차단/불명 side effect에도 원장과 비용 보존이 유지된다.

### T035-H: 관리자 제작·승인 UX와 운영 전환

**예상 코드:** `src/frontend/src/ToolAdminPage.tsx`, 선택한 admin app의 route/sidebar, API contract types, 관련 스타일·브라우저 acceptance spec.

- [ ] 현재 마법사를 ① 소스/서버 등록 ② 파싱 결과·위험 진단 ③ 도구 선택·metadata 검토 ④ scope·data classification·endpoint secret reference ⑤ 권한/승인정책 ⑥ dev sandbox contract test ⑦ 제출/receipt 단계로 나눈다.
- [ ] 상태 배지를 Draft, 검토 대기, 승인됨, 게시됨, 차단, 철회, 시험 실행, 운영 호출로 분리한다. mock test 결과는 `모의/contract test`로 표기한다.
- [ ] Tool detail에 버전/digest 변경내역, source, endpoint health의 검사 시각·결과, 권한 scope, 승인 내역, 호출/오류/차단 지표, circuit state를 표시한다. Secret은 다시 표시하지 않는다.
- [ ] 기존 사용자 A안·관리자 A안 홈, 관리자 B 승인 목록·상세 패널 확정 설계와 사이트 분리를 따른다. 화면 변경 전 확정 UI 노트 및 최신 MCP screen design을 재확인한다.
- [ ] browser에서 parse→저장→제출 receipt→타인 승인→게시→목록 필터링→인가/비인가 call→감사 trace 조회를 stub과 인증 계정으로 검증한다. 조직 전환/권한 철회 중 화면 데이터 정리도 검사한다.

**완료 기준:** UI가 실제 API 상태를 반영하고 fixture/모의/실제 sandbox를 명확히 구분한다. user/admin 독립 빌드 경계 검사 통과. 스크린샷/화면 존재만으로 기능 완료로 판정하지 않는다.

### T035-I: 단계별 수용·릴리스 gate

- [ ] **Gate 1 — 코드 계약:** parser·schema·repository·policy·mock connector 테스트. 실제 금융망 접근 없음.
- [ ] **Gate 2 — 보안 통합:** 두 tenant/두 사용자/관리자·승인자 matrix, CSRF, 권한회수, SSRF, secret redaction, tool metadata 변경, approval replay/expiry, audit access, circuit breaker 시험.
- [ ] **Gate 3 — 비운영 환경:** approved sandbox·제한 계정·합성자료로 connector 종류별 정상/거절/timeout/잘못된 응답/중복/late receipt/취소·재조정 수행. 기관 승인·시험 증거를 기록한다.
- [ ] **Gate 4 — 업무 수용:** 담당자가 각 위험등급·승인정책·최대 금액/데이터 범위·보존·운영 장애 연락·수동 복구를 서면 검토한다.
- [ ] **Gate 5 — 운영 이행:** 별도 승인된 환경 설정·인증서/Secret rotation·모니터링·복구 연습·롤백/runbook·실제 계정·UAT 후에만 진행한다. 사용자 요청 없이 배포를 수행하지 않는다.
- [ ] 시험은 기존 repo의 테스트 패턴과 새 contract tests를 사용한다. fixture DB harness/migration/browser shared service는 직렬 수행하고 실제 검증 결과만 보고한다.

**전체 완료 조건:** T-035의 connector별 수용 기준, tool registry/정책/승인/audit 구현, 실제 sandbox 증거, 업무 담당자 수용이 모두 명시적으로 충족돼야 한다. 부분 connector만 수용되면 connector별 범위로만 판정한다. 운영 배포는 별도 gate다.

## 단계 의존성·제안 순서

| 순서 | 작업 | 선행 조건 |
|---|---|---|
| 0 | T035-A 기준선·위협 모델 | 최신 코드·DB·승인/실행 원장 조사 |
| 1 | T035-B 영속 Registry | DB migration 감사, tenant/RLS 설계, Secret Manager 선택 |
| 2 | T035-C MCP 전송·connector contract | 공식 SDK/버전 선택, onboarding schema 확정 |
| 3 | T035-D 권한·인증·credential lifecycle | tenant/user/agent context 및 IdP/Vault contract |
| 4 | T035-E 금융 승인 gate | 기존 approval B 흐름과 exact publication 연결 계약 |
| 5 | T035-F guardrails·hybrid routing | 보안 분류·DLP/정책 소유자·온프렘 route 결정 |
| 6 | T035-G audit·복원력 | 기존 실행/비용/audit ledger 연결 및 retention 결정 |
| 7 | T035-H UX·T035-I 수용 | API/정책 계약 안정, 사용자 역할·sandbox 준비 |

각 단계는 별도 구현·시험 결과 문서와 작업 로그로 추적한다. 보안/승인/데이터 모델 하위 계획은 첫 구현 전에 검토 가능한 상세 설계로 확정한다. 이 계획 승인만으로 코딩·기관 연결·운영 배포가 승인된 것으로 간주하지 않는다.

## 최신 MCP 동향 반영 메모 (2026-10-18)

- 공식 MCP 문서의 draft changelog는 Streamable HTTP의 protocol-level session 및 `Mcp-Session-Id` 제거, `tools/list` 결정적 순서, trace context 전달을 설명한다. 본 계획은 세션 고정을 피하고 SDK/프로토콜 버전 확인을 T035-C 선행 항목으로 둔다.
- MCP 2026-07-28 사양 릴리스 후보는 stateless protocol 변경을 설명한다. 이를 곧바로 현재 확정 사양/모든 SDK 지원으로 가정하지 말고 정식 spec 및 사용 SDK의 호환표를 구현 직전에 재확인한다.
- Microsoft Agent 365/AI Gateway 문서는 중앙 inventory, server/tool 단위 allow/block, runtime 정책, rate limit, IP filtering, 인증·관측성을 보여 준다. 본 계획은 tool 수준 통제와 runtime 재검사를 반영한다.
- 공식 MCP protocol은 이 업무의 금융 2인 결재·MFA·업무 승인정책을 대신하지 않는다. 이를 조직 Gateway 정책과 기존 승인 workflow의 책임으로 둔다.

## 참고 자료

- [MCP 사양 draft changelog](https://modelcontextprotocol.io/specification/draft/changelog)
- [2026-07-28 MCP 사양 릴리스 후보](https://blog.modelcontextprotocol.io/posts/2026-07-28-release-candidate/)
- [Microsoft Manage Tools Gateway](https://learn.microsoft.com/en-us/microsoft-365/admin/manage/manage-tools-gateway)
- [Microsoft MCP tool-level governance](https://learn.microsoft.com/en-us/microsoft-365/admin/manage/manage-plugins-skills-mcp-servers)
- [Azure API Management AI Gateway 도구 관리](https://learn.microsoft.com/en-us/azure/api-management/ai-gateway-manage-models-tools)
- [AWS Agentic AI MCP Registry 보안 모범사례](https://docs.aws.amazon.com/wellarchitected/latest/agentic-ai-lens/agentsec02-bp03.html)

## 관련 프로젝트 기록

- [[200.프로젝트실행/240.설계/35 MCP 및 외부 Tool 연동 노코딩 자동변환 상세 구현 계획서]]
- [[200.프로젝트실행/250.구현/36 T-035 MCP 및 외부 Tool 연동 노코딩 자동변환 구현 결과]]
- [[200.프로젝트실행/250.구현/2026-10-18 노코딩 MCP Tool 자동 생성 화면 기능 설명 및 구현 범위]]
- [[100.프로젝트계획/37 미완료 기능 잔여 개발 통합 상세 계획]]
- [[400.프로젝트관리/02 포털 UI UX 작업 기록]]
