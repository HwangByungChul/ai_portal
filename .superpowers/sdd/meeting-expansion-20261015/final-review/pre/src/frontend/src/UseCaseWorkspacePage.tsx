import {useState,useEffect,useRef} from 'react';
import {api} from './api';
import {useScope,modeLabel} from './scoped';
import type {Tenant,User,UseCaseItem,WorkflowExecutionRun,MeetingResult} from './types';

export function UseCaseWorkspacePage({tenant,user}:{tenant:Tenant;user:User}){
 const scope=useScope(),options={tenantId:tenant.tenant_id,csrf:user.csrf_token,signal:scope.signal};
 const [agents,setAgents]=useState<UseCaseItem[]>([]),[selected,setSelected]=useState('AGENT_03');
 const [category,setCategory]=useState('all');
 const [memo,setMemo]=useState(''),[run,setRun]=useState<WorkflowExecutionRun|null>(null);
 const [loading,setLoading]=useState(true),[busy,setBusy]=useState(false),[error,setError]=useState<string|null>(null);
 const request=useRef<{caseId:string;memo:string;client:string}|null>(null);
 const agent=agents.find(a=>a.use_case_id===selected),active=Boolean(run&&!run.is_terminal);
 const states:Record<string,string>={accepted:'대기',running:'실행 중',completed:'완료',failed:'검증 또는 실행 실패',blocked:'권한·정책 차단',cancelled:'취소',interrupted:'중단 · 확인 필요'};
 async function fail(problem:unknown){const value=await scope.fail(problem,()=>{setRun(null);setAgents([]);setMemo('');});if(scope.current())setError(value);}
 async function load(){
  setLoading(true);setError(null);
  try{const data=await api.request<{items:UseCaseItem[]}>('/use-cases',options);if(scope.current())setAgents(data.items);}
  catch(problem){await fail(problem);}finally{if(scope.current())setLoading(false);}
 }
 useEffect(()=>{setRun(null);setMemo('');request.current=null;void load();},[tenant.tenant_id]);
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
  if(busy||active||!agent?.execution_ready||!memo.trim())return;
  setBusy(true);setError(null);const prompt=memo.trim();
  if(run?.is_terminal||request.current?.caseId!==selected||request.current?.memo!==prompt)request.current={caseId:selected,memo:prompt,client:crypto.randomUUID()};
  setRun(null);
  try{const value=await api.request<WorkflowExecutionRun>('/use-cases/'+selected+'/execute',{...options,method:'POST',body:{prompt,client_request_id:request.current!.client}});if(scope.current())setRun(value);}
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
 return <section className="admin-a-container" style={{maxWidth:1440,margin:'0 auto',padding:24}}>
  <header><h1>10대 표준 업무 Agent 워크스페이스</h1><p>회의록 및 액션아이템 Agent를 우선 연결합니다. 나머지 9종은 추후 확장합니다.</p>
   <p role="status">업무 정의 {agents.length}종 · 현재 이용 가능 {agents.filter(a=>a.execution_ready).length}종</p></header>
  {error&&<p role="alert">{error}</p>}{loading&&<p>업무 Agent 확인 중</p>}
  <div role="group" aria-label="업무 분류" style={{display:'flex',gap:8,flexWrap:'wrap',marginBottom:16}}>{Object.entries(categories).map(([key,label])=><button key={key} type="button" className="secondary" disabled={busy||active} aria-pressed={category===key} onClick={()=>setCategory(key)}>{label} ({key==='all'?agents.length:agents.filter(a=>a.category===key).length})</button>)}</div>
  <div className="approval-layout"><nav className="approval-list" aria-label="업무 Agent 목록">
   {visible.map(a=><button key={a.use_case_id} type="button" className="approval-row" aria-pressed={selected===a.use_case_id} disabled={busy||active} onClick={()=>{setSelected(a.use_case_id);setMemo('');setRun(null);setError(null);request.current=null;}}>
    <span>{a.use_case_id}</span><strong>{a.name}</strong><span>{a.execution_ready?'현재 이용 가능':a.use_case_id==='AGENT_03'?'승인·실행 연결 준비 필요':'추후 확장'}</span>{a.auto_decision_prohibited&&<span>자동확정 금지</span>}
   </button>)}
  </nav><section className="card approval-detail" aria-label="업무 실행 상세">
   {agent&&<><h2>{agent.name}</h2><p>{agent.description}</p>
    {agent.approved_version_id&&<p style={{overflowWrap:'anywhere'}}>승인 버전: {agent.approved_version_id}</p>}
    {agent.disclaimer&&<p role="note">{agent.disclaimer}</p>}
    <label htmlFor="meeting-memo">{selected==='AGENT_03'?'회의 메모':'업무 질의'}</label>
    <textarea id="meeting-memo" rows={8} maxLength={4000} value={memo} disabled={busy||active||!agent.execution_ready} onChange={e=>setMemo(e.target.value)} style={{width:'100%'}}/>
    {!agent.execution_ready&&<p role="status">{selected==='AGENT_03'?'현재 조직의 승인된 회의록 Workflow와 이용 권한을 확인해 주세요.':'이 업무 Agent는 추후 확장 예정입니다.'}</p>}
    <button className="primary" disabled={busy||active||!agent.execution_ready||!memo.trim()} onClick={()=>void execute()}>Agent 실행 및 초안 생성</button>
    {active&&<button className="secondary" disabled={busy} onClick={()=>void cancel()}>실행 취소</button>}
    {run&&<><p role="status">{states[run.state]} · {modeLabel(run.execution_mode)}</p><p style={{overflowWrap:'anywhere'}}>실행 번호: {run.run_id}</p>
     <ol>{run.steps.map(s=><li key={s.node_id}>{s.node_id} · {s.state}</li>)}</ol>
     {run.is_terminal&&!result&&<p>현재 승인·권한 또는 결과 검증 조건으로 최종 결과를 제공할 수 없습니다.</p>}</>}
    {result&&<><h3>검증된 회의록 초안</h3><p>담당자가 내용의 의미와 후속 업무를 최종 확인해 주세요.</p>
     <h4>결정사항</h4>{result.decisions.map((item,i)=><article key={i}><p>{item.text}</p><blockquote>{item.quote}</blockquote></article>)}
     <h4>미정 사항</h4>{result.unresolved.map((item,i)=><article key={i}><p>{item.text}</p><blockquote>{item.quote}</blockquote></article>)}
     <h4>액션아이템</h4>{result.actions.map((item,i)=><article key={i}><p>{item.text}</p><p>담당자: {item.assignee??'미정'} · 기한: {item.due_date??'미정'}</p><blockquote>{item.quote}</blockquote></article>)}
    </>}
   </>}
  </section></div>
 </section>;
}
