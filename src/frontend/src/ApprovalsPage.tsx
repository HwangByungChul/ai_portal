import {useEffect,useRef,useState} from 'react';
import {api,ApiError} from './api';
import {ToolApprovals} from './ToolApprovals';
import {WorkflowApprovals} from './WorkflowApprovals';
import {AssetDeployments} from './AssetDeployments';
import {SharedEvidenceReview} from './SharedEvidenceReview';
import {get,useScope} from './scoped';
import type {AgentDeployment,PageResult,Tenant,User,ApprovalKind} from './types';
export const deploymentStatus={pending:'승인 대기',approved:'승인·설정 반영 완료',rejected:'반려'} as const;
export function ApprovalsPage({tenant,user,initialId,initialKind='settings'}:{tenant:Tenant;user:User;initialId?:string;initialKind?:ApprovalKind}){
 const scope=useScope(),org=tenant.tenant_id;
 const [kind,setKind]=useState<ApprovalKind>(initialKind);
 const [items,setItems]=useState<AgentDeployment[]>([]),[cursor,setCursor]=useState<string|null>(null),[status,setStatus]=useState('pending'),[q,setQ]=useState('');
 const [selected,setSelected]=useState<string|null>(initialId??null),[detail,setDetail]=useState<AgentDeployment|null>(null),[tab,setTab]=useState<'validation'|'changes'|'history'>('validation');
 const [loading,setLoading]=useState(false),[detailLoading,setDetailLoading]=useState(false),[busy,setBusy]=useState(false),[error,setError]=useState<string|null>(null),[notice,setNotice]=useState<string|null>(null),[comment,setComment]=useState('');
 const [confirm,setConfirm]=useState<'approve'|'reject'|null>(null);
 const listVersion=useRef(0),detailVersion=useRef(0),lock=useRef(false),chosen=useRef(selected);
 async function fail(problem:unknown){const text=await scope.fail(problem,()=>{setItems([]);setDetail(null);setCursor(null);});if(scope.current())setError(text);}
 async function list(filter=status,next:string|null=null){const version=++listVersion.current;setLoading(true);setError(null);if(!next){setItems([]);setCursor(null);}
  const params=new URLSearchParams({limit:'20'});if(filter)params.set('status',filter);if(next)params.set('cursor',next);
  try{const page=await get<PageResult<AgentDeployment>>('/admin/agent-deployments?'+params,{tenantId:org,signal:scope.signal});if(scope.current()&&version===listVersion.current){setItems(old=>next?[...old,...page.items]:page.items);setCursor(page.next_cursor);}}
  catch(problem){if(version===listVersion.current){setItems([]);setCursor(null);await fail(problem);}}finally{if(scope.current()&&version===listVersion.current)setLoading(false);}
 }
 async function read(id:string){const version=++detailVersion.current;chosen.current=id;setSelected(id);setDetail(null);setDetailLoading(true);setConfirm(null);setError(null);
  try{const value=await get<AgentDeployment>('/admin/agent-deployments/'+id,{tenantId:org,signal:scope.signal});if(scope.current()&&version===detailVersion.current&&chosen.current===id)setDetail(value);}
  catch(problem){if(version===detailVersion.current)await fail(problem);}finally{if(scope.current()&&version===detailVersion.current)setDetailLoading(false);}
 }
 useEffect(()=>{if(kind==='settings'){void list();if(initialId&&initialKind==='settings')void read(initialId);}},[kind]);
 function choose(id:string){if(busy)return;setComment('');setNotice(null);setTab('validation');void read(id);}
 async function decide(){if(lock.current||!detail||!confirm||!comment.trim())return;lock.current=true;setBusy(true);setError(null);setNotice(null);
  const id=detail.request_id,decision=confirm;
  try{await api.request('/admin/agent-deployments/'+id+'/decision',{method:'POST',tenantId:org,csrf:user.csrf_token,signal:scope.signal,body:{decision,expected_revision:detail.revision,comment}});
   if(scope.current()){setNotice(decision==='approve'?'승인과 운영 설정 반영이 저장되었습니다. 운영 중지·사용 한도는 유지됩니다.':'반려 결과가 저장되었습니다.');await read(id);await list();}}
  catch(problem){await fail(problem);if(scope.current()&&problem instanceof ApiError&&[0,409,500,502,503,504].includes(problem.status)){await read(id);if(scope.current())setNotice('처리 결과를 다시 조회했습니다. 현재 상태와 의견을 확인한 뒤 판단해 주세요.');}}
  finally{if(scope.current()){setConfirm(null);lock.current=false;setBusy(false);}}
 }
 const shown=items.filter(item=>[item.proposed.name,item.agent_key,item.requester_id].some(text=>text.toLocaleLowerCase().includes(q.toLocaleLowerCase())));
 return <section aria-labelledby="approval-title"><div className="page-heading"><div><p className="eyebrow teal">DEPLOYMENT REVIEW</p><h1 id="approval-title">승인·검증</h1><p className="muted">{tenant.display_name} · AI 에이전트 배포 및 변경 요청 심사</p></div><button className="secondary small" disabled={kind!=='settings'||loading||busy} onClick={()=>{void list();if(selected)void read(selected);}}>요청 새로고침</button></div>
  <div className="approval-tabs-group" role="group" aria-label="요청 유형"><button className="approval-tab-btn" aria-pressed={kind==='settings'} disabled={busy} onClick={()=>setKind('settings')}>운영 설정 요청</button><button className="approval-tab-btn" aria-pressed={kind==='evidence'} disabled={busy} onClick={()=>setKind('evidence')}>Builder 시험 증적</button><button className="approval-tab-btn" aria-pressed={kind==='dynamic'} disabled={busy} onClick={()=>setKind('dynamic')}>동적 Agent 배포</button><button className="approval-tab-btn" aria-pressed={kind==='tool'} disabled={busy} onClick={()=>setKind('tool')}>Tool 승인</button><button className="approval-tab-btn" aria-pressed={kind==='workflow'} disabled={busy} onClick={()=>setKind('workflow')}>Workflow 승인</button></div>
  {kind==='tool'?<ToolApprovals tenant={tenant} user={user} initialId={initialKind==='tool'?initialId:undefined}/>:kind==='workflow'?<WorkflowApprovals tenant={tenant} user={user} initialId={initialKind==='workflow'?initialId:undefined}/>:kind==='dynamic'?<AssetDeployments key={initialId??'dynamic'} tenant={tenant} user={user} initialId={initialKind==='dynamic'?initialId:undefined}/>:kind==='evidence'?<SharedEvidenceReview tenant={tenant} user={user}/>:<>
  {error&&<p className="error-message" role="alert">{error}</p>}{notice&&<p role="status" className="notice">{notice}</p>}
  <div className="approval-layout"><section className="approval-list" aria-label="배포 요청 목록"><div className="approval-filters"><label htmlFor="deployment-status">요청 상태</label><select id="deployment-status" value={status} disabled={busy||loading} onChange={e=>{const next=e.target.value;setStatus(next);detailVersion.current++;chosen.current=null;setSelected(null);setDetail(null);setComment('');setNotice(null);void list(next);}}><option value="pending">승인 대기</option><option value="approved">승인 완료</option><option value="rejected">반려</option><option value="">전체</option></select><label htmlFor="deployment-query">불러온 요청 검색</label><input id="deployment-query" value={q} onChange={e=>setQ(e.target.value)} placeholder="요청명·Agent·요청자 ID"/></div>
   <p className="scope-note">검색은 불러온 요청에 적용됩니다. 더 보기로 다음 요청을 조회하세요.</p>{loading&&<p role="status">요청 목록 확인 중</p>}
   {shown.map(item=><button className="approval-row" key={item.request_id} aria-pressed={selected===item.request_id} disabled={busy} onClick={()=>choose(item.request_id)}><strong>{item.proposed.name}</strong><span>{deploymentStatus[item.status]} · 기반 버전 {item.base_version}</span><span>{new Date(item.created_at).toLocaleString('ko-KR')}</span></button>)}
   {!loading&&!shown.length&&<p className="card">조건에 맞는 배포 요청이 없습니다.</p>}{cursor&&<button className="secondary" disabled={loading||busy} onClick={()=>void list(status,cursor)}>요청 더 보기</button>}
  </section><section className="card approval-detail" aria-label="배포 요청 상세">
   {detailLoading?<p role="status">요청 상세 확인 중</p>:!detail?<p className="hub-empty">목록에서 검토할 요청을 선택하세요.</p>:<><p className="approval-status">{deploymentStatus[detail.status]}</p><h2>{detail.proposed.name}</h2><dl><dt>요청자</dt><dd>{detail.requester_id}</dd><dt>Agent · 기반 / 현재 운영 버전</dt><dd>{detail.agent_key} · {detail.base_version} / {detail.current_version}</dd><dt>변경 목적</dt><dd>{detail.reason}</dd></dl>
    <div className="approval-tabs-group" role="group" aria-label="상세 보기"><button type="button" className="approval-tab-btn" aria-pressed={tab==='validation'} onClick={()=>setTab('validation')}>검증 결과</button><button type="button" className="approval-tab-btn" aria-pressed={tab==='changes'} onClick={()=>setTab('changes')}>변경 사항</button><button type="button" className="approval-tab-btn" aria-pressed={tab==='history'} onClick={()=>setTab('history')}>처리 이력</button></div>
    {tab==='validation'&&<div><p>스키마 검사: 접수 시 이름·설명·지시문·변경 목적의 형식과 길이를 확인했습니다.</p><p>버전 검사: {detail.current_version===detail.base_version?'기반 버전 일치':'운영 버전 변경 · 이 요청은 승인할 수 없음'}</p><p>역할 검사: {detail.can_decide?'현재 승인 권한 확인됨':'현재 결정 권한 없음 또는 처리 완료'}</p><p className="scope-note">모델 품질·개인정보·보안 검토는 승인자가 별도로 확인해야 합니다. 이 조회만으로 심사 통과를 의미하지 않습니다.</p></div>}
    {tab==='changes'&&<div>{(['name','description','instructions'] as const).map(key=><section key={key}><h3>{({name:'이름',description:'설명',instructions:'기본 지시문'})[key]}</h3><p className="scope-note">요청 당시 설정</p><pre>{detail.previous?.[key]}</pre><p className="scope-note">배포 변경안</p><pre>{detail.proposed[key]}</pre></section>)}</div>}
    {tab==='history'&&<div><p>요청 접수: {new Date(detail.created_at).toLocaleString('ko-KR')}</p>{detail.decided_at&&<><p>결정: {new Date(detail.decided_at).toLocaleString('ko-KR')} · {detail.decided_by}</p><p>검토 의견: {detail.comment}</p>{detail.deployed_version&&<p>반영 버전: {detail.deployed_version}</p>}</>}</div>}
    {detail.can_decide&&<div className="operation-control"><label htmlFor="review-comment">검토 의견</label><textarea id="review-comment" value={comment} maxLength={500} rows={3} disabled={busy} onChange={e=>setComment(e.target.value)}/><div className="approval-actions"><button className="primary" disabled={busy||!comment.trim()||detail.current_version!==detail.base_version} onClick={()=>setConfirm('approve')}>배포 승인</button><button className="secondary" disabled={busy||!comment.trim()} onClick={()=>setConfirm('reject')}>반려</button></div>
     {confirm&&<div className="confirmation"><p>{confirm==='approve'?'이 변경안을 승인하고 현재 조직의 운영 설정에 반영합니다.':'이 요청을 반려합니다. 운영 설정은 유지됩니다.'}</p><button className="primary" disabled={busy} onClick={()=>void decide()}>검토 결정 저장</button><button className="secondary" disabled={busy} onClick={()=>setConfirm(null)}>돌아가기</button></div>}
    </div>}
   </>}
  </section></div>
 </> }
 </section>;
}
