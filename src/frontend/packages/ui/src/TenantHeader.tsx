import type { Tenant,User } from '../../api-contract/src/types';
import { roleName } from '../../api-contract/src/types';
export function TenantHeader({user,tenants,tenantId,site='user',pageLabel,onSwitch,onLogout}:{user:User;tenants:Tenant[];tenantId:string|null;site?:'user'|'admin';pageLabel?:string;onSwitch:(id:string)=>void;onLogout:()=>void}){
 const tenant=tenants.find(t=>t.tenant_id===tenantId);
 return <header className={'portal-topbar-header '+(site==='admin'?'topbar-admin':'topbar-user')}>
  <div className="topbar-left">
   {site==='admin'?(
    <div className="topbar-breadcrumbs topbar-breadcrumbs-admin">
     <svg className="breadcrumb-icon" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/></svg>
     <span>관리 포털</span>
     <span className="crumb-sep">/</span>
     <strong>{pageLabel??'관리 포털'}</strong>
     <span className="admin-topbar-pill">OPERATIONS</span>
    </div>
   ):(
    <div className="topbar-breadcrumbs topbar-breadcrumbs-user">
     <svg className="breadcrumb-icon" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d="m12 3-1.9 5.8a2 2 0 0 1-1.3 1.3L3 12l5.8 1.9a2 2 0 0 1 1.3 1.3L12 21l1.9-5.8a2 2 0 0 1 1.3-1.3L21 12l-5.8-1.9a2 2 0 0 1-1.3-1.3z"/></svg>
     <span>생성형 AI 플랫폼</span>
     <span className="crumb-sep">/</span>
     <strong>{pageLabel??'업무 공간'}</strong>
    </div>
   )}
   {site==='user'&&<div className="topbar-search">
    <svg className="search-icon" width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/></svg>
    <input type="search" placeholder="통합 검색 준비 중" aria-label="통합 검색 준비 중" disabled/>
   </div>}
  </div>
  <div className="topbar-right">
   {site==='admin'&&<div className="admin-status-indicator" title="서비스 상태 관측 정보가 아직 연결되지 않았습니다">
    
    <span className="status-text">관제 상태 미확인</span>
   </div>}
   <div className="tenant-controls">
    <label htmlFor="tenant-choice">현재 조직</label>
    <select id="tenant-choice" value={tenantId??''} onChange={e=>onSwitch(e.target.value)} disabled={tenants.length===0}>
     <option value="" disabled>조직을 선택하세요</option>
     {tenants.map(t=><option key={t.tenant_id} value={t.tenant_id}>{t.display_name}</option>)}
    </select>
    {tenant&&<span className={'role-badge '+(site==='admin'?'role-badge-admin':'role-badge-user')}>{roleName[tenant.effective_role]}</span>}
   </div>
   <div className="account-controls">
    <div className="user-profile-badge">
     <span className="user-avatar" aria-hidden="true">{user.display_name.slice(0,1)}</span>
     <span className="user-name">{user.display_name}</span>
    </div>
    <button className="quiet small logout-btn" onClick={onLogout}>로그아웃</button>
   </div>
  </div>
 </header>;
}
