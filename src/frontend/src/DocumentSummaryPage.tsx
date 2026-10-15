import {RunAssetInfo} from './RunAssetInfo';
import {useEffect,useRef,useState} from 'react';
import {ApiError,summaryAPI,summaryBlob} from './api';
import {get,modeLabel,useScope} from './scoped';
import {SummaryEvidencePanel} from './SummaryEvidencePanel';
import {DOCX_MEDIA_TYPE,XLSX_MEDIA_TYPE} from './types';
import type {PageResult,ReadableDocument,SummaryRun,SummarySubmission,SummaryEvidence,Tenant,User} from './types';
const stateName:Record<string,string>={queued:'접수됨',running:'요약 처리 중',cancel_requested:'취소 요청됨 · 결과 확인 중',completed:'완료 · 저장 확인됨',cancelled:'취소됨',failed:'처리 실패',blocked:'현재 처리할 수 없음',interrupted:'처리가 중단됨'};
type Pending={body:SummarySubmission}|{parent:string;body:{client_send_id:string;expected_revision:number}};
export function DocumentSummaryPage({tenant,user}:{tenant:Tenant;user:User}){
 const ctx=useScope(),org=tenant.tenant_id;
 const [documents,setDocuments]=useState<ReadableDocument[]>([]),[cursor,setCursor]=useState<string|null>(null),[selected,setSelected]=useState<string|null>(null),[count,setCount]=useState<3|5>(3),[loading,setLoading]=useState(true),[error,setError]=useState<string|null>(null),[run,setRun]=useState<SummaryRun|null>(null),[runId,setRunId]=useState<string|null>(null),[history,setHistory]=useState<string[]>([]),[sending,setSending]=useState(false),[unresolved,setUnresolved]=useState(false),[confirm,setConfirm]=useState(false),[downloading,setDownloading]=useState(false),[cancelling,setCancelling]=useState(false);
 const active=useRef<string|null>(null),current=useRef<SummaryRun|null>(null),lock=useRef(false),pending=useRef<Pending|null>(null),query=useRef(0),documentQuery=useRef(0),request=useRef<AbortController|null>(null),urls=useRef(new Set<string>());
 const options={tenantId:org,csrf:user.csrf_token,signal:ctx.signal};
 function dispose(){request.current?.abort();for(const url of urls.current)URL.revokeObjectURL(url);urls.current.clear();}
 function hide(){query.current++;documentQuery.current++;setLoading(false);dispose();current.current=null;active.current=null;setRun(null);setRunId(null);setHistory([]);setDocuments([]);setSelected(null);setCursor(null);setConfirm(false);pending.current=null;setUnresolved(false);}
 useEffect(()=>()=>{pending.current=null;active.current=null;current.current=null;dispose();},[]);
 async function failed(problem:unknown){if(!ctx.current())return;const message=await ctx.fail(problem,hide);if(ctx.current())setError(message);}
 async function list(next:string|null=null){const q=++documentQuery.current;setLoading(true);setError(null);if(!next){setDocuments([]);setSelected(null);}
  try{const result=await get<PageResult<ReadableDocument>>('/documents?limit=20'+(next?'&cursor='+encodeURIComponent(next):''),options);if(ctx.current()&&q===documentQuery.current){setDocuments(old=>next?[...old,...result.items]:result.items);setCursor(result.next_cursor);}}
  catch(problem){if(ctx.current()&&q===documentQuery.current){setDocuments([]);setSelected(null);await failed(problem);}}finally{if(ctx.current()&&q===documentQuery.current)setLoading(false);}}
 useEffect(()=>{void list();},[]);
 function choose(id:string){query.current++;dispose();current.current=null;active.current=id;setRun(null);setRunId(id);setConfirm(false);setError(null);}
 async function refresh(id:string,signal:AbortSignal=ctx.signal){const q=++query.current;
  try{const value=await summaryAPI.read(id,{...options,signal});if(!ctx.current()||signal.aborted||active.current!==id||q!==query.current)return null;if(value.run_id!==id||value.tenant_id!==org||value.task_kind!=='document_summary')throw new ApiError(503,'SCOPE_CHANGED');if(current.current?.run_id===id&&current.current.revision>value.revision)return current.current;current.current=value;setRun(value);return value;}
  catch(problem){if(ctx.current()&&!signal.aborted&&active.current===id&&q===query.current){hide();await failed(problem);}return null;}}
 useEffect(()=>{if(!runId)return;const controller=new AbortController();request.current=controller;const signal=AbortSignal.any([ctx.signal,controller.signal]);let querying=false;
  const load=async()=>{if(querying||signal.aborted||document.visibilityState!=='visible')return;querying=true;try{await refresh(runId,signal);}finally{querying=false;}};
  void load();const timer=setInterval(()=>void load(),2000);window.addEventListener('focus',load);document.addEventListener('visibilitychange',load);
  return()=>{clearInterval(timer);controller.abort();window.removeEventListener('focus',load);document.removeEventListener('visibilitychange',load);};
 },[runId]);
 async function submit(intent:'create'|'regenerate'|'replay'){if(lock.current||!ctx.current())return;let item=pending.current;
  if(intent!=='replay'){if(run&&!run.is_terminal)return;if(intent==='regenerate'){if(!run||run.content_status!=='final'||!['completed','insufficient_evidence'].includes(run.state))return;item={parent:run.run_id,body:{client_send_id:crypto.randomUUID(),expected_revision:run.revision}};}else{const doc=documents.find(d=>d.version_id===selected);if(!doc)return;item={body:{client_send_id:crypto.randomUUID(),document_ref:{document_id:doc.document_id,version_id:doc.version_id},bullet_count:count}};}pending.current=item;}
  if(!item)return;lock.current=true;setSending(true);setError(null);setConfirm(false);
  try{const accepted='parent' in item?await summaryAPI.regenerate(item.parent,item.body,options):await summaryAPI.create(item.body,options);if(!ctx.current())return;pending.current=null;setUnresolved(false);setHistory(old=>old.includes(accepted.run_id)?old:[...old,accepted.run_id]);choose(accepted.run_id);}
  catch(problem){if(ctx.current()){if(problem instanceof ApiError&&(problem.status===0||problem.status>=500)){setUnresolved(true);}else{pending.current=null;setUnresolved(false);if(problem instanceof ApiError&&[401,403,404].includes(problem.status))hide();}await failed(problem);}}
  finally{if(ctx.current()){lock.current=false;setSending(false);}}}
 async function cancel(){const value=current.current;if(!value||value.is_terminal||cancelling||value.state==='cancel_requested')return;setCancelling(true);
  try{await summaryAPI.cancel(value.run_id,value.revision,options);if(ctx.current()&&active.current===value.run_id)await refresh(value.run_id);}catch(problem){if(ctx.current()&&active.current===value.run_id){await failed(problem);await refresh(value.run_id);}}finally{if(ctx.current())setCancelling(false);}}
 async function download(row?:SummaryEvidence){const value=current.current,id=active.current;if(!value||!id||downloading)return;if(row&&row.source_url!=='/api/v1/document-summaries/'+id+'/evidence/'+row.ordinal+'/source'){setError('원문 경로를 확인할 수 없습니다.');return;}
  const signal=AbortSignal.any([ctx.signal,request.current?.signal??ctx.signal]);setDownloading(true);setError(null);
  try{const allowed=await refresh(id,signal);if(!allowed||allowed.content_status!=='final'||!allowed.result||!ctx.current()||signal.aborted||active.current!==id)return;
   const evidence=row?allowed.evidence.find(x=>x.ordinal===row.ordinal):undefined;if(row&&(!evidence||evidence.source_url!==row.source_url))throw new ApiError(503,'STORAGE_UNAVAILABLE');
   const media=evidence?.source_media_type??'text/markdown';const blob=await summaryBlob(id,{...options,signal},media,evidence?.ordinal);if(!ctx.current()||signal.aborted||active.current!==id)return;
   const url=URL.createObjectURL(blob);urls.current.add(url);const link=document.createElement('a');link.href=url;link.download=!evidence?'summary.md':media===XLSX_MEDIA_TYPE?'document.xlsx':media===DOCX_MEDIA_TYPE?'document.docx':media==='application/pdf'?'document.pdf':media==='text/markdown'?'document.md':'document.txt';link.click();setTimeout(()=>{URL.revokeObjectURL(url);urls.current.delete(url);},1000);
  }catch(problem){if(ctx.current()&&!signal.aborted&&active.current===id){hide();await failed(problem);}}finally{if(ctx.current())setDownloading(false);}}
 const busy=sending||unresolved||!!run&&!run.is_terminal,final=run?.content_status==='final'&&run.result,regenerable=final&&['completed','insufficient_evidence'].includes(run?.state??'');
 return <section className="summary-page" aria-labelledby="summary-title"><div className="page-heading"><div><p className="eyebrow teal">AI WORKSPACE</p><h1 id="summary-title">문서 요약</h1><p className="muted">{tenant.display_name} · 게시 문서의 정확한 버전 하나를 선택합니다.</p></div></div>
  <p className="scope-note">원문 문장을 선택합니다. 전체 의미나 핵심 내용을 모두 포함한다고 보장하지 않습니다. 요약은 규정 RAG 설정의 활성화·사용 한도에 따릅니다.</p>
  {error&&<p role="alert" className="error-message">{error}</p>}
  <section className="card document-picker" aria-label="요약할 문서"><div className="panel-heading"><h2>읽을 수 있는 자료</h2><button className="secondary small" disabled={loading||busy} onClick={()=>void list()}>자료 새로고침</button></div>
   {loading&&<p role="status">자료 확인 중</p>}{!loading&&!documents.length&&<p className="muted">현재 읽을 수 있는 게시 자료가 없습니다.</p>}
   <ul className="document-list">{documents.map(doc=><li key={doc.version_id}><label><input type="radio" name="summary-document" checked={selected===doc.version_id} disabled={busy} onChange={()=>setSelected(doc.version_id)}/>{doc.title} · {doc.safe_version_label} · {doc.visibility==='private'?'개인':doc.visibility==='shared'?'공유':'조직'}</label></li>)}</ul>
   {cursor&&<button className="secondary small" disabled={loading||busy} onClick={()=>void list(cursor)}>자료 더 보기</button>}
   <div className="summary-actions"><label>핵심 항목 수 <select aria-label="핵심 항목 수" value={count} disabled={busy} onChange={e=>setCount(Number(e.target.value) as 3|5)}><option value="3">3개</option><option value="5">5개</option></select></label><button className="primary" disabled={!selected||busy} onClick={()=>void submit('create')}>요약하기</button></div>
  </section>
  {unresolved&&<div className="notice" role="status"><p>접수 상태 확인 필요 · 같은 접수 ID로 확인합니다. 새 요약 전송을 보류했습니다.</p><button className="secondary" disabled={sending} onClick={()=>void submit('replay')}>요약 접수 확인</button></div>}
  {history.length>1&&<nav className="summary-history" aria-label="이번 방문의 요약 실행">{history.map((id,index)=><button key={id} className="secondary small" disabled={busy||downloading} aria-current={runId===id?'page':undefined} onClick={()=>choose(id)}>요약 실행 {index+1}</button>)}</nav>}
  {run&&<section className="card summary-result" aria-label="요약 결과"><span className="mode-tag">{modeLabel(run.execution_mode)}</span><RunAssetInfo binding={run.asset_binding}/><p role="status" className="run-status">{run.answer_kind==='insufficient_evidence'?'근거 부족':stateName[run.state]??'상태 확인 중'}</p>
   {run.error_code&&<p role="alert">{new ApiError(422,run.error_code).message}</p>}{!run.is_terminal&&<button className="secondary" disabled={cancelling||run.state==='cancel_requested'} onClick={()=>void cancel()}>요약 취소</button>}
   {final&&<><h2>원문 발췌 요약</h2><p className="scope-note">실제 항목 {run.evidence.length}개 · 요청 {run.bullet_count}개</p><p className="summary-text">{run.result!.text}</p><SummaryEvidencePanel rows={run.evidence} busy={downloading||busy} onDownload={row=>void download(row)}/><div className="summary-actions"><button className="secondary" disabled={!regenerable||busy||downloading} onClick={()=>setConfirm(true)}>다시 요약</button><button className="secondary" disabled={busy||downloading} onClick={()=>void download()}>Markdown 내려받기</button></div></>}
   {confirm&&<div className="confirmation"><p>같은 버전으로 새 실행을 만들며 실제 모드에서는 비용이 발생할 수 있습니다.</p><button className="primary" disabled={sending} onClick={()=>void submit('regenerate')}>새 실행으로 요약</button><button className="secondary" onClick={()=>setConfirm(false)}>재생성 취소</button></div>}
  </section>}
 </section>;
}
