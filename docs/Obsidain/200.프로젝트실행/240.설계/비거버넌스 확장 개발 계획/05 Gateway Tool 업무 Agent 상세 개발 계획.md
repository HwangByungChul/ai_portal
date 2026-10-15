# Gateway·연계·업무 Agent Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.
>
> 위 안내는 향후 구현 시 참고할 실행 방식입니다. 이번 요청은 계획서 작성이며 자동 구현·자동 위임을 시작하지 않습니다. 이 문서의 신규 API/파일/정책은 제안 계약으로, 기존 기능으로 간주하지 않습니다.

**Goal:** 거버넌스 포털을 제외한 사용자·관리자 AI 플랫폼을 기존 멀티테넌트/GraphRAG 기반에서 단계적으로 확장합니다.

**Architecture:** React/Vite 사용자·관리자 화면과 FastAPI 도메인 모듈을 확장합니다. PostgreSQL RLS·현재 권한 확인·불변 실행 snapshot·중앙 AI 허가/원장을 모든 새 기능에 유지하며, 외부 Gateway 구매 없이 공통 인증/한도/라우팅 모듈로 연결합니다.

**Tech Stack:** 현재 저장소의 React/TypeScript/Vite, FastAPI/Python, PostgreSQL/pgvector와 `src/common_core/ai_pipeline`을 유지합니다. Python >=3.13,<3.14, Node 22.23.1은 현행 설정입니다. 신규 라이브러리는 이 계획으로 설치하거나 버전을 변경하지 않습니다.

**Spec:** [09 제안 구축 분석 대비 현재 구현 비교 보고서(거버넌스 포털 제외)](</Users/jwpios/antigravity/202610_AI 플랫폼/docs/Obsidain/100.프로젝트계획/09 제안 구축 분석 대비 현재 구현 비교 보고서(거버넌스 포털 제외).md>). 상세 F/IA/T 원장은 해당 보고서의 근거 폴더를 사용합니다.

## Global Constraints

- AI 거버넌스 포털 F-050~060 및 SCR-GOV35개는 구현 범위에서 제외합니다.
- F-001~049에 별도로 정의된 관리자 보안·감사·SOD·배포/반입/과제 승인은 유지합니다.
- 일정/마감 제약은 없습니다. 특정 완료일·기간·전체 완료율을 약속하지 않습니다.
- 개인 학습·향후 제안 시연 목적입니다. 합성 데이터/모의 실행 우선, 실제 모델은 현재 승인된 저비용 설정을 재사용합니다.
- 논리적 조직 격리가 우선입니다. Private 서빙/GPU/Cell/K8s/기관 DRM·SSO 실연계는 조건부 하위 범위로 관리합니다.
- API G/W 상용 솔루션을 도입하지 않습니다. 기존 앱 공통 모듈과 표준 프로토콜 경계를 확장합니다.
- 사용자/tenant/role은 서버의 인증 컨텍스트에서 결정하며, body/모델출력의 값을 권한으로 사용하지 않습니다.
- 관리자 역할만으로 개인 대화·원문 열람을 허용하지 않습니다. 회수·한도·중복 실행·unknown 비용 보존은 완화하지 않습니다.
- 실행 중/완료 run snapshot·원문 version·발생 비용/감사 기록은 설정 변경/삭제/복제/복귀로 덮어쓰지 않습니다.
- T-019/020/029/034/062는 원본 최초오픈 제외로 추적하며 이번 구현 범위에 자동 추가하지 않습니다.

---
## 문서 연결

총괄: [10 비거버넌스 AI 플랫폼 상세 개발 계획서](</Users/jwpios/antigravity/202610_AI 플랫폼/docs/Obsidain/100.프로젝트계획/10 비거버넌스 AI 플랫폼 상세 개발 계획서.md>). 추적: [비거버넌스 확장 개발 요구 추적표](</Users/jwpios/antigravity/202610_AI 플랫폼/docs/Obsidain/200.프로젝트실행/220.요구정의/비거버넌스 확장 개발 요구 추적표.md>). 각 작업은 코드/DB/API/화면/시험을 함께 묶는 독립 수용 단위입니다.

### DP-20: API Gateway·표준 외부 API

**선행:** DP-13, DP-16, DP-18

**요구 연결:** F-006, F-021, F-043, F-044, F-047, F-048, F-049 / T-004, T-008, T-018, T-044, T-054

**Files / 책임:**

