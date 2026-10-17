import {useEffect,useState,useRef,useSyncExternalStore,type ReactNode} from 'react';
import {session} from '../../api-contract/src/session';
import {LoginPage} from './LoginPage';
import {TenantHeader} from './TenantHeader';
export const sitePaths={user:import.meta.env.PORTAL_USER_URL??'/user/home',admin:import.meta.env.PORTAL_ADMIN_URL??'/manage/admin'} as const;
export function usePortalSession(){
 const state=useSyncExternalStore(session.subscribe,session.getSnapshot);
 const [requestedTenant]=useState(()=>new URL(location.href).searchParams.get('tenant'));const applied=useRef(false);const [hintResolved,setHintResolved]=useState(!requestedTenant);
 useEffect(()=>{void session.restore();const disconnect=session.connectTabs();
  const check=()=>{if(document.visibilityState==='visible'&&session.getSnapshot().phase==='ready')void session.restore();};
  window.addEventListener('focus',check);document.addEventListener('visibilitychange',check);
  return()=>{disconnect();window.removeEventListener('focus',check);document.removeEventListener('visibilitychange',check);};
 },[]);
 useEffect(()=>{if(state.phase!=='ready'||applied.current)return;applied.current=true;
  // A URL hint selects only a tenant returned by the current authenticated server response.
  if(requestedTenant&&state.tenants.some(t=>t.tenant_id===requestedTenant))session.switchTenant(requestedTenant);
  if(requestedTenant){const url=new URL(location.href);url.searchParams.delete('tenant');history.replaceState(null,'',url.pathname+url.search+url.hash);}
  setHintResolved(true);
 },[state.phase,state.tenants,requestedTenant]);return requestedTenant&&!hintResolved&&state.phase==='ready'?{...state,phase:'boot' as const}:state;
}
function getNavIcon(label: string) {
  switch (label) {
    case '홈':
      return <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d="m3 9 9-7 9 7v11a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"/><polyline points="9 22 9 12 15 12 15 22"/></svg>;
    case 'AI 업무':
      return <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/></svg>;
    case '표준 업무 Agent':
      return <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><rect width="16" height="20" x="4" y="2" rx="2" ry="2"/><path d="M9 22v-4h6v4"/><path d="M8 6h.01"/><path d="M16 6h.01"/><path d="M12 6h.01"/><path d="M12 10h.01"/><path d="M12 14h.01"/><path d="M16 10h.01"/><path d="M16 14h.01"/><path d="M8 10h.01"/><path d="M8 14h.01"/></svg>;
    case 'AI 카탈로그':
      return <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><rect width="7" height="7" x="3" y="3" rx="1"/><rect width="7" height="7" x="14" y="3" rx="1"/><rect width="7" height="7" x="14" y="14" rx="1"/><rect width="7" height="7" x="3" y="14" rx="1"/></svg>;
    case 'My Agent':
      return <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><polygon points="12 2 15.09 8.26 22 9.27 17 14.14 18.18 21.02 12 17.77 5.82 21.02 7 14.14 2 9.27 8.91 8.26 12 2"/></svg>;
    case 'Agent 실행 이력':
      return <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><circle cx="12" cy="12" r="10"/><polyline points="12 6 12 12 16 14"/></svg>;
    case '문서 요약':
      return <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d="M14.5 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V7.5L14.5 2z"/><polyline points="14 2 14 8 20 8"/><line x1="8" y1="13" x2="16" y2="13"/><line x1="8" y1="17" x2="12" y2="17"/></svg>;
    case '내 자료':
    case '내 자료실':
    case '문서 관리':
      return <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d="M4 20h16a2 2 0 0 0 2-2V8a2 2 0 0 0-2-2h-7.93a2 2 0 0 1-1.66-.9l-.82-1.2A2 2 0 0 0 7.93 3H4a2 2 0 0 0-2 2v13c0 1.1.9 2 2 2Z"/></svg>;
    case '내 사용량':
    case '조직 사용량':
      return <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><line x1="18" y1="20" x2="18" y2="10"/><line x1="12" y1="20" x2="12" y2="4"/><line x1="6" y1="20" x2="6" y2="14"/></svg>;
    // 관리자 메뉴
    case '운영 현황':
      return <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><rect width="18" height="18" x="3" y="3" rx="2"/><path d="M3 9h18"/><path d="M9 21V9"/></svg>;
    case '승인·검증':
      return <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d="M9 11l3 3L22 4"/><path d="M21 12v7a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11"/></svg>;
    case '데이터 반입 심사':
      return <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="7 10 12 15 17 10"/><line x1="12" y1="15" x2="12" y2="3"/></svg>;
    case 'Workflow 오케스트레이션':
      return <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><circle cx="6" cy="6" r="3"/><circle cx="18" cy="18" r="3"/><path d="M6 9v3a3 3 0 0 0 3 3h6"/><circle cx="18" cy="6" r="3"/></svg>;
    case '보호 정책':
      return <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/><line x1="12" y1="8" x2="12" y2="12"/><line x1="12" y1="16" x2="12.01" y2="16"/></svg>;
    case 'Agent 관리':
      return <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><rect width="18" height="12" x="3" y="8" rx="2"/><path d="M12 2v6"/><circle cx="9" cy="14" r="1"/><circle cx="15" cy="14" r="1"/></svg>;
    case 'AI 자산 관리':
      return <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d="M21 8a2 2 0 0 0-1-1.73l-7-4a2 2 0 0 0-2 0l-7 4A2 2 0 0 0 3 8v8a2 2 0 0 0 1 1.73l7 4a2 2 0 0 0 2 0l7-4A2 2 0 0 0 21 16Z"/><path d="m3.3 7 8.7 5 8.7-5"/><path d="M12 22V12"/></svg>;
    case 'Agent Builder':
      return <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d="M14.7 6.3a1 1 0 0 0 0 1.4l1.6 1.6a1 1 0 0 0 1.4 0l3.77-3.77a6 6 0 0 1-7.94 7.94l-6.91 6.91a2.12 2.12 0 0 1-3-3l6.91-6.91a6 6 0 0 1 7.94-7.94l-3.76 3.76z"/></svg>;
    case 'AI 모델 관리':
      return <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><rect width="14" height="14" x="5" y="5" rx="2"/><line x1="9" y1="1" x2="9" y2="5"/><line x1="15" y1="1" x2="15" y2="5"/><line x1="9" y1="19" x2="9" y2="23"/><line x1="15" y1="19" x2="15" y2="23"/><line x1="1" y1="9" x2="5" y2="9"/><line x1="1" y1="15" x2="5" y2="15"/><line x1="19" y1="9" x2="23" y2="9"/><line x1="19" y1="15" x2="23" y2="15"/></svg>;
    case '사용자 관리':
      return <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d="M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2"/><circle cx="9" cy="7" r="4"/><path d="M22 21v-2a4 4 0 0 0-3-3.87"/><path d="M16 3.13a4 4 0 0 1 0 7.75"/></svg>;
    case '답변 평가':
      return <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d="M14 9V5a3 3 0 0 0-3-3l-4 9v11h11.28a2 2 0 0 0 2-1.7l1.38-9a2 2 0 0 0-2-2.3zM7 22H4a2 2 0 0 1-2-2v-7a2 2 0 0 1 2-2h3"/></svg>;
    case '플랫폼 운영':
      return <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1 0 2.83 2 2 0 0 1-2.83 0l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-2 2 2 2 0 0 1-2-2v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83 0 2 2 0 0 1 0-2.83l.06-.06a1.65 1.65 0 0 0 .33-1.82 1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1-2-2 2 2 0 0 1 2-2h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 0-2.83 2 2 0 0 1 2.83 0l.06.06a1.65 1.65 0 0 0 1.82.33H9a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 2-2 2 2 0 0 1 2 2v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 0 2 2 0 0 1 0 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82V9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 2 2 2 2 0 0 1-2 2h-.09a1.65 1.65 0 0 0-1.51 1z"/></svg>;
    default:
      return <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><circle cx="12" cy="12" r="10"/><line x1="12" y1="8" x2="12" y2="12"/><line x1="12" y1="16" x2="12.01" y2="16"/></svg>;
  }
}

