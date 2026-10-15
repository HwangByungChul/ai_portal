import {useEffect,useRef,useState} from 'react';
import {api,ApiError} from './api';
import {BuilderPreview} from './BuilderPreview';
import {BuilderProfileEditor,BuilderVersionPanel,emptyProfile,type BuilderProfile,type BuilderVersion} from './BuilderProfileEditor';
import {get,useScope} from './scoped';
import type {AssetConfig,AssetDetail,AssetItem,AssetReceipt,PageResult,Tenant,User} from './types';
const empty=():AssetConfig=>({name:'',description:'',instructions:'',execution_kind:'general'});
export function AssetsPage({tenant,user,onLegacy,builder=false}:{tenant:Tenant;user:User;onLegacy:()=>void;builder?:boolean}){
 const scope=useScope(),org=tenant.tenant_id;
 const [items,setItems]=useState<AssetItem[]>([]),[cursor,setCursor]=useState<string|null>(null),[selected,setSelected]=useState<string|null>(null),[detail,setDetail]=useState<AssetDetail|null>(null);
 const [profile,setProfile]=useState<BuilderProfile>(emptyProfile),[storedProfile,setStoredProfile]=useState<BuilderProfile|null>(null);
 const [config,setConfig]=useState<AssetConfig>(empty),[loading,setLoading]=useState(false),[reading,setReading]=useState(false),[busy,setBusy]=useState(false),[conflict,setConflict]=useState(false);
 const [error,setError]=useState<string|null>(null),[notice,setNotice]=useState<string|null>(null),[uncertain,setUncertain]=useState(false);
 const pending=useRef<{path:string;body:Record<string,unknown>}|null>(null),lock=useRef(false),listQuery=useRef(0),detailQuery=useRef(0);
 async function fail(problem:unknown){const message=await scope.fail(problem,()=>{setItems([]);setCursor(null);setDetail(null);setConfig(empty());setProfile(emptyProfile());setStoredProfile(null);});if(scope.current())setError(message);}
 async function list(next:string|null=null){const version=++listQuery.current;setLoading(true);
  if(!next){setItems([]);setCursor(null);}
  try{const page=await get<PageResult<AssetItem>>('/admin/assets?limit=20'+(next?'&cursor='+next:''),{tenantId:org,signal:scope.signal});if(scope.current()&&version===listQuery.current){setItems(old=>next?[...old,...page.items]:page.items);setCursor(page.next_cursor);}}
  catch(problem){if(version===listQuery.current)await fail(problem);}finally{if(scope.current()&&version===listQuery.current)setLoading(false);}
 }
 async function read(id:string,preserve=false){const version=++detailQuery.current;setSelected(id);setReading(true);setDetail(null);
  try{const value=await get<AssetDetail>('/admin/assets/'+id,{tenantId:org,signal:scope.signal});if(scope.current()&&version===detailQuery.current){if(builder&&value.state==='draft'){const saved=await get<BuilderVersion>('/admin/builder/assets/'+id+'/versions/'+value.version_id,{tenantId:org,signal:scope.signal});if(!scope.current()||version!==detailQuery.current)return;setStoredProfile(saved.profile);if(!preserve)setProfile(saved.profile);}else setStoredProfile(null);setDetail(value);if(!preserve)setConfig(value.config);}}
  catch(problem){if(version===detailQuery.current){if(!preserve)setConfig(empty());await fail(problem);}}finally{if(scope.current()&&version===detailQuery.current)setReading(false);}
 }
 useEffect(()=>{void list();},[]);
 function choose(id:string){if(busy||uncertain)return;setError(null);setNotice(null);setConflict(false);void read(id);}
 function newDraft(){detailQuery.current++;setSelected(null);setDetail(null);setReading(false);setConfig(empty());setProfile(emptyProfile());setStoredProfile(null);setConflict(false);setError(null);setNotice(null);}
 async function save(){
  if(lock.current||reading||conflict||detail?.state==='legacy'||selected&&!detail)return;
  lock.current=true;setBusy(true);setError(null);setNotice(null);
  const request=pending.current??{path:selected?(builder?'/admin/builder/assets/':'/admin/assets/')+selected+'/versions':builder?'/admin/builder/assets':'/admin/assets',body:{client_request_id:crypto.randomUUID(),config,...(builder?{profile:{...profile,system_prompt:config.instructions,model_ref:'default_'+config.execution_kind,document_refs:config.execution_kind==='general'?[]:profile.document_refs}}:{}),...(detail?{expected_revision:detail.latest_revision}:{})}};
  pending.current=request;
  try{const receipt=await api.request<AssetReceipt>(request.path,{method:'POST',tenantId:org,csrf:user.csrf_token,signal:scope.signal,body:request.body});
   if(scope.current()){pending.current=null;setUncertain(false);await read(receipt.asset_id);await list();setNotice('초안 버전 '+receipt.revision+' 저장됨 · 운영 활성화 전');}}
  catch(problem){
   if(problem instanceof ApiError&&problem.status>0&&problem.status<500){pending.current=null;setUncertain(false);}else if(scope.current())setUncertain(true);
   await fail(problem);
   if(scope.current()&&problem instanceof ApiError&&problem.status===409&&selected&&problem.code==='REVISION_CONFLICT'){await read(selected,true);setConflict(true);setNotice('다른 수정이 저장되었습니다. 입력한 초안과 최신 버전을 비교한 뒤 다시 저장하세요.');}
   else if(scope.current()&&(!(problem instanceof ApiError)||problem.status===0||problem.status>=500))setNotice('저장 결과 확인이 필요합니다. 같은 요청 확인으로 중복 없이 결과를 조회하세요.');
  }finally{if(scope.current()){setBusy(false);lock.current=false;}}
 }
 async function cloneVersion(version:string){if(lock.current||uncertain||!selected)return;pending.current={path:'/admin/builder/assets/'+selected+'/clone',body:{client_request_id:crypto.randomUUID(),source_version_id:version}};await save();}
 const [trialLocked,setTrialLocked]=useState(false);
 const disabled=trialLocked||busy||reading||uncertain||detail?.state==='legacy';
 const valid=config.name.trim()&&config.instructions.trim()&&(!builder||profile.user_template.trim());
 const dirty=busy||uncertain||conflict||JSON.stringify(config)!==JSON.stringify(detail?.config)||!!storedProfile&&JSON.stringify({...profile,system_prompt:config.instructions,model_ref:'default_'+config.execution_kind,document_refs:config.execution_kind==='general'?[]:profile.document_refs})!==JSON.stringify(storedProfile);
 return <section aria-labelledby="assets-title"><div className="page-heading"><div><p className="eyebrow teal">AI ASSETS</p><h1 id="assets-title">{builder?'Agent Builder':'AI 자산 관리'}</h1><p className="muted">{tenant.display_name} · Agent 초안과 수정 이력을 관리합니다.</p></div><button className="primary" disabled={trialLocked||busy||uncertain} onClick={newDraft}>새 Agent 초안</button></div>
  {builder&&<p className="scope-note">지시문에 {'{{audience}}'} 형식의 변수를 넣고 저장 버전을 조합 검증할 수 있습니다. 저장한 버전으로 모델·RAG 시험을 실행하고 사용량과 결과를 확인할 수 있습니다.</p>}
  <p className="scope-note">새 자산은 초안으로 저장됩니다. 운영에 사용할 수 있는 Agent는 기존 Agent 관리에서 확인하세요.</p>
  {error&&<p role="alert" className="error-message">{error}</p>}{notice&&<p role="status" className="notice">{notice}</p>}
  <div className="approval-layout"><section className="approval-list" aria-label="AI 자산 목록"><div className="panel-heading"><h2>등록 자산</h2><button className="secondary small" disabled={trialLocked||loading||busy||uncertain} onClick={()=>{setError(null);void list();}}>목록 새로고침</button></div>
   {loading&&<p role="status">자산 목록 확인 중</p>}{items.map(item=><button className="approval-row" key={item.asset_id} aria-pressed={selected===item.asset_id} disabled={trialLocked||busy||uncertain} onClick={()=>choose(item.asset_id)}><strong>{item.name}</strong><span>{item.state==='legacy'?'기존 운영 Agent':'초안'} · 버전 {item.latest_revision}</span><span>{item.description}</span></button>)}
   {!loading&&!items.length&&<p className="card">등록된 자산이 없습니다.</p>}{cursor&&<button className="secondary" disabled={trialLocked||loading||busy||uncertain} onClick={()=>void list(cursor)}>자산 더 보기</button>}
  </section><section className="card approval-detail" aria-label="AI 자산 상세">
   <h2>{selected?'자산 상세':'새 Agent 초안'}</h2>{reading?<p role="status">자산 상세 확인 중</p>:<>
   {detail&&<><p className="approval-status">{detail.state==='legacy'?'기존 운영 Agent':'초안 버전 '+detail.latest_revision}</p><p className="scope-note">내용 지문 <code>{detail.config_hash}</code></p></>}
   <form className="settings-form" onSubmit={e=>{e.preventDefault();void save();}}><label htmlFor="asset-name">자산 이름</label><input id="asset-name" value={config.name} maxLength={80} disabled={disabled} onChange={e=>setConfig({...config,name:e.target.value})}/>
    <label htmlFor="asset-description">자산 설명</label><textarea id="asset-description" value={config.description} rows={2} maxLength={500} disabled={disabled} onChange={e=>setConfig({...config,description:e.target.value})}/>
    <label htmlFor="asset-engine">실행 방식</label><select id="asset-engine" value={config.execution_kind} disabled={disabled} onChange={e=>setConfig({...config,execution_kind:e.target.value as AssetConfig['execution_kind']})}><option value="general">일반 대화</option><option value="rules_rag">문서 근거 검색</option></select>
    <label htmlFor="asset-instructions">자산 지시문</label><textarea id="asset-instructions" value={config.instructions} rows={5} maxLength={2000} disabled={disabled} onChange={e=>setConfig({...config,instructions:e.target.value})}/>
    {builder&&detail?.state!=='legacy'&&<BuilderProfileEditor key={selected??'new'} profile={profile} onChange={setProfile} rag={config.execution_kind==='rules_rag'} tenantId={org} disabled={disabled}/>}
    {detail?.state==='legacy'?<button type="button" className="secondary" onClick={onLegacy}>기존 Agent 관리로 이동</button>:<button className="primary" disabled={trialLocked||busy||!valid||conflict||!!selected&&!detail}>{busy?'저장 확인 중':uncertain?'같은 요청 확인':selected?'새 초안 버전 저장':'초안 등록'}</button>}
   </form>
   {conflict&&detail&&<div className="confirmation"><h3>최신 저장 버전 {detail.latest_revision}</h3><p>{detail.config.name}</p><p>{detail.config.description}</p><p>실행 방식: {detail.config.execution_kind==='general'?'일반 대화':'문서 근거 검색'}</p><pre>{detail.config.instructions}</pre>{builder&&storedProfile&&<><h4>최신 개발자 프롬프트</h4><pre>{storedProfile.developer_prompt||'없음'}</pre><h4>최신 사용자 질문 템플릿</h4><pre>{storedProfile.user_template}</pre><p>선택 자료 {storedProfile.document_refs.length}개</p></>}<button className="secondary" disabled={busy} onClick={()=>setConflict(false)}>최신 버전을 기준으로 수정 계속</button></div>}
   {builder&&detail?.state==='draft'&&<BuilderPreview key={'preview:'+detail.asset_id+':'+detail.version_id} detail={detail} tenant={tenant} user={user} profile={storedProfile??undefined} dirty={!!dirty} onTrialLock={setTrialLocked}/>}
   {builder&&detail?.state==='draft'&&<BuilderVersionPanel key={'history:'+detail.asset_id+':'+detail.version_id} detail={detail} tenantId={org} disabled={disabled||conflict||!!dirty} onClone={version=>void cloneVersion(version)}/>}
   {!!detail?.versions.length&&<section aria-label="자산 버전 이력"><h3>버전 이력</h3><p className="scope-note">최근 50개 버전 · 저장한 내용과 지문은 보존됩니다.</p><ol>{detail.versions.map(version=><li key={version.version_id}>버전 {version.revision} · {new Date(version.created_at).toLocaleString('ko-KR')}<p className="scope-note"><code>{version.config_hash}</code></p></li>)}</ol>{detail.history_more&&<p className="scope-note">더 오래된 버전도 저장소에 보존되어 있습니다.</p>}</section>}
   </>}
  </section></div>
 </section>;
}
