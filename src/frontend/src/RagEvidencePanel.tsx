import {useEffect,useRef,useState} from 'react';
import {sourceBlob} from './api';
import {get,useScope} from './scoped';
import type {Evidence} from './types';
export function RagEvidencePanel({tenantId,runId,onUnavailable}:{tenantId:string;runId:string;onUnavailable:()=>void}){
 const ctx=useScope();const [open,setOpen]=useState(false),[loaded,setLoaded]=useState(false),[rows,setRows]=useState<Evidence[]>([]),[error,setError]=useState<string|null>(null),[busy,setBusy]=useState(false);const active=useRef(false),request=useRef<AbortController|null>(null),urls=useRef(new Set<string>());
 function dispose(){request.current?.abort();for(const url of urls.current)URL.revokeObjectURL(url);urls.current.clear();}
 useEffect(()=>()=>{active.current=false;dispose();},[]);
 useEffect(()=>{if(!open)return;const c=new AbortController();request.current=c;const signal=AbortSignal.any([ctx.signal,c.signal]);let querying=false;
  async function load(){if(querying||document.visibilityState!=='visible'||signal.aborted)return;querying=true;
   try{const result=await get<{items:Evidence[]}>('/runs/'+runId+'/evidence',{tenantId,signal});if(ctx.current()&&!signal.aborted){if(result.items.some(x=>x.content_status==='unavailable')){setRows([]);onUnavailable();}else{setRows(result.items);setLoaded(true);setError(null);}}}
   catch(problem){if(ctx.current()&&!signal.aborted){setRows([]);const message=await ctx.fail(problem,()=>setRows([]));setError(message);onUnavailable();}}finally{querying=false;}}
  void load();const timer=setInterval(()=>void load(),5000);const visible=()=>void load();window.addEventListener('focus',visible);document.addEventListener('visibilitychange',visible);
  return()=>{clearInterval(timer);c.abort();dispose();window.removeEventListener('focus',visible);document.removeEventListener('visibilitychange',visible);};
 },[open,runId]);
 async function download(row:Evidence){if(busy||row.source_url!=='/api/v1/runs/'+runId+'/evidence/'+row.ordinal+'/source')return;setBusy(true);setError(null);
  try{const signal=AbortSignal.any([ctx.signal,request.current!.signal]);const blob=await sourceBlob(runId,row.ordinal,{tenantId,signal},row.source_media_type??'text/plain');if(!ctx.current()||signal.aborted||!active.current)return;
   const url=URL.createObjectURL(blob);urls.current.add(url);const link=document.createElement('a');link.href=url;link.download=row.source_media_type==='application/pdf'?'document.pdf':'document.txt';link.click();setTimeout(()=>{URL.revokeObjectURL(url);urls.current.delete(url);},1000);
  }catch(problem){if(ctx.current()){setRows([]);setError(await ctx.fail(problem,()=>setRows([])));onUnavailable();}}finally{if(ctx.current())setBusy(false);}}
 return <section className="evidence-panel" aria-label="답변 근거"><button type="button" className="secondary small" aria-expanded={open} onClick={()=>{active.current=!open;if(open){dispose();setRows([]);setLoaded(false);}setOpen(!open);}}>근거 {open?'닫기':'보기'}</button>
  {open&&<div>{error&&<p role="alert">{error}</p>}{!rows.length&&!error&&<p role="status">{loaded?'현재 표시할 인용 근거가 없습니다.':'표시할 근거를 확인하고 있습니다.'}</p>}
   {rows.map(row=><article key={row.ordinal}><strong>[{row.ordinal+1}] {row.title} · v{row.version_no}</strong><p>{row.source_media_type==='application/pdf'?`원문 ${row.page_start}~${row.page_end}페이지`:`원문 ${row.location?.line_start}~${row.location?.line_end}행`}</p><blockquote>{row.quote}</blockquote><button type="button" className="secondary small" disabled={busy} onClick={()=>void download(row)}>원문 내려받기</button></article>)}
  </div>}
 </section>;
}
