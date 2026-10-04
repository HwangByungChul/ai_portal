import { useEffect,useState,useSyncExternalStore } from 'react';
import { session } from './session';
import { LoginPage } from './LoginPage';
import { TenantHeader } from './TenantHeader';
import { MembersPage } from './MembersPage';
function viewFromPath(){return location.pathname==='/admin/members'?'members':'workspace';}
export default function App(){
 const state=useSyncExternalStore(session.subscribe,session.getSnapshot);const [view,setView]=useState(viewFromPath);
 function navigate(next:'members'|'workspace'){history.pushState(null,'',next==='members'?'/admin/members':'/workspace');setView(next);}
 useEffect(()=>{
  void session.restore();const disconnect=session.connectTabs();
  const check=()=>{if(document.visibilityState==='visible'&&session.getSnapshot().phase==='ready')void session.restore();};
  const pop=()=>setView(viewFromPath());window.addEventListener('focus',check);document.addEventListener('visibilitychange',check);window.addEventListener('popstate',pop);
  return()=>{disconnect();window.removeEventListener('focus',check);document.removeEventListener('visibilitychange',check);window.removeEventListener('popstate',pop);};
 },[]);
 const tenant=state.tenants.find(t=>t.tenant_id===state.tenantId);
 useEffect(()=>{if(state.phase==='ready'&&view==='members'&&(!tenant||!tenant.can_manage)){history.replaceState(null,'','/workspace');setView('workspace');}},[state.phase,tenant,view]);
 if(state.phase==='login')return <LoginPage notice={state.notice}/>;
 if(state.phase==='logout_pending')return <main className="center-state"><span className="brand-small">AI</span><h1>로그아웃 확인 중</h1>
  {state.failure?<><p role="alert">{state.failure}</p><button className="primary" onClick={()=>void session.logout()}>로그아웃 다시 확인</button></>:<p role="status">서버에서 로그아웃을 확인하고 있습니다.</p>}</main>;
 if(state.phase==='error')return <main className="center-state"><h1>연결 확인이 필요합니다.</h1><p role="alert">{state.failure}</p><button className="primary" onClick={()=>void session.restore()}>다시 확인</button></main>;
 if(state.phase==='boot'||!state.user)return <main className="center-state"><span className="brand-small">AI</span><p role="status">로그인과 조직 권한 확인 중</p></main>;
 return <div className="portal"><TenantHeader user={state.user} tenants={state.tenants} tenantId={state.tenantId} onSwitch={id=>session.switchTenant(id)} onLogout={()=>void session.logout()}/>
  <div className="portal-body"><nav className="sidebar" aria-label="주 메뉴"><p className="nav-caption">업무 공간</p><button aria-current={view==='workspace'?'page':undefined} onClick={()=>navigate('workspace')}>AI 업무</button>
   {tenant?.can_manage&&<><p className="nav-caption">조직 관리</p><button aria-current={view==='members'?'page':undefined} onClick={()=>navigate('members')}>사용자 관리</button></>}
   <div className="sidebar-footer">AI 플랫폼 MVP<br/><span>개인 학습 환경</span></div></nav>
  <main className="content">{state.notice&&<p role="status" className="notice">{state.notice}</p>}
   {!state.tenants.length?<section className="workspace-empty"><div className="empty-symbol">◎</div><h1>사용 가능한 조직이 없습니다.</h1><p className="muted">관리자에게 조직 소속 권한을 확인해 주세요.</p></section>:
   !tenant?<section className="workspace-empty"><div className="empty-symbol">◎</div><h1>업무 조직을 선택해 주세요.</h1><p className="muted">상단에서 사용할 조직을 선택하면 업무 공간이 열립니다.</p></section>:
   view==='members'&&tenant.can_manage?<MembersPage key={state.generation+':'+tenant.tenant_id} tenant={tenant} user={state.user} generation={state.generation}/>:
   <section className="workspace-empty"><p className="eyebrow teal">YOUR WORKSPACE</p><div className="empty-symbol">✦</div><h1>대화 기능 준비중</h1><p className="muted">{tenant.display_name}의 업무 공간입니다.<br/>AI 대화와 문서 검색은 다음 단계에서 연결합니다.</p>{tenant.can_manage&&<button className="primary" onClick={()=>navigate('members')}>사용자 관리 시작</button>}</section>}
  </main></div></div>;
}