- Create (제안): `src/backend/app/api_clients/routes.py` — API Gateway·표준 외부 API의 해당 도메인/화면/산출물.
- Create (제안): `src/backend/app/api_clients/auth.py` — API Gateway·표준 외부 API의 해당 도메인/화면/산출물.
- Create (제안): `src/backend/app/api_clients/limits.py` — API Gateway·표준 외부 API의 해당 도메인/화면/산출물.
- Modify: `src/backend/app/main.py` — API Gateway·표준 외부 API의 해당 도메인/화면/산출물.
- Test (제안): `src/backend/tests/test_dp20_acceptance.py` — 아래 서버/데이터 수용 case.
- Test (제안): `src/frontend/tests/dp20-acceptance.spec.ts` — 같은 계약의 실제 화면 흐름/권한/조직전환.

**Interfaces — 제안 계약:**

```json
{
  "POST /api/v1/integration/runs": "service principal+asset_version_id+client_send_id+prompt",
  "ApiClient": "tenant,allowed_assets,allowed_operations,credential_ref,rate_limit,quota,expires_at"
}
```

**데이터·상태·보존:** 별도serviceprincipal; 내부session/CSRF경로와별개. tenant는검증clientbinding에서유도. 외부응답도현행에러envelope/requestID/원장.

**상세 개발 내용:** 상용GW없는애플리케이션 공통middleware+인증/한도/감사/권한contract. 기존중앙gateway통과만허용; TLS/reverseproxy는DP-26환경작업. OpenAPI명세/scope/버전/오류/read/동일send재전송지원.

**수용 시험 벡터:** 각 벡터를 지정한 시험 파일의 독립 case로 작성합니다. request/seed·변경 전 상태·예상 응답/DB/외부송신·증거를 함께 검증합니다.

```json
[
  {
    "case_id": "DP-20-C01",
    "assertion": "client A가body/header tenant B주입실패",
    "mode": "synthetic/mock first",
    "verdict_before_implementation": "not_run"
  },
  {
    "case_id": "DP-20-C02",
    "assertion": "만료/회수client즉시차단",
    "mode": "synthetic/mock first",
    "verdict_before_implementation": "not_run"
  },
  {
    "case_id": "DP-20-C03",
    "assertion": "gateway직접우회/API경로별한도차이0",
    "mode": "synthetic/mock first",
    "verdict_before_implementation": "not_run"
  },
  {
    "case_id": "DP-20-C04",
    "assertion": "실행중재전송중복dispatch0",
    "mode": "synthetic/mock first",
    "verdict_before_implementation": "not_run"
  }
]
```

- [ ] 230 분석에서 관련 기존 SQL 정책함수/DTO/호출경로를 확인하고240에 위 계약·state/ACL·오류·snapshot·비용·migration 설계를 확정한다.
- [ ] `src/backend/tests/test_dp20_acceptance.py`에 각 case의 fixture/input/expected output·DB·송신 assertion을 작성한다. 현재 미제공 동작의 실패를 확인한다.
- [ ] schema가 필요한 경우 RLS·권한함수·migration을 추가하고, 제안 계약의 서버/adapter와 화면을 최소 수용 범위로 구현한다.
- [ ] 변경된 서버 case를 실행하여 정상/음성/충돌/회수/원장 결과가 모두 일치하는지 확인한다.
- [ ] `src/frontend/tests/dp20-acceptance.spec.ts`에서 정상흐름·접근거부·조직전환·모바일을 검증하고 frontend build를 확인한다.
- [ ] 공통 모듈 변경 영향의 기존 회귀를 수행하고260/280에 code hash·case·mode·결과를 저장한다.
- [ ] 해당 파일과 산출물만 묶어 검토 가능한 변경으로 저장하고 완료/미실행을 추적표에 갱신한다.

**종료 기준:** 외부서비스 인증→조직바인딩→허가/한도→단일실행→원장/감사의통합흐름과발급/회수증거 확보.

**실행 명령(향후 구현 후):**

```bash
# cwd: src/backend
.venv/bin/python -m pytest tests/test_dp20_acceptance.py -q
# cwd: src/frontend
npm run build
npm run test:e2e -- tests/dp20-acceptance.spec.ts
```

### DP-21: 읽기 Tool/MCP Gateway·Connector

**선행:** DP-12, DP-18, DP-20

**요구 연결:** F-011, F-021, F-032, F-043, F-044, F-048 / T-016, T-017, T-035, T-036, T-039, T-040, T-054

**Files / 책임:**

