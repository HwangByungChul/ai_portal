import {PublishedAgents} from './PublishedAgents';
import {useEffect,useRef,useState} from 'react';
import {api,ApiError} from './api';
import {get,useScope,blockReason} from './scoped';
import type {CatalogItem,PageResult,Tenant,User,ChatLaunch} from './types';
type Pending={asset:CatalogItem;body:{client_request_id:string;expected_revision:number;active:boolean}};
export function CatalogPage({tenant,user,mine=false,onChat}:{tenant:Tenant;user:User;mine?:boolean;onChat:(launch:ChatLaunch)=>void}){
 const scope=useScope(),[items,setItems]=useState<CatalogItem[]>([]),[cursor,setCursor]=useState<string|null>(null),[selected,setSelected]=useState<CatalogItem|null>(null);
 const [q,setQ]=useState(''),[category,setCategory]=useState('all'),[loading,setLoading]=useState(false),[busy,setBusy]=useState(false),[error,setError]=useState<string|null>(null),[notice,setNotice]=useState<string|null>(null),[pending,setPending]=useState<Pending|null>(null);
 const query=useRef(0),detailQuery=useRef(0),lock=useRef(false),filter=useRef({q:'',category:'all'});
 async function load(more=false){
  const version=++query.current;++detailQuery.current;setLoading(true);setError(null);setSelected(null);if(!more){setItems([]);setCursor(null);}
  const params=new URLSearchParams({...filter.current,mine:String(mine),limit:'20',...(more&&cursor?{cursor}:{})});
  try{const data=await get<PageResult<CatalogItem>>('/catalog/assets?'+params,{tenantId:tenant.tenant_id,signal:scope.signal});if(scope.current()&&version===query.current){setItems(old=>more?[...old,...data.items]:data.items);setCursor(data.next_cursor);}}
  catch(problem){const message=await scope.fail(problem,()=>{setItems([]);setSelected(null);});if(scope.current()&&version===query.current)setError(message);}
  finally{if(scope.current()&&version===query.current)setLoading(false);}
 }
 useEffect(()=>{void load();},[]);
 async function detail(asset:CatalogItem){const version=++detailQuery.current;setSelected(null);setError(null);try{const value=await get<CatalogItem>('/catalog/assets/'+asset.asset_id,{tenantId:tenant.tenant_id,signal:scope.signal});if(scope.current()&&version===detailQuery.current)setSelected(value);}catch(problem){const message=await scope.fail(problem,()=>{setItems([]);setSelected(null);});if(scope.current()&&version===detailQuery.current)setError(message);}}
 async function favorite(asset?:CatalogItem){
  if(lock.current)return;const request=pending??(asset?{asset,body:{client_request_id:crypto.randomUUID(),expected_revision:asset.favorite_revision,active:!asset.favorite}}:null);if(!request)return;
  lock.current=true;setBusy(true);setPending(request);setError(null);setNotice(null);
  try{await api.request('/catalog/assets/'+request.asset.asset_id+'/favorite',{method:'PUT',tenantId:tenant.tenant_id,csrf:user.csrf_token,signal:scope.signal,body:request.body});if(scope.current()){setPending(null);setNotice('즐겨찾기를 저장했습니다.');await load();}}
  catch(problem){
   const uncertain=!(problem instanceof ApiError)||problem.status===0||problem.status>=500;
   if(scope.current()&&!uncertain)setPending(null);
   const message=await scope.fail(problem,()=>{setItems([]);setSelected(null);});
   if(scope.current()){if(uncertain)setError('저장 결과 확인이 필요합니다. 같은 요청으로 다시 확인해 주세요.');else{if(problem instanceof ApiError&&[404,409].includes(problem.status))await load();setError(message);}}
  }finally{if(scope.current()){setBusy(false);lock.current=false;}}
 }
 const frozen=busy||!!pending;
 return <section><div className="page-heading"><div><p className="eyebrow teal">{mine?'MY AGENT':'AI CATALOG'}</p><h1>{mine?'My Agent':'AI 카탈로그'}</h1><p className="muted">{tenant.display_name} · 이용 권한이 있는 업무 도우미를 찾아 시작하세요.</p></div><button className="secondary" disabled={frozen||loading} onClick={()=>void load()}>새로고침</button></div>
 {!mine&&<PublishedAgents tenant={tenant} user={user} onFavoriteChange={()=>void load()}/>}{mine&&<PublishedAgents tenant={tenant} user={user} onFavoriteChange={()=>void load()}/>}<p className="scope-note">즐겨찾기는 개인 목록입니다. 관리자가 이용 권한을 회수하면 목록에서 숨겨지고 신규·후속 실행이 제한됩니다.</p>
 {!mine&&<div style={{display:'flex',gap:'8px',marginBottom:'12px'}}>
  {(['all','agent','tool','workflow'] as const).map(t=><button key={t} type="button" className={category===t||(t==='all'&&category==='all')?'primary small':'secondary small'} onClick={()=>{setCategory(t);filter.current={q,category:t};void load();}}>
   {{all:'전체 자산',agent:'AI 에이전트',tool:'도구 (MCP)',workflow:'워크플로우'}[t]}
  </button>)}
 </div>}
 <form className="hub-actions catalog-filters" onSubmit={e=>{e.preventDefault();filter.current={q,category};void load();}}><label htmlFor="catalog-query">도우미 검색</label><input id="catalog-query" value={q} maxLength={80} disabled={frozen} onChange={e=>setQ(e.target.value)}/><label htmlFor="catalog-category">업무 구분</label><select id="catalog-category" value={category} disabled={frozen} onChange={e=>setCategory(e.target.value)}><option value="all">전체 업무</option><option value="general">일반 업무</option><option value="knowledge">지식 검색</option></select><button className="primary" disabled={frozen||loading}>검색</button></form>
 {error&&<p role="alert" className="error-message">{error}</p>}{notice&&<p role="status" className="notice">{notice}</p>}{pending&&<button className="primary" disabled={busy} onClick={()=>void favorite()}>같은 즐겨찾기 요청 확인</button>}
 {loading&&<p role="status">도우미 조회 중</p>}
 <div className="catalog-layout"><section className="card" aria-label="도우미 목록"><div className="hub-agent-grid">{items.map(item=><article className="catalog-item" key={item.asset_id}><button className="hub-agent" disabled={frozen||loading} onClick={()=>void detail(item)}><strong>{item.name}</strong><span>{item.description||'업무 도우미'}</span><small>{item.available?'업무 시작 가능':blockReason[item.safe_block_reason??'']??'현재 실행 제한'}</small></button><button className="secondary small" aria-label={item.name+(item.favorite?' 즐겨찾기 해제':' 즐겨찾기 추가')} disabled={frozen||loading} onClick={()=>void favorite(item)}>{item.favorite?'★ 즐겨찾기 해제':'☆ 즐겨찾기 추가'}</button></article>)}</div>{!loading&&!items.length&&<p className="hub-empty">{mine?'이용 가능한 즐겨찾기가 없습니다. AI 카탈로그에서 추가해 주세요.':'검색 조건에 맞는 이용 가능한 도우미가 없습니다.'}</p>}{cursor&&<button className="secondary" disabled={frozen||loading} onClick={()=>void load(true)}>더 보기</button>}</section>
 <aside className="card" aria-label="도우미 상세">{selected?<><h2>{selected.name}</h2><p>{selected.description||'설명 없음'}</p><p className="scope-note">운영 설정 버전 {selected.revision} · {selected.category==='knowledge'?'접근 가능한 자료를 근거로 답변':'일반 업무 대화'}</p>{!selected.available&&<p role="status">{blockReason[selected.safe_block_reason??'']??'현재 실행 제한'}</p>}<button className="primary" disabled={frozen||!selected.available} onClick={()=>onChat({agentKey:selected.agent_key,assetId:selected.asset_id})}>이 도우미로 업무 시작</button></>:<p className="muted">도우미를 선택하면 설명과 실행 상태를 확인할 수 있습니다.</p>}</aside></div></section>;
}
