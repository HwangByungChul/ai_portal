import { useEffect,useState,useSyncExternalStore } from 'react';
import { session } from './session';
import { LoginPage } from './LoginPage';
import { TenantHeader } from './TenantHeader';
import { MembersPage } from './MembersPage';
import {ChatPage} from './ChatPage';
import {AgentSettingsPage} from './AgentSettingsPage';
import {UsagePage} from './UsagePage';
import {DocumentsPage} from './DocumentsPage';
import {PlatformPage} from './PlatformPage';
import {FeedbackSummaryPage} from './FeedbackSummaryPage';
const paths={workspace:'/workspace',members:'/admin/members',agents:'/admin/agents',usage:'/usage',adminUsage:'/admin/usage',platform:'/platform',documents:'/documents',adminDocuments:'/admin/documents',feedback:'/admin/feedback'} as const;
type View=keyof typeof paths;
function viewFromPath():View{return (Object.keys(paths) as View[]).find(v=>paths[v]===location.pathname)??'workspace';}
export default function App(){
 const state=useSyncExternalStore(session.subscribe,session.getSnapshot);const [view,setView]=useState(viewFromPath);
 function navigate(next:View){history.pushState(null,'',paths[next]);setView(next);}
 useEffect(()=>{
  void session.restore();const disconnect=session.connectTabs();
  const check=()=>{if(document.visibilityState==='visible'&&session.getSnapshot().phase==='ready')void session.restore();};
  const pop=()=>setView(viewFromPath());window.addEventListener('focus',check);document.addEventListener('visibilitychange',check);window.addEventListener('popstate',pop);
  return()=>{disconnect();window.removeEventListener('focus',check);document.removeEventListener('visibilitychange',check);window.removeEventListener('popstate',pop);};
 },[]);
 const tenant=state.tenants.find(t=>t.tenant_id===state.tenantId);
 useEffect(()=>{if(state.phase==='ready'&&(['members','agents','adminUsage','adminDocuments','feedback'].includes(view)&&(!tenant||!tenant.can_manage)||view==='platform'&&!state.user?.capabilities.can_view_platform_usage&&!state.user?.capabilities.can_change_platform_availability)){history.replaceState(null,'','/workspace');setView('workspace');}},[state.phase,state.user,tenant,view]);
 if(state.phase==='login')return <LoginPage notice={state.notice}/>;
 if(state.phase==='logout_pending')return <main className="center-state"><span className="brand-small">AI</span><h1>로그아웃 확인 중</h1>
  {state.failure?<><p role="alert">{state.failure}</p><button className="primary" onClick={()=>void session.logout()}>로그아웃 다시 확인</button></>:<p role="status">서버에서 로그아웃을 확인하고 있습니다.</p>}</main>;
 if(state.phase==='error')return <main className="center-state"><h1>연결 확인이 필요합니다.</h1><p role="alert">{state.failure}</p><button className="primary" onClick={()=>void session.restore()}>다시 확인</button></main>;
 if(state.phase==='boot'||!state.user)return <main className="center-state"><span className="brand-small">AI</span><p role="status">로그인과 조직 권한 확인 중</p></main>;
 return <div className="portal"><TenantHeader user={state.user} tenants={state.tenants} tenantId={state.tenantId} onSwitch={id=>session.switchTenant(id)} onLogout={()=>void session.logout()}/>
  <div className="portal-body"><nav className="sidebar" aria-label="주 메뉴"><p className="nav-caption">업무 공간</p><button aria-current={view==='workspace'?'page':undefined} onClick={()=>navigate('workspace')}>AI 업무</button>
   <button aria-current={view==='documents'?'page':undefined} onClick={()=>navigate('documents')}>내 자료</button>
   <button aria-current={view==='usage'?'page':undefined} onClick={()=>navigate('usage')}>내 사용량</button>
   {tenant?.can_manage&&<><p className="nav-caption">조직 관리</p><button aria-current={view==='adminDocuments'?'page':undefined} onClick={()=>navigate('adminDocuments')}>문서 관리</button><button aria-current={view==='members'?'page':undefined} onClick={()=>navigate('members')}>사용자 관리</button><button aria-current={view==='agents'?'page':undefined} onClick={()=>navigate('agents')}>Agent 관리</button><button aria-current={view==='adminUsage'?'page':undefined} onClick={()=>navigate('adminUsage')}>조직 사용량</button><button aria-current={view==='feedback'?'page':undefined} onClick={()=>navigate('feedback')}>답변 평가</button></>}
   {(state.user.capabilities.can_view_platform_usage||state.user.capabilities.can_change_platform_availability)&&<><p className="nav-caption">프로젝트 전체</p><button aria-current={view==='platform'?'page':undefined} onClick={()=>navigate('platform')}>플랫폼 운영</button></>}
   <div className="sidebar-footer">AI 플랫폼 MVP<br/><span>개인 학습 환경</span></div></nav>
  <main className="content">{state.notice&&<p role="status" className="notice">{state.notice}</p>}
   {view==='platform'&&(state.user.capabilities.can_view_platform_usage||state.user.capabilities.can_change_platform_availability)?<PlatformPage key={state.generation+':platform'} user={state.user}/>:!state.tenants.length?<section className="workspace-empty"><div className="empty-symbol">◎</div><h1>사용 가능한 조직이 없습니다.</h1><p className="muted">관리자에게 조직 소속 권한을 확인해 주세요.</p></section>:
   !tenant?<section className="workspace-empty"><div className="empty-symbol">◎</div><h1>업무 조직을 선택해 주세요.</h1><p className="muted">상단에서 사용할 조직을 선택하면 업무 공간이 열립니다.</p></section>:
   (view==='documents'||view==='adminDocuments'&&tenant.can_manage)?<DocumentsPage key={state.generation+':'+tenant.tenant_id+':'+view} tenant={tenant} user={state.user} admin={view==='adminDocuments'}/>:
   view==='members'&&tenant.can_manage?<MembersPage key={state.generation+':'+tenant.tenant_id} tenant={tenant} user={state.user} generation={state.generation}/>:
   view==='feedback'&&tenant.can_manage?<FeedbackSummaryPage key={state.generation+':'+tenant.tenant_id} tenant={tenant}/>:view==='agents'&&tenant.can_manage?<AgentSettingsPage key={state.generation+':'+tenant.tenant_id} tenant={tenant} user={state.user}/>:
   (view==='usage'||view==='adminUsage'&&tenant.can_manage)?<UsagePage key={state.generation+':'+tenant.tenant_id+':'+view} tenant={tenant} user={state.user} admin={view==='adminUsage'}/>:
   <ChatPage key={state.generation+':'+tenant.tenant_id} tenant={tenant} user={state.user}/>}
  </main></div></div>;
}
