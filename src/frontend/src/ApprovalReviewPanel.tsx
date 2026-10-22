import {useEffect,useRef,useState} from 'react';
import {api,ApiError} from './api';
import {get,useScope,modeLabel} from './scoped';
import type {ApprovalDetail,ApprovalPage,ReviewRequest,ToolApproval,WorkflowApproval,Tenant,User} from './types';
import {toolReviewLabel} from './toolReviewLabel';
const statusLabel={pending:'승인 대기',approved:'승인 완료',rejected:'반려'};
const isTool=(r:ReviewRequest):r is ToolApproval=>'tool_id' in r;
const idOf=(r:ReviewRequest)=>isTool(r)?r.request_id:r.version_id;
const nameOf=(r:ReviewRequest)=>isTool(r)?r.tool_id:r.definition.name;
const date=(s:string)=>new Date(s).toLocaleString('ko-KR');
function Value({value}:{value:unknown}){
 if(value===null||value===undefined)return <span className="muted">없음</span>;
 if(Array.isArray(value))return <ul>{value.map((v,i)=><li key={i}><Value value={v}/></li>)}</ul>;
 if(typeof value==='object')return <dl className="review-values">{Object.entries(value).map(([key,v])=><div key={key}><dt>{({node_id:'참조 노드',path:'결과 경로',values:'Agent 변수 연결',arguments:'Tool 인자',source:'출력 참조',asset_id:'게시 Agent',version_id:'정확한 버전',publication_revision:'게시 revision',node_type:'단계 유형',title:'단계 이름',config:'단계 계약',edges:'노드 연결',nodes:'노드 구성',source_node:'선행 노드',target_node:'후행 노드'} as Record<string,string>)[key]??key}</dt><dd><Value value={v}/></dd></div>)}</dl>;
 return <span>{String(value)}</span>;
}
export function WorkflowDiagram({request}:{request:WorkflowApproval}){
 return <><ol className="workflow-review-dag" aria-label="Workflow 노드 흐름">{request.definition.nodes.map(n=><li key={n.node_id}><strong>{n.title}</strong><span>{n.node_type} · {n.node_id}</span>{n.config.asset_id&&<p>게시 Agent {n.config.asset_id}<br/>정확한 버전 {n.config.version_id}<br/>게시 revision {n.config.publication_revision}</p>}{n.config.tool_id&&<p>허용 Tool {n.config.tool_id}</p>}<Value value={n.config.values??n.config.arguments??n.config.source??{입력:n.config.input_key}}/></li>)}</ol><p className="scope-note">연결: {request.definition.edges.map(e=>e.source_node+' → '+e.target_node).join(' / ')}</p></>;
}
export function ApprovalReviewPanel({kind,tenant,user,initialId}:{kind:'tool'|'workflow';tenant:Tenant;user:User;initialId?:string}){
 const scope=useScope(),org=tenant.tenant_id,base='/admin/'+kind+'-approvals';
 const [items,setItems]=useState<ReviewRequest[]>([]),[cursor,setCursor]=useState<string|null>(null),[pending,setPending]=useState<number|null>(null);
 const [status,setStatus]=useState(initialId?'':'pending'),[q,setQ]=useState(''),[search,setSearch]=useState('');
 const [selected,setSelected]=useState<string|null>(initialId??null),[detail,setDetail]=useState<ApprovalDetail|null>(null),[tab,setTab]=useState('validation');
 const [loading,setLoading]=useState(false),[reading,setReading]=useState(false),[busy,setBusy]=useState(false),[error,setError]=useState<string|null>(null),[notice,setNotice]=useState<string|null>(null),[comment,setComment]=useState(''),[confirm,setConfirm]=useState<'approve'|'reject'|'revoke'|null>(null);
 const listSeq=useRef(0),readSeq=useRef(0),chosen=useRef(selected),lock=useRef(false),focus=useRef<HTMLHeadingElement>(null),listFocus=useRef<HTMLHeadingElement>(null);
 async function fail(problem:unknown){const msg=await scope.fail(problem,()=>{setItems([]);setCursor(null);setDetail(null);setSelected(null);setComment('');setConfirm(null);});if(scope.current())setError(msg);}
 async function list(next:string|null=null,filter=status,query=search){const seq=++listSeq.current;setLoading(true);setError(null);if(!next){setItems([]);setCursor(null);setPending(null);}const params=new URLSearchParams({limit:'20'});if(filter)params.set('status',filter);if(query.trim())params.set('q',query.trim());if(next)params.set('cursor',next);
  try{const value=await get<ApprovalPage>(base+'?'+params,{tenantId:org,signal:scope.signal});if(scope.current()&&seq===listSeq.current){setItems(old=>next?[...old,...value.items]:value.items);setCursor(value.next_cursor);setPending(value.total_pending);}}
  catch(p){if(seq===listSeq.current)await fail(p);}finally{if(scope.current()&&seq===listSeq.current)setLoading(false);}}
 async function read(id:string){const seq=++readSeq.current;chosen.current=id;setSelected(id);setDetail(null);setReading(true);setConfirm(null);
  try{const value=await get<ApprovalDetail>(base+'/'+id,{tenantId:org,signal:scope.signal});if(scope.current()&&seq===readSeq.current&&chosen.current===id){setDetail(value);focus.current?.focus();}}
  catch(p){if(seq===readSeq.current)await fail(p);}finally{if(scope.current()&&seq===readSeq.current)setReading(false);}}
 useEffect(()=>{void list();if(initialId)void read(initialId);},[]);
 useEffect(()=>{if(detail)focus.current?.focus();},[detail]);
 useEffect(()=>{if(!selected)listFocus.current?.focus();},[selected]);
 function choose(id:string){if(lock.current)return;setError(null);setNotice(null);setComment('');setTab('validation');void read(id);}
 function back(){readSeq.current++;chosen.current=null;setSelected(null);setDetail(null);setConfirm(null);setComment('');listFocus.current?.focus();}
 function filter(value:string,query=search){back();setStatus(value);setSearch(query);void list(null,value,query);}
 async function mutate(){if(lock.current||!detail||!confirm||!validComment)return;lock.current=true;setBusy(true);setError(null);setNotice(null);const request=detail.request,id=idOf(request),action=confirm;
  const revoke=action==='revoke',target=revoke?(isTool(request)?'/admin/tools/'+request.tool_id+'/revoke':base+'/'+request.workflow_id+'/revoke'):base+'/'+id+'/decision';
  const expected=revoke?detail.current_head!.head_revision:isTool(request)?request.revision:request.decision_revision;
  try{await api.request(target,{method:'POST',tenantId:org,csrf:user.csrf_token,signal:scope.signal,body:{expected_revision:expected,comment:comment.trim(),...(!revoke?{decision:action}:{})}});if(scope.current()){setNotice(revoke?'현재 활성 승인이 철회되었습니다. 과거 승인 이력은 보존됩니다.':'검토 결정이 저장되었습니다.');setComment('');await read(id);await list();}}
  catch(p){await fail(p);if(scope.current()&&p instanceof ApiError&&[0,409,500,502,503,504].includes(p.status)){await read(id);await list();if(scope.current())setNotice('최신 처리 결과를 다시 조회했습니다. 남아 있는 의견과 현재 상태를 검토한 뒤 다시 결정하세요. 결정은 자동 재전송하지 않습니다.');}}
  finally{if(scope.current()){lock.current=false;setBusy(false);setConfirm(null);}}}
 const validComment=comment.trim().length>0&&Array.from(comment.trim()).length<=500&&!comment.includes('\0');
 return <><div className="panel-heading"><h2>{kind==='tool'?'Tool':'Workflow'} 승인 요청</h2><button className="secondary small" disabled={loading||reading||busy} onClick={()=>{void list();if(selected)void read(selected);}}>목록·상세 새로고침</button></div>
 {error&&<p role="alert" className="error-message">{error}</p>}{notice&&<p role="status" className="notice">{notice}</p>}
 <div className={'approval-layout review-layout '+(selected?'review-selected':'')}><section className="approval-list" aria-label="승인 요청 목록"><h3 ref={listFocus} tabIndex={-1}>요청 목록</h3><div className="approval-filters"><label>요청 상태<select value={status} disabled={busy} onChange={e=>filter(e.target.value)}><option value="pending">승인 대기</option><option value="approved">승인 완료</option><option value="rejected">반려</option><option value="">전체</option></select></label><form onSubmit={e=>{e.preventDefault();filter(status,q.trim());}}><label>요청 검색<input value={q} maxLength={120} disabled={busy} onChange={e=>setQ(e.target.value)} placeholder="서버 요청명·ID 검색"/></label><button className="secondary small" disabled={busy||loading}>검색</button></form></div><p className="scope-note">현재 조직 서버 검색 · 전체 대기 {pending===null?'조회 중':pending+'건'}</p>{loading&&<p role="status">목록 확인 중</p>}
 {items.map(item=><button key={idOf(item)} className="approval-row" aria-current={selected===idOf(item)?'true':undefined} aria-pressed={selected===idOf(item)} disabled={busy} onClick={()=>choose(idOf(item))}><strong>{nameOf(item)}</strong><span>{statusLabel[item.status]} · {isTool(item)?toolReviewLabel(item.descriptor):modeLabel(item.execution_mode)}</span><span>{date(item.created_at)}</span></button>)}{!loading&&!items.length&&<p>조건에 맞는 요청이 없습니다.</p>}{cursor&&<button className="secondary" disabled={loading||busy} onClick={()=>void list(cursor)}>요청 더 보기</button>}</section>
 <section className="card approval-detail" aria-label="승인 요청 상세">{selected&&<button className="secondary small review-back" disabled={busy} onClick={back}>목록으로 돌아가기</button>}{reading?<p role="status">상세 확인 중</p>:!detail?<p className="hub-empty">목록에서 검토할 요청을 선택하세요.</p>:<><p className="approval-status">{statusLabel[detail.request.status]}{detail.current_head&&idOf(detail.current_head)===idOf(detail.request)?' · 현재 head '+(detail.current_head.enabled?'활성':'철회됨'):''}</p><h2 ref={focus} tabIndex={-1}>{nameOf(detail.request)}</h2><dl className="review-values"><dt>요청자</dt><dd>{isTool(detail.request)?detail.request.requester_id:detail.request.created_by}</dd><dt>요청일</dt><dd>{date(detail.request.created_at)}</dd><dt>공개 대상</dt><dd>{detail.request.audience==='all'?'현재 조직 전체':detail.request.member_ids.join(', ')}</dd><dt>검토 가능 여부</dt><dd>{detail.decision_reason??(detail.can_approve?'현재 타인 승인 권한 확인됨':'현재 승인 불가 · 서버 정책 확인')}</dd></dl>
 <div className="approval-tabs-group" role="group" aria-label="상세 보기">{[['validation','검증 결과'],['changes','변경 사항'],['history','처리 이력']].map(([key,label])=><button className="approval-tab-btn" key={key} aria-pressed={tab===key} onClick={()=>setTab(key)}>{label}</button>)}</div>
 {tab==='validation'&&<><p>기술 검증: {detail.validation.valid?'현재 기술 조건 충족':'실패 또는 확인 불가'} · 조회 시점 {date(detail.validation.checked_at)}</p><ul>{detail.validation.checks.map(c=><li key={c.code}>{c.status==='pass'?'충족':c.status==='fail'?'실패':'확인 불가'} · {c.message}</li>)}</ul><p className="scope-note">기술·스키마 조건 충족은 품질·보안·업무 정확성 심사 통과가 아닙니다. 실제 기관 connector 연결은 별도 확인해야 합니다.</p>
 {isTool(detail.request) ? (
   detail.request.descriptor.approval_scope === 'registration_review_only' ? (
    <div>
     <p>동적 Tool 등록 검토 · revision {detail.request.descriptor.revision_number} · 보수적 고위험 분류</p>
     <dl className="review-values"><dt>위험 등급</dt><dd>{detail.request.descriptor.risk_class==='financial_side_effect'?'금융 부작용 가능성(보수적 기본값)':detail.request.descriptor.risk_class??'분류 확인 필요'}</dd><dt>분류 근거</dt><dd>{detail.request.descriptor.risk_reason??'분류 근거 없음'}</dd><dt>정책</dt><dd>{detail.request.descriptor.risk_policy_id??'정책 식별자 없음'} · revision {detail.request.descriptor.risk_policy_revision??'미기록'} · 데이터 등급 {detail.request.descriptor.data_classification??'미분류'}</dd><dt>승인 범위</dt><dd>등록 검토 요청만 접수 · PADMIN 결정 차단</dd></dl>
     <p role="note">현재 connector의 읽기 전용 여부와 부작용을 서버가 증명하지 못해 동적 Tool을 보수적으로 고위험 분류했습니다. 등록 검토는 접수되지만, 별도 exact revision 승인·게시·실행 gate가 구현되기 전까지 PADMIN 승인도 차단됩니다.</p>
     <h3>입력 스키마</h3><Value value={detail.request.descriptor.input_schema}/>
    </div>
   ) : (
    <div>
     <p>{toolReviewLabel(detail.request.descriptor)} · {modeLabel(detail.request.descriptor.mode)} · 제한 시간 {detail.request.descriptor.timeout_seconds}초</p>
     <h3>허용 인자 스키마</h3><Value value={detail.request.descriptor.arg_schema}/>
    </div>
   )
  ) : (
   <div>
    <p>{detail.request.definition.description} · 정의 v{detail.request.revision} · {modeLabel(detail.request.execution_mode)}</p>
    {detail.request.use_case_id&&<p>업무 {detail.request.use_case_id} · 자동 결정 금지 · 사람의 검토 필수</p>}
    <WorkflowDiagram request={detail.request}/>
    {detail.request.manifest_snapshot&&<details><summary>서버 업무 계약</summary><Value value={detail.request.manifest_snapshot}/></details>}
   </div>
  )}
  <details><summary>정확한 버전 기술 상세</summary><p>{isTool(detail.request)?detail.request.descriptor.digest:detail.request.version_digest}</p></details></>}
 {tab==='changes'&&<><p>{detail.diff.baseline_available?'현재 head와 신청 버전 비교':'현재 head 없음 · 최초 신청'}</p>{detail.diff.changes.map((c,i)=><section className="review-change" key={c.field+i}><h3>{c.field}</h3><div className="review-comparison"><div><h4>현재 승인</h4><Value value={c.before}/></div><div><h4>신청 변경</h4><Value value={c.after}/></div></div></section>)}{!detail.diff.changes.length&&<p>비교에서 확인된 변경 사항 없음</p>}</>}
 {tab==='history'&&<ol className="review-history">{detail.history.map((h,i)=><li key={i}><strong>{({submit:'신청',approve:'승인',reject:'반려',revoke:'활성 head 철회'} as Record<string,string>)[h.action]??h.action}</strong> · {date(h.created_at)}<p>{h.actor_id} · revision {h.revision??'미기록'}</p><p>검토 의견: {h.comment??'과거 기록 · 의견 없음'}</p></li>)}</ol>}
 {(detail.can_approve||detail.can_reject||detail.can_revoke)&&<div className="operation-control"><label htmlFor={kind+'-review-comment'}>검토 의견 (필수 · 500자 이내)</label><textarea id={kind+'-review-comment'} rows={4} value={comment} disabled={busy} onChange={e=>{setComment(e.target.value);setConfirm(null);}}/><div className="approval-actions">{detail.request.status==='pending'&&<><button className="primary" disabled={busy||!validComment||!detail.can_approve||!detail.validation.valid} onClick={()=>setConfirm('approve')}>승인</button><button className="secondary" disabled={busy||!validComment||!detail.can_reject} onClick={()=>setConfirm('reject')}>반려</button></>}{detail.can_revoke&&<button className="secondary" disabled={busy||!validComment} onClick={()=>setConfirm('revoke')}>현재 활성 승인 철회</button>}</div>{confirm&&<div className="confirmation" role="region" aria-label="검토 결정 확인"><p>{confirm==='revoke'?'신규 실행과 이후 진행 단계의 이용이 차단될 수 있습니다. 이미 실행된 비용과 완료 정산, 과거 승인 이력은 보존됩니다.':confirm==='approve'?'타인의 요청을 승인하고 현재 head에 반영합니다.':'이 요청을 반려합니다.'}</p><p>검토 의견: {comment.trim()}</p><button className="primary" disabled={busy||!validComment} onClick={()=>void mutate()}>검토 결정 저장</button><button className="secondary" disabled={busy} onClick={()=>setConfirm(null)}>돌아가기</button></div>}</div>}
 </>}</section></div></>;
}
