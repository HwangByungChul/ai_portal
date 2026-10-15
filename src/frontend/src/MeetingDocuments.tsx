import {useEffect,useRef,useState} from 'react';
import {api} from './api';
import {useScope} from './scoped';
import type {MeetingDocument,Tenant,User} from './types';
export function MeetingDocuments({tenant,user,selected,onChange,disabled}:{tenant:Tenant;user:User;selected:MeetingDocument[];onChange:(docs:MeetingDocument[])=>void;disabled:boolean}){
 const scope=useScope(),seq=useRef(0);const [items,setItems]=useState<MeetingDocument[]>([]),[cursor,setCursor]=useState<string|null>(null),[busy,setBusy]=useState(false),[error,setError]=useState<string|null>(null);
 async function load(next:string|null=null){const id=++seq.current;setBusy(true);setError(null);try{
  const fetchPage=(cursor:string|null)=>api.request<{items:MeetingDocument[];next_cursor:string|null}>('/use-cases/AGENT_03/documents?limit=20'+(cursor?'&cursor='+encodeURIComponent(cursor):''),{tenantId:tenant.tenant_id,signal:scope.signal});
  const page=await fetchPage(next);let refreshed=page.items;let end=page.next_cursor;
  // A first-page absence is not revocation. Finish the authorized listing before deciding.
  if(!next&&selected.length){const visited=new Set<string>();while(end){if(visited.has(end))throw new Error('자료 목록을 끝까지 확인하지 못했습니다. 선택은 유지됩니다.');visited.add(end);const more=await fetchPage(end);if(!scope.current()||id!==seq.current)return;refreshed=[...refreshed,...more.items];end=more.next_cursor;}}
  if(scope.current()&&id===seq.current){setItems(old=>next?[...old,...refreshed]:refreshed);setCursor(end);if(!next){const valid=selected.flatMap(d=>{const found=refreshed.find(v=>v.document_id===d.document_id&&v.version_id===d.version_id&&v.ready);return found?[found]:[];});if(valid.length!==selected.length)setError('선택한 자료 중 삭제·권한 변경 또는 원문 사용 불가로 확인된 자료를 선택에서 제외했습니다. 현재 자료를 다시 확인해 주세요.');onChange(valid);}}
 }catch(p){const msg=await scope.fail(p,()=>{setItems([]);onChange([]);});if(scope.current()&&id===seq.current)setError(msg===null?null:msg+' 자료 재확인을 완료하지 못했습니다. 확인되지 않은 선택은 유지됩니다.');}finally{if(scope.current()&&id===seq.current)setBusy(false);}}

 useEffect(()=>{void load();return()=>{seq.current++;};},[tenant.tenant_id]);
 return <fieldset className="meeting-documents" disabled={disabled||busy}><legend>회의 자료 선택 · {selected.length}/3건</legend><p>현재 읽을 수 있는 원문 버전만 사용합니다. 원문 없는 자료는 선택할 수 없습니다. <a href="/user/documents">내 자료에서 원문 업로드</a></p>{error&&<p role="alert">{error}</p>}{items.map(d=><label key={d.version_id}><input type="checkbox" checked={selected.some(s=>s.version_id===d.version_id)} disabled={!d.ready||(!selected.some(s=>s.version_id===d.version_id)&&selected.length>=3)} onChange={e=>onChange(e.target.checked?[...selected,d]:selected.filter(s=>s.version_id!==d.version_id))}/><span>{d.title} · 버전 {d.version_no} · {d.character_length}자{!d.ready?' · 원문 사용 불가':''}</span></label>)}{!busy&&!items.length&&<p>현재 사용 가능한 자료가 없습니다.</p>}{selected.length>0&&<p>선택 유지: {selected.map(d=>d.title+' (v'+d.version_no+')').join(', ')}</p>}{busy&&<p role="status">자료 확인 중</p>}{cursor&&<button type="button" disabled={busy} onClick={()=>void load(cursor)}>자료 더 보기</button>}<button type="button" disabled={busy} onClick={()=>void load()}>자료 새로고침 · 선택 재확인</button></fieldset>;
}
