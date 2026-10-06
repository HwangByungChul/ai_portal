import {useState} from 'react';
import {api,ApiError} from './api';
import {useScope} from './scoped';
import type {Conversation} from './types';
export interface HistoryFilter {q:string;pinned:boolean|null}
interface Props {items:Conversation[];selected:string|null;disabled:boolean;loading:boolean;cursor:string|null;tenantId:string;csrf:string;
 onChoose:(c:Conversation)=>void;onMore:()=>void;onFilter:(filter:HistoryFilter)=>void;onChanged:()=>Promise<void>;
 onDeleted:(id:string)=>void;onError:(problem:unknown)=>Promise<void>;stateName:Record<string,string>}
export function ConversationHistory(p:Props){
 const scope=useScope();
 const [query,setQuery]=useState('');const [pinnedOnly,setPinnedOnly]=useState(false);
 const [editing,setEditing]=useState<Conversation|null>(null);const [title,setTitle]=useState('');
 const [deleting,setDeleting]=useState<Conversation|null>(null);const [saving,setSaving]=useState(false);
 const [feedback,setFeedback]=useState<string|null>(null);
 function filter(q:string,pinned:boolean){p.onFilter({q:q.trim(),pinned:pinned?true:null});setEditing(null);setDeleting(null);setFeedback(null);}
 async function mutate(c:Conversation,operation:'title'|'pin'|'delete'){
  if(saving||p.disabled)return;setSaving(true);setFeedback(null);
  try{
   const data=await api.request<{metadata_revision:number}>('/conversations/'+c.conversation_id,{method:operation==='delete'?'DELETE':'PATCH',tenantId:p.tenantId,csrf:p.csrf,
    body:{expected_revision:c.metadata_revision,...(operation==='title'?{title}:operation==='pin'?{pinned:!c.pinned}:{})},signal:scope.signal});
   if(!scope.current())return;
   if(operation==='delete')p.onDeleted(c.conversation_id);
   setEditing(null);setDeleting(null);setFeedback(operation==='delete'?'대화 목록에서 삭제했습니다.':operation==='title'?'제목을 변경했습니다.':c.pinned?'핀을 해제했습니다.':'대화를 핀했습니다.');
   await p.onChanged();void data;
  }catch(problem){
   if(!scope.current())return;
   if(problem instanceof ApiError&&problem.code==='CONVERSATION_BUSY')setFeedback('답변이 진행 중입니다. 취소하거나 완료된 뒤 삭제해 주세요.');
   else if(problem instanceof ApiError&&problem.status===409){setEditing(null);setDeleting(null);setFeedback('다른 변경이 반영되었습니다. 목록에서 다시 선택해 주세요.');await p.onChanged();}
   else await p.onError(problem);
  }finally{if(scope.current())setSaving(false);}
 }
 return <>
  <form className="history-search" onSubmit={e=>{e.preventDefault();filter(query,pinnedOnly);}}>
   <label htmlFor="history-query">대화 제목 검색</label>
   <div className="history-query-row"><input id="history-query" value={query} maxLength={120} disabled={p.disabled||saving} onChange={e=>setQuery(e.target.value)} placeholder="제목으로 검색"/><button className="secondary small" disabled={p.disabled||saving}>검색</button></div>
   <label className="history-filter"><input type="checkbox" checked={pinnedOnly} disabled={p.disabled||saving} onChange={e=>{setPinnedOnly(e.target.checked);filter(query,e.target.checked);}}/>핀한 대화만</label>
  </form>
  {feedback&&<p role="status" className="scope-note">{feedback}</p>}
  {p.items.map((c,index)=><div className="history-row" key={c.conversation_id} data-conversation-id={c.conversation_id}>
   <button className="conversation-link" aria-pressed={p.selected===c.conversation_id} disabled={p.disabled||saving} onClick={()=>p.onChoose(c)}>{c.pinned?'📌 ':''}{c.title==='제목 없는 대화'?'대화 '+(index+1):c.title}<span>{c.agent_key==='general'?'일반 대화':'규정 검색'} · {p.stateName[c.recent_state??'']??'아직 질문 없음'}</span></button>
   <div className="history-actions"><button className="quiet small" disabled={p.disabled||saving} aria-label={c.title+' 제목 변경'} onClick={()=>{setEditing(c);setTitle(c.title);setDeleting(null);setFeedback(null);}}>제목 변경</button>
    <button className="quiet small" disabled={p.disabled||saving} aria-label={c.title+(c.pinned?' 핀 해제':' 핀')} onClick={()=>void mutate(c,'pin')}>{c.pinned?'핀 해제':'핀'}</button>
    <button className="quiet small" disabled={p.disabled||saving} aria-label={c.title+' 삭제'} onClick={()=>{setDeleting(c);setEditing(null);setFeedback(null);}}>삭제</button></div>
  </div>)}
  {editing&&<form className="history-editor" aria-label="대화 제목 편집" onSubmit={e=>{e.preventDefault();void mutate(editing,'title');}}><label htmlFor="history-title">새 대화 제목</label><input id="history-title" value={title} maxLength={120} disabled={saving} onChange={e=>setTitle(e.target.value)}/><div className="history-actions"><button className="primary small" disabled={saving||!title.trim()}>제목 저장</button><button type="button" className="secondary small" disabled={saving} onClick={()=>setEditing(null)}>편집 취소</button></div></form>}
  {deleting&&<div className="history-editor" role="group" aria-label="대화 삭제 확인"><p>이 대화를 삭제하시겠습니까?</p><p className="scope-note">삭제 후 대화와 답변을 다시 열 수 없습니다. 사용량과 감사 기록은 보존됩니다.</p><div className="history-actions"><button className="quiet small" disabled={saving} onClick={()=>void mutate(deleting,'delete')}>삭제 확인</button><button className="secondary small" disabled={saving} onClick={()=>setDeleting(null)}>삭제 취소</button></div></div>}
  {!p.loading&&!p.items.length&&<p className="muted">{query.trim()||pinnedOnly?'조건에 맞는 대화가 없습니다.':'저장된 대화가 없습니다.'}</p>}
  {p.cursor&&<button className="secondary small" disabled={p.disabled||saving} onClick={p.onMore}>대화 더 보기</button>}
 </>;
}
