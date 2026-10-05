import {useEffect,useRef,useState} from 'react';
import {api,ApiError} from './api';
import {blockReason,get,modeLabel,useRemote} from './scoped';
import type {Budget,Tenant,Usage,UsageItem,User} from './types';
export function UsageSummary({data}:{data:Pick<Usage,'execution_mode'|'estimated_accounted_krw'|'reserved_krw'|'unknown_count'>}){return <><p className="mode-tag">{modeLabel(data.execution_mode)}</p><div className="metric-grid"><div className="metric"><span>확인된 사용량의 추정 금액</span><strong>{data.estimated_accounted_krw} 원</strong></div><div className="metric"><span>유지 중인 예약 금액</span><strong>{data.reserved_krw} 원</strong></div><div className="metric"><span>사용량 확인 필요</span><strong>{data.unknown_count} 건</strong></div></div>{data.unknown_count>0&&<p className="blocked-note">사용량 확인 필요 · 예약 유지. 비용을 0원으로 확정하지 않습니다.</p>}<p className="scope-note">확인된 토큰을 기준으로 계산한 보수 추정 금액이며 공급자의 최종 청구액과 다를 수 있습니다. 실제·모의 집계는 구분됩니다.</p></>;}
function BudgetEditor({tenant,user}:{tenant:Tenant;user:User}){
 const remote=useRemote<Budget>('/admin/budget',tenant.tenant_id);const [local,setLocal]=useState(''),[allocation,setAllocation]=useState('');
 const [busy,setBusy]=useState(false),[notice,setNotice]=useState<string|null>(null);const lock=useRef(false);
 useEffect(()=>{if(remote.data){setLocal(remote.data.local_cap_krw.replace(/(\.\d*?)0+$/,'$1').replace(/\.$/,''));setAllocation(remote.data.allocated_cap_krw.replace(/(\.\d*?)0+$/,'$1').replace(/\.$/,''));}},[remote.data]);
 const money=(s:string)=>/^(0|[1-9][0-9]{0,8})(\.[0-9]{1,2})?$/.test(s)&&Number(s)<=25000;
 async function change(allocate=false){
  if(lock.current||!remote.data)return;lock.current=true;setBusy(true);setNotice(null);remote.setError(null);
  try{const value=await api.request<Budget>(allocate?'/platform/tenant-budgets/'+tenant.tenant_id:'/admin/budget',{method:'PUT',tenantId:tenant.tenant_id,csrf:user.csrf_token,signal:remote.signal,
   body:allocate?{allocated_cap_krw:allocation,expected_revision:remote.data.revision}:{local_cap_krw:local,expected_revision:remote.data.revision}});
   if(remote.current()){remote.setData(value);setNotice('한도가 저장되었습니다.');}
  }catch(problem){const message=await remote.fail(problem,()=>remote.setData(null));if(remote.current()){
   remote.setError(message);
   if(problem instanceof ApiError&&(problem.status===409||problem.status===0||problem.status>=500)){await remote.load();if(problem.status===0||problem.status>=500)remote.setError('변경 결과 확인 필요 · 현재 한도를 다시 읽었습니다.');}
  }}finally{if(remote.current()){lock.current=false;setBusy(false);}}
 }
 return <section className="card budget-editor"><div className="panel-heading"><h2>조직 사용 한도</h2><button className="secondary small" disabled={busy||remote.loading} onClick={()=>{remote.setError(null);setNotice(null);void remote.load();}}>한도 새로고침</button></div>
  {remote.error&&<p role="alert" className="error-message">{remote.error}</p>}{notice&&<p role="status" className="notice">{notice}</p>}
  {remote.loading?<p role="status">한도 확인 중</p>:remote.data&&<><p className="mode-tag">{modeLabel(remote.data.execution_mode)}</p><p>상위 배정 {remote.data.allocated_cap_krw} 원 · 조직 제한 {remote.data.local_cap_krw} 원</p>
   {remote.data.blocked&&<p className="blocked-note">{blockReason[remote.data.safe_block_reason??'']??'현재 호출 제한'}</p>}
   <form className="inline-form" onSubmit={e=>{e.preventDefault();void change();}}><label>조직 제한 금액 (원)<input value={local} inputMode="decimal" disabled={busy} onChange={e=>setLocal(e.target.value)}/></label><button className="primary" disabled={busy||!money(local)||Number(local)===Number(remote.data.local_cap_krw)}>조직 제한 저장</button></form>
   {tenant.effective_role==='PADMIN'&&tenant.can_manage&&<form className="inline-form" onSubmit={e=>{e.preventDefault();void change(true);}}><label>현재 조직 상위 배정 (원)<input value={allocation} inputMode="decimal" disabled={busy} onChange={e=>setAllocation(e.target.value)}/></label><button className="secondary" disabled={busy||!money(allocation)||Number(allocation)===Number(remote.data.allocated_cap_krw)}>상위 배정 저장</button></form>}
   <p className="scope-note">배정 이하에서 조직 제한을 설정합니다. 다른 조직의 배정과 기존 사용·예약 금액도 서버가 확인합니다.</p></>}
 </section>;
}
const operationName:Record<string,string>={generate_general:'일반 답변 생성',generation:'답변 생성',general_generation:'일반 답변 생성',document_embedding:'문서 임베딩',query_embedding:'질의 임베딩'};
const usageName:Record<string,string>={accounted:'사용량 확인됨',unknown:'사용량 확인 필요 · 예약 유지',pending:'사용량 대기',reserved:'예약 중',released:'예약 해제'};
export function UsagePage({tenant,user,admin=false}:{tenant:Tenant;user:User;admin?:boolean}){
 const remote=useRemote<Usage>(admin?'/admin/usage':'/usage/me',tenant.tenant_id);const [items,setItems]=useState<UsageItem[]>([]),[cursor,setCursor]=useState<string|null>(null);const [paging,setPaging]=useState(false);const pageLock=useRef(false);
 useEffect(()=>{if(remote.data&&admin){setItems(remote.data.items);setCursor(remote.data.next_cursor);}},[remote.data]);
 async function more(){if(pageLock.current||!cursor)return;pageLock.current=true;setPaging(true);try{const value=await get<Usage>('/admin/usage?cursor='+encodeURIComponent(cursor??''),{tenantId:tenant.tenant_id,signal:remote.signal});if(remote.current())remote.setData({...value,items:[...items,...value.items]});}catch(problem){const message=await remote.fail(problem,()=>{remote.setData(null);setItems([]);});if(remote.current())remote.setError(message);}finally{if(remote.current()){pageLock.current=false;setPaging(false);}}}
 return <section><div className="page-heading"><div><p className="eyebrow teal">USAGE</p><h1>{admin?'조직 사용량':'내 사용량'}</h1><p className="muted">{tenant.display_name} · {admin?'조직 전체의 최소 운영 정보':'본인의 호출만 집계합니다.'}</p></div><button className="secondary" disabled={remote.loading||paging} onClick={()=>{setItems([]);remote.setError(null);void remote.load();}}>사용량 새로고침</button></div>
  {remote.error&&<p role="alert" className="error-message">{remote.error}</p>}
  {remote.loading?<p role="status" className="loading-panel">사용량 확인 중</p>:remote.data&&<section className="card"><p className="scope-note">집계 기간 {remote.data.period} · 호출 {remote.data.call_count} 건</p><UsageSummary data={remote.data}/><p>확인된 토큰: {remote.data.known_tokens?.total_tokens??'확인 필요'}</p>
   {remote.data.blocked&&<p className="blocked-note">{blockReason[remote.data.safe_block_reason??'']??'현재 호출 제한'}</p>}
   {admin&&<div className="usage-items" aria-label="조직 호출 목록">{items.map(item=><article className="usage-item" key={item.call_id}><strong>{operationName[item.operation]??'AI 호출'}</strong><p>{modeLabel(item.execution_mode)}</p><p>{usageName[item.usage_status]??'호출 결과 확인 필요'} · 예약 {item.reserved_krw} 원</p><small>{new Date(item.created_at).toLocaleString('ko-KR')}</small></article>)}{!items.length&&<p className="muted">현재 기간의 호출 기록이 없습니다.</p>}{cursor&&<button className="secondary" disabled={paging} onClick={()=>void more()}>호출 더 보기</button>}</div>}
  </section>}
  {admin&&<BudgetEditor tenant={tenant} user={user}/>}
 </section>;
}
