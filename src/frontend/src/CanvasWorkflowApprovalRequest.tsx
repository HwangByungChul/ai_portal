import {useEffect,useRef,useState} from 'react';
import {api} from './api';
import {get,useScope,modeLabel} from './scoped';
import {ApprovalAudience} from './ApprovalAudience';
import {flowToApprovedWorkflow, type AssetInputBinding} from './workflow/workflowAdapter';
import type {Edge,Node} from '@xyflow/react';
import type {ApprovedWorkflow,PublishedWorkflowAsset,Tenant,ToolSupportItem,User,WorkflowApproval,WorkflowSupport} from './types';

type DraftRef={draft_id:string;revision:number};
export function CanvasWorkflowApprovalRequest({tenant,user,draft,name,description,nodes,edges,onClose}:{tenant:Tenant;user:User;draft:DraftRef;name:string;description:string;nodes:Node[];edges:Edge[];onClose:()=>void}){
 const scope=useScope(),options={tenantId:tenant.tenant_id,csrf:user.csrf_token,signal:scope.signal};
 const [support,setSupport]=useState<WorkflowSupport|null>(null),[assets,setAssets]=useState<PublishedWorkflowAsset[]>([]),[asset,setAsset]=useState<PublishedWorkflowAsset|null>(null),[tools,setTools]=useState<ToolSupportItem[]>([]);
 const [bindings,setBindings]=useState<Record<string,AssetInputBinding>>({}),[audience,setAudience]=useState<'all'|'restricted'>('restricted'),[members,setMembers]=useState<string[]>([]);
 const [loading,setLoading]=useState(true),[busy,setBusy]=useState(false),[error,setError]=useState<string|null>(null),[validated,setValidated]=useState(''),[receipt,setReceipt]=useState<Pick<WorkflowApproval,'version_id'|'workflow_id'|'status'>|null>(null);
 const request=useRef<{fingerprint:string;id:string}|null>(null),assetSequence=useRef(0),locked=useRef(false);
 async function fail(problem:unknown){const msg=await scope.fail(problem,()=>{setSupport(null);setAssets([]);setTools([]);setAsset(null);setReceipt(null);setValidated('');});if(scope.current())setError(msg);}
 useEffect(()=>{let alive=true;async function load(){setLoading(true);setError(null);try{
  const [s,t]=await Promise.all([get<WorkflowSupport>('/admin/workflow-approvals/submission-support',options),get<{items:ToolSupportItem[]}>('/admin/tool-approvals/submission-support',options)]);
  const all:PublishedWorkflowAsset[]=[];let cursor:string|null=null;do{const page:{items:PublishedWorkflowAsset[];next_cursor:string|null}=await get('/published-agents'+(cursor?'?cursor='+encodeURIComponent(cursor):''),options);all.push(...page.items);cursor=page.next_cursor;}while(cursor&&scope.current());
  if(alive&&scope.current()){setSupport(s);setTools(t.items.filter(v=>v.enabled&&v.current_head?.enabled&&v.current_head.descriptor.digest===v.descriptor.digest));setAssets(all);}
 }catch(p){if(alive)await fail(p);}finally{if(alive&&scope.current())setLoading(false);}}void load();return()=>{alive=false;};},[]);
 async function chooseAsset(id:string){const seq=++assetSequence.current;setAsset(null);setBindings({});setValidated('');if(!id)return;try{const value=await get<PublishedWorkflowAsset>('/published-agents/'+id,options);if(scope.current()&&seq===assetSequence.current)setAsset(value);}catch(p){if(seq===assetSequence.current)await fail(p);}}

 let definition:ApprovedWorkflow|null=null,conversionError:string|null=null;
 if(asset){try{definition=flowToApprovedWorkflow(nodes,edges,draft.draft_id,name,description,asset,tools,bindings);}catch(p){conversionError=p instanceof Error?p.message:'승인 정의로 변환할 수 없습니다.';}}
 const expectedHead=support?.workflow_heads.find(h=>h.workflow_id===draft.draft_id)?.revision??0;
 const fingerprint=definition?JSON.stringify({definition,audience,members:audience==='all'?[]:members,expectedHead,draft_revision:draft.revision}):'';
 const ready=!!support&&!!asset&&!!definition&&!loading&&!busy&&(audience==='all'||members.length>0);
 useEffect(()=>{setValidated('');setReceipt(null);},[fingerprint]);
 async function validate(){if(locked.current||!ready||!definition)return;locked.current=true;setBusy(true);setError(null);setValidated('');try{await api.request('/workflows/approved/validate',{...options,method:'POST',body:definition});if(scope.current())setValidated(fingerprint);}catch(p){await fail(p);}finally{if(scope.current()){locked.current=false;setBusy(false);}}}
 async function submit(){if(locked.current||!ready||!definition||validated!==fingerprint)return;locked.current=true;setBusy(true);setError(null);if(request.current?.fingerprint!==fingerprint)request.current={fingerprint,id:crypto.randomUUID()};try{
  const value=await api.request<Pick<WorkflowApproval,'version_id'|'workflow_id'|'status'>>('/admin/workflow-approvals',{...options,method:'POST',body:{definition,audience,member_ids:audience==='all'?[]:members,expected_head_revision:expectedHead,client_request_id:request.current.id}});
  if(scope.current())setReceipt(value);
 }catch(p){await fail(p);}finally{if(scope.current()){locked.current=false;setBusy(false);}}}
 function changeBinding(variable:string,binding:AssetInputBinding){setBindings(old=>({...old,[variable]:binding}));setValidated('');}
 const toolNodes=nodes.filter(node=>(node.data as any)?.category==='tool');
 return <section className="card approval-request-form" aria-labelledby="canvas-workflow-approval-title">
  <header style={{display:'flex',justifyContent:'space-between',alignItems:'center',gap:12}}><div><h2 id="canvas-workflow-approval-title">캔버스 초안 승인 요청</h2><p>저장 초안 r{draft.revision}에서 지원되는 선형 흐름만 변환합니다. 승인 전까지 실행할 수 없습니다.</p></div><button type="button" className="secondary" onClick={onClose} disabled={busy}>닫기</button></header>
  {error&&<p role="alert">{error}</p>}{loading&&<p role="status">승인 가능한 Agent·Tool과 현재 승인 head를 확인 중입니다.</p>}
  <fieldset disabled={loading||busy}><legend>실행 자산과 입력</legend>
   <label>게시 Agent<select aria-label="승인 definition에 사용할 게시 Agent" value={asset?.asset_id??''} onChange={e=>void chooseAsset(e.target.value)}><option value="">정확한 게시 Agent 버전 선택</option>{assets.map(item=><option key={item.asset_id} value={item.asset_id}>{item.name} · 게시 revision {item.publication_revision}</option>)}</select></label>
   {asset&&<p className="scope-note">{modeLabel(asset.execution_mode)} · exact version {asset.version_id} · publication {asset.publication_revision}</p>}
   {asset&&asset.variables.length>0&&<fieldset><legend>게시 Agent 변수 binding</legend>{asset.variables.map(variable=>{const binding=bindings[variable];return <div className="workflow-binding" key={variable}>
    <label>{variable} 연결<select value={binding?.source??''} onChange={e=>{const source=e.target.value as AssetInputBinding['source']|'';if(!source){setBindings(old=>{const next={...old};delete next[variable];return next;});setValidated('');return;}changeBinding(variable,source==='input'?{source:'input'}:source==='literal'?{source:'literal',value:''}:{source:'tool',nodeId:'',path:[]});}}><option value="">연결 선택</option><option value="input">Workflow 입력</option>{toolNodes.length>0&&<option value="tool">선행 Tool 결과</option>}<option value="literal">고정 문자열</option></select></label>
    {binding?.source==='tool'&&<><label>{variable} Tool 노드<select value={binding.nodeId} onChange={e=>changeBinding(variable,{...binding,nodeId:e.target.value})}><option value="">선행 Tool 선택</option>{toolNodes.map(node=><option key={node.id} value={node.id}>{(node.data as any).label} · {node.id}</option>)}</select></label><label>{variable} 결과 경로<input value={binding.path.join('.')} maxLength={160} placeholder="비우면 Tool 결과 전체" onChange={e=>changeBinding(variable,{...binding,path:e.target.value.split('.').filter(Boolean)})}/></label></>}
    {binding?.source==='literal'&&<label>{variable} 고정 문자열<textarea maxLength={4000} value={binding.value} onChange={e=>changeBinding(variable,{...binding,value:e.target.value})}/></label>}
   </div>;})}</fieldset>}
  </fieldset>
  {conversionError&&asset&&<p role="alert">{conversionError}</p>}
  <p className="scope-note">캔버스 모델·프롬프트 선택은 승인 definition으로 복사하지 않습니다. 모델과 지시문은 선택한 게시 Agent exact version이 소유합니다. Tool은 현재 조직에서 승인되고 활성화된 exact descriptor만 사용합니다.</p>
  <ApprovalAudience tenantId={tenant.tenant_id} audience={audience} members={members} disabled={busy||loading} onChange={(a,m)=>{setAudience(a);setMembers(m);setValidated('');}}/>
  {definition&&<details><summary>변환된 승인 definition JSON 확인</summary><pre>{JSON.stringify(definition,null,2)}</pre></details>}
  <button type="button" className="secondary" disabled={!ready||busy} onClick={()=>void validate()}>서버 strict 승인 schema 검증</button>
  <button type="button" className="primary" disabled={!ready||busy||validated!==fingerprint} onClick={()=>void submit()}>타인 승인 요청 제출</button>
  {validated===fingerprint&&!!fingerprint&&<p role="status">서버 ApprovedWorkflow schema 검증 통과. 제출은 미승인 상태이며 타인 PADMIN 결정이 필요합니다.</p>}
  {receipt&&<p role="status">승인 요청 접수 · 아직 미승인 <a href={'/manage/admin/approvals?'+new URLSearchParams({kind:'workflow',request_id:receipt.version_id})}>승인 B 상세 열기</a></p>}
 </section>;
}
