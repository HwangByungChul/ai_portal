import {useState,useEffect,useRef} from 'react';
import {api} from './api';
import {useScope,modeLabel} from './scoped';
import type {Tenant,User,UseCaseItem,WorkflowExecutionRun,MeetingResult,MeetingDocument,MeetingEvidenceItem} from './types';

import {MeetingDocuments} from './MeetingDocuments';
import {MeetingQualityPanel} from './MeetingQualityPanel';
import './meeting.css';
export function UseCaseWorkspacePage({tenant,user}:{tenant:Tenant;user:User}){
 const scope=useScope(),options={tenantId:tenant.tenant_id,csrf:user.csrf_token,signal:scope.signal};
 const [agents,setAgents]=useState<UseCaseItem[]>([]),[selected,setSelected]=useState('AGENT_03');
 const [meetingDate,setMeetingDate]=useState(''),[documents,setDocuments]=useState<MeetingDocument[]>([]);
 const [category,setCategory]=useState('all');
 const [memo,setMemo]=useState(''),[run,setRun]=useState<WorkflowExecutionRun|null>(null);
 const [loading,setLoading]=useState(true),[busy,setBusy]=useState(false),[error,setError]=useState<string|null>(null);
 const request=useRef<{fingerprint:string;client:string}|null>(null);
 const agent=agents.find(a=>a.use_case_id===selected),active=Boolean(run&&!run.is_terminal);
 const states:Record<string,string>={accepted:'대기',running:'실행 중',completed:'완료',failed:'검증 또는 실행 실패',blocked:'권한·정책 차단',cancelled:'취소',interrupted:'중단 · 확인 필요'};
 async function fail(problem:unknown){const value=await scope.fail(problem,()=>{setRun(null);setAgents([]);setMemo('');setDocuments([]);setMeetingDate('');request.current=null;});if(scope.current())setError(value);}
 async function load(){
  setLoading(true);setError(null);
  try{const data=await api.request<{items:UseCaseItem[]}>('/use-cases',options);if(scope.current())setAgents(data.items);}
  catch(problem){await fail(problem);}finally{if(scope.current())setLoading(false);}
 }
 useEffect(()=>{setRun(null);setMemo('');setDocuments([]);setMeetingDate('');request.current=null;void load();},[tenant.tenant_id]);
 useEffect(()=>{
  if(!run||run.is_terminal)return;
  let current=true;let timer:ReturnType<typeof setTimeout>;
  async function poll(){
   try{const value=await api.request<WorkflowExecutionRun>('/use-cases/'+selected+'/runs/'+run!.run_id,options);
    if(current&&scope.current()){setRun(value);if(!value.is_terminal)timer=setTimeout(()=>void poll(),800);}}
   catch(problem){if(current)await fail(problem);}
  }
  timer=setTimeout(()=>void poll(),800);return()=>{current=false;clearTimeout(timer);};
 },[run?.run_id,run?.is_terminal,selected]);
 async function execute(){
  if(busy||active||!agent?.execution_ready||(!memo.trim()&&!documents.length))return;
  setBusy(true);setError(null);const prompt=memo;
  const payload={prompt,...(selected==='AGENT_03'?{meeting_date:meetingDate||null,document_refs:documents.map(d=>({document_id:d.document_id,version_id:d.version_id}))}: {})};
  const fingerprint=JSON.stringify({caseId:selected,...payload});
  if(request.current?.fingerprint!==fingerprint)request.current={fingerprint,client:crypto.randomUUID()};
  setRun(null);
  try{const value=await api.request<WorkflowExecutionRun>('/use-cases/'+selected+'/execute',{...options,method:'POST',body:{...payload,client_request_id:request.current!.client}});if(scope.current())setRun(value);}
  catch(problem){await fail(problem);}finally{if(scope.current())setBusy(false);}
 }
 async function cancel(){
  if(!run||busy)return;setBusy(true);setError(null);
  try{const value=await api.request<WorkflowExecutionRun>('/use-cases/'+selected+'/runs/'+run.run_id+'/cancel',{...options,method:'POST',body:{expected_revision:run.revision}});if(scope.current())setRun(value);}
  catch(problem){await fail(problem);if(scope.current()&&run){try{setRun(await api.request<WorkflowExecutionRun>('/use-cases/'+selected+'/runs/'+run.run_id,options));}catch(next){await fail(next);}}}
  finally{if(scope.current())setBusy(false);}
 }
 const categories:Record<string,string>={all:'전체',compliance:'규정·준법',document:'문서·기안',customer:'고객·VOC',finance:'금융·여신·외환',operation:'영업점 운영'};
 const visible=agents.filter(a=>category==='all'||a.category===category);
 const result=run?.result_access==='final'?run.result as MeetingResult:null;
 return <section className="admin-a-container meeting-workspace" style={{maxWidth:1440,margin:'0 auto',padding:24}}>
  <header><h1>10대 표준 업무 Agent 워크스페이스</h1><p>회의록 및 액션아이템 Agent를 우선 연결합니다. 나머지 9종은 추후 확장합니다.</p>
   <p role="status">업무 정의 {agents.length}종 · 현재 이용 가능 {agents.filter(a=>a.execution_ready).length}종</p></header>
  {error&&<p role="alert">{error}</p>}{loading&&<p>업무 Agent 확인 중</p>}
  <div role="group" aria-label="업무 분류" style={{display:'flex',gap:8,flexWrap:'wrap',marginBottom:16}}>{Object.entries(categories).map(([key,label])=><button key={key} type="button" className="secondary" disabled={busy||active} aria-pressed={category===key} onClick={()=>setCategory(key)}>{label} ({key==='all'?agents.length:agents.filter(a=>a.category===key).length})</button>)}</div>
  <div className="approval-layout"><nav className="approval-list" aria-label="업무 Agent 목록">
   {visible.map(a=><button key={a.use_case_id} type="button" className="approval-row" aria-pressed={selected===a.use_case_id} disabled={busy||active} onClick={()=>{setSelected(a.use_case_id);setMemo('');setMeetingDate('');setDocuments([]);setRun(null);setError(null);request.current=null;}}>
    <span>{a.use_case_id}</span><strong>{a.name}</strong><span>{a.execution_ready?'현재 이용 가능':a.use_case_id==='AGENT_03'?'승인·실행 연결 준비 필요':'추후 확장'}</span>{a.auto_decision_prohibited&&<span>자동확정 금지</span>}
   </button>)}
  </nav><section className="card approval-detail" aria-label="업무 실행 상세">
   {agent&&<><h2>{agent.name}</h2><p>{agent.description}</p>
    {agent.approved_version_id&&<p style={{overflowWrap:'anywhere'}}>승인 버전: {agent.approved_version_id}</p>}
    {agent.disclaimer&&<p role="note">{agent.disclaimer}</p>}
    {selected==='AGENT_03'&&<><label htmlFor="meeting-date">회의일 (선택 · 한국 업무 날짜)</label><input id="meeting-date" type="date" value={meetingDate} disabled={busy||active||!agent.execution_ready} onChange={e=>setMeetingDate(e.target.value)}/><p>오늘·내일은 입력한 회의일 기준입니다. 날짜가 없거나 모호한 기한은 미확정으로 남습니다.</p>{agent.execution_ready&&<MeetingDocuments key={tenant.tenant_id} tenant={tenant} user={user} selected={documents} onChange={setDocuments} disabled={busy||active}/>}</>}
    <label htmlFor="meeting-memo">{selected==='AGENT_03'?'회의 메모':'업무 질의'}</label>
    <textarea id="meeting-memo" rows={8} maxLength={4000} value={memo} disabled={busy||active||!agent.execution_ready} onChange={e=>setMemo(e.target.value)} style={{width:'100%'}}/>
    <p role="status">메모 {memo.length}/4000자 · 자료 {documents.reduce((n,d)=>n+d.character_length,0)}자 · 회의일 {meetingDate.length}자 · 합계 예비 계산 {memo.length+documents.reduce((n,d)=>n+d.character_length,0)+meetingDate.length}/4000자</p><p>서버 구분 문구가 추가됩니다. 최종 한도는 서버가 확인하며 초과 시 분량을 줄여야 합니다. 입력은 자동으로 잘리지 않습니다.</p>
    {!agent.execution_ready&&<p role="status">{selected==='AGENT_03'?'현재 조직의 승인된 회의록 Workflow와 이용 권한을 확인해 주세요.':'이 업무 Agent는 추후 확장 예정입니다.'}</p>}
    <button className="primary" disabled={busy||active||!agent.execution_ready||(!memo.trim()&&!documents.length)} onClick={()=>void execute()}>Agent 실행 및 초안 생성</button>
    {active&&<button className="secondary" disabled={busy} onClick={()=>void cancel()}>실행 취소</button>}
    {run&&<><p role="status">{states[run.state]} · {modeLabel(run.execution_mode)}</p><p style={{overflowWrap:'anywhere'}}>실행 번호: {run.run_id}</p>
     <p>봉인된 회의일: {run?.meeting_context?.meeting_date??(run?.meeting_context?'미입력':'과거 실행의 회의 정보 없음')}</p>{run?.meeting_context?.documents.map(d=><p key={d.version_id}>{d.current_available?d.title:'현재 원문 사용 불가'}<details><summary>정확한 출처 식별자</summary>{d.source_ref}</details></p>)}<ol>{run.steps.map(s=><li key={s.node_id}>{s.node_id} · {s.state}</li>)}</ol>
     {run.is_terminal&&!result&&<p>현재 승인·권한 또는 결과 검증 조건으로 최종 결과를 제공할 수 없습니다.</p>}</>}
    {result&&<><h3>원문 근거를 검사한 회의록 초안</h3><p>담당자가 내용의 의미와 후속 업무를 최종 확인해 주세요.</p>
     <h4>결정사항</h4>{result.decisions.map((item,i)=><article key={i}><p>{item.text}</p><Evidence item={item}/></article>)}
     <h4>미정 사항</h4>{result.unresolved.map((item,i)=><article key={i}><p>{item.text}</p><Evidence item={item}/></article>)}
     <h4>액션아이템</h4>{result.actions.map((item,i)=><article key={i}><p>{item.text}</p><p>담당자: {item.assignee??'미정'} · 기한: {item.due_date??'미확정'} · 원표현: {item.due_expression??'없음'} · 상태: {deadlineLabel(item.deadline_status,false)} · 사유: {deadlineLabel(item.deadline_reason,true)}</p><Evidence item={item}/></article>)}
     {run?.state==='completed'&&<MeetingQualityPanel key={tenant.tenant_id+run.run_id} tenant={tenant} user={user} runId={run.run_id}/>}
    </>}
   </>}
  </section></div>
 </section>;
}

