---
title: Workflow Canvas 자연어 초안 연결 구현 계획
date: 2026-10-21
status: 실행 계획 · 공통 proposal API 의존
tags: [ai-platform, workflow, studio, no-code]
---

# Workflow Canvas 자연어 초안 연결 Implementation Plan

> **For agentic workers:** Start only after the common proposal API in [[2026-10-21 AI Builder 자연어 초안 생성 서비스 구현 계획]] passes its contract tests.

**Goal:** 현업 사용자가 Workflow 설명을 입력해 검토 가능한 graph 제안을 받고, 기존 Canvas에서 편집한 뒤 명시적으로 Workflow 초안으로 저장한다.

**Architecture:** WorkflowScaffoldPanel requests a typed workflow proposal, maps only supported nodes/edges into React Flow, and runs the existing DAG validation. Explicit save calls the current draft endpoint. Approval conversion and /workflows/run remain separate.

**Tech Stack:** React 19, TypeScript, @xyflow/react 12, FastAPI/Pydantic Workflow schema, existing draft RPC, Playwright.

**Spec:** [[2026-10-21 AI Builder 고도화 통합 Studio 설계]].

## Global Constraints

- Do not edit migrations 000–064. Workflow-specific migration is not expected.
- Allowed node types follow the proposal schema: input, read_tool, llm, validate, output. Proposal bounds are 3–20 nodes and 2–30 edges; approval conversion remains stricter.
- Never accept natural-language model/provider/URL/credential/secret values or raw Tool arguments. Tool IDs come from current authorized registry choices.
- An llm node binds only to an exact published Agent version selected by the user. Never synthesize IDs or connect a draft Agent automatically.
- Generation/display do not save, test, run, approve, publish, or call Tools.
- Preserve tenant/owner scope, CSRF, idempotency, costs, approval gates and published-version constraints.
- If DP16 agent_developer is unavailable, use the authorized fixture principal for tests and defer real field-user UAT.

### Task 1: Map a proposal into Canvas state

**Files:**
- Create: src/frontend/src/WorkflowScaffoldPanel.tsx
- Modify: src/frontend/src/WorkflowCanvasPage.tsx
- Modify: src/frontend/src/workflow/workflowAdapter.ts
- Modify: src/frontend/src/workflow/WorkflowStudio.tsx
- Modify: src/frontend/src/AIStudioHubPage.tsx and src/frontend/src/types.ts
- Test: src/frontend/tests/workflow-scaffolds.spec.ts

**Interfaces:** WorkflowScaffoldPanel receives tenant/user and callbacks onApplyProposal(WorkflowProposal), onDiscard(). Applying maps through backendToFlowGraph and returns unsaved Canvas state; it never calls a save/run API.

- [x] **Step 1: Write mapping tests.** `workflow-scaffolds.spec.ts` covers both valid chains, missing endpoints, cycle, unsupported node, forged Agent/Tool IDs, URL/secret, 21-node and 31-edge overflow.
- [x] **Step 2: Implement the proposal panel.** Accessible intent/question/warning/node review and explicit “Canvas에 가져와 편집”; text renders normally without HTML injection. Existing Canvas content requires a second explicit replacement confirmation.
- [x] **Step 3: Map through current adapter safely.** Proposal client validation and `validateDAG` run before `backendToFlowGraph` mapping and again when applying. LLM and read_tool nodes are labeled as unbound; exact published Agent version and authorized Tool selection remain manual Canvas work.

### Task 2: Save only through current Workflow draft contract

**Files:**
- Modify: src/frontend/src/WorkflowCanvasPage.tsx
- Modify: src/frontend/src/workflow/workflowAdapter.ts
- Test: src/frontend/tests/workflow-scaffolds.spec.ts
- Reuse: src/backend/app/workflows/routes.py draft endpoints
- Reuse: src/backend/tests/test_workflow_approved_schema.py and test_workflow_runtime.py for regression

**Interface:** Save posts to /api/v1/workflows/drafts with draft_id, client_request_id, expected_revision, name, description and typed graph. Draft success is not approval-ready, approval, publication or execution. Only an approved immutable version can enter the current approved run path.

- [x] **Step 1: Test explicit save and no-run boundary.** Browser contract asserts proposal/apply do not save or validate/run, explicit save does, and a failed-save retry reuses `client_request_id`. Revision-conflict browser behavior remains unverified.
- [x] **Step 2: Integrate save and truthful state.** Existing tenant-scoped CAS/idempotent draft save is reused. The UI distinguishes a saved draft from an approved or executable version and identifies unbound Agent/Tool steps.
- [ ] **Step 3: Run focused browser/build checks.** Admin/User production builds pass. Playwright test discovery lists all 6 tests, but browser execution could not start because the configured `webServer` refuses to reuse the existing listener on `127.0.0.1:5173` (`reuseExistingServer:false`). Existing process was left running.

**Final review note (2026-10-22):** Independent review found no blocking defect. `WorkflowCanvasPage.quickStart` now defaults to `false`; the Studio passes the selected mode explicitly. A subsequent build attempt was blocked by `EPERM` while Vite wrote its temporary config file, so the earlier successful build evidence predates this one-line default change. Browser execution and disposable-clone migration/RLS verification remain pending.

## Handoff

The deliverable is a typed Workflow proposal that can be reviewed and saved as an owner-scoped draft. It is not approval-ready, published, executing, institutionally accepted or deployed.
