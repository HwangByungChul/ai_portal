# Task1 spec and quality review · 2026-10-15

Final verdict after I1 correction: **PASS for Task1 pure spec and quality scope.** No open Important or Critical finding. Initial review requested I1 correction; that history and original targeted evidence are preserved below. Review limited to the seven exact paths in task1-review/paths.json, scoped.diff, pre/post evidence, task1 brief/report/contract. Current source SHA256 matches every post-manifest entry. No source edits, suite rerun, DB access/test, live-service change, paid call, or other-Agent change.

## Important

**I1 — Unrecognized deadline expression silently becomes unspecified if the model omits due_expression.** `src/backend/app/use_cases/meeting_dates.py:10-11,30-31`. Quote `월말까지 제출` with meeting date 2026-10-15 and no due_expression returns `due_date=None, expression=None, status=unspecified, reason=None, human_review_required=False`; the same verified quote with explicit expression `월말` returns unresolved/unsupported_expression. The brief requires ambiguous expressions to retain an unconfirmed deadline and reason. Because due_expression is optional, the server must not depend on the model supplying it to distinguish this visible ambiguous deadline from no deadline. This also undercounts unresolved_deadlines in meeting_quality.py:29. Add a bounded explicit ambiguous-expression policy (including this known fixture expression), preserve no-deadline unspecified behavior, and regression coverage through check_evidence/evaluate_structure. Do not invent a calendar date.

Evidence: one targeted pure command, no pytest suite or DB: `src/backend/.venv/bin/python -c 'import sys; sys.path.insert(0,"src/backend"); from app.use_cases.meeting_dates import resolve_deadline; from datetime import date; print(resolve_deadline("월말까지 제출",date(2026,10,15))); print(resolve_deadline("월말까지 제출",date(2026,10,15),"월말"))'`. Outputs reproduced the two states above. Existing test_meeting_dates.py:33 checks only the explicit-expression branch and misses default omission.

## Strengths and spec coverage

- meeting.py:21-46 maintains <=4000 StrictStr memo, exact ISO/date input (rejecting datetime/bool/coercion), blank memo only with selected refs, <=3 unique document/version refs. Legacy memo-only invocation and default memo source are retained.
- meeting.py:69-86 permits only selected canonical document-version source keys from a server mapping; exact quote and explicit owner substring are required. Model-created source identities cannot introduce documents; a map cannot replace memo. Wrong supplied relative or ISO deadline is rejected; server status/reason replaces model claims.
- meeting_dates.py:35-57 uses meeting date, Monday weeks and calendar-day offsets; leap/year/week boundaries, huge offsets, overflow, missing base, supported ambiguity and conflicting expressions have focused tests. No wall-clock/holiday inference.
- meeting.py:91-101 bumps revision to 2 and hashes both date and quality helper bytes into the manifest digest. Catalog/ready flags are unchanged. Fresh approval enforcement is a subsequent runtime integration gate, not proven by this pure helper.
- meeting_quality.py:6-29 separates structural checks from human accuracy/omission/owner/deadline review; deep copy avoids historical-result mutation and human_review_required is always true. No numerical semantic score, real-provider benchmark or semantic-pass claim. Synthetic fixture revision/provenance and deliberately wrong-but-literal owner example are appropriate.

## Minor observations

Fixture data has four synthetic cases; rules coverage primarily resides in focused contract/date tests rather than the reusable evaluation corpus. Later actual-model evaluation should expand the versioned corpus with document-source identity, conflicting/ambiguous deadlines and wrong model dates, and human semantic expectations. This does not constitute a paid/model-quality result and is not a Task1 blocker beyond I1.

## Validation limits and next-task gates

Existing report records 47 pure tests passed in 0.27s for these exact source bytes; reviewer did not rerun that suite. Runtime ACL/tenant/version/SHA/text assembly, aggregate 4000-character/6000-token bounds, raw Workflow routes, execution/result access rechecks, approved snapshot preservation and fresh-approval end-to-end are **not verified**. They belong to Task2/later integration, not missing Task1 implementation. Actual model quality/UAT/deployment remains outside this task. Current live DB51/service state was untouched.


## I1 re-review and final gate · 2026-10-15

**I1 resolved.** Re-read updated report/contract, refreshed scoped.diff and corrected resolver/test code. meeting_dates.py:13-14,33-35 now detects a bounded unsupported calendar-period set directly from the quote, preserving unresolved/unsupported_expression and the verbatim detected expression even without model due_expression or meeting base. Supported-plus-unsupported quotes remain unresolved; supplied model dates still fail check_evidence equality validation. This adds no calendar inference. Existing recognized relative dates/week/leap/overflow/conflict branches remain unchanged. No-date quotes remain unspecified.

Added regression coverage verifies omitted/supplied expression equivalence, missing base, seven unsupported periods, mixed supported/unsupported dates, this-week ambiguity, no-date behavior, normalized metadata, unresolved quality count, copy nonmutation, and rejection of model-invented month-end dates. The updated report and captured test-output.txt record **76 passed in 0.31s**. Reviewer did not rerun suites or access DB/services. All seven current source/test/fixture hashes again match refreshed post-manifest. Original pre snapshot remains the baseline for refreshed scoped.diff.

Final spec verdict PASS; final code-quality verdict PASS within the explicitly bounded pure layer. Bounded substring recognition is conservative and cannot establish semantic date/owner association; always-required human review continues to cover that limitation. The reusable four-case synthetic fixture corpus remains a Minor future evaluation improvement, not a failed gate or measured model accuracy claim.

Task2 may proceed. Runtime/current ACL, exact version/SHA assembly, context limits, Workflow raw routes and snapshot/fresh-approval enforcement must still be implemented and separately verified there. No runtime/backend integration, actual-model benchmark, UAT or deployment success is claimed by this approval.
