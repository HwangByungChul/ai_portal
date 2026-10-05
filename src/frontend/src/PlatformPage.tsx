import {useEffect,useRef,useState} from 'react';
import {api,ApiError} from './api';
import {get,useScope} from './scoped';
import {session} from './session';
import {UsageSummary} from './UsagePage';
import type {PlatformSummary,User} from './types';
export function PlatformPage({user}:{user:User}){
 const context=useScope();const [me,setMe]=useState<User|null>(user),[summary,setSummary]=useState<PlatformSummary|null>(null);
 const [availability,setAvailability]=useState(user.platform_availability??null),[error,setError]=useState<string|null>(null),[notice,setNotice]=useState<string|null>(null);
 const [loading,setLoading]=useState(true),[busy,setBusy]=useState(false),[confirm,setConfirm]=useState(false);const lock=useRef(false);
 function clear(){setMe(null);setSummary(null);setAvailability(null);setConfirm(false);}
 async function load(){
  setLoading(true);clear();
  try{const current=await get<User>('/auth/me',{signal:context.signal});if(!context.current())return;if(!current.capabilities.can_view_platform_usage&&!current.capabilities.can_change_platform_availability){await session.restore('현재 플랫폼 운영 권한을 다시 확인했습니다.');return;}setMe(current);setAvailability(current.platform_availability??null);
   if(current.capabilities.can_view_platform_usage){const value=await get<PlatformSummary>('/platform/summary',{signal:context.signal});if(context.current()){setSummary(value);if(current.capabilities.can_change_platform_availability)setAvailability({enabled:value.enabled,revision:value.revision});}}
  }catch(problem){const message=await context.fail(problem,clear);if(context.current())setError(message);}
  finally{if(context.current())setLoading(false);}
 }
 useEffect(()=>{void load();},[]);
 async function change(){
  if(lock.current||!availability||!me?.capabilities.can_change_platform_availability)return;lock.current=true;setBusy(true);setError(null);setNotice(null);
  try{await api.request('/platform/availability',{method:'PUT',csrf:me.csrf_token,signal:context.signal,body:{enabled:!availability.enabled,expected_revision:availability.revision}});
   if(context.current()){setConfirm(false);await load();if(context.current())setNotice('운영 상태가 저장되었습니다.');}
  }catch(problem){const message=await context.fail(problem,clear);if(context.current()){
   setConfirm(false);setError(message);if(problem instanceof ApiError&&(problem.status===409||problem.status===0||problem.status>=500)){await load();if(problem.status===0||problem.status>=500)setError('변경 결과 확인 필요 · 현재 운영 상태를 다시 읽었습니다.');}
  }}finally{if(context.current()){setBusy(false);lock.current=false;}}
 }
 return <section><div className="page-heading"><div><p className="eyebrow teal">PLATFORM OPERATIONS</p><h1>플랫폼 운영</h1><p className="muted">프로젝트 전체 · 조직별 본문을 제공하지 않습니다.</p></div><button className="secondary" disabled={loading||busy} onClick={()=>{setError(null);setNotice(null);void load();}}>운영 상태 새로고침</button></div>
  {error&&<p role="alert" className="error-message">{error}</p>}{notice&&<p role="status" className="notice">{notice}</p>}
  {loading?<p role="status">프로젝트 운영 상태 확인 중</p>:<>
   {summary&&me?.capabilities.can_view_platform_usage&&<section className="card"><UsageSummary data={summary}/><p>승인 한도 {summary.approved_cap_krw} 원 · 운영 상한 {summary.operational_cap_krw} 원</p><p>전체 조직 배정 {summary.allocated_total_krw} 원</p><p className="scope-note">운영 상한 내에서만 호출을 허가합니다. 여유 금액을 자동으로 투입하지 않습니다.</p></section>}
   {(availability||summary)&&<section className="card"><h2>공통 운영 상태</h2><p className="run-status">{(availability??summary)?.enabled?'운영 허용':'프로젝트 전체 운영 중지'}</p>
    {availability&&me?.capabilities.can_change_platform_availability&&<><button className="quiet" disabled={busy} onClick={()=>setConfirm(true)}>{availability.enabled?'프로젝트 전체 중지':'프로젝트 전체 재개'}</button>
     {confirm&&<div className="confirmation"><p>프로젝트 전체의 신규·후속 AI 호출을 {availability.enabled?'중지':'재개'}합니다. 기존 사용·예약 금액과 각 조직의 Agent·한도는 별도입니다.</p><button className="primary" disabled={busy} onClick={()=>void change()}>프로젝트 운영 변경 확인</button><button className="secondary" disabled={busy} onClick={()=>setConfirm(false)}>돌아가기</button></div>}</>}
   </section>}
   {!me?.capabilities.can_view_platform_usage&&!me?.capabilities.can_change_platform_availability&&<p role="alert">현재 플랫폼 운영 권한이 없습니다.</p>}
  </>}
 </section>;
}
