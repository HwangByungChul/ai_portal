# Corrective re-review · 2026-10-14

Spec verdict: PASS for the resumed scoped UI corrections and AGENT_03 Tool/Workflow approval expansion. Quality verdict: PASS. Open Critical/Important/Minor findings: none in the captured corrective delta. This is not whole-repository or production acceptance.

Reviewed resume-frontend-report.md and resume-frontend-review/scoped.diff, individual pre/post snapshots and files.json. All three pre/post SHA256 values match the manifest, and each live file matches its post snapshot. The frontend package has no README; files.json identifies the exact scope. No tests, builds, browser sessions, DB actions or source mutations were performed by this reviewer.

## Closure evidence
- Important1 closed: WorkflowApprovalRequest.tsx:13–15,23 uses a stable component-lifetime Map from tool_id to node_id. Removing a Tool explicitly empties affected binding sources, and readiness :32 rejects missing sources. WF10 checks removing first_reader preserves second_reader/tool_2 identity and disables validation/submission until explicit reselection; submitted generated definition is inspected.
- Important2 closed: WorkflowApprovalRequest.tsx:17–18 refetches selected readable exact publication detail on refresh, clears old asset/bindings/validation during refresh, and rebuilds bindings from current variables. WF10 inspects revision2/new version/new_question and absence of old question in both validator/submission payloads.
- Minor1 closed: AdminHomePage.tsx:142 explicitly scopes empty wording to operating settings/dynamic Agent deployment, rather than the combined pending list.
- Minor2 closed: WorkflowApprovalRequest.tsx:33 clears prior receipt on fingerprint changes. WF10 asserts editing name removes the prior receipt link.
- Race handling: WorkflowApprovalRequest.tsx:13,17–18 guards exact selection by assetSeq and support refresh by loadSeq plus selection sequence. A newer choice beats old exact bytes; a newer refresh whose list removes the selected asset beats earlier in-flight exact detail. WF11 awaits released HTTP response completion and two rendered frames before assertions, covering these two races meaningfully.

## Validation provenance
The implementer reports Node22 split builds user26/admin43 modules and boundary checks passed. Browser evidence reports 15 unique passes. Coordinator inspected test sources and corrected the partition:6 actual disposable DB/API paths using mock providers/fixtures (D1201,D1202,WF01,WF04,WF05,U1102) +9 HTTP-stub paths (WF02,WF03,D1207,WF06–11). The implementer initial9 actual/6 stub partition was misclassified because actual auth/DB harness presence does not make a stubbed scenario an actual API path. Runs14+2+1 overlap; they are not17 unique passes. This reviewer inspected changed test assertions but did not rerun commands. Controller reports visual inspection at1440/1024/768 with no overflow and approved current technical-valid state; reviewer does not claim independent screenshot inspection.
Backend corrective report now separately records spec/quality PASS for approved-head identity CAS and PublishedRun expected_publication_revision; those initial tracked integration issues are no longer open according to that scoped review, not independently backend-tested here. Historical original reports below are preserved as initial-state evidence.

Remaining limits: nine cases deferred; actual institution connector/model quality/business UAT/primary migration/operational deployment unverified. Full existing evidence/settings/dynamic system behavior outside selected browser paths is not a full-suite claim. Obsidian narrative sync remains controller responsibility.

---
# Immutable initial review (superseded verdict and findings)

# Resumed Tool / Workflow approval UI review
Date: 2026-10-14. Read-only static review of current scoped files; attribution to the prior implementation is unverified because the earlier exact diff/report was cleared. This is not a review of the entire dirty tree.

## Verdict
Spec: incomplete (Important correction required in Task2). Quality: changes required. No Critical finding established by this static inspection.
Scope: plan32 Tasks2/3/4; AGENT_03 only; remaining nine cases deferred. User A / admin A / approval B retained in the examined routing and components.