- Create (제안): `src/backend/app/tools/registry.py` — 읽기 Tool/MCP Gateway·Connector의 해당 도메인/화면/산출물.
- Create (제안): `src/backend/app/tools/gateway.py` — 읽기 Tool/MCP Gateway·Connector의 해당 도메인/화면/산출물.
- Create (제안): `src/backend/app/tools/credentials.py` — 읽기 Tool/MCP Gateway·Connector의 해당 도메인/화면/산출물.
- Create (제안): `src/backend/app/connectors/synthetic_catalog.py` — 읽기 Tool/MCP Gateway·Connector의 해당 도메인/화면/산출물.
- Create (제안): `src/frontend/src/ToolAdminPage.tsx` — 읽기 Tool/MCP Gateway·Connector의 해당 도메인/화면/산출물.
- Test (제안): `src/backend/tests/test_dp21_acceptance.py` — 아래 서버/데이터 수용 case.
- Test (제안): `src/frontend/tests/dp21-acceptance.spec.ts` — 같은 계약의 실제 화면 흐름/권한/조직전환.

**Interfaces — 제안 계약:**

```json
{
  "invoke_tool(ctx,asset_version,tool_version,arguments,client_operation_id)": "ToolResult(data,trace_id,source_refs)",
  "ToolVersion": "id,operation_allowlist,arg_schema,result_schema,server_binding,credential_ref"
}
```

**데이터·상태·보존:** 합성상품/규정readconnector1개→MCP프로토콜 adapter→OpenAPIconnector순. JDBC/WSDL/전문자동wrapping은제각각adapter시험필요.

**상세 개발 내용:** 명시등록server·operation/schema/크기/시간/egress검증; arbitraryURL/path/shell금지. user위임credential서버보관; Tool전후scope/정책/현재권한검사. Tool호출원장은모델과별타입이나동일requesttrace. 모델최종답변만중앙모델op.

**수용 시험 벡터:** 각 벡터를 지정한 시험 파일의 독립 case로 작성합니다. request/seed·변경 전 상태·예상 응답/DB/외부송신·증거를 함께 검증합니다.

```json
[
  {
    "case_id": "DP-21-C01",
    "assertion": "allowlist밖host/operation차단",
    "mode": "synthetic/mock first",
    "verdict_before_implementation": "not_run"
  },
  {
    "case_id": "DP-21-C02",
    "assertion": "복합arguments형/길이위반차단",
    "mode": "synthetic/mock first",
    "verdict_before_implementation": "not_run"
  },
  {
    "case_id": "DP-21-C03",
    "assertion": "작업ID동일재전송은한번실행",
    "mode": "synthetic/mock first",
    "verdict_before_implementation": "not_run"
  },
  {
    "case_id": "DP-21-C04",
    "assertion": "중간회수/timeout/실패 secret노출0",
    "mode": "synthetic/mock first",
    "verdict_before_implementation": "not_run"
  }
]
```

- [ ] 230 분석에서 관련 기존 SQL 정책함수/DTO/호출경로를 확인하고240에 위 계약·state/ACL·오류·snapshot·비용·migration 설계를 확정한다.
- [ ] `src/backend/tests/test_dp21_acceptance.py`에 각 case의 fixture/input/expected output·DB·송신 assertion을 작성한다. 현재 미제공 동작의 실패를 확인한다.
- [ ] schema가 필요한 경우 RLS·권한함수·migration을 추가하고, 제안 계약의 서버/adapter와 화면을 최소 수용 범위로 구현한다.
- [ ] 변경된 서버 case를 실행하여 정상/음성/충돌/회수/원장 결과가 모두 일치하는지 확인한다.
- [ ] `src/frontend/tests/dp21-acceptance.spec.ts`에서 정상흐름·접근거부·조직전환·모바일을 검증하고 frontend build를 확인한다.
- [ ] 공통 모듈 변경 영향의 기존 회귀를 수행하고260/280에 code hash·case·mode·결과를 저장한다.
- [ ] 해당 파일과 산출물만 묶어 검토 가능한 변경으로 저장하고 완료/미실행을 추적표에 갱신한다.

**종료 기준:** syntheticread→검증결과→근거→trace가동작. 실제MCP서버/레거시연계는adapter별fixture로판정.

**실행 명령(향후 구현 후):**

```bash
# cwd: src/backend
.venv/bin/python -m pytest tests/test_dp21_acceptance.py -q
# cwd: src/frontend
npm run build
npm run test:e2e -- tests/dp21-acceptance.spec.ts
```

