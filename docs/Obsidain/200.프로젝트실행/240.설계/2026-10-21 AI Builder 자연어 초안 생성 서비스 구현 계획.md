---
title: AI Builder 자연어 초안 생성 서비스 구현 계획
date: 2026-10-21
status: 실행 계획
tags: [ai-platform, builder, workflow, generation, backend]
---

# AI Builder 자연어 초안 생성 서비스 Implementation Plan

> **For agentic workers:** Execute in order. Provider calls must use the project Gateway, policy admission, guardrails, and cost settlement.

**Goal:** 업무 설명을 편집 가능한 Agent/Workflow 제안으로 바꾸는 owner-scoped API를 만들고, Agent Builder에서 저장 전 검토를 지원한다.

**Architecture:** A typed proposal endpoint accepts target=agent|workflow and produces validated JSON. Proposal request/result is private and distinct from an Agent asset or approved Workflow. Only a separate explicit save action invokes the current immutable asset/profile API.

**Tech Stack:** FastAPI, Pydantic v2, PostgreSQL RLS/security RPC, existing model Registry/AiGateway/guardrails/meter, React 19, TypeScript, pytest/Playwright.

**Spec:** [[2026-10-21 AI Builder 고도화 통합 Studio 설계]].

## Global Constraints

- Never edit existing migrations. Check current source and applied migration versions immediately before work. If 064 remains latest, start with new file 065_builder_scaffold_proposals.sql; otherwise use the next unused number.
- Before DB apply: backup, disposable fixture clone, row/checksum comparison, then isolated active fixture apply. Do not run DB/fixture/browser harnesses in parallel.
- Natural-language generation only returns proposals. It does not save assets, test/run Agents, call Tools, request approval, publish, or execute.
- Provider/model are selected server-side from the approved registry. No request-supplied URL, credential, role, tenant, model override, or raw Tool endpoint.
- Keep proposal payload owner/tenant scoped; reviewers cannot read it. Same client_request_id/body returns the same receipt/result; same id with different payload conflicts.
- On malformed output, guardrail block, unknown cost, or provider timeout, do not infer success or retry automatically.
- Do not place secrets or real customer data in fixtures/evidence. Separate Mock provider evidence from provider/UAT evidence.

### Task 1: Define typed schemas and validator

**Files:**
- Create: src/backend/app/builder/scaffold_schemas.py
- Test: src/backend/tests/test_builder_scaffold_schemas.py

**Interfaces:**
- ScaffoldRequest: client_request_id UUID, target Literal['agent','workflow'], intent StrictStr (1–4000 UTF-8 bytes), answers dict[str, StrictStr] (max 20), document_refs list[DocumentRef] (max 5).
- AgentProposal: AssetConfig, Profile, missing_questions, warnings.
- WorkflowProposal: name, description, StudioDraftGraph, missing_questions, warnings.
- validate_proposal(target, payload) -> AgentProposal | WorkflowProposal; pure function with no I/O.

- [ ] **Step 1: Write schema tests.** Include valid Agent and acyclic Workflow, extra keys, unknown model ref, unsupported Workflow node, secret/URL field, NUL, UTF-8 size, duplicate refs, graph over 20 nodes/30 edges. Example:
    
    def test_agent_instruction_matches_profile():
        proposal = validate_proposal("agent", valid_agent_payload())
        assert proposal.config.instructions == proposal.profile.system_prompt

- [ ] **Step 2: Implement typed models.** Reuse Profile, AssetConfig, DocumentRef, WorkflowNode/Edge and current model contract. Reject unknown fields, unsupported node types, invalid model refs, secrets and provider overrides.
- [ ] **Step 3: Run focused schema tests.** Run from src/backend: .venv/bin/python -m pytest tests/test_builder_scaffold_schemas.py -q. Expected: valid fixtures pass; invalid inputs fail before network/database access.

### Task 2: Add owner-only admission, storage, and metering

**Files:**
- Create: src/backend/migrations/065_builder_scaffold_proposals.sql (only if 064 remains latest; otherwise next unused number)
- Create: src/backend/app/builder/scaffold_repository.py
- Create: src/backend/app/builder/scaffold_service.py
- Create: src/backend/tests/test_builder_scaffold_migration.py
- Create: src/backend/tests/test_builder_scaffolds.py
- Modify: src/backend/app/main.py

