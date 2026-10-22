# AI Builder Task 2 implementation report

Status: implementation complete; runtime migration validation pending.

## Implemented

- Added migration `069_builder_scaffold_shared_meter.sql` after committed 068. It extends `ops.call_attempts` with a mutually exclusive proposal binding, stores an owner-bound worker permit digest, reserves through the existing `ops.usage_events` ledger, and keeps settlement exclusively on `security.call_meter`. It creates no new meter and no conversation/run/message rows.
- Added the non-conversation Builder call repository and Gateway ticket. The provider/model are selected server-side through the approved router (`gpt-4o-mini`); admission/reservation/dispatch recheck owner, tenant, active capability, budget, stop latch, and guardrail revision. Unknown or invalid usage cannot become ready.
- Added typed generation, input/output guardrail checks, selected-document ACL checks before and after generation, terminal content-free failures, and audit receipts for admission, success, failure, and discard.
- Added bounded POST/GET/DELETE routes at `/api/v1/admin/builder/scaffolds`, CSRF and tenant context, rate-window checks, no-store/request-id responses, and main-router/service registration. Proposals remain unsaved drafts; no asset/version/trial/Tool/Workflow execution or publication is invoked.
- Added Builder-specific isolated-clone verification code. It requires an explicit DSN naming an `_builder_clone` database and rolls back. It was not run and no database was changed.
- `068_builder_scaffold_proposals.sql` SHA-256 is asserted as `d70eb773d2e252c4336dcf6d3ff3e0671ab509a774c47e32681567ac04fbda1b`; previous migrations were not edited.

## Verification

- Focused command: `PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m pytest -p no:cacheprovider tests/test_builder_scaffold_schemas.py tests/test_builder_scaffold_repository.py tests/test_builder_scaffold_migration.py tests/test_builder_scaffolds.py tests/test_db_migration_clone.py -q` → 116 passed.
- `git diff --check` passed.
- Tests exercise typed proposal persistence boundaries, idempotency/static owner fences, no conversation side effects, and an actual `AiGateway` invalid-usage settlement path. Migration execution/RLS behavior on PostgreSQL remains unverified pending an explicitly provisioned disposable clone.

## Remaining

- Do not apply migration 069 to an active/shared database. Create/restore the approved disposable clone, run `verify_builder_scaffold_clone.py` using `AI_BUILDER_DISPOSABLE_CLONE_DSN`, compare source checksums and existing data fingerprints, then perform independent review.
- No real paid-provider call, institutional UAT, production deployment, or publishing/execution flow was exercised.
