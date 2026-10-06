import {useEffect,useId,useRef,useState} from 'react';
import {api,ApiError} from './api';
import {get,useScope} from './scoped';
import type {ResponseFeedbackValue,Rating} from './types';

export function ResponseFeedback({tenantId,runId,csrf,onUnavailable}:{tenantId:string;runId:string;csrf:string;onUnavailable:()=>void}){
 const commentId=useId();const context=useScope();const [data,setData]=useState<ResponseFeedbackValue|null>(null);
 const [rating,setRating]=useState<Rating|null>(null),[comment,setComment]=useState('');
 const [loading,setLoading]=useState(true),[busy,setBusy]=useState(false),[error,setError]=useState<string|null>(null),[notice,setNotice]=useState<string|null>(null);
 const lock=useRef(false),query=useRef(0);const path='/runs/'+runId+'/feedback';
 function clear(){setData(null);setRating(null);setComment('');setNotice(null);}
 function publish(value:ResponseFeedbackValue){setData(value);setRating(value.active?value.rating:null);setComment(value.active?value.comment??'':'');}
 async function fail(problem:unknown){
  if(!context.current())return;
  if(problem instanceof ApiError&&(problem.status===404||problem.code==='FEEDBACK_NOT_READY')){clear();onUnavailable();return;}
  const message=await context.fail(problem,clear);if(context.current())setError(message);
 }
 async function load(){
  const version=++query.current;setLoading(true);setError(null);
  try{const value=await get<ResponseFeedbackValue>(path,{tenantId,signal:context.signal});if(context.current()&&version===query.current)publish(value);}
  catch(problem){if(version===query.current)await fail(problem);}
  finally{if(context.current()&&version===query.current)setLoading(false);}
 }
 useEffect(()=>{void load();const refresh=()=>{if(document.visibilityState==='visible'&&!lock.current)void load();};window.addEventListener('focus',refresh);document.addEventListener('visibilitychange',refresh);return()=>{window.removeEventListener('focus',refresh);document.removeEventListener('visibilitychange',refresh);};},[]);
 async function change(withdraw=false){
  if(lock.current||!data||(!withdraw&&!rating))return;lock.current=true;query.current++;setBusy(true);setNotice(null);setError(null);
  try{const value=await api.request<ResponseFeedbackValue>(path,{method:withdraw?'DELETE':'PUT',tenantId,csrf,signal:context.signal,
   body:withdraw?{expected_revision:data.revision}:{rating,comment,expected_revision:data.revision}});
   if(context.current()){publish(value);setNotice(withdraw?'평가를 철회했습니다.':'평가를 저장했습니다.');}
  }catch(problem){await fail(problem);if(context.current()&&problem instanceof ApiError&&problem.code==='FEEDBACK_CONFLICT'){await load();if(context.current())setError('다른 변경이 반영되었습니다. 최신 평가를 확인한 뒤 다시 저장해 주세요.');}}
  finally{if(context.current()){lock.current=false;setBusy(false);setLoading(false);}}
 }
 const changed=!!data&&(rating!==data.rating||comment!==(data.comment??''));
 return <section className="response-feedback" aria-label="답변 평가">
  <p className="feedback-heading">이 답변이 도움이 되었나요?</p>
  {loading?<p role="status" className="muted">평가 확인 중</p>:data?<form onSubmit={e=>{e.preventDefault();void change();}}>
   <div className="feedback-actions"><button type="button" className="secondary small" aria-pressed={rating==='positive'} disabled={busy} onClick={()=>setRating('positive')}>도움 됐어요</button><button type="button" className="secondary small" aria-pressed={rating==='negative'} disabled={busy} onClick={()=>setRating('negative')}>아쉬워요</button></div>
   <label htmlFor={commentId}>평가 의견 (선택)</label><textarea id={commentId} value={comment} maxLength={1000} rows={2} disabled={busy||!rating} onChange={e=>setComment(e.target.value)} placeholder="개선 의견을 남겨 주세요."/>
   <p className="muted feedback-privacy">의견은 본인만 조회합니다. 관리자에게는 평가 집계만 제공합니다. {comment.length.toLocaleString()} / 1,000자</p>
   <div className="feedback-actions"><button className="secondary small" type="submit" disabled={busy||!rating||!changed}>평가 저장</button>{data.active&&<button className="quiet small" type="button" disabled={busy} onClick={()=>void change(true)}>평가 철회</button>}</div>
  </form>:<button className="secondary small" onClick={()=>void load()}>평가 다시 확인</button>}
  {error&&<p role="alert">{error}</p>}{notice&&<p role="status">{notice}</p>}
 </section>;
}
