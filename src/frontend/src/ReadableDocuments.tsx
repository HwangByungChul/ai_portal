import {useEffect,useRef,useState} from 'react';
import {get,useScope} from './scoped';
import type {DocumentRef,ReadableDocument,PageResult} from './types';
export function ReadableDocuments({tenantId,selected=[],onChange,disabled=false,emptyScope='readable',clearOnLoad=true}:{tenantId:string;selected?:DocumentRef[];onChange?:(rows:DocumentRef[])=>void;disabled?:boolean;emptyScope?:'readable'|'none';clearOnLoad?:boolean}){
 const ctx=useScope();const [rows,setRows]=useState<ReadableDocument[]>([]),[cursor,setCursor]=useState<string|null>(null),[scope,setScope]=useState(''),[error,setError]=useState<string|null>(null),[loading,setLoading]=useState(true);const query=useRef(0);
 async function load(next:string|null=null){const q=++query.current;setLoading(true);setError(null);if(!next){setRows([]);if(clearOnLoad)onChange?.([]);}
  try{const params=new URLSearchParams({limit:'20'});if(scope)params.set('scope',scope);if(next)params.set('cursor',next);
   const page=await get<PageResult<ReadableDocument>>('/documents?'+params,{tenantId,signal:ctx.signal});if(ctx.current()&&q===query.current){setRows(old=>next?[...old,...page.items]:page.items);setCursor(page.next_cursor);}
  }catch(problem){const message=await ctx.fail(problem,()=>{setRows([]);if(clearOnLoad)onChange?.([]);});if(ctx.current()&&q===query.current){setRows([]);onChange?.([]);setError(message);}}
  finally{if(ctx.current()&&q===query.current)setLoading(false);}}
 useEffect(()=>{void load();},[scope]);
 const names={org:'조직',private:'개인',shared:'공유'};
 function toggle(row:ReadableDocument){const exists=selected.some(x=>x.document_id===row.document_id&&x.version_id===row.version_id);onChange?.(exists?selected.filter(x=>x.document_id!==row.document_id||x.version_id!==row.version_id):[...selected,{document_id:row.document_id,version_id:row.version_id}]);}
 return <section className="card document-picker" aria-label="읽을 수 있는 자료"><div className="panel-heading"><h2>읽을 수 있는 자료</h2><button type="button" className="secondary small" disabled={loading||disabled} onClick={()=>void load()}>자료 새로고침</button></div>
  <label>자료 범위 <select aria-label="자료 범위" value={scope} disabled={disabled} onChange={e=>setScope(e.target.value)}><option value="">전체</option><option value="org">조직</option><option value="private">개인</option><option value="shared">공유</option></select></label>
  {onChange&&<p className="scope-note">최대 5개 버전을 선택할 수 있습니다. {emptyScope==='none'?'선택하지 않으면 검증 자료 범위는 비어 있습니다.':'선택하지 않으면 현재 읽을 수 있는 자료에서 검색합니다.'}</p>}
  {error&&<p role="alert">{error}</p>}{loading&&<p role="status">자료 확인 중</p>}
  {!loading&&!rows.length&&<p className="muted">현재 읽을 수 있는 게시 자료가 없습니다.</p>}
  <ul className="document-list">{rows.map(row=>{const checked=selected.some(x=>x.document_id===row.document_id&&x.version_id===row.version_id);return <li key={row.version_id}>{onChange?<label><input type="checkbox" checked={checked} disabled={disabled||!checked&&selected.length>=5} onChange={()=>toggle(row)}/>{row.title} · {row.safe_version_label} · {names[row.visibility]}</label>:<span>{row.title} · {row.safe_version_label} · {names[row.visibility]}</span>}</li>;})}</ul>
  {cursor&&<button type="button" className="secondary small" disabled={loading||disabled} onClick={()=>void load(cursor)}>자료 더 보기</button>}
 </section>;
}