### DP-22: RDB/NAS·데이터 가상화·망연계

**선행:** DP-17, DP-19, DP-21

**요구 연결:** F-021, F-041, F-043, F-044, F-045, F-048 / T-014, T-015, T-016, T-017, T-018, T-021, T-050, T-056

**Files / 책임:**

- Create (제안): `src/backend/app/connectors/relational_views.py` — RDB/NAS·데이터 가상화·망연계의 해당 도메인/화면/산출물.
- Create (제안): `src/backend/app/connectors/file_source.py` — RDB/NAS·데이터 가상화·망연계의 해당 도메인/화면/산출물.
- Create (제안): `src/backend/app/connectors/routing.py` — RDB/NAS·데이터 가상화·망연계의 해당 도메인/화면/산출물.
- Test (제안): `src/backend/tests/test_dp22_acceptance.py` — 아래 서버/데이터 수용 case.
- Test (제안): `src/frontend/tests/dp22-acceptance.spec.ts` — 같은 계약의 실제 화면 흐름/권한/조직전환.

**Interfaces — 제안 계약:**

```json
{
  "read_view(ctx,approved_view_id,filters,cursor)": "bounded rows,masked schema,lineage",
  "ingest_source(ctx,connector_version,source_ref)": "import_id",
  "EnvironmentBinding": "draft→synthetic/test; approved+권원→production"
}
```

**데이터·상태·보존:** 미리승인된parameterizedquery/readview만; maxrows100·허용컬럼·timeout고정. 자유SQL/NL-to-SQL제외. NAS검사/원문hash/변경분처리.

**상세 개발 내용:** 합성DB/readview와샌드박스파일소스로먼저검증. 운영망는승인manifest·주체·권원·서버binding검사; 인터넷URL임의연결불가. 검사안된자료는index금지.

**수용 시험 벡터:** 각 벡터를 지정한 시험 파일의 독립 case로 작성합니다. request/seed·변경 전 상태·예상 응답/DB/외부송신·증거를 함께 검증합니다.

```json
[
  {
    "case_id": "DP-22-C01",
    "assertion": "SQL문문자열/미허용필터거부",
    "mode": "synthetic/mock first",
    "verdict_before_implementation": "not_run"
  },
  {
    "case_id": "DP-22-C02",
    "assertion": "draft의productionbinding차단",
    "mode": "synthetic/mock first",
    "verdict_before_implementation": "not_run"
  },
  {
    "case_id": "DP-22-C03",
    "assertion": "조회row/column/tenantbounded",
    "mode": "synthetic/mock first",
    "verdict_before_implementation": "not_run"
  },
  {
    "case_id": "DP-22-C04",
    "assertion": "NASsource교체/중복/중간실패manifest정합",
    "mode": "synthetic/mock first",
    "verdict_before_implementation": "not_run"
  }
]
```

- [ ] 230 분석에서 관련 기존 SQL 정책함수/DTO/호출경로를 확인하고240에 위 계약·state/ACL·오류·snapshot·비용·migration 설계를 확정한다.
- [ ] `src/backend/tests/test_dp22_acceptance.py`에 각 case의 fixture/input/expected output·DB·송신 assertion을 작성한다. 현재 미제공 동작의 실패를 확인한다.
- [ ] schema가 필요한 경우 RLS·권한함수·migration을 추가하고, 제안 계약의 서버/adapter와 화면을 최소 수용 범위로 구현한다.
- [ ] 변경된 서버 case를 실행하여 정상/음성/충돌/회수/원장 결과가 모두 일치하는지 확인한다.
- [ ] `src/frontend/tests/dp22-acceptance.spec.ts`에서 정상흐름·접근거부·조직전환·모바일을 검증하고 frontend build를 확인한다.
- [ ] 공통 모듈 변경 영향의 기존 회귀를 수행하고260/280에 code hash·case·mode·결과를 저장한다.
- [ ] 해당 파일과 산출물만 묶어 검토 가능한 변경으로 저장하고 완료/미실행을 추적표에 갱신한다.

**종료 기준:** 가상화view·원천lineage·routing·권원/감사증거가연결. 기관망/실DB자료없이는생산연계완료아님.

**실행 명령(향후 구현 후):**

```bash
# cwd: src/backend
.venv/bin/python -m pytest tests/test_dp22_acceptance.py -q
# cwd: src/frontend
npm run build
npm run test:e2e -- tests/dp22-acceptance.spec.ts
```

### DP-23: Workflow 모델·실행엔진·Canvas

