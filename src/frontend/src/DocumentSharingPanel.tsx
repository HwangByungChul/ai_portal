import {useEffect,useState} from 'react';
import {api} from './api';
import {get,useScope} from './scoped';
import type {GrantPage,User} from './types';
export function DocumentSharingPanel({tenantId,documentId,versionId,user}:{tenantId:string;documentId:string;versionId:string;user:User}){
 const ctx=useScope();const [data,setData]=useState<GrantPage|null>(null),[targets,setTargets]=useState<{tenant_id:string;display_name:string}[]>([]),[recipient,setRecipient]=useState(''),[error,setError]=useState<string|null>(null),[busy,setBusy]=useState(false);const path='/admin/documents/'+documentId+'/versions/'+versionId+'/grants';
 async function load(){setData(null);try{const [page,list]=await Promise.all([get<GrantPage>(path,{tenantId,signal:ctx.signal}),get<{items:{tenant_id:string;display_name:string}[]}>('/admin/share-recipients',{tenantId,signal:ctx.signal})]);if(ctx.current()){setData(page);setTargets(list.items);}}
  catch(problem){const message=await ctx.fail(problem,()=>{setData(null);setTargets([]);});if(ctx.current()){setData(null);setError(message);}}}
 useEffect(()=>{void load();},[]);
 async function change(grant?:{grant_id:string;revision:number}){if(busy||!data||!grant&&!recipient)return;setBusy(true);setError(null);
  try{await api.request(grant?'/admin/grants/'+grant.grant_id:path,{method:grant?'DELETE':'POST',tenantId,csrf:user.csrf_token,signal:ctx.signal,body:grant?{expected_revision:grant.revision}:{recipient_tenant_id:recipient,expected_publication_revision:data.publication_revision}});}
  catch(problem){const message=await ctx.fail(problem,()=>setData(null));if(ctx.current())setError(message);}
  finally{if(ctx.current()){await load();setBusy(false);}}}
 return <section className="card" aria-label="버전 공유"><h3>선택 버전 공유</h3><p className="scope-note">이 버전에만 적용합니다. 새 버전은 따로 공유해야 합니다.</p>{error&&<p role="alert">{error}</p>}
  {data&&<><label>수신 조직 <select aria-label="수신 조직" value={recipient} disabled={busy} onChange={e=>setRecipient(e.target.value)}><option value="">선택해 주세요</option>{targets.map(x=><option key={x.tenant_id} value={x.tenant_id}>{x.display_name}</option>)}</select></label><button type="button" className="primary small" disabled={busy||!recipient} onClick={()=>void change()}>이 버전 공유</button>
   <ul>{data.items.map(x=><li key={x.grant_id}>{targets.find(t=>t.tenant_id===x.recipient_tenant_id)?.display_name??'허용 수신 조직'} · {x.active?'공유 중':'회수됨'} {x.active&&<button type="button" className="quiet small" disabled={busy} onClick={()=>void change(x)}>공유 회수</button>}</li>)}</ul></>}
 </section>;
}
