import type {ApprovalKind} from '../../../src/types';
import {readApprovalLaunch} from '../../../src/approvalLaunch';
import {useEffect,useState,useRef} from 'react';
import {PortalShell,OrganizationEmpty,usePortalSession,sitePaths} from '../../../packages/ui/src/PortalShell';
import {AdminHomePage} from '../../../src/AdminHomePage';
import {ApprovalsPage} from '../../../src/ApprovalsPage';
import {MembersPage} from '../../../src/MembersPage';
import {AssetsPage} from '../../../src/AssetsPage';
import {AgentSettingsPage} from '../../../src/AgentSettingsPage';
import {DocumentsPage} from '../../../src/DocumentsPage';
import {UsagePage} from '../../../src/UsagePage';
import {FeedbackSummaryPage} from '../../../src/FeedbackSummaryPage';
import {PlatformPage} from '../../../src/PlatformPage';
import {ModelAdminPage} from '../../../src/ModelAdminPage';
import {DataImportReviewPage} from '../../../src/DataImportReviewPage';
import {WorkflowCanvasPage} from '../../../src/WorkflowCanvasPage';
import {GuardrailPolicyPage} from '../../../src/GuardrailPolicyPage';
const paths={home:'/manage/admin',approvals:'/manage/admin/approvals',data_imports:'/manage/admin/data-imports',workflows:'/manage/admin/workflows',guardrails:'/manage/admin/guardrails',agents:'/manage/admin/agents',assets:'/manage/admin/assets',builder:'/manage/admin/builder',models:'/manage/admin/models',documents:'/manage/admin/documents',members:'/manage/admin/members',usage:'/manage/admin/usage',feedback:'/manage/admin/feedback',platform:'/manage/platform'} as const;
type View=keyof typeof paths;
function current():View{return (Object.keys(paths) as View[]).find(v=>paths[v]===location.pathname)??'home';}
export default function AdminApp(){
 const state=usePortalSession(),[view,setView]=useState<View>(current),[requestId,setRequestId]=useState<string|undefined>(()=>readApprovalLaunch(location.search)?.requestId),[requestKind,setRequestKind]=useState<ApprovalKind>(()=>readApprovalLaunch(location.search)?.kind??'settings');
 function navigate(next:View){history.pushState(null,'',paths[next]);setView(next);setRequestId(undefined);}
 function approvals(id?:string,kind?:string){navigate('approvals');const actual:ApprovalKind=kind==='dynamic'||kind==='tool'||kind==='workflow'?kind:'settings';setRequestId(id);setRequestKind(actual);if(id)history.replaceState(null,'',paths.approvals+'?'+new URLSearchParams({kind:actual,request_id:id}));}
 useEffect(()=>{const pop=()=>{setView(current());const launch=readApprovalLaunch(location.search);setRequestId(launch?.requestId);setRequestKind(launch?.kind??'settings');};window.addEventListener('popstate',pop);return()=>window.removeEventListener('popstate',pop);},[]);
 const launchTenant=useRef<string|undefined>(undefined);
 useEffect(()=>{
  if(state.phase!=='ready'||!state.tenantId)return;
  if(launchTenant.current!==undefined&&launchTenant.current!==state.tenantId){
   setRequestId(undefined);setRequestKind('settings');
   const url=new URL(location.href);url.searchParams.delete('kind');url.searchParams.delete('request_id');history.replaceState(null,'',url.pathname+url.search+url.hash);
  }else{const launch=readApprovalLaunch(location.search);setRequestId(launch?.requestId);setRequestKind(launch?.kind??'settings');}
  launchTenant.current=state.tenantId;
 },[state.phase,state.tenantId,state.generation]);
 const tenant=state.tenants.find(t=>t.tenant_id===state.tenantId),user=state.user;
 const globalAccess=!!(user?.capabilities.can_view_platform_usage||user?.capabilities.can_change_platform_availability);
 useEffect(()=>{if(state.phase==='ready'&&view==='home'&&!tenant?.can_manage&&globalAccess&&(!new URL(location.href).searchParams.has('tenant'))){history.replaceState(null,'',paths.platform);setView('platform');}},[state.phase,view,tenant?.can_manage,globalAccess]);
 const labels:Record<View,string>={home:'운영 현황',approvals:'승인·검증',data_imports:'데이터 반입 심사',workflows:'Workflow 오케스트레이션',guardrails:'보호 정책',agents:'Agent 관리',assets:'AI 자산 관리',builder:'Agent Builder',models:'AI 모델 관리',documents:'문서 관리',members:'사용자 관리',usage:'조직 사용량',feedback:'답변 평가',platform:'플랫폼 운영'};
 const items=(Object.keys(paths) as View[]).filter(v=>v==='platform'?globalAccess:tenant?.can_manage).map(v=>({label:labels[v],active:view===v,onClick:()=>navigate(v)}));
 const allowed=view==='platform'?globalAccess:!!tenant?.can_manage;
 return <PortalShell state={state} site="admin" items={items}>
 {view!=='platform'&&!tenant&&!!state.tenants.length?<OrganizationEmpty hasOrganizations/>:!allowed?<section className="workspace-empty"><h1>관리자 접근 권한이 없습니다.</h1><p role="alert">현재 조직과 권한을 확인해 주세요.</p><a className="secondary" href={sitePaths.user}>업무 홈으로 이동</a></section>:
 view==='platform'&&user?<PlatformPage key={state.generation+':platform'} user={user}/>:
 !tenant||!user?<OrganizationEmpty hasOrganizations={!!state.tenants.length}/>:<div key={state.generation+':'+tenant.tenant_id+':'+view}>
 {view==='home'?<AdminHomePage tenant={tenant} onApprovals={approvals} onUsage={()=>navigate('usage')} onAssets={()=>navigate('agents')} onMembers={()=>navigate('members')}/>:
 view==='approvals'?<ApprovalsPage key={requestKind+':'+(requestId??'')} tenant={tenant} user={user} initialId={requestId} initialKind={requestKind}/>:
 view==='data_imports'?<DataImportReviewPage tenant={tenant} user={user}/>:
 view==='workflows'?<WorkflowCanvasPage tenant={tenant} user={user}/>:
 view==='guardrails'?<GuardrailPolicyPage tenant={tenant} user={user}/>:
 view==='builder'?<AssetsPage builder tenant={tenant} user={user} onLegacy={()=>navigate('agents')}/>:view==='assets'?<AssetsPage tenant={tenant} user={user} onLegacy={()=>navigate('agents')}/>:view==='models'?<ModelAdminPage tenant={tenant} user={user}/>:view==='agents'?<AgentSettingsPage tenant={tenant} user={user}/>:
 view==='documents'?<DocumentsPage tenant={tenant} user={user} admin/>:
 view==='members'?<MembersPage tenant={tenant} user={user} generation={state.generation}/>:
 view==='usage'?<UsagePage tenant={tenant} user={user} admin/>:<FeedbackSummaryPage tenant={tenant}/>}
 </div>}</PortalShell>;
}
