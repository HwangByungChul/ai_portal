### Spec Compliance

- ❌ Issues found: the selected-document current-authorization gate is not protected against concurrent document withdrawal/republication. This leaves the Task2 SQL/current-gate and concurrency requirement incomplete (`src/backend/migrations/051_meeting_context_quality.sql:75`, `:136`, `:198`). The backend behavior otherwise matches the scoped request on the inspected paths.
- ⚠️ Cannot verify from this diff: Task1's full date-language rules and pure evidence helper correctness; Task3 UI and safe admin context presentation; live database preservation/application; fresh normal two-person approval; actual-provider semantic quality. The controller must retain their separate gates. The fixture results are not real-model quality evidence. No live deployment approval is implied.

### Strengths

- `src/backend/app/use_cases/runtime.py:40` preserves the original memo-only prompt and explicitly rejects oversized compiled context. `:91` reconstructs context from current verified sources and compares it with the immutable saved authority, preventing a memo header from becoming a meeting-date authority.
- `src/backend/app/use_cases/runtime.py:76` reuses StoredSource/SourceStorage and compares deterministic parser mapping; the focused check of `src/backend/app/documents/storage.py:180` confirmed that read verifies source size/hash and invokes original-file verification when origin metadata exists.
- `src/backend/migrations/051_meeting_context_quality.sql:44` introduces private FORCE-RLS context/review tables with immutable triggers; `:136` binds source text to stored SHA/length and selected refs. Context insertion shares the parent admission transaction.
- `src/backend/migrations/051_meeting_context_quality.sql:190` serializes reviews, checks exact run revision/result digest, distinguishes matching replay from changed payload, and writes review plus audit atomically at `:218`. `src/backend/app/use_cases/runtime.py:180` returns structural metrics and explicitly requires human review.
- `src/backend/app/workflows/service.py:61` checks current sources before decorating public results. The raw DTO check at `src/backend/app/workflows/routes.py:39` confirmed extra top-level context fields are forbidden. The new test covers header/date forgery, document tampering, withdrawal, owner isolation, replay, CAS and audit rollback; it does not substitute these structural checks for semantic accuracy.

### Issues

#### Critical (Must Fix)

- None identified in the inspected scope.

#### Important (Should Fix)

- **P1 — Hold selected-document authorization locks through the protected SQL operation.** `src/backend/migrations/051_meeting_context_quality.sql:82` only calls the STABLE read predicate and checks metadata with EXISTS; the admission loop at `:136` does the same. Neither locks `security.document_access` or the selected publication/version state. The wrapper invokes this check before claim/checkpoint/finish at `:157`; quality checks at `:198` also precede review insertion without such locks. Consequently a different session can delete/withdraw/replace the selected source after the predicate reads it and commit before the execution fence or quality transaction completes. The later Python/SQL checks close ordinary sequential revocation but cannot prevent that interleaving. Current authorization is therefore not a transaction fence at these boundaries.
  - Focused dependency evidence: `src/backend/migrations/007_run_control.sql:15` locks account/tenant/session/membership state only; `src/backend/migrations/048_workflow_execution_ledger.sql:127` adds parent/workflow locks, not the newly selected source rows. Normal owner deletion obtains and updates document access at `src/backend/migrations/023_user_documents.sql:157`; a separate session avoids same-session serialization. The existing source fence explicitly uses ordered document/publication FOR SHARE locks at `src/backend/migrations/016_rag_provenance.sql:27`, showing the repository's established approach to this race.
  - Fix: acquire compatible locks on selected document access and applicable publication/version metadata in a deterministic order, then re-evaluate current ACL/version/SHA under those locks for admission and each guarded operation. Coordinate with the existing mutation lock order to avoid introducing deadlocks. Use a shared helper for the new source gate rather than copying the locking block.
  - Required focused regression: use two independent authenticated sessions and controlled transaction barriers, pause the selected-source fence while the other session attempts withdrawal/republication, and prove it blocks until the protected operation completes or the operation rejects after the mutation wins. Cover at least child dispatch and quality POST; assert no review/audit/provider permit is committed using authorization invalidated before the fence. Existing sequential tests and mocked pre-RPC failures do not answer this concurrency doubt. No test or DB service was run during this review.

#### Minor (Nice to Have)

- None retained; speculative coverage and style suggestions are omitted.

