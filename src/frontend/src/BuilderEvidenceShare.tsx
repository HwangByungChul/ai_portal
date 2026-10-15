import {useEffect,useRef,useState} from 'react';
import {api,ApiError} from './api';
import {useScope} from './scoped';
import type {Tenant,User} from './types';
type Evaluation={evaluation_id:string;engine:string;passed:boolean;case_id:string};
type Body={client_request_id:string;run_id:string;evaluation_id:string;consent:true};
export function BuilderEvidenceShare({run,evaluations,tenant,user}:{run:string;evaluations:Evaluation[];tenant:Tenant;user:User}){
 const scope=useScope(),alive=useRef(true),lock=useRef(false),pending=useRef<Body|null>(null);
 const [evaluation,setEvaluation]=useState(''),[consent,setConsent]=useState(false),[busy,setBusy]=useState(false),[uncertain,setUncertain]=useState(false),[error,setError]=useState<string|null>(null),[receipt,setReceipt]=useState<string|null>(null);
 useEffect(()=>{alive.current=true;return()=>{alive.current=false;};},[]);
 async function submit(){if(lock.current||(!pending.current&&(!consent||!evaluation)))return;lock.current=true;setBusy(true);setError(null);
  const body=pending.current??{client_request_id:crypto.randomUUID(),run_id:run,evaluation_id:evaluation,consent:true as const};pending.current=body;
  try{const result=await api.request<{share_id:string;status:string}>('/admin/builder/evidence-shares',{method:'POST',tenantId:tenant.tenant_id,csrf:user.csrf_token,body,signal:scope.signal});if(alive.current&&scope.current()){setReceipt(result.status==='withdrawn'?'해당 증적 공유는 철회되어 있습니다.':'승인용 증적이 제출되었습니다. 승인·검증의 Builder 시험 증적에서 확인하세요.');pending.current=null;setUncertain(false);}}
  catch(problem){const unknown=problem instanceof ApiError&&(problem.status===0||problem.status>=500);const text=await scope.fail(problem,()=>{setReceipt(null);});if(alive.current&&scope.current()){setError(text);setReceipt(null);setUncertain(unknown);if(!unknown)pending.current=null;}}
  finally{if(alive.current&&scope.current()){setBusy(false);lock.current=false;}}
 }
 return <section aria-label="승인용 증적 공유"><h5>승인용 증적 제출</h5><p>현재 조직의 승인 담당자에게 이 시험의 버전·결과 지문·자료 연결과 선택한 자동 검증의 조건 충족 여부를 공유합니다. 개인 질문·답변 원문·기대 문구·평가 의견은 포함하지 않습니다.</p><p className="scope-note">증적 제출은 배포 승인이나 운영 게시가 아닙니다.</p><label>공유할 자동 검증<select aria-label="공유할 자동 검증" value={evaluation} disabled={busy||uncertain} onChange={e=>{setEvaluation(e.target.value);setReceipt(null);}}><option value="">선택하세요</option>{evaluations.map(e=><option key={e.evaluation_id} value={e.evaluation_id}>{e.passed?'조건 충족':'조건 미충족'} · {e.engine} · 사례 {e.case_id.slice(0,8)}</option>)}</select></label><label><input type="checkbox" checked={consent} disabled={busy||uncertain} onChange={e=>setConsent(e.target.checked)}/>위 범위의 증적 공유에 동의합니다</label><button disabled={busy||(!uncertain&&(!consent||!evaluation))} onClick={()=>void submit()}>{uncertain?'동일 증적 제출 확인':'승인용 증적 제출'}</button>{uncertain&&<p role="status">접수 여부가 불명확합니다. 같은 요청으로 확인하세요.</p>}{error&&<p role="alert">{error}</p>}{receipt&&<p role="status">{receipt}</p>}{!evaluations.length&&<p>완료 시험에 자동 조건 검증을 먼저 저장해 주세요.</p>}</section>;
}