const deadlineLabels:Record<string,string>={resolved:'확정',unresolved:'미확정',unspecified:'기한 언급 없음',past_due:'회의일 이전 기한',meeting_date_required:'회의일 필요',ambiguous_expression:'모호한 기한 표현',unsupported_expression:'지원하지 않는 기한 표현',expression_not_in_quote:'인용에서 기한 표현 확인 불가',invalid_calendar_date:'유효하지 않은 날짜',offset_out_of_bounds:'일수 범위 초과',calendar_out_of_bounds:'날짜 범위 초과',conflicting_expressions:'기한 표현 간 날짜 불일치'};
function deadlineLabel(value:string|null|undefined,reason:boolean){return value==null?(reason?'없음':'과거 정보 없음'):(deadlineLabels[value]??'확인 필요 (알 수 없는 기한 정보)');}
function Evidence({item}:{item:MeetingEvidenceItem}){const display=item.source_display;return <><p>출처: {item.source_ref==='memo'?'회의 메모':display?.title??'과거 출처 정보 없음'}{display&&<> · 버전 {display.version_id.slice(0,8)}{display.page_start!==undefined&&' · 페이지 '+display.page_start+(display.page_end!==undefined?'~'+display.page_end:'')}{display.structure_locations?.length?' · '+display.structure_locations.join(', '):''}{display.location_ambiguous?' · 동일 인용 위치가 여러 곳: 사람 확인 필요':''}</>}</p><details><summary>정확한 출처·버전 식별자</summary><p>{item.source_ref??'과거 출처 정보 없음'}</p>{display&&<p>버전: {display.version_id}</p>}</details><blockquote>{item.quote}</blockquote></>;}