### Assessment

**Task quality:** Needs fixes.

**Reasoning:** The implementation has strong immutable-source, replay, privacy and audit boundaries, but the selected-document gate needs the same transaction-level authorization locking used by existing provenance controls before this task is accepted.

### Review evidence and scope

- Reviewed the supplied exact dirty-baseline diff, brief, implementation report and Task1/Task2 handoff contracts. The initial tool output truncated the middle of the diff; only the omitted ranges were recovered, followed by a line-number-only extraction for report anchors. No changed source file was separately reread and no git/index/source modification was made.
- Outside-diff focused checks were limited to named risks: original-byte integrity (`SourceStorage.read`); raw context injection (raw request DTO); selected-document concurrency (existing authorization, parent, mutation and source-guard functions). These checks support the findings above and do not constitute a whole-branch review.
- Read the saved final-contract output (103 passed) and final-child-guards output (6 passed): neither contains warning/error noise. These are implementer-produced outputs, not rerun results. The capture-check artifact reports 17 matching source paths and 51 unchanged historical migrations; live database preservation remains a separate gate.
- Review artifact is the sole file written by this review. No test suite, browser, DB/service operation, provider call or implementation edit was performed.

### P1 fix re-review · 2026-10-15 — Final verdict

- ✅ **Spec compliance: Approved within Task2 backend scope.** The original P1 above is resolved by `src/backend/migrations/051_meeting_context_quality.sql:78`: the private shared `meeting_sources_guard` acquires document-access, publication and exact-version SHARE locks, and rechecks authorization and immutable metadata after any wait. `:107` invokes it from the immutable context gate and `:164` invokes it during admission, preserving all previously reviewed parent/child/read/quality call paths. The initial finding is retained above as history and no longer blocks acceptance.
- ✅ **Task quality: Approved.** The fix centralizes the fence without copying logic or expanding public privileges. UUID ordering across selected documents and publication rows is deterministic. The access lock protects missing-publication and latest-version cases through the existing mutation protocol; source text length/hash remains checked for admission.
- ✅ Lock-order risk check: inspected the existing mutation protocol only: `src/backend/migrations/023_user_documents.sql:99` locks document access before version registration, `src/backend/migrations/011_document_ingest_control.sql:213` locks access before deletion/publication updates, `src/backend/migrations/013_document_lifecycle_control.sql:7` locks access before cleanup/version mutation, and `src/backend/migrations/014_document_sharing.sql:20` takes access before publication locks. No new conflicting document lock order was identified in these checks. This is scoped static analysis, not a claim that every possible database schedule has been exhaustively tested.
- ✅ Regression evidence: `src/backend/tests/test_meeting_runtime_context.py:264` adds four independently authenticated two-session controlled races for actual `call_dispatch` and `meeting_quality_control` RPCs, testing both fence-first and withdrawal-first. The assertions check blocking backend PIDs, no losing review/audit, and durable provider-permit state/hash/timestamp rather than a mocked function result. Withdrawal-first rejects after the lock wait; fence-first completes before withdrawal. `src/backend/tests/test_meeting_context_migration.py:26` checks the shared helper's use/order and denies direct web execution.
- ✅ Saved output inspected: `task2-review/p1-focused-output.txt:1` reports 22 passed; `task2-review/p1-runtime-output.txt:1` reports 31 passed, without warnings or errors. The retained initial failed assertion is disclosed in the fix report and replaced with checks of the actual durable dispatch contract. These outputs were inspected, not rerun.
- ✅ Capture evidence inspected: `task2-review/capture-check.json:1` records all 17 source paths matching, all 51 historical migrations unchanged, the original pre-manifest preserved, and exactly four P1 changed paths. Only `p1-fix.diff` was needed for the fix review; the full refreshed scoped diff was not reread.
- ⚠️ Remaining cross-task limits are unchanged: Task1 pure-rule coverage, Task3 UI/admin display/UAT, live backup/migration preservation, fresh approval and actual-provider semantic evaluation require their own gates. The four race tests exercise withdrawal, not every publication-replacement permutation; the shared access/publication locking gives static coverage of the normal replacement protocol. No unresolved scoped finding remains.
- Review-only actions: no tests, DB/services, browser, provider calls, git/index or implementation changes. This appendix is the only write during re-review.
