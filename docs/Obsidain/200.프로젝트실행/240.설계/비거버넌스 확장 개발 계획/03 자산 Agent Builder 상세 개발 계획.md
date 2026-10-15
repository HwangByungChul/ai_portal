# 자산·Agent Builder Implementation Plan

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

### DP-09: 동적 자산 모델·고정 Agent 호환 이전

**선행:** DP-01

**요구 연결:** F-004, F-019, F-020, F-022, F-024, F-032, F-034, F-046, F-047, F-049 / T-022, T-032, T-038, T-042

**Files / 책임:**

- Create (제안): `src/backend/app/assets/models.py` — 동적 자산 모델·고정 Agent 호환 이전의 해당 도메인/화면/산출물.
- Create (제안): `src/backend/app/assets/repository.py` — 동적 자산 모델·고정 Agent 호환 이전의 해당 도메인/화면/산출물.
- Create (제안): `src/backend/migrations/023_asset_registry.sql` — 동적 자산 모델·고정 Agent 호환 이전의 해당 도메인/화면/산출물.
- Modify: `src/backend/app/conversations/routes.py` — 동적 자산 모델·고정 Agent 호환 이전의 해당 도메인/화면/산출물.
- Modify: `src/backend/app/conversations/repository.py` — 동적 자산 모델·고정 Agent 호환 이전의 해당 도메인/화면/산출물.
- Modify: `src/backend/app/execution/manager.py` — 동적 자산 모델·고정 Agent 호환 이전의 해당 도메인/화면/산출물.
- Modify: `src/frontend/src/types.ts` — 동적 자산 모델·고정 Agent 호환 이전의 해당 도메인/화면/산출물.
- Test (제안): `src/backend/tests/test_dp09_acceptance.py` — 아래 서버/데이터 수용 case.
- Test (제안): `src/frontend/tests/dp09-acceptance.spec.ts` — 같은 계약의 실제 화면 흐름/권한/조직전환.

**Interfaces — 제안 계약:**

```json
{
  "Asset": "id,owner_tenant,kind(agent|prompt|workflow|tool|model),visibility,active_version",
  "AssetVersion": "id,asset_id,revision,state,config_hash,execution_kind(general|rules_rag|document_summary)",
  "run snapshot": "asset_id,asset_version_id,config_hash"
}
```

**데이터·상태·보존:** 고정general/rules_rag는 seeded asset UUID alias로 유지. 기존agent_key 계약은 compatibility resolver로 처리; 기존완료run config_snapshot은 변경하지 않음.

**상세 개발 내용:** 새schema RLS/정책함수·immutableversion 추가. 기존DB→새DB expand/backfill/검증/compat읽기/후속contract 단계. 임의execution_kind/URL/key 등록 차단. 사용중버전 hard delete 금지.

**수용 시험 벡터:** 각 벡터를 지정한 시험 파일의 독립 case로 작성합니다. request/seed·변경 전 상태·예상 응답/DB/외부송신·증거를 함께 검증합니다.

```json
[
  {
    "case_id": "DP-09-C01",
    "assertion": "기존데이터 migration 전후 row/hash/비용 일치",
    "mode": "synthetic/mock first",
    "verdict_before_implementation": "not_run"
  },
  {
    "case_id": "DP-09-C02",
    "assertion": "고정2종 API호환·기존SSE/run 재조회",
    "mode": "synthetic/mock first",
    "verdict_before_implementation": "not_run"
  },
  {
    "case_id": "DP-09-C03",
    "assertion": "다른 tenant asset조회404",
    "mode": "synthetic/mock first",
    "verdict_before_implementation": "not_run"
  },
  {
    "case_id": "DP-09-C04",
    "assertion": "중간실패 rollback·반복migration 변경0",
    "mode": "synthetic/mock first",
    "verdict_before_implementation": "not_run"
  }
]
```

