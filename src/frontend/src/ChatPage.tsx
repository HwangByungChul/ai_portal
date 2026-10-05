import {useEffect,useRef,useState} from 'react';
import {api,ApiError,isAbort} from './api';
import {blockReason,get,modeLabel,useScope,wait} from './scoped';
import {subscribe} from './stream';
import type {AgentKey,AgentSummary,Conversation,Message,PageResult,Run,Tenant,User} from './types';
type Submission={client_send_id:string;agent_key:AgentKey;prompt:string;conversation_id?:string};
const stateName:Record<string,string>={queued:'접수됨',running:'답변 작성 중',cancel_requested:'취소 요청됨 · 결과 확인 중',completed:'완료 · 저장 확인됨',cancelled:'취소됨',failed:'처리 실패',blocked:'현재 처리할 수 없음',interrupted:'처리가 중단됨'};
export function ChatPage({tenant,user}:{tenant:Tenant;user:User}){
 const context=useScope();const org=tenant.tenant_id;
 const [agents,setAgents]=useState<AgentSummary[]>([]);const [agent,setAgent]=useState<AgentKey>('general');
 const [conversations,setConversations]=useState<Conversation[]>([]);const [conversationCursor,setConversationCursor]=useState<string|null>(null);
 const [selected,setSelected]=useState<string|null>(null);const [messages,setMessages]=useState<Message[]>([]);const [messageCursor,setMessageCursor]=useState<string|null>(null);
 const [prompt,setPrompt]=useState('');const [run,setRun]=useState<Run|null>(null);const [draft,setDraft]=useState('');
 const [error,setError]=useState<string|null>(null);const [notice,setNotice]=useState<string|null>(null);const [loading,setLoading]=useState(true);
 const [historyOpen,setHistoryOpen]=useState(false);const [sending,setSending]=useState(false);const [unresolved,setUnresolved]=useState(false);const [cancelling,setCancelling]=useState(false);
 const lock=useRef(false);const pending=useRef<Submission|null>(null);const selection=useRef(0);const listQuery=useRef(0);const chosen=useRef<string|null>(null);
 const currentRun=useRef<Run|null>(null);
 const active=agents.find(a=>a.agent_key===agent);const busy=!!run&&!run.is_terminal;
 function publishRun(value:Run){
  if(!context.current()||value.tenant_id!==org)return;
  const prior=currentRun.current;if(prior?.run_id===value.run_id&&prior.revision>value.revision)return;
  currentRun.current=value;setRun(value);
 }
 function clear(){setMessages([]);setConversations([]);setAgents([]);currentRun.current=null;setRun(null);setDraft('');setPrompt('');pending.current=null;}
 async function failed(problem:unknown){const message=await context.fail(problem,clear);if(context.current())setError(message);}
 async function list(next:string|null=null){
  const version=++listQuery.current;
  try{const page=await get<PageResult<Conversation>>('/conversations'+(next?'?cursor='+encodeURIComponent(next):''),{tenantId:org,signal:context.signal});
   if(context.current()&&version===listQuery.current){setConversations(old=>next?[...old,...page.items]:page.items);setConversationCursor(page.next_cursor);}
  }catch(problem){await failed(problem);}
 }
 async function history(id:string,next:string|null=null,version=selection.current):Promise<Message[]|null>{
  try{const page=await get<PageResult<Message>>('/conversations/'+id+'/messages'+(next?'?cursor='+encodeURIComponent(next):''),{tenantId:org,signal:context.signal});
   if(!context.current()||version!==selection.current||chosen.current!==id)return null;
   setMessages(old=>next?[...old,...page.items]:page.items);setMessageCursor(page.next_cursor);return page.items;
  }catch(problem){if(context.current()&&version===selection.current){setMessages([]);setMessageCursor(null);await failed(problem);}return null;}
 }
 async function initialize(){
  setLoading(true);setError(null);
  try{const value=await get<{items:AgentSummary[]}>('/agents',{tenantId:org,signal:context.signal});if(context.current())setAgents(value.items);}
  catch(problem){await failed(problem);}
  await list();if(context.current())setLoading(false);
 }
 useEffect(()=>{void initialize();},[]);
 function fresh(){selection.current++;chosen.current=null;setSelected(null);setMessages([]);setMessageCursor(null);currentRun.current=null;setRun(null);setDraft('');setError(null);setNotice(null);setPrompt('');}
 async function choose(conversation:Conversation){
  if(lock.current||unresolved)return;
  const version=++selection.current;chosen.current=conversation.conversation_id;
  setSelected(conversation.conversation_id);setAgent(conversation.agent_key);setMessages([]);currentRun.current=null;setRun(null);setDraft('');setPrompt('');setError(null);setNotice(null);
  const items=await history(conversation.conversation_id,null,version);const last=items?.at(-1);
  if(last&&context.current()&&version===selection.current){
   try{const value=await get<Run>('/runs/'+last.run_id,{tenantId:org,signal:context.signal});
    if(context.current()&&version===selection.current&&value.tenant_id===org)publishRun(value);
   }catch(problem){if(version===selection.current)await failed(problem);}
  }
 }
 function accept(value:Run){
  if(!context.current()||value.tenant_id!==org)throw new ApiError(503,'SCOPE_CHANGED');
  chosen.current=value.conversation_id;setSelected(value.conversation_id);publishRun(value);setPrompt('');setDraft('');
  pending.current=null;setUnresolved(false);setNotice(null);void history(value.conversation_id);void list();
 }
 async function recover(payload:Submission,allowReplay:boolean){
  try{const value=await get<Run>('/runs/by-send/'+payload.client_send_id,{tenantId:org,signal:context.signal});accept(value);}
  catch(problem){
   if(problem instanceof ApiError&&problem.status===404&&allowReplay){
    try{accept(await api.request<Run>('/runs',{method:'POST',tenantId:org,csrf:user.csrf_token,body:payload,signal:context.signal}));return;}
    catch(retryError){
     if(retryError instanceof ApiError&&retryError.status>0&&retryError.status<500){pending.current=null;setUnresolved(false);await failed(retryError);return;}
     await failed(retryError);
    }
   }else await failed(problem);
   if(context.current()){setUnresolved(true);setNotice('접수 상태 확인 필요 · 추가 질문 전송을 보류했습니다. 접수 상태만 다시 확인해 주세요.');}
  }
 }
 async function send(){
  if(lock.current||busy||unresolved||!active?.available||!prompt.trim())return;
  if(prompt.length>4000||new TextEncoder().encode(prompt).byteLength>16384){setError('질문은 4,000자와 16KB 이내로 입력해 주세요.');return;}
  lock.current=true;setSending(true);setError(null);setNotice(null);selection.current++;
  const payload:Submission={client_send_id:crypto.randomUUID(),agent_key:agent,prompt,...(selected?{conversation_id:selected}:{})};pending.current=payload;
  try{accept(await api.request<Run>('/runs',{method:'POST',tenantId:org,csrf:user.csrf_token,body:payload,signal:context.signal}));}
  catch(problem){
   if(problem instanceof ApiError&&(problem.status===0||problem.status>=500)){await recover(payload,true);}
   else{pending.current=null;await failed(problem);void initialize();}
  }finally{if(context.current()){lock.current=false;setSending(false);}}
 }
 async function confirmAdmission(){
  if(lock.current||!pending.current)return;lock.current=true;setSending(true);setError(null);
  try{await recover(pending.current,false);}finally{if(context.current()){lock.current=false;setSending(false);}}
 }
 useEffect(()=>{
  if(!run||run.is_terminal)return;
  const id=run.run_id,conversationId=run.conversation_id,version=selection.current;
  const controller=new AbortController();const signal=AbortSignal.any([context.signal,controller.signal]);let done=false,querying=false,draftSequence=0;
  const valid=()=>context.current()&&!signal.aborted&&selection.current===version&&currentRun.current?.run_id===id;
  async function reconcile(){
   if(!valid()||querying||document.visibilityState!=='visible')return;
   querying=true;
   try{const value=await get<Run>('/runs/'+id,{tenantId:org,signal});
    if(!valid())return;if(value.tenant_id!==org||value.run_id!==id)throw new ApiError(503,'SCOPE_CHANGED');
    const prior=currentRun.current;if(prior&&value.revision<prior.revision)return;
    currentRun.current=value;publishRun(value);
    if(value.is_terminal){done=true;setDraft('');setNotice(null);controller.abort();await history(conversationId,null,version);void list();}
   }catch(problem){if(valid()){setNotice('연결 또는 저장 상태 확인 필요');await failed(problem);}}
   finally{querying=false;}
  }
  const hidden=()=>{if(document.visibilityState!=='visible')controller.abort();};document.addEventListener('visibilitychange',hidden);
  void subscribe(id,org,signal,event=>{
   if(!valid())return;
   if(event.event==='draft_delta'){
    const sequence=event.data.draft_sequence as number;
    if(sequence<=draftSequence)return;draftSequence=sequence;setDraft(event.data.text as string);
   }else if(event.event==='terminal'||event.event==='delivery_error'){setDraft('');void reconcile();}
   // All persisted status/body updates use the current-authority GET, including snapshot.
  }).then(()=>{if(valid()&&!done){setDraft('');setNotice('연결 종료 · 저장 상태를 확인하고 있습니다.');void reconcile();}})
   .catch(async problem=>{if(valid()&&!isAbort(problem)){setDraft('');setNotice('실시간 연결 확인 필요 · 저장 상태를 조회합니다.');if(problem instanceof ApiError&&[401,403].includes(problem.status))await failed(problem);else void reconcile();}});
  void (async()=>{try{while(valid()&&!done){await reconcile();if(!done)await wait(2000,signal);}}catch(problem){if(!isAbort(problem)&&valid())await failed(problem);}})();
  return()=>{controller.abort();document.removeEventListener('visibilitychange',hidden);};
 },[run?.run_id]);
 async function moreMessages(){
  if(!selected||!messageCursor)return;const id=selected,version=selection.current;
  const items=await history(id,messageCursor,version);const last=items?.at(-1);
  if(last&&context.current()&&version===selection.current){try{const value=await get<Run>('/runs/'+last.run_id,{tenantId:org,signal:context.signal});if(context.current()&&version===selection.current&&value.tenant_id===org){publishRun(value);setDraft('');}}catch(problem){if(version===selection.current)await failed(problem);}}
 }
 async function cancel(){
  if(!run||run.is_terminal||cancelling||run.state==='cancel_requested')return;
  setCancelling(true);setError(null);
  try{const value=await api.request<Run>('/runs/'+run.run_id+'/cancel',{method:'POST',tenantId:org,csrf:user.csrf_token,body:{expected_revision:run.revision},signal:context.signal});if(context.current()){publishRun(value);setDraft('');}}
  catch(problem){await failed(problem);if(context.current()){
   try{const value=await get<Run>('/runs/'+run.run_id,{tenantId:org,signal:context.signal});if(context.current())publishRun(value);}catch(error){await failed(error);}
  }}finally{if(context.current())setCancelling(false);}
 }
 const final=run?.is_terminal&&run.content_status==='final'&&run.result;
 return <section className="chat-panel" aria-labelledby="chat-title">
  <div className="page-heading"><div><p className="eyebrow teal">AI WORKSPACE</p><h1 id="chat-title">AI 업무</h1><p className="muted">{tenant.display_name} · 본인의 대화만 표시합니다.</p></div><button className="secondary" disabled={sending||unresolved} onClick={()=>void initialize()}>업무 새로고침</button></div>
  <div className="chat-layout"><aside className="conversation-panel" aria-label="내 대화"><div className="panel-heading"><h2>내 대화</h2><button className="secondary small history-toggle" aria-expanded={historyOpen} aria-controls="conversation-list" onClick={()=>setHistoryOpen(open=>!open)}>{historyOpen?'목록 닫기':'목록 열기'}</button><button className="secondary small" disabled={sending||unresolved||busy} onClick={fresh}>새 대화</button></div>
   <div id="conversation-list" className={'conversation-list '+(historyOpen?'expanded':'')}>{conversations.map((c,index)=><button className="conversation-link" key={c.conversation_id} aria-pressed={selected===c.conversation_id} disabled={sending||unresolved} onClick={()=>void choose(c)}>대화 {index+1}<span>{c.agent_key==='general'?'일반 대화':'규정 검색'} · {stateName[c.recent_state??'']??'아직 질문 없음'}</span></button>)}
   {!loading&&!conversations.length&&<p className="muted">저장된 대화가 없습니다.</p>}
   {conversationCursor&&<button className="secondary small" onClick={()=>void list(conversationCursor)}>대화 더 보기</button>}
   </div></aside><div className="chat-main">
   {error&&<p role="alert" className="error-message">{error}</p>}{notice&&<p role="status" className="notice">{notice}</p>}
   <div className="card agent-choice"><label htmlFor="agent-choice">Agent</label><select id="agent-choice" value={agent} disabled={sending||busy||unresolved||!!selected} onChange={e=>setAgent(e.target.value as AgentKey)}>{agents.map(a=><option key={a.agent_key} value={a.agent_key}>{a.name}</option>)}</select>
    <p className="muted">{active?.description||'질문에 대한 답변을 작성합니다.'}</p><p className="scope-note">{agent==='general'?'문서 검색 사용 안 함':'문서 검색과 근거 표시는 후속 단계에서 연결합니다.'}</p>
    {active&&!active.available&&<p className="blocked-note">{blockReason[active.safe_block_reason??'']??'현재 사용할 수 없습니다.'}</p>}
   </div>
   <div className="message-list" aria-label="대화 내용">{messages.map(m=><article className={'message '+m.role} key={m.message_id}><strong>{m.role==='user'?'내 질문':'저장된 답변'}</strong><p>{m.text}</p></article>)}
    {messageCursor&&selected&&<button className="secondary small" onClick={()=>void moreMessages()}>메시지 더 보기</button>}
    {run&&<article className="run-card" aria-label="실행 상태"><p className="mode-tag">{modeLabel(run.execution_mode)}</p><p role="status" className="run-status">{stateName[run.state]??'상태 확인 중'}</p>
     {draft&&!run.is_terminal&&<div className="draft"><strong>작성 중 · 저장 미확정</strong><p>{draft}</p></div>}
     {final&&!messages.some(m=>m.run_id===run.run_id&&m.role==='assistant')&&<div className="message assistant"><strong>저장된 답변</strong><p>{run.result!.text}</p></div>}
     {run.is_terminal&&run.content_status==='unavailable'&&<p className="muted">답변을 표시할 수 없습니다. 실행 결과와 현재 권한을 확인해 주세요.</p>}
     {run.usage_status==='unknown'&&<p className="blocked-note">사용량 확인 필요 · 예약 유지</p>}
     {!run.is_terminal&&<button className="quiet" disabled={cancelling||run.state==='cancel_requested'} onClick={()=>void cancel()}>답변 취소 요청</button>}
    </article>}
    {!run&&!messages.length&&<div className="chat-welcome"><span className="empty-symbol">✦</span><h2>질문을 입력해 주세요.</h2><p className="muted">일반 대화부터 업무 흐름을 확인할 수 있습니다.</p></div>}
   </div>
   <form className="card prompt-form" onSubmit={e=>{e.preventDefault();void send();}}><label htmlFor="prompt">질문</label><textarea id="prompt" value={prompt} maxLength={4000} rows={4} disabled={sending||busy||unresolved} onChange={e=>setPrompt(e.target.value)} placeholder="확인하고 싶은 내용을 입력해 주세요."/><div className="prompt-actions"><p className="muted">{prompt.length.toLocaleString()} / 4,000자</p><button type="submit" className="primary" disabled={loading||sending||busy||unresolved||!active?.available||!prompt.trim()}>{sending?'접수 확인 중':'질문 보내기'}</button></div>
    {unresolved&&<button type="button" className="secondary" disabled={sending} onClick={()=>void confirmAdmission()}>접수 상태 확인</button>}
    <p className="scope-note">조직 전환이나 화면 닫기는 업무 취소가 아닙니다. 저장된 대화에서 결과를 다시 확인할 수 있습니다.</p>
   </form>
  </div></div>
 </section>;
}
