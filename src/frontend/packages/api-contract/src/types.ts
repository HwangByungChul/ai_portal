export const XLSX_MEDIA_TYPE='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet' as const;
export const DOCX_MEDIA_TYPE='application/vnd.openxmlformats-officedocument.wordprocessingml.document' as const;
export type Role='USER'|'TADMIN'|'PADMIN';
export interface User {user_id:string;display_name:string;session_expires_at:string;csrf_token:string;platform_availability?:{enabled:boolean;revision:number};capabilities:{can_view_platform_usage:boolean;can_change_platform_availability:boolean}}
export interface Tenant {tenant_id:string;display_name:string;effective_role:Role;can_manage:boolean}
export interface Member {user_id:string;display_name:string;role:Role;active:boolean;revision:number}
export interface MemberPage {items:Member[];next_cursor:string|null}
export interface Scope {generation:number;tenantId:string|null;userId:string|null;signal:AbortSignal}
export const roleName:Record<Role,string>={USER:'일반 사용자',TADMIN:'조직 관리자',PADMIN:'플랫폼 관리자'};

export type AgentKey='general'|'rules_rag';
export type Mode='mock'|'real';
export interface AgentSummary {agent_key:AgentKey;name:string;description:string;config_version:number;available:boolean;safe_block_reason:string|null}
export interface AgentAdmin {agent_key:AgentKey;name:string;description:string;instructions:string;enabled:boolean;config_version:number}
export interface PageResult<T> {items:T[];next_cursor:string|null}
export interface Conversation {conversation_id:string;tenant_id:string;agent_key:AgentKey;created_at:string;updated_at:string;recent_state:string|null;title:string;pinned:boolean;metadata_revision:number}
export interface Message {message_id:string;run_id:string;sequence_no:number;role:'user'|'assistant';text:string;created_at:string;run_state:string;answer_kind:string|null}
export interface RunAssetBinding {source:'legacy';asset_id:string;revision:number;version_id:string;config_hash:string}
export interface Run {run_id:string;tenant_id:string;conversation_id:string;agent_key:AgentKey;config_version:number;asset_binding:RunAssetBinding|null;state:string;stage:string;revision:number;is_terminal:boolean;
 answer_kind:string|null;content_status:'pending'|'final'|'unavailable';execution_mode:Mode;usage_status:'none'|'estimated'|'unknown'|'final';error_code:string|null;
 created_at:string;ended_at:string|null;cancel_requested_at:string|null;result:{message_id:string;text:string;evidence:unknown[]}|null}
export interface UsageItem {call_id:string;operation:string;execution_mode:Mode;state:string;usage_status:string;reserved_krw:string;created_at:string}
export interface Usage {period:string;execution_mode:Mode;call_count:number;unknown_count:number;estimated_accounted_krw:string;reserved_krw:string;
 known_tokens:{input_tokens:number;output_tokens:number;total_tokens:number}|null;blocked:boolean;safe_block_reason:string|null;items:UsageItem[];next_cursor:string|null}
export interface Budget {period:string;execution_mode:Mode;allocated_cap_krw:string;local_cap_krw:string;estimated_accounted_krw:string;reserved_krw:string;blocked:boolean;safe_block_reason:string|null;revision:number}
export interface PlatformSummary {period:string;execution_mode:Mode;approved_cap_krw:string;operational_cap_krw:string;allocated_total_krw:string;
 estimated_accounted_krw:string;reserved_krw:string;unknown_count:number;enabled:boolean;revision:number;stop_latch:boolean}

export interface DocumentRef {document_id:string;version_id:string}
export interface ReadableDocument extends DocumentRef {title:string;version_no:number;safe_version_label:string;visibility:'org'|'private'|'shared';execution_mode:Mode}
export interface ManagedDocument extends DocumentRef {title?:string|null;index_id:string;revision:number;visibility:'org'|'private';access_state:string;processing_state:string;publication_state:string;cleanup_state:string;can_read_content:boolean}
export interface DocumentJob extends DocumentRef {job_id:string;index_id:string;job_kind:string;state:string;stage:string;revision:number;execution_mode:Mode;retry_allowed?:boolean;publication_state?:string;cleanup_state?:string;safe_error_code:string|null}
export interface UploadReceipt extends DocumentRef {job_id:string;index_id:string}
export interface Grant {grant_id:string;recipient_tenant_id:string;active:boolean;revision:number}
export interface GrantPage extends DocumentRef {publication_revision:number;items:Grant[]}
export interface Evidence {ordinal:number;content_status:'available'|'unavailable';title?:string;version_no?:number;quote?:string;location?:{line_start:number;line_end:number};source_url?:string;source_media_type?:'application/pdf'|typeof DOCX_MEDIA_TYPE|typeof XLSX_MEDIA_TYPE;structure_locations?:({kind:'paragraph';paragraph:number}|{kind:'table_cell';table:number;row:number;column:number}|{kind:'sheet';sheet_index:number;sheet_name:string}|{kind:'cell';sheet_index:number;sheet_name:string;cell:string})[];page_start?:number;page_end?:number}