- [ ] 230 분석에서 관련 기존 SQL 정책함수/DTO/호출경로를 확인하고240에 위 계약·state/ACL·오류·snapshot·비용·migration 설계를 확정한다.
- [ ] `src/backend/tests/test_dp09_acceptance.py`에 각 case의 fixture/input/expected output·DB·송신 assertion을 작성한다. 현재 미제공 동작의 실패를 확인한다.
- [ ] schema가 필요한 경우 RLS·권한함수·migration을 추가하고, 제안 계약의 서버/adapter와 화면을 최소 수용 범위로 구현한다.
- [ ] 변경된 서버 case를 실행하여 정상/음성/충돌/회수/원장 결과가 모두 일치하는지 확인한다.
- [ ] `src/frontend/tests/dp09-acceptance.spec.ts`에서 정상흐름·접근거부·조직전환·모바일을 검증하고 frontend build를 확인한다.
- [ ] 공통 모듈 변경 영향의 기존 회귀를 수행하고260/280에 code hash·case·mode·결과를 저장한다.
- [ ] 해당 파일과 산출물만 묶어 검토 가능한 변경으로 저장하고 완료/미실행을 추적표에 갱신한다.

**종료 기준:** 고정2종과 새자산이 같은 허가경로로 실행되고 대화·근거·snapshot·ledger가 보존됨.

**실행 명령(향후 구현 후):**

```bash
# cwd: src/backend
.venv/bin/python -m pytest tests/test_dp09_acceptance.py -q
# cwd: src/frontend
npm run build
npm run test:e2e -- tests/dp09-acceptance.spec.ts
```

### DP-10: 카탈로그·My Agent·사용권한·공유

**선행:** DP-09, DP-02

**요구 연결:** F-004, F-017, F-019, F-020, F-022, F-023, F-033, F-034, F-046 / T-008, T-038

**Files / 책임:**

- Create (제안): `src/backend/app/assets/routes.py` — 카탈로그·My Agent·사용권한·공유의 해당 도메인/화면/산출물.
- Create (제안): `src/backend/app/assets/policy.py` — 카탈로그·My Agent·사용권한·공유의 해당 도메인/화면/산출물.
- Create (제안): `src/frontend/src/AssetCatalogPage.tsx` — 카탈로그·My Agent·사용권한·공유의 해당 도메인/화면/산출물.
- Create (제안): `src/frontend/src/MyAgentsPage.tsx` — 카탈로그·My Agent·사용권한·공유의 해당 도메인/화면/산출물.
- Test (제안): `src/backend/tests/test_dp10_acceptance.py` — 아래 서버/데이터 수용 case.
- Test (제안): `src/frontend/tests/dp10-acceptance.spec.ts` — 같은 계약의 실제 화면 흐름/권한/조직전환.

**Interfaces — 제안 계약:**

```json
{
  "GET /api/v1/assets": "q,kind,tag,category,cursor",
  "PUT /api/v1/assets/{id}/pin": "pinned:bool",
  "POST /api/v1/assets/{id}/access-requests": "reason",
  "POST /api/v1/admin/asset-grants": "asset_version,subject,scope,expires_at,expected_revision"
}
```

**데이터·상태·보존:** private/tenant/shared-approved; common자산은 소유tenant가공유한 승인version을 참조하며 별도COMMON tenant 자동생성은 하지 않음.

**상세 개발 내용:** 허용목록/상세·태그/검색·핀·평가집계. 핀≠권한; 복제는 DP-11에서 비밀/문서Grant 제외. 그룹공유는 targettenant/subject 명시·회수·만료. 부서은 DP-16 이후.

**수용 시험 벡터:** 각 벡터를 지정한 시험 파일의 독립 case로 작성합니다. request/seed·변경 전 상태·예상 응답/DB/외부송신·증거를 함께 검증합니다.

