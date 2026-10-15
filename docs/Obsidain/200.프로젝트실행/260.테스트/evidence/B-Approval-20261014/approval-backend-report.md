# Backend approval review implementation (2026-10-14)
Scope: plan32 Task1 + submission-support API; AGENT_03 immutable manifest only. No frontend edits, git commits, primary migration/seed, paid calls or Obsidian writes. SQL000–049 unchanged. PostgreSQL fixture tests exclusively sequential.

Implementation:
- Add050 append-only FORCE RLS review ledger, mandatory comments, currentactor/body/CAS exact replay, conflict on altered comments, and atomically saved underlying decision+audit+review. Old helper web grants revoked; historical decisions stay commentNULL.
- Exact per-UUID detail independent of latest50; server current head/dependency/runtime/use-case/audience validation, safe reasons, current permission flags, exact snapshots diff and history.
- Signed cursor scoped current tenant+actor+kind+filter; status/server title/UUID search,20 default/50 max pages; total_pending and own-excluding PADMIN actionable_pending counts.
- New AGENT03 submissions seal complete server meeting_contract snapshot; old versions remainNULL; immutable snapshot constrained to case/digest; current Workflow code digest includes050 SQL.
- Tool approve uses current server-generated descriptor comparison; real unconfigured execution remains unavailable.
- Static Tool/Workflow submission-support endpoints return raw heads even when old execution code is unavailable; existing paginated published-agent APIs reused for readable version/variables; separate strict /workflows/approved/validate.

Exact DTO: /tmp/approval-ui-contract.md
Task review package: /tmp/approval-backend-review (files.json lists new/edited paths). Post snapshots exact; pre snapshots reconstructed by reversing this agent's known edits because initial copies were not captured and most source was already untracked. Review must retain that baseline limitation. Historical migration tests now isolate complete intended through049 directories rather than ingest later050; support schema expected66tables/51migrations/172securityfunctions.

New paths:
- app/approval_reviews/{__init__.py,models.py,repository.py}
- migrations/050_tool_workflow_approval_reviews.sql
- tests/test_tool_workflow_review_http.py
- tests/test_approval_review_migration.py
Edited paths:
- app/tools/{routes.py,repository.py}
- app/workflows/{routes.py,repository.py,identity.py}
- tests/support.py
- tests/test_tool_persistent_execution.py
- tests/test_workflow_approvals.py
- tests/test_workflow_runtime.py
- tests/test_meeting_workflow.py
- tests/test_meeting_migration.py

Commands from src/backend (venv Python):
1. `.venv/bin/python -m pytest tests/test_workflow_approvals.py::test_catalog_and_approval_queue_are_scoped -q`:1pass3.69s.
2. `.venv/bin/python -m pytest tests/test_workflow_approvals.py tests/test_tool_persistent_execution.py tests/test_meeting_migration.py -q`:30pass/3fail44.81s. Fixed early own-request SOD before replay and historical migration file completeness.
3. `.venv/bin/python -m pytest tests/test_tool_workflow_review_http.py tests/test_approval_review_migration.py tests/test_workflow_approvals.py tests/test_tool_persistent_execution.py tests/test_meeting_migration.py -q`:36pass/3fail56.91s. Replaced non-deterministic audit policy drop (another permissive policy remained) with deterministic audit failure trigger; two failures from source/fixture SQL mismatch while a process was running were resolved by clean restart.
4. `.venv/bin/python -m pytest tests/test_tool_workflow_review_http.py tests/test_approval_review_migration.py tests/test_workflow_approvals.py tests/test_tool_persistent_execution.py tests/test_meeting_migration.py tests/test_workflow_runtime.py tests/test_meeting_workflow.py -q`:65pass/1fail116.03s. Only failure: new test treated prepared proposal dict as UUID; corrected to proposal['version_id'].
5. Final clean post-fix command `.venv/bin/python -m pytest tests/test_tool_workflow_review_http.py tests/test_approval_review_migration.py tests/test_meeting_migration.py tests/test_workflow_runtime_migration.py tests/test_catalog.py -q`: 46passed/0failed93.62s (clean post-fix, includes corrected Workflow manifest test).

Meaningful tests cover own/other-PADMIN decision, USER/other tenant detail denial, >50 deep link, search/keyset/cursor filter tampering, required blank/NUL/too-long comments, same comment replay/different comment conflict, revoke status/history, audit/review failure rollback, migration row/checksum preservation/NULL historical manifest/direct web denial, new AGENT03 snapshot/digest and current dependency unavailable approve blocking with rejection allowed. Existing Workflow runtime/meeting fixture regression covers stale CAS/current code/dependency/parent execution fences and mock execution only. Full suite/browser/UI/primary/real connector/business quality/UAT/production remain outside this backend unit.

6. Final chronology/legacy/append-only check `.venv/bin/python -m pytest tests/test_tool_workflow_review_http.py tests/test_approval_review_migration.py -q`: 8passed/0failed17.84s. PostgreSQL fixture test ownership released; no processes running.

## Task review correction (2026-10-14)
- Important mode finding fixed: ToolRepository.approval accepts server-owned mode; decision route passes current settings.mode; descriptor generation never replaces it with stored snapshot mode. HTTP mock→real and real→mock pending approvals conflict and remain pending with no head/review; rejection succeeds.
- Important audience finding fixed in additive050: initial Tool approval rechecks current tenant membership and account active predicates inside the decision transaction, before legacy decision+audit+review. Exact replay remains before audience revalidation; rejection remains available. HTTP membership/account deactivation after successful detail produces invalid detail and409 direct decision, with pending request/no head/no review/no approved audit.
- Workflow concrete chain049→048→047 already rechecks restricted membership/account on approve in047. New actual DB regression deactivates audience after successful detail; approve409 leaves original head, pending version, no review; rejection succeeds. No000–049 edits.
- Minor strict endpoint coverage added: actual HTTP valid typed graph/order, invalid future-node binding, cycle, USER403 and missing CSRF403.
- Changed files for correction: app/tools/repository.py, app/tools/routes.py, migrations/050_tool_workflow_approval_reviews.sql, tests/test_tool_workflow_review_http.py. No frontend/primary/paid/commit/Obsidian edits.
- First command `.venv/bin/python -m pytest tests/test_tool_workflow_review_http.py tests/test_approval_review_migration.py tests/test_tool_persistent_execution.py -q`:41passed/1failed62.33s. Failure was test fixture membership DELETE disallowed by existing conversation FK; unsupported removal variation removed, active membership/account cases retained.
- Final clean command `.venv/bin/python -m pytest tests/test_tool_workflow_review_http.py tests/test_approval_review_migration.py tests/test_tool_persistent_execution.py tests/test_workflow_approvals.py -q`:46passed/0failed72.48s. This includes all correction tests, SOD, exact replay/comment conflicts, rejection with unavailable dependencies, migration preservation and existing Tool/Workflow approval regressions.
- /tmp/approval-backend-review post snapshots and diffs refreshed from exact corrected source for every files.json entry, including new-file diffs. Original reconstructed-pre attribution limitation retained.
- PostgreSQL fixture ownership released after successful completion; no test process remains. Existing untested full-suite/browser/frontend/primary/real execution/UAT/production exclusions remain.
