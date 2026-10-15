import {AgentAccessEditor} from './AgentAccessEditor';
import {useEffect,useRef,useState} from 'react';
import {api,ApiError} from './api';
import {useRemote} from './scoped';
import type {AgentAdmin,AgentKey,Tenant,User} from './types';
function AgentEditor({agentKey,tenant,user}:{agentKey:AgentKey;tenant:Tenant;user:User}){
 const remote=useRemote<AgentAdmin>('/admin/agents/'+agentKey,tenant.tenant_id);
 const [name,setName]=useState(''),[description,setDescription]=useState(''),[instructions,setInstructions]=useState('');
 const [reason,setReason]=useState('');
 const requestBody=useRef<Record<string,unknown>|null>(null);
 const [busy,setBusy]=useState(false),[success,setSuccess]=useState<string|null>(null),[confirm,setConfirm]=useState(false);const lock=useRef(false);
 useEffect(()=>{if(remote.data){setName(remote.data.name);setDescription(remote.data.description);setInstructions(remote.data.instructions);}},[remote.data]);
 async function save(availability=false){
  if(lock.current||!remote.data)return;lock.current=true;setBusy(true);remote.setError(null);setSuccess(null);
  try{if(!availability){
    const body=requestBody.current??{client_request_id:crypto.randomUUID(),agent_key:agentKey,name,description,instructions,reason,expected_revision:remote.data.config_version};
    requestBody.current=body;
    const receipt=await api.request<{request_id:string}>('/admin/agent-deployments',{method:'POST',tenantId:tenant.tenant_id,csrf:user.csrf_token,signal:remote.signal,body});
    if(remote.current()){requestBody.current=null;setSuccess('배포 요청이 저장되었습니다. 승인·검증에서 확인하세요. 운영 설정은 승인 후 반영됩니다.');setReason('');}
   }else{
    const value=await api.request<AgentAdmin>('/admin/agents/'+agentKey+'/availability',{method:'PUT',tenantId:tenant.tenant_id,csrf:user.csrf_token,signal:remote.signal,body:{enabled:!remote.data.enabled,expected_revision:remote.data.config_version}});
    if(remote.current()){remote.setData(value);setSuccess('운영 상태가 저장되었습니다.');setConfirm(false);}
   }
  }catch(problem){
   if(problem instanceof ApiError&&problem.status>0&&problem.status<500)requestBody.current=null;
   const message=await remote.fail(problem,()=>remote.setData(null));
   if(remote.current()){
    setConfirm(false);remote.setError(message);
    if(problem instanceof ApiError&&problem.status===409)await remote.load();
    else if(problem instanceof ApiError&&(problem.status===0||problem.status>=500)){if(availability){await remote.load();remote.setError('운영 변경 결과 확인 필요 · 현재 설정을 다시 읽었습니다.');}else remote.setError('배포 요청 결과 확인 필요 · 같은 요청으로 다시 확인해 주세요.');}
   }
  }finally{if(remote.current()){setBusy(false);lock.current=false;}}
 }
 const data=remote.data;
 return <section className="card agent-editor" aria-label={agentKey==='general'?'일반 대화 설정':'규정 검색 설정'}><div className="panel-heading"><h2>{agentKey==='general'?'일반 대화':'규정 검색'}</h2><button className="secondary small" disabled={busy||remote.loading||!!requestBody.current} onClick={()=>{remote.setError(null);setSuccess(null);void remote.load();}}>설정 새로고침</button></div>
  {remote.error&&<p role="alert" className="error-message">{remote.error}</p>}{success&&<p role="status" className="notice">{success}</p>}
  {remote.loading?<p role="status">설정 확인 중</p>:data&&<><p className="scope-note">현재 설정 버전 {data.config_version} · {data.enabled?'운영 허용':'운영 중지'}{agentKey==='rules_rag'?' · 접근 가능한 문서를 근거로 답변':''}</p>
   <form className="settings-form" onSubmit={e=>{e.preventDefault();void save();}}><label>이름<input value={name} maxLength={80} disabled={busy||!!requestBody.current} onChange={e=>setName(e.target.value)}/></label>
    <label>설명<textarea value={description} maxLength={500} rows={2} disabled={busy||!!requestBody.current} onChange={e=>setDescription(e.target.value)}/></label>
    <label>기본 지시문<textarea value={instructions} maxLength={2000} rows={4} disabled={busy||!!requestBody.current} onChange={e=>setInstructions(e.target.value)}/></label>
    <label>변경 목적<textarea value={reason} maxLength={500} rows={2} disabled={busy||!!requestBody.current} onChange={e=>setReason(e.target.value)}/></label>
    <button className="primary" disabled={busy||!name.trim()||!instructions.trim()||!reason.trim()||!requestBody.current&&name===data.name&&description===data.description&&instructions===data.instructions}>{busy?'요청 확인 중':requestBody.current?'같은 배포 요청 확인':'배포 승인 요청'}</button>
   </form>
   <div className="operation-control"><button className="quiet" disabled={busy||!!requestBody.current} onClick={()=>setConfirm(true)}>{data.enabled?'Agent 중지':'Agent 재개'}</button>
    {confirm&&<div className="confirmation"><p>{tenant.display_name}의 {data.name}를 {data.enabled?'중지':'재개'}합니다. 신규·후속 AI 호출 허가에 적용되며 기존 호출의 비용은 별도입니다.</p><button className="primary small" disabled={busy} onClick={()=>void save(true)}>운영 변경 확인</button><button className="secondary small" disabled={busy} onClick={()=>setConfirm(false)}>돌아가기</button></div>}
   </div></>}
 </section>;
}
export function AgentSettingsPage({tenant,user}:{tenant:Tenant;user:User}){return <section><div className="page-heading"><div><p className="eyebrow teal">AGENT OPERATIONS</p><h1>Agent 관리</h1><p className="muted">{tenant.display_name} · 변경안을 제출하고 승인된 설정을 운영에 반영합니다.</p></div></div><p className="scope-note">재개 후에도 플랫폼 중지·조직 한도·사용량 확인 필요 상태가 있으면 새 호출은 제한됩니다.</p><div className="editor-grid">{(['general','rules_rag'] as const).map(key=><AgentEditor key={key} agentKey={key} tenant={tenant} user={user}/>)}</div><div className="editor-grid">{(['general','rules_rag'] as const).map(key=><AgentAccessEditor key={key} agentKey={key} tenant={tenant} user={user}/>)}</div></section>;}
