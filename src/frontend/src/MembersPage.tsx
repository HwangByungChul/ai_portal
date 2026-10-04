import { useEffect,useRef,useState } from 'react';
import { api,ApiError,isAbort } from './api';
import { session } from './session';
import type { Member,MemberPage,Role,Scope,Tenant,User } from './types';
import { roleName } from './types';
function MemberRow({member,tenant,user,busy,onActive,onRole}:{member:Member;tenant:Tenant;user:User;busy:boolean;onActive:(m:Member)=>void;onRole:(m:Member,role:'USER'|'TADMIN')=>void}){
 const [role,setRole]=useState<'USER'|'TADMIN'>(member.role==='TADMIN'?'TADMIN':'USER');
 const self=member.user_id===user.user_id;
 const allowed=!self&&member.role!=='PADMIN'&&(tenant.effective_role==='PADMIN'||member.role==='USER');
 const canRole=allowed&&tenant.effective_role==='PADMIN';
 return <tr data-user-id={member.user_id}><td><strong>{member.display_name}</strong>{self&&<span className="self-tag">본인</span>}</td>
  <td><span className="role-text">{roleName[member.role]}</span></td><td><span className={'status-pill '+(member.active?'active':'inactive')}>{member.active?'활성':'비활성'}</span></td>
  <td><div className="row-actions">{allowed?<button className="secondary small" disabled={busy} onClick={()=>onActive(member)}>{member.active?'비활성화':'활성화'}</button>:<span className="muted">변경 불가</span>}
  {canRole&&<div className="role-edit"><select aria-label="변경할 역할" value={role} disabled={busy} onChange={e=>setRole(e.target.value as 'USER'|'TADMIN')}><option value="USER">일반 사용자</option><option value="TADMIN">조직 관리자</option></select>
  <button className="secondary small" disabled={busy||role===member.role} onClick={()=>onRole(member,role)}>역할 저장</button></div>}</div></td></tr>;
}
export function MembersPage({tenant,user,generation}:{tenant:Tenant;user:User;generation:number}){
 const [items,setItems]=useState<Member[]>([]);const [cursor,setCursor]=useState<string|null>(null);const [loading,setLoading]=useState(true);
 const [saving,setSaving]=useState(false);const [error,setError]=useState<string|null>(null);const [success,setSuccess]=useState<string|null>(null);
 const scopeRef=useRef<Scope>(session.scope());const local=useRef<AbortController|null>(null);
 async function failure(problem:unknown,scope:Scope){
  if(isAbort(problem)||!session.current(scope))return;
  const e=problem instanceof ApiError?problem:new ApiError(0,'NETWORK');
  setItems([]);setCursor(null);setError(e.message);setSuccess(null);
  if(e.status===401)session.signedOut('세션이 만료되었습니다. 다시 로그인해 주세요.');
  else if(e.status===403)await session.restore(e.message+' 현재 권한을 다시 확인했습니다.');
 }
 async function load(next:string|null=null,append=false):Promise<boolean>{
  const scope=scopeRef.current;if(!session.current(scope))return false;
  local.current?.abort();const controller=new AbortController();local.current=controller;
  const abort=()=>controller.abort();scope.signal.addEventListener('abort',abort,{once:true});
  setLoading(true);if(!append){setItems([]);setCursor(null);}
  try{
   const query=next?'?cursor='+encodeURIComponent(next):'';
   const page=await api.request<MemberPage>('/admin/memberships'+query,{tenantId:tenant.tenant_id,signal:controller.signal});
   if(!session.current(scope)||controller.signal.aborted)return false;
   setItems(old=>append?[...old,...page.items]:page.items);setCursor(page.next_cursor);return true;
  }catch(problem){await failure(problem,scope);return false;}
  finally{scope.signal.removeEventListener('abort',abort);if(session.current(scope)&&!controller.signal.aborted)setLoading(false);}
 }
 useEffect(()=>{scopeRef.current=session.scope();void load();return()=>local.current?.abort();},[tenant.tenant_id,generation]);
 async function mutate(member:Member,role?:'USER'|'TADMIN'){
  if(saving||loading)return;const scope=scopeRef.current;setSaving(true);setError(null);setSuccess(null);
  try{
   await api.request<Member>('/admin/memberships/'+member.user_id+(role?'/role':''),{method:role?'PUT':'PATCH',tenantId:tenant.tenant_id,csrf:user.csrf_token,
    body:role?{role,expected_revision:member.revision}:{active:!member.active,expected_revision:member.revision},signal:scope.signal});
   if(!session.current(scope))return;
   const refreshed=await load();if(refreshed&&session.current(scope))setSuccess('저장되었습니다.');
  }catch(problem){
   if(problem instanceof ApiError&&problem.status===409&&session.current(scope)){setError(problem.message);await load();}
   else await failure(problem,scope);
  }finally{if(session.current(scope))setSaving(false);}
 }
 return <section className="members-panel" aria-labelledby="members-title"><div className="page-heading"><div><p className="eyebrow teal">ORGANIZATION</p><h1 id="members-title">사용자 관리</h1><p className="muted">{tenant.display_name}의 소속과 역할을 관리합니다.</p></div>
  <button className="secondary" disabled={loading||saving} onClick={()=>{setError(null);setSuccess(null);void load();}}>목록 새로고침</button></div>
  <p className="scope-note">조직의 소속 권한을 변경합니다. 계정 전체의 권한은 변경하지 않습니다.</p>
  {error&&<p role="alert" className="error-message">{error}</p>}{success&&<p role="status" className="notice">{success}</p>}
  {loading&&!items.length?<div role="status" className="loading-panel">사용자 목록 확인 중</div>:<div className="table-shell"><table><thead><tr><th>사용자</th><th>현재 역할</th><th>소속 상태</th><th>관리</th></tr></thead><tbody>
  {items.map(m=><MemberRow key={m.user_id+':'+m.revision} member={m} tenant={tenant} user={user} busy={saving||loading} onActive={m=>void mutate(m)} onRole={(m,role)=>void mutate(m,role)}/>)}</tbody></table>
  {!items.length&&!error&&<p className="empty-table">등록된 사용자가 없습니다.</p>}</div>}
  {saving&&<p role="status" className="muted">변경 내용 저장 중</p>}
  {cursor&&<button className="secondary load-more" disabled={loading||saving} onClick={()=>void load(cursor,true)}>{loading?'확인 중':'더 보기'}</button>}
 </section>;
}
