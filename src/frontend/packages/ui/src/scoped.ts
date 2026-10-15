import {useEffect,useRef,useState} from 'react';
import {api,ApiError,isAbort,type RequestOptions} from '../../api-contract/src/api';
import {session} from '../../api-contract/src/session';
export const blockReason:Record<string,string>={AGENT_DISABLED:'Agent 운영 중지',FEATURE_NOT_READY:'문서 검색 준비 중',PROJECT_STOPPED:'플랫폼 운영 중지',TENANT_STOPPED:'조직 운영 중지',QUOTA_EXCEEDED:'사용 한도 도달',BUDGET_NOT_READY:'사용 한도 설정 필요',EXECUTION_NOT_READY:'실행 설정 필요',REVIEW_REQUIRED:'사용량 확인 필요'};
export function modeLabel(mode:string){return mode==='mock'?'모의 응답 · 실제 비용 아님':mode==='real'?'실제 모델 호출':'실행 모드 확인 필요';}
export function wait(ms:number,signal:AbortSignal):Promise<void>{return new Promise((resolve,reject)=>{
 if(signal.aborted){reject(new DOMException('Aborted','AbortError'));return;}
 const aborted=()=>{clearTimeout(timer);signal.removeEventListener('abort',aborted);reject(new DOMException('Aborted','AbortError'));};
 const timer=setTimeout(()=>{signal.removeEventListener('abort',aborted);resolve();},ms);signal.addEventListener('abort',aborted,{once:true});
});}
export async function get<T>(path:string,options:RequestOptions):Promise<T>{
 for(let attempt=0;;attempt++){
  try{return await api.request<T>(path,options);}catch(error){
   if(!(error instanceof ApiError)||![0,500,502,503,504].includes(error.status)||attempt>=2)throw error;
   await wait(attempt===0?1000:3000,options.signal??new AbortController().signal);
  }
 }
}
// Component lifetime complements the session generation: leaving a page also invalidates late bytes.
export function useScope(){
 const [context]=useState(()=>{const scope=session.scope();const local=new AbortController();
  return {scope,local,signal:AbortSignal.any([scope.signal,local.signal]),current:()=>!local.signal.aborted&&session.current(scope)};});
 useEffect(()=>()=>context.local.abort(),[context]);
 async function fail(problem:unknown,clear:()=>void):Promise<string|null>{
  if(isAbort(problem)||!context.current())return null;
  const error=problem instanceof ApiError?problem:new ApiError(0,'NETWORK');
  if(error.status===401){clear();session.signedOut('세션이 만료되었습니다. 다시 로그인해 주세요.');return null;}
  if(error.status===403){clear();await session.restore(error.message+' 현재 권한을 다시 확인했습니다.');return null;}
  return error.message+(error.requestId?' (문의 번호: '+error.requestId+')':'');
 }
 return {...context,fail};
}
export function useRemote<T>(path:string,tenantId?:string){
 const context=useScope();const [data,setData]=useState<T|null>(null);const [loading,setLoading]=useState(true);
 const [error,setError]=useState<string|null>(null);const query=useRef(0);
 async function load(next=path):Promise<T|null>{
  const version=++query.current;setLoading(true);setData(null);
  try{const value=await get<T>(next,{tenantId,signal:context.signal});
   if(!context.current()||version!==query.current)return null;setData(value);return value;
  }catch(problem){const message=await context.fail(problem,()=>setData(null));if(context.current()&&version===query.current)setError(message);return null;}
  finally{if(context.current()&&version===query.current)setLoading(false);}
 }
 useEffect(()=>{void load();},[]);
 return {...context,data,setData,loading,error,setError,load};
}
