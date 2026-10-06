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
export interface Run {run_id:string;tenant_id:string;conversation_id:string;agent_key:AgentKey;config_version:number;state:string;stage:string;revision:number;is_terminal:boolean;
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
export interface ManagedDocument extends DocumentRef {index_id:string;revision:number;visibility:'org'|'private';access_state:string;processing_state:string;publication_state:string;cleanup_state:string;can_read_content:boolean}
export interface DocumentJob extends DocumentRef {job_id:string;index_id:string;job_kind:string;state:string;stage:string;revision:number;execution_mode:Mode;retry_allowed?:boolean;publication_state?:string;cleanup_state?:string;safe_error_code:string|null}
export interface UploadReceipt extends DocumentRef {job_id:string;index_id:string}
export interface Grant {grant_id:string;recipient_tenant_id:string;active:boolean;revision:number}
export interface GrantPage extends DocumentRef {publication_revision:number;items:Grant[]}
export interface Evidence {ordinal:number;content_status:'available'|'unavailable';title?:string;version_no?:number;quote?:string;location?:{line_start:number;line_end:number};source_url?:string}