```json
[
  {
    "case_id": "DP-10-C01",
    "assertion": "비공개이름/카운트/랭킹 노출0",
    "mode": "synthetic/mock first",
    "verdict_before_implementation": "not_run"
  },
  {
    "case_id": "DP-10-C02",
    "assertion": "핀한 자산 회수 즉시 목록/실행 차단",
    "mode": "synthetic/mock first",
    "verdict_before_implementation": "not_run"
  },
  {
    "case_id": "DP-10-C03",
    "assertion": "공유되지 않은 version 직접조회404",
    "mode": "synthetic/mock first",
    "verdict_before_implementation": "not_run"
  },
  {
    "case_id": "DP-10-C04",
    "assertion": "폐기/만료 자산 새run 차단",
    "mode": "synthetic/mock first",
    "verdict_before_implementation": "not_run"
  }
]
```

- [ ] 230 분석에서 관련 기존 SQL 정책함수/DTO/호출경로를 확인하고240에 위 계약·state/ACL·오류·snapshot·비용·migration 설계를 확정한다.
- [ ] `src/backend/tests/test_dp10_acceptance.py`에 각 case의 fixture/input/expected output·DB·송신 assertion을 작성한다. 현재 미제공 동작의 실패를 확인한다.
- [ ] schema가 필요한 경우 RLS·권한함수·migration을 추가하고, 제안 계약의 서버/adapter와 화면을 최소 수용 범위로 구현한다.
- [ ] 변경된 서버 case를 실행하여 정상/음성/충돌/회수/원장 결과가 모두 일치하는지 확인한다.
- [ ] `src/frontend/tests/dp10-acceptance.spec.ts`에서 정상흐름·접근거부·조직전환·모바일을 검증하고 frontend build를 확인한다.
- [ ] 공통 모듈 변경 영향의 기존 회귀를 수행하고260/280에 code hash·case·mode·결과를 저장한다.
- [ ] 해당 파일과 산출물만 묶어 검토 가능한 변경으로 저장하고 완료/미실행을 추적표에 갱신한다.

**종료 기준:** 검색→상세→이용신청/승인→핀→실행→회수의 실제흐름과 조직격리 검증.

**실행 명령(향후 구현 후):**

```bash
# cwd: src/backend
.venv/bin/python -m pytest tests/test_dp10_acceptance.py -q
# cwd: src/frontend
npm run build
npm run test:e2e -- tests/dp10-acceptance.spec.ts
```

### DP-11: Builder·Prompt/RAG Playground·복제

**선행:** DP-07, DP-09, DP-16

**요구 연결:** F-016, F-022, F-024, F-032 / T-005, T-022, T-023, T-030, T-032

**Files / 책임:**

- Create (제안): `src/backend/app/assets/builder.py` — Builder·Prompt/RAG Playground·복제의 해당 도메인/화면/산출물.
- Create (제안): `src/backend/app/assets/evaluations.py` — Builder·Prompt/RAG Playground·복제의 해당 도메인/화면/산출물.
- Create (제안): `src/frontend/src/AgentBuilderPage.tsx` — Builder·Prompt/RAG Playground·복제의 해당 도메인/화면/산출물.
- Create (제안): `src/frontend/src/RagPlaygroundPage.tsx` — Builder·Prompt/RAG Playground·복제의 해당 도메인/화면/산출물.
- Test (제안): `src/backend/tests/test_dp11_acceptance.py` — 아래 서버/데이터 수용 case.
- Test (제안): `src/frontend/tests/dp11-acceptance.spec.ts` — 같은 계약의 실제 화면 흐름/권한/조직전환.

**Interfaces — 제안 계약:**

```json
{
  "POST /api/v1/assets": "kind,name",
  "POST /api/v1/assets/{id}/versions": "expected_revision,execution_kind,prompt,approved_model_ref,rag_settings",
  "POST /api/v1/assets/{id}/clone": "name,target_tenant",
  "POST /api/v1/asset-versions/{id}/evaluations": "dataset_id,client_send_id"
}
```

**데이터·상태·보존:** draft version별 prompt/top_k/threshold/chunk settings과evaluation manifest; 모델은 승인 allowlist.

**상세 개발 내용:** 처음 기존실행유형/현재단일모델만 조합; 임의 toolkey/secret/freeURL 금지. Prompt 전체조회도capability+마스킹. RAG 비교는 평가dataset+설정snapshot+선택근거로 기록.

