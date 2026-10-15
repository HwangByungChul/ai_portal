# Backend corrective implementation report · 2026-10-14

Status: DONE; implementation and focused fixture tests complete. Fresh task review remains a controller gate. No commits.

## Scope and exact files
- `src/backend/migrations/050_tool_workflow_approval_reviews.sql`
- `src/backend/app/assets/published.py`
- `src/backend/tests/test_tool_workflow_review_http.py`
- `src/backend/tests/test_published_agents.py`

Read repository AGENTS.md, durable 관리 B implementation report, backend report and UI contract. AGENT_03 only; other nine use cases deferred. Existing earlier approval implementation/review gates preserved. No frontend or Obsidian edits, primary migration, seeds, paid calls, production actions, or migrations000–049 edits.

Exact pre copies were captured before edits in `.superpowers/sdd/resume-backend-review/pre`. Post snapshots, individual diffs, files.json and scoped.diff are in the same durable package. These compare this correction against the existing implementation, not the original initial050 work. No reconstructed pre attribution is necessary for these four changes.

## Corrected behavior
Pending Tool/Workflow requests retain comparison of submitted base expected_head_revision to the current head. Approved requests instead require the exact current request/version identity and enabled head. A successful approval's own head increment no longer yields HEAD_CHANGED. Superseded or revoked approved requests remain invalid without rewriting historical approved status.

Pending AGENT_03 requests retain use_case_revision base CAS. Approved AGENT_03 requests require the exact current use_case_heads.version_id; their own case-head increment no longer yields CASE_CHANGED. Meeting manifest digest, Workflow runtime digest/mode, actual published version/publication revision, Tool dependency mode/digest/access and current audience checks remain. Existing Tool HTTP descriptor/current connector checks remain.

PublishedRun now requires expected_publication_revision as StrictInt bounded0..9223372036854775806, matching repository/DB CAS. Existing extra-forbid policy and version_id/publication CAS remain. A valid POST reaches admission202, exact replay200; stale publication or version409; missing, bool, string, float, negative and overflowing revision422.

## Validation commands and results
Working directory `src/backend`; fixture PostgreSQL tests executed exclusively and sequentially.
1. `.venv/bin/python -m pytest tests/test_tool_workflow_review_http.py tests/test_approval_review_migration.py tests/test_published_agents.py -q`:21 passed46.86s, before newly added test collection. The first test append command used root-relative paths from backend cwd and failed; no files were changed by those failed appends. Corrected paths before adding tests.
2. `.venv/bin/python -m pytest tests/test_tool_workflow_review_http.py tests/test_approval_review_migration.py tests/test_published_agents.py tests/test_workflow_approvals.py tests/test_tool_persistent_execution.py -q`:54 passed/1 failed100.24s. Only failure was new test calling Workflow revoke with workflow UUID as target instead of target=None and body.workflow_id. Current approved-valid, stale pending, superseded head/case assertions all passed before that test fixture call error. Corrected revoke contract and closed both service and agent.
3. Final clean `.venv/bin/python -m pytest tests/test_tool_workflow_review_http.py tests/test_approval_review_migration.py tests/test_published_agents.py -q`:23 passed/0 failed50.34s. Includes current approved Tool valid and revoked invalid HTTP assertions; Workflow current approved valid, stale pending HEAD_CHANGED+CASE_CHANGED, superseded exact head/case invalid, replacement valid and revoked invalid; actual PublishedRun HTTP202/200/409/422; existing mode/current audience/dependency/replay/rollback tests and migration preservation.

The broader Workflow approval and Tool persistent execution tests passed in command2 and were not unnecessarily repeated after correcting only the new fixture revoke call. Counts are separate runs and are not additive.

## Limitations and handoff
No full suite, browser, real connector/model, UAT or operational deployment verified by this unit. Primary DB unchanged. Published accepted run exercises existing admission with mock fixture settings, not actual business quality or production execution. Owner released fixture DB after final tests; all test sessions exited. Controller can dispatch read-only task review using this report and scoped.diff, then proceed with UI fixes/browser acceptance and durable Obsidian update.