## Important findings
1. src/frontend/src/WorkflowApprovalRequest.tsx:20 (binding consumption :23, editor :34): Tool node IDs depend on selected-tools position (nodes.length). Selecting A then B creates tool_1=A/tool_2=B. Binding an Agent variable to tool_1, then removing A, produces tool_1=B while that binding remains unchanged. The generated definition silently reads B instead of the deliberately selected A. The structural validator can accept this valid reference and cannot recover user intent. Give each Tool a stable node ID and invalidate/reset bindings when their selected source disappears; a removed source must not retarget a different Tool.
2. src/frontend/src/WorkflowApprovalRequest.tsx:16: support refresh refreshes the list but preserves the selected exact asset object whenever asset_id remains present. Republishing the same asset leaves version_id, publication_revision and variables from the old detail (:15/:24), while the list now represents a new publication. Refresh does not refetch selected exact detail, so users cannot update a stale selection using the advertised refresh action. Server submission dependency checks should reject stale refs; no unsafe acceptance claimed. Refresh the selected exact detail and reconcile/reset bindings and validation against the new variables/version before allowing validation/submission.

## Minor findings
- src/frontend/src/AdminHomePage.tsx:139–142: existing-deployment empty text is displayed beside Tool/Workflow pending rows whenever overview.pending.items is empty. Wording says no pending deployment requests, but placement inside the combined priority list is confusing. Scope the message explicitly to settings/dynamic or show it only when all combined rows are empty.
- src/frontend/src/WorkflowApprovalRequest.tsx:37: previous receipt remains visible when Workflow definition/audience changes (unlike Tool form :13). It is a valid prior request link, but the form has no clear submitted-snapshot association; label it as a previous receipt or clear it on edits.

## Confirmed by source inspection
- ApprovalReviewPanel.tsx:41 uses Workflow decision_revision, Tool revision, and current head_revision for revoke.
- ApprovalReviewPanel.tsx:39–45,57 requires a nonempty trimmed <=500 Unicode-character/NUL-free comment and explicit confirmation; lock prevents duplicate decision sends. 409/network/5xx refetches current state without automatic decision replay and preserves comment for reconsideration.
- ToolApprovalRequest.tsx:11–12 / WorkflowApprovalRequest.tsx:31 retain client_request_id for identical fingerprints after failed receipts; submitted Tool descriptor is server owned.
- WorkflowApprovalRequest.tsx:15 selects exact readable publication detail; :16 exhausts published pagination. :19–25 generates AGENT_03 with one LLM, no read_tool nodes, output text, and :29 requires an input binding. Meeting server contract is displayed (:36); only AGENT_03 is a business-case option.
- ApprovalReviewPanel.tsx:27–32 provides server filters/cursor/exact detail with local request sequencing. :49 current selected row is accessible; :31/:34 focus detail heading; :37 returns to preserved list/filter state.
- apps/admin-web/src/App.tsx:29–34 clears tenant-change deep links; :44 generation/tenant/view remount plus packages/ui/src/scoped.ts scope invalidation prevents late former-session bytes. Authorization failure clears scoped details. This static conclusion is not fresh browser verification.
- approvalLaunch.ts:5–6 enforces exactly one kind/request_id, UUID format and allowed supported deep-link kinds. Evidence remains a tab, not a supported ID deep link (existing design).
- AdminHomePage.tsx:48,97 uses server total_pending/actionable_pending, never loaded list length; separate all-pending and actionable labels are explicit.
- ApprovalsPage.tsx:39–40 retains settings/evidence/dynamic components alongside Tool/Workflow. Static presence is not proof of unchanged runtime behavior.
- packages/ui/src/portal.css:1633–1634 includes wrapping, min-width:0, narrow-screen list/detail switching and comparison stacking. Real visual/keyboard acceptance still needs runtime verification.
- Shared API types distinguish version revision, decision CAS and head revision; Review detail/current checks/diff/history match durable approval-ui-contract.md.

## Verification limits and tracked integration issues
No tests, builds, browser actions, database reads/writes, source edits, or migrations ran during this review; backend exclusive DB ownership was respected.
Prior reports of six new browser passes (two actual DB/API with mock provider + four HTTP stubs), user26/admin43 split builds, and existing dynamic positive failing422 schema are historical reported claims, not reverified results. Current test source includes these real/stub distinctions and screenshot widths1440/1024/768, but pass status/artifacts were not rerun.
Backend post-approved-base CAS false failure and PublishedRun missing expected_publication_revision are tracked separate integration corrections, not resolved by this UI review.
Cannot verify current backend gate atomicity/replay, migrations/RLS, existing settings/evidence/dynamic full regression, primary migration, actual institution connections, business-quality acceptance, production deploy, or Obsidian reading view.
Test-only backend helper attribution was not re-established from a prior exact diff; no assertion that helper changes are reviewed/accepted.
