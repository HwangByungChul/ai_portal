import {useEffect,useRef,useState} from 'react';
import {api,ApiError} from './api';
import {get,useScope,modeLabel} from './scoped';
import type {DocumentJob,User} from './types';
export const jobState:Record<string,string>={queued:'접수됨',running:'처리 중',completed:'처리 완료',failed:'처리 실패',blocked:'처리 차단',interrupted:'처리 중단',needs_review:'사용량·처리 확인 필요',cancelled:'취소됨',cancel_requested:'취소 요청됨',not_started:'미처리'};
const stages:Record<string,string>={validate_source:'원문 확인',parse_plan:'문서·관계 처리',embed_batches:'색인 생성',validate_index:'색인 검증',publish:'게시',cleanup:'삭제 정리'};
export function DocumentJobsPage({tenantId,jobId,user,onPublished,onRetry,personal=false}:{tenantId:string;jobId:string;user:User;onPublished:()=>void;onRetry:(id:string)=>void;personal?:boolean}){
 const ctx=useScope();const [job,setJob]=useState<DocumentJob|null>(null),[error,setError]=useState<string|null>(null),[busy,setBusy]=useState(false);const pending=useRef<{expected_revision:number;client_retry_id:string}|null>(null);const ended=useRef(false);
 async function load(){try{const value=await get<DocumentJob>((personal?'/document-jobs/':'/admin/jobs/')+jobId,{tenantId,signal:ctx.signal});if(ctx.current()){setJob(value);if(['completed','failed','blocked','interrupted','needs_review','cancelled'].includes(value.state)&&!ended.current){ended.current=true;onPublished();}}}catch(problem){const message=await ctx.fail(problem,()=>setJob(null));if(ctx.current()){setJob(null);setError(message);}}}
 useEffect(()=>{void load();let querying=false;const timer=setInterval(()=>{if(document.visibilityState==='visible'&&!ended.current&&!querying){querying=true;void load().finally(()=>{querying=false;});}},2000);return()=>clearInterval(timer);},[]);
 async function retry(){if(busy||!job)return;setBusy(true);setError(null);const body=pending.current??{expected_revision:job.revision,client_retry_id:crypto.randomUUID()};pending.current=body;
  try{const receipt=await api.request<{job_id:string}>('/admin/jobs/'+jobId+'/retry',{method:'POST',tenantId,csrf:user.csrf_token,signal:ctx.signal,body});if(ctx.current()){pending.current=null;setError(receipt.job_id===jobId?'재시도 접수를 확인했습니다.':'새 작업이 접수됐습니다. 처리 목록에서 확인해 주세요.');onPublished();onRetry(receipt.job_id);}}
  catch(problem){if(problem instanceof ApiError&&problem.status>0&&problem.status<500)pending.current=null;const message=await ctx.fail(problem,()=>setJob(null));if(ctx.current())setError(message);}
  finally{if(ctx.current()){await load();setBusy(false);}}}
 return <section className="card" aria-label="문서 처리 상태"><h2>문서 처리 상태</h2>{error&&<p role="alert">{error}</p>}{job?<><p role="status">{jobState[job.state]??'상태 확인 필요'} · {stages[job.stage]??'상태 확인'}</p><p>{modeLabel(job.execution_mode)}</p><p>게시: {job.publication_state==='published'?'게시됨':'아직 게시되지 않음'} · 삭제 정리: {job.cleanup_state==='completed'?'완료':job.cleanup_state==='pending'?'진행 중':'해당 없음'}</p>
 {job.state==='needs_review'&&<p className="blocked-note">예약을 유지합니다. 자동으로 다시 호출하지 않습니다.</p>}{!personal&&(job.retry_allowed||pending.current)&&<button className="secondary" disabled={busy} onClick={()=>void retry()}>{pending.current?'재시도 접수 확인':'처리 재시도'}</button>}<button className="secondary" disabled={busy} onClick={()=>void load()}>처리 상태 새로고침</button></>:<p role="status">처리 상태 확인 중</p>}</section>;
}
