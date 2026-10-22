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

- [ ] **Step 1: Test migration/RPC boundaries.** Assert forced RLS, no direct ai_web/ai_index/ai_meter payload access, owner-only executor, immutable cost receipt, idempotency conflict and conditional discard. Compare prior migration source hashes.
- [ ] **Step 2: Implement admission and receipt.** Reuse AiGateway reserve/dispatch/settle semantics; store validated proposal separately from assets/approved versions. Persist request/result only behind owner RLS so a replay recovers exactly the same proposal without another provider call. Never persist credentials.
- [ ] **Step 3: Run migration test on disposable clone.** Run from src/backend: .venv/bin/python -m pytest tests/test_builder_scaffold_migration.py -q. Expected: old rows/checksums unchanged; cross-tenant/owner cases denied; no active/shared DB is touched by this test.
- [ ] **Step 4: Implement provider-backed typed generation.** Inject MockProvider in tests. Parse strictly to target schema; reject invented IDs, models, documents, Tools, endpoints or unsupported nodes. Recheck current ACL for selected document refs before return. Store minimal terminal failure receipt for malformed/blocked/unknown usage and return no proposal body.
- [ ] **Step 5: Expose bounded API.** Add POST /api/v1/admin/builder/scaffolds, GET /api/v1/admin/builder/scaffolds/{proposal_id}, DELETE /api/v1/admin/builder/scaffolds/{proposal_id}; register router in main.py. Apply CSRF, strict body/query, no-store, request-id, rate/window limits and current capability checks. Do not bypass DP16; until agent_developer capability is implemented, use the existing authorized fixture principal only.
- [ ] **Step 6: Run backend contract tests.** Run from src/backend: .venv/bin/python -m pytest tests/test_builder_scaffolds.py -q. Expected: same id/body has one admission, different body conflicts, unknown settle is not success, cross-user/tenant reads 404, revocation blocks replay, mock calls have no production charge.

### Task 3: Connect Agent proposal review to explicit save

**Files:**
- Create: src/frontend/src/BuilderScaffold.tsx
- Modify: src/frontend/src/AssetsPage.tsx
- Modify: src/frontend/src/types.ts
- Test: src/frontend/tests/builder-scaffolds.spec.ts

**Interfaces:** BuilderScaffold receives tenant/user and callbacks onUseProposal(AgentProposal), onDiscard(). Applying fills editable form state only. Existing Asset save handler remains the only path that creates an immutable version.

- [ ] **Step 1: Write browser contract tests.** Verify escaped output, editable fields, warnings/missing questions, discard, explicit review confirmation, and no save/trial/approval call when generating/viewing.
- [ ] **Step 2: Implement quick-start panel.** Add bounded intent inputs, progress/error/recovery states, proposal review for name/description/instructions/prompts/model/docs, and explicit “이 제안으로 편집” action. Do not render raw JSON as HTML.
- [ ] **Step 3: Reuse immutable save.** Copy accepted values into the existing editor; allow edits; save only through current profile API. On successful save, discard proposal; if discard fails preserve the asset receipt and show a retry notice.
- [ ] **Step 4: Run focused browser/build checks.** Run from src/frontend: npx playwright test tests/builder-scaffolds.spec.ts; npm run build:admin; npm run build:user. Expected: generation/display are side-effect free; only explicit save creates a version.

## Handoff

This plan covers mock-tested local proposal generation and Agent integration. It does not claim actual provider quality, workflow execution, role rollout, institutional UAT or deployment.