**Interfaces:**
- ScaffoldRepository.admit(ctx, request, trace_id) -> ScaffoldTicket uses server principal/tenant, payload hash, approved model id, policy revision and budget window.
- ScaffoldService.generate(ticket) -> ScaffoldResponse calls existing router/Gateway and settles actual or unknown usage before returning.
- ScaffoldRepository.read(ctx, proposal_id) -> ScaffoldResponse is current owner/tenant only.
- ScaffoldRepository.discard(ctx, proposal_id, expected_revision) -> Receipt removes proposal payload but retains minimal cost/audit receipt.

- [x] **Step 1: Test migration/RPC boundaries.** Assert forced RLS, no direct ai_web/ai_index/ai_meter payload access, owner-only executor, immutable cost receipt, idempotency conflict and conditional discard. Compare prior migration source hashes.
- [x] **Step 2: Implement admission and receipt.** Reuse AiGateway reserve/dispatch/settle semantics; store validated proposal separately from assets/approved versions. Persist request/result only behind owner RLS so a replay recovers exactly the same proposal without another provider call. Never persist credentials.
- [ ] **Step 3: Run migration test on disposable clone.** Run from src/backend: .venv/bin/python -m pytest tests/test_builder_scaffold_migration.py -q. Expected: old rows/checksums unchanged; cross-tenant/owner cases denied; no active/shared DB is touched by this test.
- [x] **Step 4: Implement provider-backed typed generation.** Inject MockProvider in tests. Parse strictly to target schema; reject invented IDs, models, documents, Tools, endpoints or unsupported nodes. Recheck current ACL for selected document refs before return. Store minimal terminal failure receipt for malformed/blocked/unknown usage and return no proposal body.
- [x] **Step 5: Expose bounded API.** Add POST /api/v1/admin/builder/scaffolds, GET /api/v1/admin/builder/scaffolds/{proposal_id}, DELETE /api/v1/admin/builder/scaffolds/{proposal_id}; register router in main.py. Apply CSRF, strict body/query, no-store, request-id, rate/window limits and current capability checks. Do not bypass DP16; until agent_developer capability is implemented, use the existing authorized fixture principal only.
- [x] **Step 6: Run backend contract tests.** Run from src/backend: .venv/bin/python -m pytest tests/test_builder_scaffolds.py -q. Expected: same id/body has one admission, different body conflicts, unknown settle is not success, cross-user/tenant reads 404, revocation blocks replay, mock calls have no production charge.

### Task 3: Connect Agent proposal review to explicit save

**Files:**
- Create: src/frontend/src/BuilderScaffold.tsx
- Modify: src/frontend/src/AssetsPage.tsx
- Modify: src/frontend/src/types.ts
- Test: src/frontend/tests/builder-scaffolds.spec.ts

**Interfaces:** BuilderScaffold receives tenant/user and callbacks onUseProposal(AgentProposal), onDiscard(). Applying fills editable form state only. Existing Asset save handler remains the only path that creates an immutable version.

- [x] **Step 1: Write browser contract tests.** Verify escaped output, editable fields, warnings/missing questions, discard, explicit review confirmation, and no save/trial/approval call when generating/viewing.
- [x] **Step 2: Implement quick-start panel.** Add bounded intent inputs, progress/error/recovery states, proposal review for name/description/instructions/prompts/model/docs, and explicit “이 제안으로 편집” action. Do not render raw JSON as HTML.
- [x] **Step 3: Reuse immutable save.** Copy accepted values into the existing editor; allow edits; save only through current profile API. On successful save, discard proposal; if discard fails preserve the asset receipt and show a retry notice.
- [ ] **Step 4: Run focused browser/build checks.** Run from src/frontend: npx playwright test tests/builder-scaffolds.spec.ts; npm run build:admin; npm run build:user. Expected: generation/display are side-effect free; only explicit save creates a version.

## Handoff

This plan covers mock-tested local proposal generation and Agent integration. It does not claim actual provider quality, workflow execution, role rollout, institutional UAT or deployment.

## 2026-10-22 · 빠른 시작 입력 선택지와 배열 보완