export type Rating='positive'|'negative';
export interface ResponseFeedbackValue {run_id:string;active:boolean;revision:number;rating:Rating|null;comment:string|null;updated_at:string|null;replayed?:boolean}
export interface FeedbackSummary {period:string;execution_mode:Mode;minimum_participants:number;items:{agent_key:AgentKey;status:'empty'|'suppressed'|'available';positive_count:number|null;negative_count:number|null;total_count:number|null}[]}

export type SummaryMediaType='text/plain'|'text/markdown'|'application/pdf'|typeof DOCX_MEDIA_TYPE|typeof XLSX_MEDIA_TYPE;
export interface SummaryEvidence {ordinal:number;document_id:string;version_id:string;title:string;version_no:number;quote:string;location:{start_offset:number;end_offset:number;line_start:number;line_end:number};source_url:string;source_media_type:SummaryMediaType;structure_locations?:Evidence['structure_locations'];page_start?:number;page_end?:number}
export interface SummaryAdmission {run_id:string;state:string;revision:number;replayed:boolean}
export interface SummaryRun extends Omit<Run,'result'> {task_kind:'document_summary';bullet_count:3|5;parent_run_id:string|null;result:{text:string}|null;evidence:SummaryEvidence[]}
export interface SummarySubmission {client_send_id:string;document_ref:DocumentRef;bullet_count:3|5}

export interface ChatLaunch {assetId?:string;prompt?:string;agentKey?:AgentKey;conversation?:Conversation}
export interface AgentDeployment {request_id:string;agent_key:AgentKey;requester_id:string;status:'pending'|'approved'|'rejected';base_version:number;revision:number;created_at:string;proposed:{name:string;description:string;instructions?:string};reason?:string;previous?:{name:string;description:string;instructions:string};current_version?:number;comment?:string|null;decided_by?:string|null;decided_at?:string|null;deployed_version?:number|null;can_decide?:boolean}

export interface AssetConfig {name:string;description:string;instructions:string;execution_kind:'general'|'rules_rag'}
export interface AssetItem {asset_id:string;owner_id:string|null;kind:'agent';latest_revision:number;created_at:string|null;legacy_agent_key:AgentKey|null;version_id:string|null;config_hash:string;state:'draft'|'legacy';name:string;description:string;execution_kind:AgentKey}
export interface AssetVersion {revision:number;version_id:string;config_hash:string;created_by:string;created_at:string}
export interface AssetDetail extends Omit<AssetItem,'name'|'description'|'execution_kind'> {config:AssetConfig;versions:AssetVersion[];history_more:boolean}
export interface AssetReceipt {asset_id:string;revision:number;version_id:string;config_hash:string;replayed:boolean}

export interface CatalogItem {asset_id:string;agent_key:AgentKey;revision:number;name:string;description:string;category:'general'|'knowledge';available:boolean;safe_block_reason:string|null;favorite:boolean;favorite_revision:number}
export interface AgentAccess {agent_key:AgentKey;mode:'all'|'restricted';member_ids:string[];revision:number;replayed?:boolean}

export interface ModelInfo {model_id:string;provider_key:string;model_name:string;pricing_version:string;input_usd_per_million:string;output_usd_per_million:string;context_window:number;max_output_tokens:number;enabled:boolean;capabilities:string[]}

export interface DataImportItem {import_id:string;tenant_id:string;requester_id:string;document_id:string;version_id:string;classification:'internal'|'confidential'|'restricted';target_scope:'org'|'department'|'team';reason:string;status:'pending'|'approved'|'rejected';revision:number;decided_by?:string|null;decided_at?:string|null;comment?:string|null;created_at:string;updated_at:string}
export interface DataImportRequest {client_request_id:string;document_id:string;version_id:string;classification:'internal'|'confidential'|'restricted';target_scope:'org'|'department'|'team';reason:string}