**선행:** DP-12, DP-21

**요구 연결:** F-004, F-022, F-024, F-032, F-039, F-049 / T-033, T-035, T-036, T-039, T-040, T-042

**Files / 책임:**

- Create (제안): `src/backend/app/workflows/models.py` — Workflow 모델·실행엔진·Canvas의 해당 도메인/화면/산출물.
- Create (제안): `src/backend/app/workflows/runner.py` — Workflow 모델·실행엔진·Canvas의 해당 도메인/화면/산출물.
- Create (제안): `src/backend/app/workflows/checkpoints.py` — Workflow 모델·실행엔진·Canvas의 해당 도메인/화면/산출물.
- Create (제안): `src/frontend/src/WorkflowCanvasPage.tsx` — Workflow 모델·실행엔진·Canvas의 해당 도메인/화면/산출물.
- Test (제안): `src/backend/tests/test_dp23_acceptance.py` — 아래 서버/데이터 수용 case.
- Test (제안): `src/frontend/tests/dp23-acceptance.spec.ts` — 같은 계약의 실제 화면 흐름/권한/조직전환.

**Interfaces — 제안 계약:**

```json
{
  "WorkflowVersion": "id,revision,nodes,edges,max_steps,max_cost,max_seconds,config_hash",
  "node types": [
    "input",
    "llm",
    "read_tool",
    "validate",
    "output"
  ],
  "NodeResult": "state,attempt_id,output_ref,error_code,checkpoint_revision"
}
```

**데이터·상태·보존:** 첫버전DAG/선형·노드max20·실행stepmax20·루프금지; 입출력JSONschema·checkpoint/취소·trace.

**상세 개발 내용:** 실행engine 먼저→저장/검증→Canvas. 재시작은미dispatch단계만재개; 불확실Tool결과는수동검토/중지. 쓰기Tool/외부sideeffect는첫범위제외.후속Saga보상은작업별contract후추가.

**수용 시험 벡터:** 각 벡터를 지정한 시험 파일의 독립 case로 작성합니다. request/seed·변경 전 상태·예상 응답/DB/외부송신·증거를 함께 검증합니다.

```json
[
  {
    "case_id": "DP-23-C01",
    "assertion": "순환graph/unknownnode/shape오류거부",
    "mode": "synthetic/mock first",
    "verdict_before_implementation": "not_run"
  },
  {
    "case_id": "DP-23-C02",
    "assertion": "중간cancel/회수즉시다음node중지",
    "mode": "synthetic/mock first",
    "verdict_before_implementation": "not_run"
  },
  {
    "case_id": "DP-23-C03",
    "assertion": "crash재시작시중복model/tooldispatch0",
    "mode": "synthetic/mock first",
    "verdict_before_implementation": "not_run"
  },
  {
    "case_id": "DP-23-C04",
    "assertion": "Canvas저장 version과실행hash일치",
    "mode": "synthetic/mock first",
    "verdict_before_implementation": "not_run"
  }
]
```

- [ ] 230 분석에서 관련 기존 SQL 정책함수/DTO/호출경로를 확인하고240에 위 계약·state/ACL·오류·snapshot·비용·migration 설계를 확정한다.
- [ ] `src/backend/tests/test_dp23_acceptance.py`에 각 case의 fixture/input/expected output·DB·송신 assertion을 작성한다. 현재 미제공 동작의 실패를 확인한다.
- [ ] schema가 필요한 경우 RLS·권한함수·migration을 추가하고, 제안 계약의 서버/adapter와 화면을 최소 수용 범위로 구현한다.
- [ ] 변경된 서버 case를 실행하여 정상/음성/충돌/회수/원장 결과가 모두 일치하는지 확인한다.
- [ ] `src/frontend/tests/dp23-acceptance.spec.ts`에서 정상흐름·접근거부·조직전환·모바일을 검증하고 frontend build를 확인한다.
- [ ] 공통 모듈 변경 영향의 기존 회귀를 수행하고260/280에 code hash·case·mode·결과를 저장한다.
- [ ] 해당 파일과 산출물만 묶어 검토 가능한 변경으로 저장하고 완료/미실행을 추적표에 갱신한다.

**종료 기준:** 그림→검증→승인version실행→노드trace→취소/재시작흐름증명. 자연어Workflow생성T034는제외유지.

**실행 명령(향후 구현 후):**

```bash
# cwd: src/backend
.venv/bin/python -m pytest tests/test_dp23_acceptance.py -q
# cwd: src/frontend
npm run build
npm run test:e2e -- tests/dp23-acceptance.spec.ts
```

