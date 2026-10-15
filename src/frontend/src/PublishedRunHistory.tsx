import {useEffect,useRef,useState} from 'react';
import {api,ApiError} from './api';
import {useScope,modeLabel} from './scoped';
import {RunAssetInfo} from './RunAssetInfo';
import type {Tenant,User,Run} from './types';
type RecordRow={run_id:string;asset_id:string;asset_revision:number;asset_version_id:string;publication_revision:number;state:string;revision:number;is_terminal:boolean;execution_mode:string;created_at:string;available:boolean;display_name:string|null};
const states:Record<string,string>={accepted:'접수됨',running:'실행 중',cancel_requested:'취소 확인 중',completed:'완료',cancelled:'취소됨',failed:'실패',blocked:'차단됨',interrupted:'중단됨'};
export function PublishedRunHistory({tenant,user,onCatalog}:{tenant:Tenant;user:User;onCatalog:()=>void}){
 const scope=useScope(),listSeq=useRef(0),selection=useRef(0),selected=useRef<string|null>(null),refreshing=useRef(false),listLock=useRef(false);
 const [items,setItems]=useState<RecordRow[]>([]),[cursor,setCursor]=useState<string|null>(null),[filter,setFilter]=useState(''),[busy,setBusy]=useState(false),[record,setRecord]=useState<RecordRow|null>(null),[run,setRun]=useState<Run|null>(null),[error,setError]=useState<string|null>(null),[cancelling,setCancelling]=useState(false);
 const options={tenantId:tenant.tenant_id,signal:scope.signal};
 function clear(){selection.current++;selected.current=null;setRecord(null);setRun(null);setItems([]);setCursor(null);}
 async function fail(problem:unknown){const message=await scope.fail(problem,clear);if(scope.current())setError(message);}
 async function list(more=false,state=filter){if(listLock.current)return;listLock.current=true;const n=++listSeq.current;setBusy(true);setError(null);
  const params=new URLSearchParams();if(state)params.set('state',state);if(more&&cursor)params.set('cursor',cursor);
  try{const data=await api.request<{items:RecordRow[];next_cursor:string|null}>('/published-agent-runs'+(params.size?'?'+params:''),options);if(scope.current()&&n===listSeq.current){setItems(old=>more?[...old,...data.items]:data.items);setCursor(data.next_cursor);}}
  catch(problem){if(scope.current()&&n===listSeq.current){setItems([]);setCursor(null);await fail(problem);}}
  finally{if(scope.current()){listLock.current=false;setBusy(false);}}
 }
 async function refresh(id:string,n:number){if(refreshing.current)return;refreshing.current=true;
  const valid=()=>scope.current()&&selection.current===n&&selected.current===id;
  try{const meta=await api.request<RecordRow>('/published-agent-runs/'+id+'/record',options);if(!valid())return;setRecord(meta);setItems(old=>old.map(row=>row.run_id===id?meta:row));
   if(!meta.available){setRun(null);return;}
   const detail=await api.request<Run>('/published-agent-runs/'+id,options);if(valid()){setRun(detail);setError(null);}
  }catch(problem){if(valid()){setRun(null);setRecord(old=>old?{...old,available:false,display_name:null}:null);await fail(problem);}}
  finally{refreshing.current=false;}
 }
 function choose(row:RecordRow){const n=++selection.current;selected.current=row.run_id;setRecord(row);setRun(null);setError(null);void refresh(row.run_id,n);}
 useEffect(()=>{void list();return()=>{listSeq.current++;selection.current++;};},[]);
 useEffect(()=>{if(!record)return;const id=record.run_id,n=selection.current;const check=()=>{if(document.visibilityState==='visible')void refresh(id,n);};const timer=setInterval(check,record.is_terminal?5000:1000);window.addEventListener('focus',check);document.addEventListener('visibilitychange',check);return()=>{clearInterval(timer);window.removeEventListener('focus',check);document.removeEventListener('visibilitychange',check);};},[record?.run_id,record?.is_terminal]);
 async function cancel(){if(!record||cancelling)return;const id=record.run_id,n=selection.current;setCancelling(true);setError(null);setRun(null);
  try{await api.request('/published-agent-runs/'+id+'/cancel',{...options,method:'POST',csrf:user.csrf_token,body:{expected_revision:record.revision}});}
  catch(problem){if(scope.current()&&n===selection.current&&!(problem instanceof ApiError&&problem.status===409))await fail(problem);}
  finally{if(scope.current()){setCancelling(false);void refresh(id,n);}}
 }
 return <section aria-labelledby="published-history-title"><div className="page-heading"><div><h1 id="published-history-title">Agent 실행 이력</h1><p>본인의 독립 Agent 실행 기록입니다. 철회된 Agent의 최소 기록도 보존합니다.</p></div><button className="secondary" onClick={onCatalog} disabled={cancelling}>AI 카탈로그로 이동</button></div>
 {error&&<p role="alert">{error}</p>}<div className="catalog-layout"><section className="card" aria-label="나의 전체 Agent 실행 목록"><div className="history-filter-bar"><div className="history-filter-group"><label htmlFor="published-history-filter">실행 상태 필터</label><select id="published-history-filter" aria-label="실행 상태 필터" value={filter} disabled={busy||cancelling} onChange={e=>{const state=e.target.value;setFilter(state);selection.current++;selected.current=null;setRecord(null);setRun(null);setItems([]);setCursor(null);void list(false,state);}}><option value="">모든 상태</option>{Object.entries(states).map(([key,label])=><option key={key} value={key}>{label}</option>)}</select></div><button className="secondary small" disabled={busy||cancelling} onClick={()=>void list()}>실행 목록 새로고침</button></div>
 {items.map(row=><button className="hub-agent" key={row.run_id} aria-pressed={record?.run_id===row.run_id} disabled={cancelling} onClick={()=>choose(row)}><strong>{row.display_name??'상세 조회가 제한된 Agent'}</strong><span>버전 {row.asset_revision} · {states[row.state]??row.state}</span><small>{new Date(row.created_at).toLocaleString('ko-KR')} · {row.available?'현재 상세 조회 가능':'현재 상세 조회 제한'}</small></button>)}{busy&&<p role="status">실행 기록 조회 중</p>}{!busy&&!items.length&&<p>표시할 Agent 실행 기록이 없습니다.</p>}{cursor&&<button disabled={busy||cancelling} onClick={()=>void list(true)}>전체 실행 기록 더 보기</button>}</section>
 <section className="card" aria-label="Agent 실행 기록 상세">{record?<><h2>{record.display_name??'Agent 실행 기록'}</h2><p>실행 버전 {record.asset_revision} · 게시 revision {record.publication_revision}</p><p>{new Date(record.created_at).toLocaleString('ko-KR')}</p><p>{modeLabel(record.execution_mode)}</p><p role="status">{states[record.state]??record.state}</p>{!record.available&&<p>현재 권한으로 상세를 조회할 수 없습니다. 게시 철회·버전 변경·공개 대상 또는 자료 권한을 확인해 주세요.</p>}{!record.is_terminal&&<button className="secondary" disabled={cancelling||record.state==='cancel_requested'} onClick={()=>void cancel()}>이력 실행 취소</button>}
 {run&&<section aria-label="이력의 현재 실행 결과"><p>사용량 {run.usage_status==='final'?'정산 완료':run.usage_status==='unknown'?'확인 필요':'정산 확인 중'}</p>{run.content_status==='final'&&run.result?<p style={{whiteSpace:'pre-wrap'}}>{run.result.text}</p>:run.is_terminal&&<p>제공 가능한 최종 답변이 없습니다.</p>}<RunAssetInfo binding={run.asset_binding}/></section>}</>:<p>실행 기록을 선택하세요.</p>}</section></div></section>;
}
