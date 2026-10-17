import {useEffect,useState,useSyncExternalStore} from 'react';
import {session} from './session';
import {LoginPage} from './LoginPage';
import {TenantHeader} from './TenantHeader';
import {MembersPage} from './MembersPage';
import {DocumentSummaryPage} from './DocumentSummaryPage';
import {ChatPage} from './ChatPage';
import {AgentSettingsPage} from './AgentSettingsPage';
import {UsagePage} from './UsagePage';
import {DocumentsPage} from './DocumentsPage';
import {PlatformPage} from './PlatformPage';
import {FeedbackSummaryPage} from './FeedbackSummaryPage';
import {HomePage} from './HomePage';
import {AdminHomePage} from './AdminHomePage';
import {ApprovalsPage} from './ApprovalsPage';
import {CatalogPage} from './CatalogPage';
import {PublishedRunHistory} from './PublishedRunHistory';
import {UseCaseWorkspacePage} from './UseCaseWorkspacePage';
import type {ChatLaunch} from './types';
const paths={home:'/home',workspace:'/workspace',use_cases:'/use-cases',catalog:'/catalog',mine:'/my-agents',history:'/agent-history',summary:'/document-summary',members:'/admin/members',agents:'/admin/agents',usage:'/usage',adminUsage:'/admin/usage',platform:'/platform',documents:'/documents',adminDocuments:'/admin/documents',feedback:'/admin/feedback',adminHome:'/admin',approvals:'/admin/approvals'} as const;
type View=keyof typeof paths;
const adminViews:View[]=['members','agents','adminUsage','adminDocuments','feedback','adminHome','approvals','platform'];
function viewFromPath():View{return (Object.keys(paths) as View[]).find(v=>paths[v]===location.pathname)??(location.pathname.startsWith('/admin')?'adminHome':'home');}
export default function App(){
 const state=useSyncExternalStore(session.subscribe,session.getSnapshot);
 const [view,setView]=useState(viewFromPath),[mobileOpen,setMobileOpen]=useState(false),[launch,setLaunch]=useState<ChatLaunch>({}),[requestId,setRequestId]=useState<string>(),[requestKind,setRequestKind]=useState<'settings'|'dynamic'>('settings');
 function navigate(next:View){history.pushState(null,'',paths[next]);setView(next);setMobileOpen(false);setLaunch({});setRequestId(undefined);}
 function chat(next:ChatLaunch){navigate('workspace');setLaunch(next);}
 function approvals(id?:string,kind?:string){navigate('approvals');setRequestId(id);setRequestKind(kind==='dynamic'?'dynamic':'settings');}
 useEffect(()=>{void session.restore();const disconnect=session.connectTabs();
  const check=()=>{if(document.visibilityState==='visible'&&session.getSnapshot().phase==='ready')void session.restore();};
  const pop=()=>{setView(viewFromPath());setLaunch({});setRequestId(undefined);setMobileOpen(false);};
  window.addEventListener('focus',check);document.addEventListener('visibilitychange',check);window.addEventListener('popstate',pop);
  return()=>{disconnect();window.removeEventListener('focus',check);document.removeEventListener('visibilitychange',check);window.removeEventListener('popstate',pop);};
 },[]);
 useEffect(()=>{setLaunch({});setRequestId(undefined);},[state.generation]);
 const tenant=state.tenants.find(t=>t.tenant_id===state.tenantId);
 const globalAccess=!!(state.user?.capabilities.can_view_platform_usage||state.user?.capabilities.can_change_platform_availability);
 const denied=state.phase==='ready'&&(view==='platform'?!globalAccess:adminViews.includes(view)&&tenant&&!tenant.can_manage);
 useEffect(()=>{if(denied){history.replaceState(null,'','/home');setView('home');setLaunch({});setRequestId(undefined);}},[denied]);
 if(state.phase==='login')return <LoginPage site={adminViews.includes(view)?'admin':'user'} notice={state.notice}/>;
 if(state.phase==='logout_pending')return <main className="center-state"><span className="brand-small">AI</span><h1>로그아웃 확인 중</h1>{state.failure?<><p role="alert">{state.failure}</p><button className="primary" onClick={()=>void session.logout()}>로그아웃 다시 확인</button></>:<p role="status">서버에서 로그아웃을 확인하고 있습니다.</p>}</main>;
 if(state.phase==='error')return <main className="center-state"><h1>연결 확인이 필요합니다.</h1><p role="alert">{state.failure}</p><button className="primary" onClick={()=>void session.restore()}>다시 확인</button></main>;
 if(state.phase==='boot'||!state.user)return <main className="center-state"><span className="brand-small">AI</span><p role="status">로그인과 조직 권한 확인 중</p></main>;
 const admin=adminViews.includes(view)&&!denied;
 const nav=(next:View,label:string)=><button aria-current={view===next?'page':undefined} onClick={()=>navigate(next)}>{label}</button>;
 return <div className="portal"><a className="skip-link" href="#portal-main">본문으로 이동</a><TenantHeader user={state.user} tenants={state.tenants} tenantId={state.tenantId} onSwitch={id=>session.switchTenant(id)} onLogout={()=>void session.logout()}/>
  <button className="mobile-nav-toggle secondary" aria-controls="portal-navigation" aria-expanded={mobileOpen} onClick={()=>setMobileOpen(!mobileOpen)}>메뉴 {mobileOpen?'닫기':'열기'}</button>
  <div className="portal-body"><nav id="portal-navigation" className={'sidebar'+(mobileOpen?' mobile-open':'')} aria-label={admin?'관리자 메뉴':'사용자 메뉴'}>
   {admin?<><p className="nav-caption">관리자 사이트</p>{tenant?.can_manage&&<>{nav('adminHome','운영 현황')}{nav('approvals','승인·검증')}{nav('agents','Agent 관리')}{nav('adminDocuments','문서 관리')}{nav('members','사용자 관리')}{nav('adminUsage','조직 사용량')}{nav('feedback','답변 평가')}</>}{globalAccess&&nav('platform','플랫폼 운영')}<p className="nav-caption">사이트 이동</p>{nav('home','사용자 사이트')}</>:<><p className="nav-caption">업무 공간</p>{nav('home','홈')}{nav('workspace','AI 업무')}{nav('use_cases','표준 업무 Agent')}{nav('catalog','AI 카탈로그')}{nav('mine','My Agent')}{nav('history','Agent 실행 이력')}{nav('summary','문서 요약')}{nav('documents','내 자료')}{nav('usage','내 사용량')}{(tenant?.can_manage||globalAccess)&&<><p className="nav-caption">사이트 이동</p>{nav(tenant?.can_manage?'adminHome':'platform','관리자 사이트')}</>}</>}
   <div className="sidebar-footer">생성형 AI 플랫폼</div></nav>
  <main className="content" id="portal-main" tabIndex={-1}>{state.notice&&<p role="status" className="notice">{state.notice}</p>}
   {view==='platform'&&globalAccess?<PlatformPage key={state.generation+':platform'} user={state.user}/>:!state.tenants.length?<section className="workspace-empty"><h1>사용 가능한 조직이 없습니다.</h1><p className="muted">관리자에게 조직 소속 권한을 확인해 주세요.</p></section>:!tenant?<section className="workspace-empty"><h1>업무 조직을 선택해 주세요.</h1><p className="muted">상단에서 사용할 조직을 선택하면 업무 공간이 열립니다.</p></section>:
   <div key={state.generation+':'+tenant.tenant_id+':'+view}>
    {view==='home'||denied?<HomePage tenant={tenant} user={state.user} onChat={chat} onDocuments={()=>navigate('documents')} onSummary={()=>navigate('summary')} onCatalog={()=>navigate('catalog')} onMine={()=>navigate('mine')} onUseCases={()=>navigate('use_cases')}/>:
     view==='use_cases'?<UseCaseWorkspacePage tenant={tenant} user={state.user}/>:
     view==='history'?<PublishedRunHistory tenant={tenant} user={state.user} onCatalog={()=>navigate('catalog')}/>:
     view==='catalog'||view==='mine'?<CatalogPage tenant={tenant} user={state.user} mine={view==='mine'} onChat={chat}/>:
     view==='adminHome'&&tenant.can_manage?<AdminHomePage tenant={tenant} onApprovals={approvals} onUsage={()=>navigate('adminUsage')} onAssets={()=>navigate('agents')} onMembers={()=>navigate('members')}/>:
     view==='approvals'&&tenant.can_manage?<ApprovalsPage tenant={tenant} user={state.user} initialId={requestId} initialKind={requestKind}/>:
     view==='summary'?<DocumentSummaryPage tenant={tenant} user={state.user}/>:
     view==='documents'||view==='adminDocuments'&&tenant.can_manage?<DocumentsPage tenant={tenant} user={state.user} admin={view==='adminDocuments'}/>:
     view==='members'&&tenant.can_manage?<MembersPage tenant={tenant} user={state.user} generation={state.generation}/>:
     view==='feedback'&&tenant.can_manage?<FeedbackSummaryPage tenant={tenant}/>:
     view==='agents'&&tenant.can_manage?<AgentSettingsPage tenant={tenant} user={state.user}/>:
     view==='usage'||view==='adminUsage'&&tenant.can_manage?<UsagePage tenant={tenant} user={state.user} admin={view==='adminUsage'}/>:
     <ChatPage tenant={tenant} user={state.user} initial={launch}/>}
   </div>}
  </main></div></div>;
}
