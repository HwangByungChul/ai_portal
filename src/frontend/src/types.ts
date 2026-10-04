export type Role='USER'|'TADMIN'|'PADMIN';
export interface User {user_id:string;display_name:string;session_expires_at:string;csrf_token:string;capabilities:{can_view_platform_usage:boolean;can_change_platform_availability:boolean}}
export interface Tenant {tenant_id:string;display_name:string;effective_role:Role;can_manage:boolean}
export interface Member {user_id:string;display_name:string;role:Role;active:boolean;revision:number}
export interface MemberPage {items:Member[];next_cursor:string|null}
export interface Scope {generation:number;tenantId:string|null;userId:string|null;signal:AbortSignal}
export const roleName:Record<Role,string>={USER:'일반 사용자',TADMIN:'조직 관리자',PADMIN:'플랫폼 관리자'};