export interface ToolInfo {tool_id:string;name:string;description:string;category:string;arg_schema:Record<string,any>;timeout_seconds:number;enabled:boolean;execution_ready?:boolean;execution_mode?:'mock'|'real';version_digest?:string}
export interface WorkflowNodeInfo {node_id:string;node_type:'input'|'read_tool'|'llm'|'validate'|'output';title:string;config:Record<string,any>}
export interface WorkflowEdgeInfo {source_node:string;target_node:string}
export interface WorkflowCheckpoint {node_id:string;node_type:string;title:string;status:'success'|'failed';output:any;elapsed_ms:number;error_code?:string|null}
export interface WorkflowRunResult {workflow_id:string;status:'completed'|'failed';total_elapsed_ms:number;step_count:number;checkpoints:WorkflowCheckpoint[];final_output:any}

export interface GuardrailPolicy {revision:number;engine_revision:string;input_enabled:boolean;output_enabled:boolean;pii_severity:'block'|'warn'|'log';injection_severity:'block'|'warn'|'log';forbidden_severity:'block'|'warn'|'log';output_pii_action:'mask'|'block';input_rules:string[];output_rules:string[]}
export interface GuardrailViolation {violation_id:string;tenant_id:string;user_id:string;direction:'input'|'output';rule_ids:string[];content_hash:string;policy_revision:string;created_at:string}
export interface UseCaseItem {approved_version_id?:string|null;execution_ready?:boolean;use_case_id:string;name:string;category:string;description:string;approved_asset_version:string;required_tools:string[];role_scope:string[];auto_decision_prohibited:boolean;disclaimer:string|null;example_queries:string[]}
export interface UseCaseExecutionResult {execution_id:string;use_case_id:string;name:string;draft:string;citations:Array<{type:string;ref:string;title:string}>;tool_results:Array<{tool_id:string;data:any}>;review_required:boolean;auto_decision_prohibited:boolean;disclaimer:string|null}

export interface DailyCallStat {date:string;calls:number;confirmed_amount:number}
export interface PendingRequestSummary {kind:ApprovalKind;request_id:string;requester_id:string;asset_name:string;base_version:number;created_at:string}
export interface OverviewMetrics {calls:number;confirmed_amount:number;reserved_amount:number;unknown_calls:number}
export interface ServiceStatus {service_name:string;status:'observed_ok'|'degraded'|'unavailable'|'unknown';observed_at:string;source:string;scope:string}
export interface AdminOverview {
  as_of:string;
  period:{from:string;to:string};
  timezone:string;
  metrics:OverviewMetrics;
  daily_calls:DailyCallStat[];
  pending:{settings:number;dynamic:number;total:number;items:PendingRequestSummary[]};
  services:ServiceStatus[];
}

export interface ApprovedWorkflowSummary {workflow_id:string;version_id:string;revision:number;name:string;description:string;input_key:string;execution_mode:'mock'|'real';execution_ready:boolean;node_count:number}
export interface WorkflowExecutionStep {node_id:string;node_type:string;state:string;child_run_id:string|null;tool_client_id:string|null;error_code:string|null}
export interface WorkflowExecutionRun {run_id:string;version_id:string;workflow_id:string;state:'accepted'|'running'|'completed'|'cancelled'|'failed'|'blocked'|'interrupted';revision:number;is_terminal:boolean;execution_mode:'mock'|'real';steps:WorkflowExecutionStep[];result_access:'final'|'unavailable'|'blocked';result:unknown;error_code:string|null;replayed?:boolean;meeting_context?:MeetingContext}
export interface WorkflowRecoveryItem {request_id:string;run_id:string;requester_id:string;expected_run_revision:number;current_run_revision:number;version_digest:string;resume_node_id:string;reason:string;created_at:string;status:'requested'|'approved'|'rejected'|'resumed';workflow_id:string;version_id:string;run_state:string;steps:WorkflowExecutionStep[]}

export interface MeetingDocument {document_id:string;version_id:string;version_no:number;title:string;character_length:number;source_sha256:string;ready:boolean;unavailable_reason:string|null}
export interface MeetingContext {meeting_date:string|null;memo_character_count:number;aggregate_character_count:number;documents:{document_id:string;version_id:string;source_ref:string;title:string|null;current_available:boolean}[]}
export type MeetingStructureLocation =
 | {kind:'paragraph';paragraph:number}
 | {kind:'table_cell';table:number;row:number;column:number}
 | {kind:'sheet';sheet_index:number;sheet_name:string}
 | {kind:'cell';sheet_index:number;sheet_name:string;cell:string};