**수용 시험 벡터:** 각 벡터를 지정한 시험 파일의 독립 case로 작성합니다. request/seed·변경 전 상태·예상 응답/DB/외부송신·증거를 함께 검증합니다.

```json
[
  {
    "case_id": "DP-11-C01",
    "assertion": "revision충돌409·승인version수정409",
    "mode": "synthetic/mock first",
    "verdict_before_implementation": "not_run"
  },
  {
    "case_id": "DP-11-C02",
    "assertion": "clone credentials/Grant/개인문서 참조 복사0",
    "mode": "synthetic/mock first",
    "verdict_before_implementation": "not_run"
  },
  {
    "case_id": "DP-11-C03",
    "assertion": "평가모드 비용stop/cap 적용",
    "mode": "synthetic/mock first",
    "verdict_before_implementation": "not_run"
  },
  {
    "case_id": "DP-11-C04",
    "assertion": "튜닝실행과운영index 분리",
    "mode": "synthetic/mock first",
    "verdict_before_implementation": "not_run"
  }
]
```

- [ ] 230 분석에서 관련 기존 SQL 정책함수/DTO/호출경로를 확인하고240에 위 계약·state/ACL·오류·snapshot·비용·migration 설계를 확정한다.
- [ ] `src/backend/tests/test_dp11_acceptance.py`에 각 case의 fixture/input/expected output·DB·송신 assertion을 작성한다. 현재 미제공 동작의 실패를 확인한다.
- [ ] schema가 필요한 경우 RLS·권한함수·migration을 추가하고, 제안 계약의 서버/adapter와 화면을 최소 수용 범위로 구현한다.
- [ ] 변경된 서버 case를 실행하여 정상/음성/충돌/회수/원장 결과가 모두 일치하는지 확인한다.
- [ ] `src/frontend/tests/dp11-acceptance.spec.ts`에서 정상흐름·접근거부·조직전환·모바일을 검증하고 frontend build를 확인한다.
- [ ] 공통 모듈 변경 영향의 기존 회귀를 수행하고260/280에 code hash·case·mode·결과를 저장한다.
- [ ] 해당 파일과 산출물만 묶어 검토 가능한 변경으로 저장하고 완료/미실행을 추적표에 갱신한다.

**종료 기준:** draft→설정→모의평가→비교가 재현되며 설계되지 않은 모델/노드가 실행되지 않음.

**실행 명령(향후 구현 후):**

```bash
# cwd: src/backend
.venv/bin/python -m pytest tests/test_dp11_acceptance.py -q
# cwd: src/frontend
npm run build
npm run test:e2e -- tests/dp11-acceptance.spec.ts
```

### DP-12: 자산 검토·승인·활성화·설정 복귀

**선행:** DP-11, DP-17, DP-18

**요구 연결:** F-024, F-029, F-031, F-032, F-039, F-041 / T-009, T-018, T-042, T-055

**Files / 책임:**

- Create (제안): `src/backend/app/assets/approvals.py` — 자산 검토·승인·활성화·설정 복귀의 해당 도메인/화면/산출물.
- Create (제안): `src/backend/app/assets/releases.py` — 자산 검토·승인·활성화·설정 복귀의 해당 도메인/화면/산출물.
- Create (제안): `src/frontend/src/ApprovalInboxPage.tsx` — 자산 검토·승인·활성화·설정 복귀의 해당 도메인/화면/산출물.
- Create (제안): `src/frontend/src/AssetReleasePage.tsx` — 자산 검토·승인·활성화·설정 복귀의 해당 도메인/화면/산출물.
- Test (제안): `src/backend/tests/test_dp12_acceptance.py` — 아래 서버/데이터 수용 case.
- Test (제안): `src/frontend/tests/dp12-acceptance.spec.ts` — 같은 계약의 실제 화면 흐름/권한/조직전환.

**Interfaces — 제안 계약:**

