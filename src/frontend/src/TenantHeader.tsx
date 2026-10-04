import type { Tenant,User } from './types';
import { roleName } from './types';
export function TenantHeader({user,tenants,tenantId,onSwitch,onLogout}:{user:User;tenants:Tenant[];tenantId:string|null;onSwitch:(id:string)=>void;onLogout:()=>void}){
 const tenant=tenants.find(t=>t.tenant_id===tenantId);
 return <header className="topbar"><div className="portal-brand"><span className="brand-small">AI</span><strong>AI 통합 포털</strong></div>
  <div className="tenant-controls"><label htmlFor="tenant-choice">현재 조직</label><select id="tenant-choice" value={tenantId??''} onChange={e=>onSwitch(e.target.value)} disabled={tenants.length===0}>
   <option value="" disabled>조직을 선택하세요</option>{tenants.map(t=><option key={t.tenant_id} value={t.tenant_id}>{t.display_name}</option>)}</select>
  {tenant&&<span className="role-badge">{roleName[tenant.effective_role]}</span>}</div>
  <div className="account-controls"><span className="user-name">{user.display_name}</span><button className="quiet" onClick={onLogout}>로그아웃</button></div></header>;
}
