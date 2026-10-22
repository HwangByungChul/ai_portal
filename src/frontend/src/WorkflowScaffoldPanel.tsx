import {useId,useRef,useState} from 'react';
import {api,ApiError} from './api';
import {useScope} from './scoped';
import type {Tenant,User,WorkflowEdgeInfo,WorkflowNodeInfo} from './types';
import {validateWorkflowProposal,type WorkflowProposal} from './workflow/workflowAdapter';

type Receipt={proposal_id:string;state:'admitted'|'generating'|'ready'|'failed'|'discarded';revision:number;proposal?:WorkflowProposal|null;error_code?:string|null};

async function discardProposal(id:string,revision:number,tenantId:string,csrf:string,signal:AbortSignal){
  try{return await api.request<Receipt>('/admin/builder/scaffolds/'+id+'?expected_revision='+revision,{method:'DELETE',tenantId,csrf,signal});}
  catch(problem){
    try{const current=await api.request<Receipt>('/admin/builder/scaffolds/'+id,{tenantId,signal});if(current.state==='discarded')return current;}catch{}
    throw problem;
  }
}

export function WorkflowScaffoldPanel({tenant,user,disabled=false,hidden=false,onApplyProposal}:{tenant:Tenant;user:User;disabled?:boolean;hidden?:boolean;onApplyProposal:(proposal:WorkflowProposal)=>void}){
  const id=useId(),scope=useScope(),tenantId=tenant.tenant_id;
  const [intent,setIntent]=useState(''),[audience,setAudience]=useState('');
  const [receipt,setReceipt]=useState<Receipt|null>(null),[proposal,setProposal]=useState<WorkflowProposal|null>(null);
  const [busy,setBusy]=useState(false),[error,setError]=useState<string|null>(null),[notice,setNotice]=useState<string|null>(null);
  const request=useRef<{client_request_id:string;target:'workflow';intent:string;answers:Record<string,string>;document_refs:never[]}|null>(null);

  async function generate(){
    if(busy||disabled||!intent.trim())return;
    setBusy(true);setError(null);setNotice(null);
    request.current??={client_request_id:crypto.randomUUID(),target:'workflow',intent:intent.trim(),answers:audience.trim()?{audience:audience.trim()}:{},document_refs:[]};
    try{
      const result=await api.request<Receipt>('/admin/builder/scaffolds',{method:'POST',tenantId,csrf:user.csrf_token,signal:scope.signal,body:request.current});
      if(!scope.current())return;
      request.current=null;setReceipt(result);setProposal(result.proposal??null);
      if(result.state==='ready'&&result.proposal)setNotice('Workflow 제안이 준비되었습니다. 내용을 확인하고 Canvas로 가져오세요.');
      else if(result.state==='failed')setError('Workflow 제안을 만들지 못했습니다. 입력은 남아 있으니 확인 후 다시 시도해 주세요.');
      else setNotice('제안 요청을 접수했습니다. 상태를 확인해 주세요.');
    }catch(problem){if(scope.current())setError(problem instanceof ApiError?problem.message:'제안 요청 결과를 확인할 수 없습니다. 같은 요청으로 다시 확인해 주세요.');}
    finally{if(scope.current())setBusy(false);}
  }

  async function refresh(){
    if(!receipt||busy)return;setBusy(true);setError(null);
    try{const value=await api.request<Receipt>('/admin/builder/scaffolds/'+receipt.proposal_id,{tenantId,signal:scope.signal});if(!scope.current())return;setReceipt(value);setProposal(value.proposal??null);if(value.state==='ready'&&value.proposal)setNotice('Workflow 제안이 준비되었습니다. 내용을 확인하고 Canvas로 가져오세요.');else if(value.state==='failed')setError('Workflow 제안을 만들지 못했습니다. 입력을 확인해 주세요.');}
    catch(problem){if(scope.current())setError(problem instanceof ApiError?problem.message:'제안 상태를 확인하지 못했습니다.');}
    finally{if(scope.current())setBusy(false);}
  }

  async function discard(){
    if(!receipt||busy)return;setBusy(true);setError(null);setNotice(null);
    try{await discardProposal(receipt.proposal_id,receipt.revision,tenantId,user.csrf_token,scope.signal);if(!scope.current())return;setReceipt(null);setProposal(null);request.current=null;setNotice('Workflow 제안 내용을 삭제했습니다.');}
    catch(problem){if(scope.current())setError((problem instanceof ApiError?problem.message:'제안 삭제 결과를 확인하지 못했습니다.')+' 제안 내용은 보존되어 있습니다.');}
    finally{if(scope.current())setBusy(false);}
  }

  function apply(){
    if(!proposal||receipt?.state!=='ready')return;
    const issue=validateWorkflowProposal(proposal);
    if(issue){setError(issue);return;}
    onApplyProposal(proposal);
  }

  return <section hidden={hidden} className="card" aria-labelledby={id+':title'}>
    <div className="panel-heading"><div><p className="eyebrow teal">빠른 시작</p><h2 id={id+':title'}>업무 설명으로 Workflow 초안 제안</h2></div></div>
    <p className="scope-note">제안은 저장 전 편집 내용입니다. 생성·Canvas 적용만으로 저장, 검증, 승인, 게시, 실행 또는 Tool 호출을 하지 않습니다.</p>
    <label htmlFor={id+':intent'}>어떤 업무 흐름을 만들고 싶나요?</label>
    <textarea id={id+':intent'} rows={4} maxLength={4000} value={intent} disabled={disabled||busy||request.current!==null} onChange={event=>setIntent(event.target.value)} placeholder="예: 직원 질문을 받고 사내 규정을 검색해 근거와 함께 안내합니다." />
    <label htmlFor={id+':audience'}>주 사용자는 누구인가요? <span className="muted">선택</span></label>
    <input id={id+':audience'} maxLength={500} value={audience} disabled={disabled||busy||request.current!==null} onChange={event=>setAudience(event.target.value)} />
    {error&&<p role="alert" className="error-message">{error}</p>}{notice&&<p role="status" className="notice">{notice}</p>}
    <div className="button-row">
      {!receipt||receipt.state==='failed'?<button type="button" className="primary" disabled={disabled||busy||!intent.trim()} onClick={()=>void generate()}>{busy?'제안 만드는 중':request.current?'같은 요청 다시 확인':'Workflow 제안 만들기'}</button>:<button type="button" className="secondary" disabled={busy} onClick={()=>void refresh()}>{busy?'확인 중':'제안 상태 확인'}</button>}
      {receipt&&<button type="button" className="secondary" disabled={busy} onClick={()=>void discard()}>Workflow 제안 삭제</button>}
    </div>
    {proposal&&receipt?.state==='ready'&&<section className="confirmation" aria-label="Workflow 초안 제안 검토">
      <h3>{proposal.name}</h3><p>{proposal.description}</p>
      {!!proposal.missing_questions.length&&<div><h4>더 정하면 좋은 내용</h4><ul>{proposal.missing_questions.map((text,index)=><li key={index}>{text}</li>)}</ul></div>}
      {!!proposal.warnings.length&&<div><h4>확인할 점</h4><ul>{proposal.warnings.map((text,index)=><li key={index}>{text}</li>)}</ul></div>}
      <h4>제안된 노드 순서</h4>
      <ol>{proposal.nodes.map(node=><li key={node.node_id}><strong>{node.title}</strong> · {node.node_type==='input'?'입력':node.node_type==='read_tool'?'도구 단계 (도구 미연결)':node.node_type==='llm'?'AI 단계 (게시 Agent 버전 미연결)':node.node_type==='validate'?'조건 검토':'출력'}{node.node_type==='input'&&<span> · 입력 키 {node.config.input_key}</span>}</li>)}</ol>
      <p className="scope-note">AI/도구 참조는 자동으로 연결하지 않았습니다. Canvas에서 직접 확인하고 정확한 게시 Agent 버전 및 권한 있는 Tool을 선택하세요. 이 제안은 승인·실행 준비 상태가 아닙니다.</p>
      <button type="button" className="primary" disabled={disabled||busy} onClick={apply}>Canvas에 가져와 편집</button>
    </section>}
  </section>;
}

export type {WorkflowProposal};