```json
{
  "POST /api/v1/asset-versions/{id}/submit": "expected_revision,evaluation_id",
  "POST /api/v1/asset-versions/{id}/decisions": "approve|reject,reason,expected_revision",
  "POST /api/v1/assets/{id}/activate": "approved_version_id,expected_revision"
}
```

**데이터·상태·보존:** draft→evaluated→review→approved/rejected→active→retired; 작성자≠승인자; immutable evaluation/config hash와ReleaseManifest.

**상세 개발 내용:** 승인함은 자산/과제/반입만 포함. 자기승인 금지. 활성화는 신규run부터 적용; 진행run snapshot 보존. 이전승인version 복귀와 인프라배포rollback을 구분.

**수용 시험 벡터:** 각 벡터를 지정한 시험 파일의 독립 case로 작성합니다. request/seed·변경 전 상태·예상 응답/DB/외부송신·증거를 함께 검증합니다.

```json
[
  {
    "case_id": "DP-12-C01",
    "assertion": "작성자 승인403·반려사유 필수",
    "mode": "synthetic/mock first",
    "verdict_before_implementation": "not_run"
  },
  {
    "case_id": "DP-12-C02",
    "assertion": "승인후config/hash변조 차단",
    "mode": "synthetic/mock first",
    "verdict_before_implementation": "not_run"
  },
  {
    "case_id": "DP-12-C03",
    "assertion": "복귀해도기존run/발생비용 변경0",
    "mode": "synthetic/mock first",
    "verdict_before_implementation": "not_run"
  },
  {
    "case_id": "DP-12-C04",
    "assertion": "권한회수·중복결재·동시activation 충돌",
    "mode": "synthetic/mock first",
    "verdict_before_implementation": "not_run"
  }
]
```

- [ ] 230 분석에서 관련 기존 SQL 정책함수/DTO/호출경로를 확인하고240에 위 계약·state/ACL·오류·snapshot·비용·migration 설계를 확정한다.
- [ ] `src/backend/tests/test_dp12_acceptance.py`에 각 case의 fixture/input/expected output·DB·송신 assertion을 작성한다. 현재 미제공 동작의 실패를 확인한다.
- [ ] schema가 필요한 경우 RLS·권한함수·migration을 추가하고, 제안 계약의 서버/adapter와 화면을 최소 수용 범위로 구현한다.
- [ ] 변경된 서버 case를 실행하여 정상/음성/충돌/회수/원장 결과가 모두 일치하는지 확인한다.
- [ ] `src/frontend/tests/dp12-acceptance.spec.ts`에서 정상흐름·접근거부·조직전환·모바일을 검증하고 frontend build를 확인한다.
- [ ] 공통 모듈 변경 영향의 기존 회귀를 수행하고260/280에 code hash·case·mode·결과를 저장한다.
- [ ] 해당 파일과 산출물만 묶어 검토 가능한 변경으로 저장하고 완료/미실행을 추적표에 갱신한다.

**종료 기준:** 승인→활성화→이전승인version 복귀의 감사/권한/버전 일치. 운영DB 접근은 DP-22의별도 권원 없이 허용하지 않음.

**실행 명령(향후 구현 후):**

```bash
# cwd: src/backend
.venv/bin/python -m pytest tests/test_dp12_acceptance.py -q
# cwd: src/frontend
npm run build
npm run test:e2e -- tests/dp12-acceptance.spec.ts
```

### DP-13: 모델 Registry·다중모델 Gateway

**선행:** DP-09, DP-18

**요구 연결:** F-012, F-016, F-032, F-046, F-047 / T-001, T-002, T-003, T-005, T-054

**Files / 책임:**

