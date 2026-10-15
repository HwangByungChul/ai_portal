import {RunAssetInfo} from './RunAssetInfo';
import {useEffect,useRef,useState} from 'react';
import {api,ApiError,isAbort} from './api';
import {blockReason,get,modeLabel,useScope,wait} from './scoped';
import {ReadableDocuments} from './ReadableDocuments';
import {RagEvidencePanel} from './RagEvidencePanel';
import {subscribe} from './stream';
import {ConversationHistory,type HistoryFilter} from './ConversationHistory';
import {ResponseFeedback} from './ResponseFeedback';
import type {AgentKey,AgentSummary,Conversation,DocumentRef,Message,PageResult,Run,Tenant,User,ChatLaunch} from './types';
type Submission={asset_id?:string;client_send_id:string;agent_key:AgentKey;prompt:string;conversation_id?:string;document_refs?:DocumentRef[]};
const stateName:Record<string,string>={queued:'접수됨',running:'답변 작성 중',cancel_requested:'취소 요청됨 · 결과 확인 중',completed:'완료 · 저장 확인됨',cancelled:'취소됨',failed:'처리 실패',blocked:'현재 처리할 수 없음',interrupted:'처리가 중단됨'};
export function ChatPage({tenant,user,initial={},onPublishedHistory}:{tenant:Tenant;user:User;initial?:ChatLaunch;onPublishedHistory?:()=>void}){
 const context=useScope();const org=tenant.tenant_id;
 const [agents,setAgents]=useState<AgentSummary[]>([]);const [agent,setAgent]=useState<AgentKey>(initial.agentKey??initial.conversation?.agent_key??'general');
 const [conversations,setConversations]=useState<Conversation[]>([]);const [conversationCursor,setConversationCursor]=useState<string|null>(null);
 const [selected,setSelected]=useState<string|null>(null);const [messages,setMessages]=useState<Message[]>([]);const [messageCursor,setMessageCursor]=useState<string|null>(null);
 const [documentRefs,setDocumentRefs]=useState<DocumentRef[]>([]);
 const [prompt,setPrompt]=useState(initial.prompt??'');const [run,setRun]=useState<Run|null>(null);const [draft,setDraft]=useState('');
 const [error,setError]=useState<string|null>(null);const [notice,setNotice]=useState<string|null>(null);const [loading,setLoading]=useState(true);
 const [historyOpen,setHistoryOpen]=useState(false);const [sending,setSending]=useState(false);const [unresolved,setUnresolved]=useState(false);const [cancelling,setCancelling]=useState(false);
 const lock=useRef(false);const pending=useRef<Submission|null>(null);const selection=useRef(0);const listQuery=useRef(0);const chosen=useRef<string|null>(null);
 const historyFilter=useRef<HistoryFilter>({q:'',pinned:null});
 const currentRun=useRef<Run|null>(null);const historyQuery=useRef(0),authorityBusy=useRef(false);
 const active=agents.find(a=>a.agent_key===agent);const busy=!!run&&!run.is_terminal;
 function publishRun(value:Run){
  if(!context.current()||value.tenant_id!==org)return;
  const prior=currentRun.current;if(prior?.run_id===value.run_id&&prior.revision>value.revision)return;
  currentRun.current=value;setRun(value);
 }
 function clear(){setMessages([]);setConversations([]);setAgents([]);currentRun.current=null;setRun(null);setDraft('');setPrompt('');setDocumentRefs([]);pending.current=null;}
 async function failed(problem:unknown){const message=await context.fail(problem,clear);if(context.current())setError(message);}
 async function list(next:string|null=null){
  const version=++listQuery.current;
  const params=new URLSearchParams();if(next)params.set('cursor',next);if(historyFilter.current.q)params.set('q',historyFilter.current.q);if(historyFilter.current.pinned!==null)params.set('pinned',String(historyFilter.current.pinned));
  try{const page=await get<PageResult<Conversation>>('/conversations'+(params.size?'?'+params.toString():''),{tenantId:org,signal:context.signal});
   if(context.current()&&version===listQuery.current){setConversations(old=>next?[...old,...page.items]:page.items);setConversationCursor(page.next_cursor);}
  }catch(problem){await failed(problem);}
 }
 async function history(id:string,next:string|null=null,version=selection.current):Promise<Message[]|null>{
  const query=++historyQuery.current;
  try{const page=await get<PageResult<Message>>('/conversations/'+id+'/messages'+(next?'?cursor='+encodeURIComponent(next):''),{tenantId:org,signal:context.signal});
   if(!context.current()||version!==selection.current||chosen.current!==id||query!==historyQuery.current)return null;
   setMessages(old=>next?[...old,...page.items]:page.items);setMessageCursor(page.next_cursor);return page.items;
  }catch(problem){if(context.current()&&version===selection.current){setMessages([]);setMessageCursor(null);await failed(problem);}return null;}
 }
 async function initialize(){
  setLoading(true);setError(null);
  try{const value=await get<{items:AgentSummary[]}>('/agents',{tenantId:org,signal:context.signal});if(context.current())setAgents(value.items);}
  catch(problem){await failed(problem);}
  await list();await currentAuthority();if(context.current())setLoading(false);
 }
 useEffect(()=>{void initialize().then(()=>{if(initial.conversation?.tenant_id===org&&context.current())void choose(initial.conversation);});},[]);
 function hideAnswer(id:string){historyQuery.current++;setMessages(old=>old.filter(m=>m.role!=='assistant'||m.run_id!==id));const value=currentRun.current;if(value?.run_id===id){publishRun({...value,content_status:'unavailable',result:null});}}
 async function currentAuthority(){
  if(!context.current()||!chosen.current||authorityBusy.current||currentRun.current&&!currentRun.current.is_terminal)return;authorityBusy.current=true;
  const id=chosen.current,version=selection.current;
  try{const current=currentRun.current;if(current){const value=await get<Run>('/runs/'+current.run_id,{tenantId:org,signal:context.signal});if(context.current()&&version===selection.current){publishRun(value);if(value.content_status==='unavailable')hideAnswer(value.run_id);}}
   await history(id,null,version);
  }catch(problem){if(context.current()&&version===selection.current){setMessages([]);setDraft('');currentRun.current=null;setRun(null);await failed(problem);}}finally{authorityBusy.current=false;}
 }
 useEffect(()=>{if(agent!=='rules_rag')return;const refresh=()=>{if(document.visibilityState==='visible')void currentAuthority();};const timer=setInterval(refresh,5000);window.addEventListener('focus',refresh);document.addEventListener('visibilitychange',refresh);return()=>{clearInterval(timer);window.removeEventListener('focus',refresh);document.removeEventListener('visibilitychange',refresh);};},[agent]);
 function fresh(){setDocumentRefs([]);selection.current++;chosen.current=null;setSelected(null);setMessages([]);setMessageCursor(null);currentRun.current=null;setRun(null);setDraft('');setError(null);setNotice(null);setPrompt('');}
 async function choose(conversation:Conversation){
  if(lock.current||unresolved)return;
  setDocumentRefs([]);const version=++selection.current;chosen.current=conversation.conversation_id;
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
  const payload:Submission={...(initial?.assetId&&agent===initial.agentKey?{asset_id:initial.assetId}:{}),...(agent==='rules_rag'&&documentRefs.length?{document_refs:documentRefs}:{}),client_send_id:crypto.randomUUID(),agent_key:agent,prompt,...(selected?{conversation_id:selected}:{})};pending.current=payload;
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
 return <section className="chat-workspace-v2" aria-labelledby="chat-title">
  {/* 좌측: 대화 목록 사이드 패널 */}
  <aside className="chat-sidebar-v2" aria-label="내 대화">
   <div className="chat-sidebar-header">
    <div className="sidebar-title-row">
     <h2 id="chat-title">내 대화</h2>
     <button type="button" className="secondary small" disabled={sending||unresolved||busy} onClick={fresh}>+ 새 대화</button>
    </div>
   </div>
   <div id="conversation-list" className="chat-sidebar-list">
    <ConversationHistory items={conversations} selected={selected} disabled={sending||unresolved} loading={loading} cursor={conversationCursor} tenantId={org} csrf={user.csrf_token} stateName={stateName}
     onChoose={c=>void choose(c)} onMore={()=>void list(conversationCursor)} onFilter={filter=>{historyFilter.current=filter;setConversations([]);setConversationCursor(null);void list();}}
     onChanged={()=>list()} onDeleted={id=>{if(chosen.current===id)fresh();}} onError={failed}/>
   </div>
  </aside>

  {/* 우측: 메인 대화 콘솔 */}
  <div className="chat-main-v2">
   {/* 상단: Agent 선택 및 도구 툴바 */}
   <div className="chat-top-toolbar">
    <div className="chat-agent-selector-bar">
     <label htmlFor="agent-choice"><strong>Agent</strong></label>
     <select id="agent-choice" value={agent} disabled={sending||busy||unresolved||!!selected} onChange={e=>{setAgent(e.target.value as AgentKey);setDocumentRefs([]);}}>
      {agents.map(a=><option key={a.agent_key} value={a.agent_key}>{a.name}</option>)}
     </select>
     <span className="chat-agent-desc">{active?.description||'질문에 대한 답변을 작성합니다.'} · {agent==='general'?'일반 대화':'자료 검색'}</span>
     {active&&!active.available&&<span className="blocked-note" style={{padding:'2px 8px',margin:0,fontSize:'11px'}}>{blockReason[active.safe_block_reason??'']??'현재 사용 불가'}</span>}
    </div>
    <div className="chat-toolbar-actions">
     {onPublishedHistory&&<button type="button" className="quiet small" disabled={sending||unresolved} onClick={onPublishedHistory}>독립 Agent 실행 이력</button>}
     <button type="button" className="quiet small" disabled={sending||unresolved} onClick={()=>void initialize()}>새로고침</button>
    </div>
   </div>

   {error&&<div style={{padding:'12px 24px 0'}}><p role="alert" className="error-message" style={{margin:0}}>{error}</p></div>}
   {notice&&<div style={{padding:'12px 24px 0'}}><p role="status" className="notice" style={{margin:0}}>{notice}</p></div>}
   {agent==='rules_rag'&&<div style={{padding:'12px 24px 0'}}><ReadableDocuments tenantId={org} selected={documentRefs} onChange={setDocumentRefs} disabled={sending||busy||unresolved}/></div>}

   {/* 중앙: 대화 메시지 스크롤 영역 */}
   <div className="chat-messages-container" aria-label="대화 내용">
    <div className="chat-messages-inner">
     {messages.map(m=><article className={`chat-message-bubble ${m.role}`} key={m.message_id}>
      <div className="bubble-role-header">{m.role==='user'?'내 질문':'답변'}</div>
      <p style={{margin:0,whiteSpace:'pre-wrap'}}>{m.text}</p>
      {m.role==='assistant'&&agent==='rules_rag'&&<RagEvidencePanel tenantId={org} runId={m.run_id} onUnavailable={()=>hideAnswer(m.run_id)}/>}
      {m.role==='assistant'&&m.run_state==='completed'&&m.answer_kind==='answer'&&<ResponseFeedback key={org+':'+m.run_id} tenantId={org} runId={m.run_id} csrf={user.csrf_token} onUnavailable={()=>hideAnswer(m.run_id)}/>}
     </article>)}

     {messageCursor&&selected&&<button type="button" className="secondary small" style={{alignSelf:'center'}} onClick={()=>void moreMessages()}>메시지 더 보기</button>}

     {run&&<article className="run-card" aria-label="실행 상태" style={{width:'100%',boxSizing:'border-box'}}>
      <p className="mode-tag">{modeLabel(run.execution_mode)}</p>
      <p role="status" className="run-status">{stateName[run.state]??'상태 확인 중'}{agent==='rules_rag'&&!run.is_terminal?' · '+({retrieval:'자료 검색',generation:'근거 선택',finalizing:'근거 검증·저장'}[run.stage]??'처리 중'):''}</p>
      {draft&&!run.is_terminal&&<div className="draft"><strong>작성 중 · 저장 미확정</strong><p>{draft}</p></div>}
      {final&&!messages.some(m=>m.run_id===run.run_id&&m.role==='assistant')&&<div className="chat-message-bubble assistant">
       <div className="bubble-role-header">저장된 답변</div>
       <p style={{margin:0,whiteSpace:'pre-wrap'}}>{run.result!.text}</p>
       {agent==='rules_rag'&&<RagEvidencePanel tenantId={org} runId={run.run_id} onUnavailable={()=>hideAnswer(run.run_id)}/>}
       {run.answer_kind==='answer'&&<ResponseFeedback key={org+':'+run.run_id} tenantId={org} runId={run.run_id} csrf={user.csrf_token} onUnavailable={()=>hideAnswer(run.run_id)}/>}
      </div>}
      {run.is_terminal&&run.answer_kind==='insufficient_evidence'&&<p className="scope-note">현재 허용 자료에서 필요한 근거를 확인하지 못했습니다.</p>}
      {run.is_terminal&&run.content_status==='unavailable'&&<p className="muted">답변을 표시할 수 없습니다. 실행 결과와 현재 권한을 확인해 주세요.</p>}
      <RunAssetInfo binding={run.asset_binding}/>
      {run.usage_status==='unknown'&&<p className="blocked-note">사용량 확인 필요 · 예약 유지</p>}
      {!run.is_terminal&&<button type="button" className="quiet" disabled={cancelling||run.state==='cancel_requested'} onClick={()=>void cancel()}>답변 취소 요청</button>}
     </article>}

     {!run&&!messages.length&&<div className="chat-welcome-box">
      <div className="chat-welcome-symbol">✦</div>
      <h2>질문을 입력해 주세요</h2>
      <p>업무 규정 확인, 공문서 초안 작성, 안건 요약 등 궁금한 점을 질문하시면 AI 에이전트가 신속하게 답변해 드립니다.</p>
     </div>}
    </div>
   </div>

   {/* 하단: 프롬프트 입력 영역 */}
   <div className="chat-bottom-input-bar">
    <form className="chat-input-wrapper" onSubmit={e=>{e.preventDefault();void send();}}>
     <textarea
      id="prompt"
      value={prompt}
      maxLength={4000}
      rows={2}
      disabled={sending||busy||unresolved}
      onChange={e=>setPrompt(e.target.value)}
      placeholder="확인하고 싶은 내용을 입력해 주세요 (Enter 키로 줄바꿈 가능)"
     />
     <div className="chat-input-controls">
      <span className="chat-char-counter">{prompt.length.toLocaleString()} / 4,000자</span>
      <div style={{display:'flex',gap:'8px',alignItems:'center'}}>
       {unresolved&&<button type="button" className="secondary small" disabled={sending} onClick={()=>void confirmAdmission()}>접수 상태 확인</button>}
       <button type="submit" className="chat-send-btn" disabled={loading||sending||busy||unresolved||!active?.available||!prompt.trim()}>
        {sending?'접수 확인 중':'질문 보내기'}
       </button>
      </div>
     </div>
    </form>
   </div>
  </div>
 </section>;
}
