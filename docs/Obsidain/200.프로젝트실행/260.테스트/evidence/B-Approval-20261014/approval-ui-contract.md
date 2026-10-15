# Tool / Workflow approval UI contract
All endpoints use existing envelope `{data: ...}`, current tenant headers/auth/CSRF. IDs are Tool request UUID / Workflow version UUID. Mandatory comments on decision/revoke are trimmed strict strings of 1–500 Unicode characters, valid UTF8, no NUL. No comment backfill.

## Lists
GET `/api/v1/admin/tool-approvals` and `/api/v1/admin/workflow-approvals`
Optional `status=pending|approved|rejected`, `q` (trim, max120), `cursor` (opaque signed), `limit` (1–50, default20); duplicate/unknown query keys rejected422. Cursor scoped tenant+actor+kind+status+q; tampered/mismatched cursor422.
Response `{items: Request[], next_cursor: string|null, total_pending:number, actionable_pending:number}`.
Tool Request: `{request_id,tool_id,descriptor,audience:'all'|'restricted',member_ids:string[],expected_head_revision,status:'pending'|'approved'|'rejected',revision,requester_id,decided_by:string|null,created_at,decided_at:string|null}`.
Tool descriptor: `{tool_id,mode:'mock'|'real',adapter_revision,registry_module_sha256,adapter_module_sha256,arg_schema,timeout_seconds,read_only:true,digest}` (no name: support items include name/description).
Workflow Request: `{version_id,workflow_id,revision:<version revision>,decision_revision:<decision CAS>,created_by,definition,version_digest,audience,member_ids,expected_head_revision,status,decided_by,decided_at,created_at,execution_mode,runtime_digest,use_case_id:string|null,use_case_digest:string|null,use_case_revision:number|null,manifest_snapshot:object|null}`.
Use `decision_revision` for Workflow decision expected_revision, `revision` for Tool.

## Exact detail
GET `/api/v1/admin/tool-approvals/{request_id}` / `/api/v1/admin/workflow-approvals/{version_id}`
`{request:Request,current_head:(Request & {head_revision:number,enabled:boolean})|null,validation:{valid:boolean,checks:{code:string,status:'pass'|'fail'|'unavailable',message:string}[],checked_at:string},diff:{baseline_available:boolean,changes:{field:string,before:unknown,after:unknown}[]},history:{action:string,actor_id:string,created_at:string,comment:string|null,revision:number|null}[],can_approve:boolean,can_reject:boolean,can_revoke:boolean,decision_reason:string|null}`.
Empty checks + valid means technical checks passed, not quality/security/business acceptance. Current head may be disabled and includes exact baseline. Existing approved status is not rewritten on revoke. History actions submit/approve/reject/revoke; legacy approved/rejected has null comment. No run/messages/private docs returned.

## Mutations
Existing POST `/api/v1/admin/{tool|workflow}-approvals/{id}/decision` body `{decision:'approve'|'reject',expected_revision:number,comment:string}`.
Existing Tool POST `/api/v1/admin/tools/{tool_id}/revoke`, Workflow POST `/api/v1/admin/workflow-approvals/{workflow_id}/revoke`, body `{expected_revision:<current head_revision>,comment:string}`.
Same actor+action+target+CAS+trimmed comment replay200; changed actor/comment409. Review/audit/decision atomic. Approval permissions/CAS/dependencies rechecked server; rejection remains possible with unavailable dependencies.

## Submission support
GET `/api/v1/admin/tool-approvals/submission-support` -> `{items:[{tool_id,name,description,category,arg_schema,timeout_seconds,enabled,descriptor,head_revision:number,current_head:Detail.current_head,execution_ready:boolean}]}`. New heads revision0; real unconfigured tools never execution ready. Use current_head.descriptor.digest for optional read_tool reference only when enabled/current descriptor matches.
GET `/api/v1/admin/workflow-approvals/submission-support` -> `{workflow_heads:[{workflow_id,version_id,revision,enabled}],use_case_heads:[{use_case_id,version_id,revision}],meeting_contract:object,published_assets_endpoint:'/api/v1/published-agents'}`. Head revisions returned even if runtime code/dependency unavailable. Missing head revision0.
GET `/api/v1/published-agents` existing paginated API -> `{items,next_cursor}`; next_cursor UUID passed as `cursor`. Iterate until null. Existing GET `/api/v1/published-agents/{asset_id}` is exact readable published asset detail including top-level variables:string[], version_id, publication_revision, name and execution_mode; current ACL/availability enforced by existing API. Use readable exact refs, never private builder lists.
POST `/api/v1/workflows/approved/validate` with direct ApprovedWorkflow object -> `{valid:true,workflow_id,node_count,execution_order:string[]}`; schema/DAG/reference errors422. This is distinct from legacy `/workflows/validate` and validates structure, not current dependency permissions. Submission rechecks current refs.
Existing POST `/api/v1/admin/tool-approvals` retained. Existing Workflow submission retained body `{definition,client_request_id,audience,member_ids,expected_head_revision,use_case_id?:'AGENT_03',expected_use_case_revision?:number}`. Server generates manifest snapshot on new AGENT03 submission, never accepts manifest from client. Full contract returned in support; old rows remain null.

`total_pending` counts all current tenant pending requests; `actionable_pending` counts pending requests requiring another current PADMIN (excludes own; TADMIN0). Use actionable_pending for decision workload home count, while list tabs may display total_pending.