- Create (제안): `src/backend/app/ai/model_registry.py` — 모델 Registry·다중모델 Gateway의 해당 도메인/화면/산출물.
- Create (제안): `src/backend/app/ai/routing.py` — 모델 Registry·다중모델 Gateway의 해당 도메인/화면/산출물.
- Modify: `src/backend/app/ai/gateway.py` — 모델 Registry·다중모델 Gateway의 해당 도메인/화면/산출물.
- Create (제안): `src/frontend/src/ModelAdminPage.tsx` — 모델 Registry·다중모델 Gateway의 해당 도메인/화면/산출물.
- Test (제안): `src/backend/tests/test_dp13_acceptance.py` — 아래 서버/데이터 수용 case.
- Test (제안): `src/frontend/tests/dp13-acceptance.spec.ts` — 같은 계약의 실제 화면 흐름/권한/조직전환.

**Interfaces — 제안 계약:**

```json
{
  "ModelRef": "id,provider_key,model_name,credential_ref,pricing_version,enabled,capabilities",
  "resolve_model(ctx,asset_version,operation)": "ApprovedModelBinding",
  "GET /api/v1/models": "allowed metadata only"
}
```

**데이터·상태·보존:** 현재OpenAI설정 seed1개; credential_ref 서버전용. 실제키는 DB평문/UI/trace에 넣지 않음. 모델별token가격/입력·출력상한·허용op.

**상세 개발 내용:** 모의provider2개로routing/실패/stop 검증 후 실제허용모델1개 유지. 요청별 자동fallback 기본off; dispatched/unknown 이후 다른모델 재호출 금지. Private 서빙은 DP-27.

**수용 시험 벡터:** 각 벡터를 지정한 시험 파일의 독립 case로 작성합니다. request/seed·변경 전 상태·예상 응답/DB/외부송신·증거를 함께 검증합니다.

```json
[
  {
    "case_id": "DP-13-C01",
    "assertion": "임의모델/공급자/keypayload 차단",
    "mode": "synthetic/mock first",
    "verdict_before_implementation": "not_run"
  },
  {
    "case_id": "DP-13-C02",
    "assertion": "미승인모델목록/실행 금지",
    "mode": "synthetic/mock first",
    "verdict_before_implementation": "not_run"
  },
  {
    "case_id": "DP-13-C03",
    "assertion": "가격version snapshot/예약/unknown 정합",
    "mode": "synthetic/mock first",
    "verdict_before_implementation": "not_run"
  },
  {
    "case_id": "DP-13-C04",
    "assertion": "gateway밖provider직접호출 정적/통합 점검",
    "mode": "synthetic/mock first",
    "verdict_before_implementation": "not_run"
  }
]
```

- [ ] 230 분석에서 관련 기존 SQL 정책함수/DTO/호출경로를 확인하고240에 위 계약·state/ACL·오류·snapshot·비용·migration 설계를 확정한다.
- [ ] `src/backend/tests/test_dp13_acceptance.py`에 각 case의 fixture/input/expected output·DB·송신 assertion을 작성한다. 현재 미제공 동작의 실패를 확인한다.
- [ ] schema가 필요한 경우 RLS·권한함수·migration을 추가하고, 제안 계약의 서버/adapter와 화면을 최소 수용 범위로 구현한다.
- [ ] 변경된 서버 case를 실행하여 정상/음성/충돌/회수/원장 결과가 모두 일치하는지 확인한다.
- [ ] `src/frontend/tests/dp13-acceptance.spec.ts`에서 정상흐름·접근거부·조직전환·모바일을 검증하고 frontend build를 확인한다.
- [ ] 공통 모듈 변경 영향의 기존 회귀를 수행하고260/280에 code hash·case·mode·결과를 저장한다.
- [ ] 해당 파일과 산출물만 묶어 검토 가능한 변경으로 저장하고 완료/미실행을 추적표에 갱신한다.

**종료 기준:** 모델선택이 승인binding에서만 이루어지고 현재permit/ledger·실험비용 통제가 유지됨. Mock 다중모델은 Private서빙 완료 아님.

**실행 명령(향후 구현 후):**

```bash
# cwd: src/backend
.venv/bin/python -m pytest tests/test_dp13_acceptance.py -q
# cwd: src/frontend
npm run build
npm run test:e2e -- tests/dp13-acceptance.spec.ts
```