export function PortalShell({state,site,items,children,canEnterAdmin=false}:{state:ReturnType<typeof session.getSnapshot>;site:'user'|'admin';items:{label:string;active:boolean;onClick:()=>void}[];children:ReactNode;canEnterAdmin?:boolean}){
 const [mobileOpen,setMobileOpen]=useState(false);
 if(state.phase==='login')return <LoginPage site={site} notice={state.notice}/>;
 if(state.phase==='logout_pending')return <main className="center-state"><h1>로그아웃 확인 중</h1>{state.failure?<><p role="alert">{state.failure}</p><button className="primary" onClick={()=>void session.logout()}>로그아웃 다시 확인</button></>:<p role="status">서버에서 로그아웃을 확인하고 있습니다.</p>}</main>;
 if(state.phase==='error')return <main className="center-state"><h1>연결 확인이 필요합니다.</h1><p role="alert">{state.failure}</p><button className="primary" onClick={()=>void session.restore()}>다시 확인</button></main>;
 if(state.phase!=='ready'||!state.user)return <main className="center-state"><p role="status">로그인과 조직 권한 확인 중</p></main>;
 return <div className={'portal '+(site==='admin'?'portal-admin-theme':'portal-user-theme')} data-portal-site={site}><a className="skip-link" href="#portal-main">본문으로 이동</a>
  <button className="mobile-nav-toggle secondary" aria-controls="portal-navigation" aria-expanded={mobileOpen} onClick={()=>setMobileOpen(!mobileOpen)}>메뉴 {mobileOpen?'닫기':'열기'}</button>
  <nav id="portal-navigation" className={'portal-sidebar sidebar '+(site==='admin'?'admin-sidebar':'user-sidebar')+(mobileOpen?' mobile-open':'')} aria-label={site==='admin'?'관리자 메뉴':'사용자 메뉴'}>
   {site==='admin'?(
    <div className="sidebar-brand sidebar-brand-admin">
     <div className="brand-logo-badge brand-logo-badge-admin" aria-hidden="true">
      <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round"><path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/></svg>
     </div>
     <div className="brand-title-wrap">
      <strong>관리자 콘솔</strong>
      <span className="admin-ops-badge">OPERATIONS</span>
     </div>
    </div>
   ):(
    <div className="sidebar-brand sidebar-brand-user">
     <div className="brand-logo-badge brand-logo-badge-user" aria-hidden="true">
      <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round"><path d="m12 3-1.9 5.8a2 2 0 0 1-1.3 1.3L3 12l5.8 1.9a2 2 0 0 1 1.3 1.3L12 21l1.9-5.8a2 2 0 0 1 1.3-1.3L21 12l-5.8-1.9a2 2 0 0 1-1.3-1.3z"/></svg>
     </div>
     <div className="brand-title-wrap">
      <strong>생성형 AI 플랫폼</strong>
      <span className="user-work-badge">WORK</span>
     </div>
    </div>
   )}
   <div className="portal-nav-group"><p className="portal-nav-caption nav-caption">{site==='admin'?'운영 관리':'업무 공간'}</p>
    {items.map(item=>(
     <button key={item.label} className="portal-nav-btn" aria-current={item.active?'page':undefined} onClick={()=>{setMobileOpen(false);item.onClick();}}>
      <span className="nav-btn-icon" aria-hidden="true">{getNavIcon(item.label)}</span>
      <span className="nav-btn-label">{item.label}</span>
     </button>
    ))}
    {(site==='admin'||canEnterAdmin)&&<>
     <p className="portal-nav-caption nav-caption">사이트 전환</p>
     <a className="site-link" href={(site==='admin'?sitePaths.user:sitePaths.admin)+(state.tenantId?'?tenant='+encodeURIComponent(state.tenantId):'')}>
      <span className="nav-btn-icon" aria-hidden="true">
       <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M15 3h6v6"/><path d="M10 14 21 3"/><path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6"/></svg>
      </span>
      <span className="nav-btn-label">{site==='admin'?'사용자 사이트로 이동 →':'관리자 콘솔로 이동 →'}</span>
     </a>
    </>}
   </div>
   <div className="sidebar-footer">
    <div className="footer-status-row">
     
     <span className="footer-status-text">{site==='admin'?'서비스 상태: 운영 현황에서 확인':'자료 검색: 현재 권한 범위'}</span>
    </div>
    <span className="footer-brand-text">생성형 AI 플랫폼 v1.2</span>
   </div>
  </nav>
  <div className="portal-main-wrapper">
   <TenantHeader user={state.user} tenants={state.tenants} tenantId={state.tenantId} site={site} pageLabel={items.find(item=>item.active)?.label} onSwitch={id=>session.switchTenant(id)} onLogout={()=>void session.logout()}/>
   <main className="content" id="portal-main" tabIndex={-1}>{state.notice&&<p role="status" className="notice">{state.notice}</p>}{children}</main>
  </div></div>;
}
export function OrganizationEmpty({hasOrganizations}:{hasOrganizations:boolean}){return <section className="workspace-empty"><h1>{hasOrganizations?'업무 조직을 선택해 주세요.':'사용 가능한 조직이 없습니다.'}</h1><p className="muted">{hasOrganizations?'상단에서 사용할 조직을 선택하면 업무 공간이 열립니다.':'관리자에게 조직 소속 권한을 확인해 주세요.'}</p></section>;}