### DP-24: 업무 Agent 10종 단계별 평가

**선행:** DP-07, DP-10, DP-12, DP-22

**요구 연결:** F-012, F-019, F-022, F-026, F-032 / T-037, T-043

**Files / 책임:**

- Create (제안): `src/backend/app/use_cases/catalog.py` — 업무 Agent 10종 단계별 평가의 해당 도메인/화면/산출물.
- Create (제안): `src/backend/tests/data/agent_acceptance_cases.json` — 업무 Agent 10종 단계별 평가의 해당 도메인/화면/산출물.
- Create (제안): `src/frontend/src/UseCaseWorkspacePage.tsx` — 업무 Agent 10종 단계별 평가의 해당 도메인/화면/산출물.
- Test (제안): `src/backend/tests/test_dp24_acceptance.py` — 아래 서버/데이터 수용 case.
- Test (제안): `src/frontend/tests/dp24-acceptance.spec.ts` — 같은 계약의 실제 화면 흐름/권한/조직전환.

**Interfaces — 제안 계약:**

```json
{
  "UseCaseManifest": "use_case_id,approved_asset_version,dataset_version,required_connectors,role_scope,acceptance_evidence",
  "case verdict": "supported|insufficient|unsupported"
}
```

**데이터·상태·보존:** 규정책무/그룹웨어문서/회의/문서작성/고객민원마케팅/광고심의/지식상품/여신/외환/단말내비10종. 각종정상2·근거부족1·권한거부2·회수1 최소6case.

**상세 개발 내용:** 규정/문서/회의부터실행유형연결. 그외합성문서+읽기connector로시연; 금융판정은보조초안/원문근거로표시.현업자료·업무API없는종류는미실행을표시. 각종별작업표가별도reviewgate.

**수용 시험 벡터:** 각 벡터를 지정한 시험 파일의 독립 case로 작성합니다. request/seed·변경 전 상태·예상 응답/DB/외부송신·증거를 함께 검증합니다.

```json
[
  {
    "case_id": "DP-24-C01",
    "assertion": "각종별원문숫자/규칙일치",
    "mode": "synthetic/mock first",
    "verdict_before_implementation": "not_run"
  },
  {
    "case_id": "DP-24-C02",
    "assertion": "고객/여신/외환결정자동확정금지",
    "mode": "synthetic/mock first",
    "verdict_before_implementation": "not_run"
  },
  {
    "case_id": "DP-24-C03",
    "assertion": "10종최소60case 결과개별기록",
    "mode": "synthetic/mock first",
    "verdict_before_implementation": "not_run"
  },
  {
    "case_id": "DP-24-C04",
    "assertion": "모의60개통과와실제현업수용분리",
    "mode": "synthetic/mock first",
    "verdict_before_implementation": "not_run"
  }
]
```

- [ ] 230 분석에서 관련 기존 SQL 정책함수/DTO/호출경로를 확인하고240에 위 계약·state/ACL·오류·snapshot·비용·migration 설계를 확정한다.
- [ ] `src/backend/tests/test_dp24_acceptance.py`에 각 case의 fixture/input/expected output·DB·송신 assertion을 작성한다. 현재 미제공 동작의 실패를 확인한다.
- [ ] schema가 필요한 경우 RLS·권한함수·migration을 추가하고, 제안 계약의 서버/adapter와 화면을 최소 수용 범위로 구현한다.
- [ ] 변경된 서버 case를 실행하여 정상/음성/충돌/회수/원장 결과가 모두 일치하는지 확인한다.
- [ ] `src/frontend/tests/dp24-acceptance.spec.ts`에서 정상흐름·접근거부·조직전환·모바일을 검증하고 frontend build를 확인한다.
- [ ] 공통 모듈 변경 영향의 기존 회귀를 수행하고260/280에 code hash·case·mode·결과를 저장한다.
- [ ] 해당 파일과 산출물만 묶어 검토 가능한 변경으로 저장하고 완료/미실행을 추적표에 갱신한다.

**종료 기준:** 각Agent별지원범위/실연계/평가근거분리. 종류등록만으로10업무구현완료판정하지않음.

**실행 명령(향후 구현 후):**

```bash
# cwd: src/backend
.venv/bin/python -m pytest tests/test_dp24_acceptance.py -q
# cwd: src/frontend
npm run build
npm run test:e2e -- tests/dp24-acceptance.spec.ts
```