export interface MeetingEvidenceItem {text:string;quote:string;source_ref:string;source_display?:{title:string;version_id:string;page_start?:number;page_end?:number;structure_locations?:MeetingStructureLocation[];location_ambiguous:boolean}}
export interface MeetingActionItem extends MeetingEvidenceItem {assignee:string|null;due_date:string|null;due_expression?:string|null;deadline_status?:string;deadline_reason?:string|null}
export interface MeetingResult {decisions:MeetingEvidenceItem[];unresolved:MeetingEvidenceItem[];actions:MeetingActionItem[]}

// Administrative review DTOs: status records the historical decision, head records current availability.
export type ApprovalKind='settings'|'evidence'|'dynamic'|'tool'|'workflow';
export type ApprovalStatus='pending'|'approved'|'rejected';
export interface ToolDescriptor {tool_id:string;mode:Mode;adapter_revision:string;registry_module_sha256:string;adapter_module_sha256:string;arg_schema:Record<string,unknown>;timeout_seconds:number;read_only:true;digest:string}
export interface ToolApproval {request_id:string;tool_id:string;descriptor:ToolDescriptor;audience:'all'|'restricted';member_ids:string[];expected_head_revision:number;status:ApprovalStatus;revision:number;requester_id:string;decided_by:string|null;created_at:string;decided_at:string|null}
export interface NodeReference {node_id:string;path:string[]}
export type WorkflowBinding=string|NodeReference;
export interface ApprovedNode {node_id:string;node_type:'input'|'read_tool'|'llm'|'validate'|'output';title:string;config:{input_key?:string;tool_id?:string;version_digest?:string;arguments?:Record<string,WorkflowBinding>;asset_id?:string;version_id?:string;publication_revision?:number;values?:Record<string,WorkflowBinding>;source?:NodeReference}}
export interface ApprovedWorkflow {workflow_id:string;name:string;description:string;nodes:ApprovedNode[];edges:WorkflowEdgeInfo[];max_steps:number}
export interface WorkflowApproval {version_id:string;workflow_id:string;revision:number;decision_revision:number;created_by:string;definition:ApprovedWorkflow;version_digest:string;audience:'all'|'restricted';member_ids:string[];expected_head_revision:number;status:ApprovalStatus;decided_by:string|null;decided_at:string|null;created_at:string;execution_mode:Mode;runtime_digest:string;use_case_id:string|null;use_case_digest:string|null;use_case_revision:number|null;manifest_snapshot:Record<string,unknown>|null}
export type ReviewRequest=ToolApproval|WorkflowApproval;
export interface ApprovalDetail<T extends ReviewRequest=ReviewRequest> {request:T;current_head:(T & {head_revision:number;enabled:boolean})|null;validation:{valid:boolean;checked_at:string;checks:{code:string;status:'pass'|'fail'|'unavailable';message:string}[]};diff:{baseline_available:boolean;changes:{field:string;before:unknown;after:unknown}[]};history:{action:string;actor_id:string;created_at:string;comment:string|null;revision:number|null}[];can_approve:boolean;can_reject:boolean;can_revoke:boolean;decision_reason:string|null}
export interface ApprovalPage<T extends ReviewRequest=ReviewRequest> extends PageResult<T> {total_pending:number;actionable_pending:number}
export interface ToolSupportItem extends ToolInfo {descriptor:ToolDescriptor;head_revision:number;current_head:ApprovalDetail<ToolApproval>['current_head']}
export interface WorkflowSupport {workflow_heads:{workflow_id:string;version_id:string;revision:number;enabled:boolean}[];use_case_heads:{use_case_id:string;version_id:string;revision:number}[];meeting_contract:Record<string,unknown>;published_assets_endpoint:string}
export interface PublishedWorkflowAsset {asset_id:string;version_id:string;publication_revision:number;name:string;variables:string[];execution_mode:Mode;required_tools?:string[]}

export type MeetingRating='acceptable'|'needs_review'|'not_assessed';
export interface MeetingRatings {accuracy:MeetingRating;omission:MeetingRating;owner:MeetingRating;deadline:MeetingRating;comment:string}
export interface MeetingQuality {run_id:string;run_revision:number;result_digest:string;review_revision:number;history_limit:number;human_review_required:boolean;structural:{evidence_valid:boolean;item_count:number;unresolved_deadlines:number;past_deadlines:number;error:string|null;human_review_required:boolean};items:{review_id:string;review_revision:number;run_revision:number;result_digest:string;ratings:MeetingRatings;created_at:string}[]}
