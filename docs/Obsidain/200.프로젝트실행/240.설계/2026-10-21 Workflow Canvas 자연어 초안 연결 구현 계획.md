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
- Allowed node types follow WorkflowNode: input, read_tool, llm, validate, output. Draft bounds are 1–20 nodes and 0–30 edges; approval conversion remains stricter.
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
- Modify: src/frontend/src/workflow/workflowTypes.ts
- Test: src/frontend/tests/workflow-scaffolds.spec.ts

**Interfaces:** WorkflowScaffoldPanel receives tenant/user and callbacks onApplyProposal(WorkflowProposal), onDiscard(). Applying maps through backendToFlowGraph and returns unsaved Canvas state; it never calls a save/run API.

- [ ] **Step 1: Write mapping tests.** Test valid input→llm→output and input→read_tool→llm→output proposals, duplicate/missing endpoints, cycle, unsupported node, forged Agent/Tool ID, secret/URL field, 21-node and 31-edge cases.
- [ ] **Step 2: Implement the proposal panel.** Show intent, missing questions, warnings and proposed node sequence as accessible text. Require “Canvas에 가져와 편집”. Keep output escaped; do not use dangerouslySetInnerHTML.
- [ ] **Step 3: Map through current adapter safely.** Use backendToFlowGraph and rebind callbacks. Run validateDAG. Require exact published asset selection for llm and authorized registry selection for read_tool. Unresolved references remain visible as incomplete and cannot be described as approval-ready.

### Task 2: Save only through current Workflow draft contract

**Files:**
- Modify: src/frontend/src/WorkflowCanvasPage.tsx
- Modify: src/frontend/src/workflow/workflowAdapter.ts
- Test: src/frontend/tests/workflow-scaffolds.spec.ts
- Reuse: src/backend/app/workflows/routes.py draft endpoints
- Reuse: src/backend/tests/test_workflow_approved_schema.py and test_workflow_runtime.py for regression

**Interface:** Save posts to /api/v1/workflows/drafts with draft_id, client_request_id, expected_revision, name, description and typed graph. Draft success is not approval-ready, approval, publication or execution. Only an approved immutable version can enter the current approved run path.

- [ ] **Step 1: Test explicit save and no-run boundary.** Applying/editing a proposal sends no request. Clicking Save sends one drafts POST. Assert there are no /validate, approval, Tool, or /workflows/run requests before independent approval. Retry keeps the same client_request_id; revision conflict preserves local edits and latest server revision.
- [ ] **Step 2: Integrate save and truthful state.** Preserve draft CAS/idempotency and receipt. Show “저장된 Workflow 초안 · 승인/실행 전용 버전 아님”. If a graph is outside the current approval subset, identify exact missing node/binding and do not imply it can run.
- [ ] **Step 3: Run focused browser/build checks.** Run from src/frontend: npx playwright test tests/workflow-scaffolds.spec.ts tests/workflow-orchestration.spec.ts; npm run build:admin; npm run build:user. Expected: editable proposal, explicit draft save only, no /workflows/run before independent approval.

## Handoff

The deliverable is a typed Workflow proposal that can be reviewed and saved as an owner-scoped draft. It is not approval-ready, published, executing, institutionally accepted or deployed.
