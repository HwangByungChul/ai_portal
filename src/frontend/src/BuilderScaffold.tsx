import {useId,useRef,useState} from 'react';
import {api,ApiError} from './api';
import {BuilderProfileEditor,type BuilderProfile} from './BuilderProfileEditor';
import {useScope} from './scoped';
import type {AgentScaffoldProposal,AssetConfig,BuilderScaffoldReceipt as ScaffoldReceipt,DocumentRef,Tenant,User} from './types';
import './builderScaffold.css';

async function deleteProposal(proposalId:string,revision:number,tenantId:string,csrf:string,signal:AbortSignal){
 try{return await api.request<ScaffoldReceipt>('/admin/builder/scaffolds/'+proposalId+'?expected_revision='+revision,{method:'DELETE',tenantId,csrf,signal});}
 catch(problem){
  // DELETE may have committed even if its response was lost. Re-read before offering a retry.
  try{const current=await api.request<ScaffoldReceipt>('/admin/builder/scaffolds/'+proposalId,{tenantId,signal});if(current.state==='discarded')return current;}
  catch{}
  throw problem;
 }
}

export function BuilderScaffold({tenant,user,disabled,hidden=false,onUseProposal,onDiscard}:{tenant:Tenant;user:User;disabled?:boolean;hidden?:boolean;onUseProposal:(proposal:AgentScaffoldProposal,proposalId:string,revision:number)=>void;onDiscard:()=>void}){
 const id=useId(),scope=useScope(),org=tenant.tenant_id;
 const [intent,setIntent]=useState('');
 const [audienceChoice,setAudienceChoice]=useState(''),[audienceCustom,setAudienceCustom]=useState('');
 const [inputsChoice,setInputsChoice]=useState(''),[inputsCustom,setInputsCustom]=useState('');
 const [outputsChoice,setOutputsChoice]=useState(''),[outputsCustom,setOutputsCustom]=useState('');
 const [receipt,setReceipt]=useState<ScaffoldReceipt|null>(null),[proposal,setProposal]=useState<AgentScaffoldProposal|null>(null);
 const [busy,setBusy]=useState(false),[error,setError]=useState<string|null>(null),[notice,setNotice]=useState<string|null>(null);
 const request=useRef<{client_request_id:string;target:'agent';intent:string;answers:Record<string,string>;document_refs:DocumentRef[]}|null>(null);
 const audience=audienceChoice==='custom'?audienceCustom:audienceChoice;
 const inputs=inputsChoice==='custom'?inputsCustom:inputsChoice;
 const outputs=outputsChoice==='custom'?outputsCustom:outputsChoice;

 async function generate(){
  if(busy||disabled||!intent.trim())return;
  setBusy(true);setError(null);setNotice(null);
  request.current??={client_request_id:crypto.randomUUID(),target:'agent',intent:intent.trim(),answers:{...(audience.trim()?{audience:audience.trim()}:{}),...(inputs.trim()?{inputs:inputs.trim()}:{}),...(outputs.trim()?{outputs:outputs.trim()}:{})},document_refs:[]};
  try{
    const result=await api.request<ScaffoldReceipt>('/admin/builder/scaffolds',{method:'POST',tenantId:org,csrf:user.csrf_token,signal:scope.signal,body:request.current});
   if(!scope.current())return;
   setReceipt(result);setProposal(result.proposal??null);request.current=null;
   if(result.state==='ready'&&result.proposal)setNotice('초안 제안이 준비되었습니다. 검토하고 필요한 내용을 수정해 주세요.');
   else if(result.state==='failed')setError('초안 제안을 완성하지 못했습니다. 입력을 보존했으니 내용을 확인한 뒤 다시 시도해 주세요.');
   else setNotice('요청이 접수되었습니다. 잠시 뒤 제안 상태를 다시 확인해 주세요.');
  }catch(problem){if(!scope.current())return;setError(problem instanceof ApiError?problem.message:'초안 요청 결과를 확인할 수 없습니다. 같은 요청으로 다시 확인해 주세요.');}
  finally{if(scope.current())setBusy(false);}
 }
 async function refresh(){
  if(!receipt||busy)return;setBusy(true);setError(null);
  try{const result=await api.request<ScaffoldReceipt>('/admin/builder/scaffolds/'+receipt.proposal_id,{tenantId:org,signal:scope.signal});if(!scope.current())return;setReceipt(result);setProposal(result.proposal??null);if(result.state==='ready'&&result.proposal)setNotice('초안 제안이 준비되었습니다. 검토하고 필요한 내용을 수정해 주세요.');else if(result.state==='failed')setError('초안 제안을 완성하지 못했습니다. 입력을 보존했으니 내용을 확인해 주세요.');}
  catch(problem){if(scope.current())setError(problem instanceof ApiError?problem.message:'제안 상태를 확인할 수 없습니다.');}
  finally{if(scope.current())setBusy(false);}
 }
 async function discard(){
  if(!receipt||busy)return;setBusy(true);setError(null);setNotice(null);
  try{await deleteProposal(receipt.proposal_id,receipt.revision,org,user.csrf_token,scope.signal);if(!scope.current())return;setReceipt(null);setProposal(null);request.current=null;onDiscard();setNotice('제안 내용을 삭제했습니다.');}
  catch(problem){if(scope.current())setError((problem instanceof ApiError?problem.message:'제안 삭제 결과를 확인할 수 없습니다.')+' 제안은 유지됩니다. 다시 삭제를 시도할 수 있습니다.');}
  finally{if(scope.current())setBusy(false);}
 }
 function updateProfile(profile:BuilderProfile){if(proposal)setProposal({...proposal,profile,config:{...proposal.config,instructions:profile.system_prompt}});}
 function updateExecutionKind(execution_kind:AssetConfig['execution_kind']){if(!proposal)return;const defaultModel=proposal.profile.model_ref.startsWith('default_');setProposal({...proposal,config:{...proposal.config,execution_kind},profile:{...proposal.profile,model_ref:defaultModel?(execution_kind==='general'?'default_general':'default_rules_rag'):proposal.profile.model_ref,document_refs:execution_kind==='general'?[]:proposal.profile.document_refs}});}
 function apply(){if(proposal&&receipt?.state==='ready')onUseProposal(proposal,receipt.proposal_id,receipt.revision);}
 const reviewDisabled=disabled||busy||receipt?.state!=='ready';
 return <section className="card" hidden={hidden} aria-labelledby={id+':title'}>
  <div className="panel-heading"><div><p className="eyebrow teal">빠른 시작</p><h2 id={id+':title'}>업무 설명으로 Agent 초안 만들기</h2></div></div>
  <p className="scope-note">AI가 저장 전 제안을 만듭니다. 제안만으로 Agent 저장, 시험, 승인 요청은 실행되지 않습니다.</p>
  <div className="builder-scaffold-form">
   <div className="builder-scaffold-field builder-scaffold-intent">
    <label htmlFor={id+':intent'}>어떤 업무를 돕는 Agent인가요?</label>
    <textarea id={id+':intent'} rows={4} maxLength={4000} value={intent} disabled={disabled||busy||request.current!==null} onChange={event=>setIntent(event.target.value)} placeholder="예: 사내 복리후생 규정을 찾아 직원의 질문에 근거와 함께 답변합니다." />
    <p className="builder-scaffold-help">해결할 업무와 원하는 결과를 한두 문장으로 적어 주세요.</p>
   </div>
   <div className="builder-scaffold-choice-grid">
    <div className="builder-scaffold-field">
     <label htmlFor={id+':audience'}>주로 누가 사용하나요? <span className="muted">선택</span></label>
     <select id={id+':audience'} value={audienceChoice} disabled={disabled||busy||request.current!==null} onChange={event=>setAudienceChoice(event.target.value)}>
      <option value="">선택하세요</option><option value="사내 임직원">사내 임직원</option><option value="고객">고객</option><option value="관리자">관리자</option><option value="협력사">협력사</option><option value="custom">직접 입력</option>
     </select>
     {audienceChoice==='custom'&&<input aria-label="사용 대상 직접 입력" maxLength={500} value={audienceCustom} disabled={disabled||busy||request.current!==null} onChange={event=>setAudienceCustom(event.target.value)} placeholder="예: 신규 입사자, 인사 담당자" />}
    </div>
    <div className="builder-scaffold-field">
     <label htmlFor={id+':inputs'}>어떤 질문이나 정보를 받나요? <span className="muted">선택</span></label>
     <select id={id+':inputs'} value={inputsChoice} disabled={disabled||busy||request.current!==null} onChange={event=>setInputsChoice(event.target.value)}>
      <option value="">선택하세요</option><option value="사용자 질문">사용자 질문</option><option value="문서·파일">문서·파일</option><option value="업무 정보">업무 정보</option><option value="질문과 참고 자료">질문과 참고 자료</option><option value="custom">직접 입력</option>
     </select>
     {inputsChoice==='custom'&&<input aria-label="입력 정보 직접 입력" maxLength={500} value={inputsCustom} disabled={disabled||busy||request.current!==null} onChange={event=>setInputsCustom(event.target.value)} placeholder="예: 질문, 부서명, 적용 기준일" />}
    </div>
    <div className="builder-scaffold-field">
     <label htmlFor={id+':outputs'}>어떤 답변이나 결과가 필요하나요? <span className="muted">선택</span></label>
     <select id={id+':outputs'} value={outputsChoice} disabled={disabled||busy||request.current!==null} onChange={event=>setOutputsChoice(event.target.value)}>
      <option value="">선택하세요</option><option value="근거를 포함한 답변">근거를 포함한 답변</option><option value="요약·정리">요약·정리</option><option value="분석·권고">분석·권고</option><option value="절차·다음 단계 안내">절차·다음 단계 안내</option><option value="custom">직접 입력</option>
     </select>
     {outputsChoice==='custom'&&<input aria-label="원하는 결과 직접 입력" maxLength={500} value={outputsCustom} disabled={disabled||busy||request.current!==null} onChange={event=>setOutputsCustom(event.target.value)} placeholder="예: 담당 부서와 관련 규정 조항" />}
    </div>
   </div>
  </div>
  {error&&<p role="alert" className="error-message">{error}</p>}{notice&&<p role="status" className="notice">{notice}</p>}
  <div className="button-row">
   {!receipt||receipt.state==='failed'?<button type="button" className="primary" disabled={disabled||busy||!intent.trim()} onClick={()=>void generate()}>{busy?'제안 만드는 중':request.current?'같은 요청 다시 확인':'Agent 초안 제안 만들기'}</button>:<button type="button" className="secondary" disabled={busy} onClick={()=>void refresh()}>{busy?'확인 중':'제안 상태 확인'}</button>}
   {receipt&&<button type="button" className="secondary" disabled={busy} onClick={()=>void discard()}>제안 삭제</button>}
  </div>
  {proposal&&receipt?.state==='ready'&&<section className="confirmation" aria-label="Agent 초안 제안 검토">
   <h3>제안 내용 검토</h3>
   {!!proposal.missing_questions.length&&<div><h4>더 정하면 좋은 내용</h4><ul>{proposal.missing_questions.map((item,index)=><li key={index}>{item}</li>)}</ul></div>}
   {!!proposal.warnings.length&&<div><h4>확인할 점</h4><ul>{proposal.warnings.map((item,index)=><li key={index}>{item}</li>)}</ul></div>}
   <label htmlFor={id+':name'}>Agent 이름</label><input id={id+':name'} maxLength={80} disabled={reviewDisabled} value={proposal.config.name} onChange={event=>setProposal({...proposal,config:{...proposal.config,name:event.target.value}})} />
   <label htmlFor={id+':description'}>Agent 설명</label><textarea id={id+':description'} rows={2} maxLength={500} disabled={reviewDisabled} value={proposal.config.description} onChange={event=>setProposal({...proposal,config:{...proposal.config,description:event.target.value}})} />
   <label htmlFor={id+':instructions'}>Agent 지침</label><textarea id={id+':instructions'} rows={5} maxLength={2000} disabled={reviewDisabled} value={proposal.config.instructions} onChange={event=>setProposal({...proposal,config:{...proposal.config,instructions:event.target.value},profile:{...proposal.profile,system_prompt:event.target.value}})} />
   <label htmlFor={id+':execution'}>실행 방식</label><select id={id+':execution'} disabled={reviewDisabled} value={proposal.config.execution_kind} onChange={event=>updateExecutionKind(event.target.value as AssetConfig['execution_kind'])}><option value="general">일반 대화</option><option value="rules_rag">문서 근거 검색</option></select>
   <BuilderProfileEditor profile={proposal.profile} onChange={updateProfile} rag={proposal.config.execution_kind==='rules_rag'} tenantId={tenant.tenant_id} disabled={reviewDisabled} />
   <p className="scope-note">제안의 이름·설명·지침·프롬프트·실행 방식·모델·자료는 편집할 수 있습니다. 적용해도 저장되지 않으며 기존 저장 버튼을 눌러야 합니다.</p>
   <button type="button" className="primary" disabled={reviewDisabled||!proposal.config.name.trim()||!proposal.config.instructions.trim()||!proposal.profile.user_template.trim()} onClick={apply}>이 제안으로 편집 시작</button>
  </section>}
 </section>;
}