- 화면 점검에서 대상 사용자·입력 정보·원하는 결과 필드는 선택지가 제공되는 select가 아니라 placeholder 없는 일반 텍스트 input이었다. 라벨과 컨트롤에도 전용 배치 규칙이 없어 한 줄에 붙어 보였다.
- 세 필드를 “선택하세요” placeholder가 있는 한국어 select로 바꾸고, 각 목록에 “직접 입력” 옵션과 조건부 텍스트 입력을 추가했다. 기존 API `answers`의 문자열 계약은 유지한다.
- 작업 설명은 전체 폭, 보조 필드는 넓은 화면 3열/중간 화면 2열/좁은 화면 1열로 배치한다. CSS는 Builder quick-start 전용으로 제한했다.
- Playwright 회귀 사례는 선택지 노출과 직접 입력 값의 요청 전달을 확인한다. `tsc --noEmit` 통과. 로컬 Admin Studio에서 세 placeholder/옵션과 직접 입력 전환 및 데스크톱 배열을 실제 브라우저로 시각 확인했다. Playwright 시나리오는 아직 실행하지 않았다. Admin 빌드는 코드 변환까지 수행했으나 현재 `portal-sites` 플러그인의 입력 HTML 경로를 찾지 못해 마무리되지 않았다.


## Task 2 실행 기록 (2026-10-22)

- Task 2 코드는 구현했으며, 069 migration은 기존 shared call/usage ledger와 `security.call_meter`를 확장한다. `portal.messages`에는 프롬프트를 쓰지 않는다.
- 집중 backend 검증 115 passed, `git diff --check` 통과.
- Task 2 Step 3의 실제 disposable-clone 적용/롤백과 기존 데이터 지문 대조는 아직 실행하지 않았다. migration 미적용 상태이며 런타임 SQL/RLS 검증은 미완료다. 자세한 변경 파일과 제한은 [[250.구현/28 AI Builder 자연어 초안 생성 Task 2 구현 결과]]에 기록했다.


## Task 3 실행 기록 (2026-10-22)

- Agent Builder 빠른 시작에 자연어 입력, 누락 질문·주의점, 이름/설명/지침/개발자·사용자 프롬프트 검토를 추가했다. 기존 `BuilderProfileEditor`의 모델 선택과 tenant ACL 기반 자료 선택을 재사용하며 실행 방식도 제안 검토 중 바꿀 수 있다. Agent와 Workflow 탭은 Studio 안에 유지하고, Workflow 빠른 시작 UI는 아직 연결되지 않았다고 화면에 표시한다.
- 적용은 기존 편집기 상태 복사만 수행한다. 새 Agent/다른 자산으로 이동해도 제안 삭제 기회를 유지하고, 단계별/빠른 시작 전환에서도 제안 검토 상태를 보존한다. 기존 불변 저장 핸들러만 asset POST를 수행한다. 저장 성공 뒤 proposal DELETE를 시도하고, 삭제가 실패하면 저장 영수증을 보존한 채 재시도를 제공한다.
- 현재 백엔드가 `TADMIN`/`PADMIN`만 허용하므로 UI에서도 해당 역할만 생성 기능을 보여준다. `USER`에게는 현업 제작자 권한이 아직 연결되지 않았음을 안내한다.
- 브라우저 계약 테스트에 생성/보기의 무저장·무시험·무승인, 경고문 escape, 적용 전환 보존, 명시적 저장 후 삭제, 저장 실패 시 삭제 안 함을 추가했다. 실행 시 Playwright 설정의 `127.0.0.1:5173/api/v1/health`가 이미 사용 중이라 `reuseExistingServer:false` 검사에서 시작하지 못했다. 기존 서비스는 중단하지 않았다.
- `npm run build:admin`, `npm run build:user` 통과(각 `boundary_verified: true`). Admin 빌드에는 기존 500 kB 초과 번들 안내가 있다.
- 미완료: Playwright 브라우저 실행, Workflow 자연어 초안 검토/편집 UI. Task 2 migration 069 미적용, disposable clone/runtime 검증 미완료이며 이 Task 3 완료는 provider 품질, 기관 수용 또는 운영 배포를 의미하지 않는다.
- 변경 파일: `src/frontend/src/BuilderScaffold.tsx`, `src/frontend/src/AssetsPage.tsx`, `src/frontend/src/AIStudioHubPage.tsx`, `src/frontend/src/types.ts`, `src/frontend/tests/builder-scaffolds.spec.ts`.
