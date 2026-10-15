import {useEffect,useRef,useState} from 'react';
import {api,ApiError} from './api';
import {BuilderEvidence} from './BuilderEvidence';
import {BuilderEvaluation} from './BuilderEvaluation';
import {useScope} from './scoped';
import type {AssetDetail,Tenant,User} from './types';
type Trial={model_contract:{generation_model:string;max_completion_tokens:number;price_version:string};run_id:string;revision:number;state:string;is_terminal:boolean;execution_mode:'mock'|'real';usage_status:string;content_status:string;error_code:string|null;result:{kind:string;text?:string;answer_kind:string;reason?:string;candidates?:unknown[];evidence?:unknown[]}|null};
type Pending={client_send_id:string;purpose:'generate'|'search';values:Record<string,string>;case_id?:string};
export function BuilderTrial({detail,tenant,user,values,invalid,dirty,onLock,onApply,documentRefs}:{detail:AssetDetail;tenant:Tenant;user:User;values:Record<string,string>;invalid:boolean;dirty:boolean;onLock:(locked:boolean)=>void;onApply:(values:Record<string,string>)=>void;documentRefs:{document_id:string;version_id:string}[]}){
 const scope=useScope(),lock=useRef(false),pending=useRef<Pending|null>(null),sequence=useRef(0);
 const [runId,setRunId]=useState<string|null>(null),[trial,setTrial]=useState<Trial|null>(null),[busy,setBusy]=useState(false),[uncertain,setUncertain]=useState(false),[error,setError]=useState<string|null>(null);
 const [caseBusy,setCaseBusy]=useState(false);
 const active=!!runId&&!trial?.is_terminal;
 useEffect(()=>{onLock(busy||uncertain||active||caseBusy);},[busy,uncertain,active,caseBusy,onLock]);
 useEffect(()=>{if(!runId)return;let stopped=false,timer:ReturnType<typeof setTimeout>|undefined;
  async function poll(){try{const data=await api.request<Trial>('/admin/builder/trials/'+runId,{tenantId:tenant.tenant_id,signal:scope.signal});if(!stopped&&scope.current()){setTrial(data);if(!data.is_terminal)timer=setTimeout(()=>void poll(),1500);}}
   catch(problem){const message=await scope.fail(problem,()=>setTrial(null));if(!stopped&&scope.current()){setTrial(null);setError(message);timer=setTimeout(()=>void poll(),3000);}}}
  void poll();return()=>{stopped=true;clearTimeout(timer);};
 },[runId,tenant.tenant_id,scope.signal]);
 async function start(purpose:'generate'|'search',caseId?:string){
  if(lock.current||dirty||active||(!pending.current&&!caseId&&invalid))return;lock.current=true;setBusy(true);setError(null);const seq=++sequence.current;
  pending.current??={client_send_id:crypto.randomUUID(),purpose,values:{...values},case_id:caseId};
  try{const data=await api.request<{run_id:string}>(pending.current.case_id?'/admin/builder/evaluation-cases/'+pending.current.case_id+'/trials':'/admin/builder/assets/'+detail.asset_id+'/versions/'+detail.version_id+'/trials',{method:'POST',tenantId:tenant.tenant_id,csrf:user.csrf_token,signal:scope.signal,body:pending.current.case_id?{client_send_id:pending.current.client_send_id}:{client_send_id:pending.current.client_send_id,purpose:pending.current.purpose,values:pending.current.values}});
   if(scope.current()&&sequence.current===seq){pending.current=null;setUncertain(false);setTrial(null);setRunId(data.run_id);}}
  catch(problem){const message=await scope.fail(problem,()=>setTrial(null));if(scope.current()&&sequence.current===seq){setError(message);const unknown=!(problem instanceof ApiError)||problem.status===0||problem.status>=500;setUncertain(unknown);if(!unknown)pending.current=null;}}
  finally{if(scope.current()){lock.current=false;setBusy(false);}}
 }
 async function cancel(){if(lock.current||!trial||trial.is_terminal)return;lock.current=true;setBusy(true);setError(null);
  try{let current=trial;
   for(let attempt=0;attempt<2;attempt++){
    try{await api.request('/admin/builder/trials/'+current.run_id+'/cancel',{method:'POST',tenantId:tenant.tenant_id,csrf:user.csrf_token,signal:scope.signal,body:{expected_revision:current.revision}});break;}
    catch(problem){if(!(problem instanceof ApiError)||problem.status!==409||attempt===1)throw problem;current=await api.request<Trial>('/admin/builder/trials/'+current.run_id,{tenantId:tenant.tenant_id,signal:scope.signal});if(current.is_terminal)break;}
   }
   const data=await api.request<Trial>('/admin/builder/trials/'+trial.run_id,{tenantId:tenant.tenant_id,signal:scope.signal});if(scope.current())setTrial(data);
  }
  catch(problem){const message=await scope.fail(problem,()=>setTrial(null));if(scope.current())setError(message);}
  finally{if(scope.current()){lock.current=false;setBusy(false);}}
 }
 const stateLabels:Record<string,string>={accepted:'대기',running:'실행 중',cancel_requested:'취소 처리 중',completed:'완료',failed:'실패',blocked:'실행 차단',cancelled:'취소',interrupted:'중단'};
 return <section aria-label="저장 버전 시험 실행" className="confirmation"><h4>저장 버전 시험 실행</h4>
  <p className="scope-note">버전 {detail.latest_revision}을 본인 전용으로 시험합니다. 실행 시 사용량과 비용이 기록됩니다. 운영 게시 전 단계입니다.</p>
  {uncertain?<><p role="status">접수 결과가 불명확합니다. 같은 요청으로 접수 여부를 확인하세요.</p><button disabled={busy||dirty} onClick={()=>void start(pending.current?.purpose??'generate')}>동일 시험 요청 확인</button></>:<><button disabled={busy||active||dirty||invalid} onClick={()=>void start('generate')}>모델 시험 실행</button>{detail.config.execution_kind==='rules_rag'&&<button className="secondary" disabled={busy||active||dirty||invalid} onClick={()=>void start('search')}>RAG 검색 시험</button>}</>}
  {active&&<button className="secondary" disabled={busy||!trial} onClick={()=>void cancel()}>시험 실행 취소</button>}
  {error&&<p role="alert" className="error-message">{error}</p>}
  {trial&&<section aria-label="시험 실행 결과"><p role="status">시험 {stateLabels[trial.state]??trial.state} · {trial.execution_mode==='mock'?'모의 제공자':'실제 제공자'}</p><p>모델: {trial.model_contract.generation_model} · 출력 상한 {trial.model_contract.max_completion_tokens} 토큰</p><p>사용량: {trial.usage_status==='final'?'정산 완료':trial.usage_status==='unknown'?'확인 불가 · 비용 원장 보존':trial.usage_status==='estimated'?'예상 사용량':'호출 없음'}</p>{trial.error_code&&<p>처리 코드: {trial.error_code}</p>}
   {!dirty&&trial.content_status==='final'&&trial.result&&<><p>{trial.result.answer_kind==='insufficient_evidence'?'선택한 자료에서 충분한 근거를 찾지 못했습니다.':'시험 결과'}</p>{trial.result.text&&<pre style={{whiteSpace:'pre-wrap'}}>{trial.result.text}</pre>}{trial.result.candidates&&<><p>검색 근거 {trial.result.candidates.length}건</p><pre style={{whiteSpace:'pre-wrap',overflowWrap:'anywhere'}}>{JSON.stringify(trial.result.candidates,null,2)}</pre></>}{!!trial.result.evidence?.length&&<details><summary>답변 근거</summary><pre style={{whiteSpace:'pre-wrap',overflowWrap:'anywhere'}}>{JSON.stringify(trial.result.evidence,null,2)}</pre></details>}</>}
  </section>}
  <BuilderEvaluation detail={detail} documentRefs={documentRefs} tenant={tenant} user={user} values={values} disabled={dirty||active||busy||uncertain} refresh={trial?.is_terminal?trial.run_id:''} onLock={setCaseBusy} onApply={onApply} onRun={value=>{onApply(value.spec.values);void start(value.spec.purpose,value.case_id);}}/>
  <BuilderEvidence detail={detail} tenant={tenant} user={user} dirty={dirty} refresh={trial?.is_terminal?trial.run_id:''}/>
 </section>;
}
