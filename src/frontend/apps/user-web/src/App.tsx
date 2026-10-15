import {useEffect,useState} from 'react';
import {PortalShell,OrganizationEmpty,usePortalSession} from '../../../packages/ui/src/PortalShell';
import {PublishedRunHistory} from '../../../src/PublishedRunHistory';
import {CatalogPage} from '../../../src/CatalogPage';
import {HomePage} from '../../../src/HomePage';
import {ChatPage} from '../../../src/ChatPage';
import {DocumentSummaryPage} from '../../../src/DocumentSummaryPage';
import {DocumentsPage} from '../../../src/DocumentsPage';
import {UsagePage} from '../../../src/UsagePage';
import {UseCaseWorkspacePage} from '../../../src/UseCaseWorkspacePage';
import type {ChatLaunch} from '../../../packages/api-contract/src/types';
const paths={home:'/user/home',workspace:'/user/workspace',use_cases:'/user/use-cases',catalog:'/user/catalog',mine:'/user/my-agents',history:'/user/agent-history',summary:'/user/document-summary',documents:'/user/documents',usage:'/user/usage'} as const;
type View=keyof typeof paths;
function current():View{return (Object.keys(paths) as View[]).find(v=>paths[v]===location.pathname)??'home';}
export default function UserApp(){
 const state=usePortalSession(),[view,setView]=useState<View>(current),[launch,setLaunch]=useState<ChatLaunch>({});
 function navigate(next:View){history.pushState(null,'',paths[next]);setView(next);setLaunch({});}
 function chat(next:ChatLaunch){navigate('workspace');setLaunch(next);}
 useEffect(()=>{const pop=()=>{setView(current());setLaunch({});};window.addEventListener('popstate',pop);return()=>window.removeEventListener('popstate',pop);},[]);
 useEffect(()=>{setLaunch({});},[state.generation]);
 const tenant=state.tenants.find(t=>t.tenant_id===state.tenantId),user=state.user;
 const labels:Record<View,string>={history:'Agent 실행 이력',catalog:'AI 카탈로그',mine:'My Agent',use_cases:'표준 업무 Agent',home:'홈',workspace:'AI 업무',summary:'문서 요약',documents:'내 자료',usage:'내 사용량'};
 const canAdmin=!!(tenant?.can_manage||user?.capabilities.can_view_platform_usage||user?.capabilities.can_change_platform_availability);
 return <PortalShell state={state} site="user" canEnterAdmin={canAdmin} items={(Object.keys(paths) as View[]).map(v=>({label:labels[v],active:view===v,onClick:()=>navigate(v)}))}>
 {!tenant||!user?<OrganizationEmpty hasOrganizations={!!state.tenants.length}/>:<div key={state.generation+':'+tenant.tenant_id+':'+view}>
 {view==='home'?<HomePage tenant={tenant} user={user} onChat={chat} onDocuments={()=>navigate('documents')} onSummary={()=>navigate('summary')} onCatalog={()=>navigate('catalog')} onMine={()=>navigate('mine')} onUseCases={()=>navigate('use_cases')}/>:
 view==='use_cases'?<UseCaseWorkspacePage tenant={tenant} user={user}/>:
 view==='history'?<PublishedRunHistory tenant={tenant} user={user} onCatalog={()=>navigate('catalog')}/>:view==='catalog'||view==='mine'?<CatalogPage tenant={tenant} user={user} mine={view==='mine'} onChat={chat}/>:view==='workspace'?<ChatPage tenant={tenant} user={user} initial={launch} onPublishedHistory={()=>navigate('history')}/>:
 view==='summary'?<DocumentSummaryPage tenant={tenant} user={user}/>:
 view==='documents'?<DocumentsPage tenant={tenant} user={user}/>:<UsagePage tenant={tenant} user={user}/>}
 </div>}</PortalShell>;
}
