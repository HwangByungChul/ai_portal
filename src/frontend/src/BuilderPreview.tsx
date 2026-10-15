import {useEffect,useRef,useState,useId} from 'react';
import {api} from './api';
import {BuilderTrial} from './BuilderTrial';
import {ReadableDocuments} from './ReadableDocuments';
import type {BuilderProfile} from './BuilderProfileEditor';
import {useScope} from './scoped';
import type {AssetDetail,Tenant,User} from './types';
type Ref={document_id:string;version_id:string};
type Preview={revision:number;version_id:string;config_hash:string;instructions?:string;messages?:{role:string;content:string}[];composition_hash:string;variables:string[];sources:Ref[];provider_called:false;kind:'composition_preview'};
export function BuilderPreview({detail,tenant,user,dirty,profile,onTrialLock}:{detail:AssetDetail;tenant:Tenant;user:User;dirty:boolean;profile?:BuilderProfile;onTrialLock?:(locked:boolean)=>void}){
 const inputId=useId();
 const scope=useScope(),sequence=useRef(0),lock=useRef(false);
 const names=[...new Set([...(profile?[profile.system_prompt,profile.developer_prompt,profile.user_template].join('\n'):detail.config.instructions).matchAll(/\{\{([A-Za-z][A-Za-z0-9_]{0,39})\}\}/g)].map(x=>x[1]))].sort();
 const [trialLocked,setTrialLocked]=useState(false);
 const [values,setValues]=useState<Record<string,string>>({}),[refs,setRefs]=useState<Ref[]>([]),[result,setResult]=useState<Preview|null>(null),[error,setError]=useState<string|null>(null),[busy,setBusy]=useState(false);
 useEffect(()=>{sequence.current++;setResult(null);setError(null);},[dirty]);
 async function preview(){if(lock.current||dirty)return;lock.current=true;const seq=++sequence.current;setBusy(true);setResult(null);setError(null);
  try{const value=await api.request<Preview>('/admin/builder/assets/'+detail.asset_id+(profile?'/versions/'+detail.version_id:'/')+(profile?'/preview':'preview'),{method:'POST',tenantId:tenant.tenant_id,csrf:user.csrf_token,signal:scope.signal,body:profile?{values}:{expected_revision:detail.latest_revision,values,document_refs:refs}});
   if(scope.current()&&seq===sequence.current)setResult(value);
  }catch(problem){const message=await scope.fail(problem,()=>setResult(null));if(scope.current()&&seq===sequence.current)setError(message);}
  finally{if(scope.current()){lock.current=false;setBusy(false);}}
 }
 useEffect(()=>{onTrialLock?.(trialLocked);},[trialLocked,onTrialLock]);
 const disabled=dirty||busy||trialLocked;
 return <section aria-label="프롬프트 조합 검증" className="confirmation"><h3>프롬프트 · RAG Playground</h3>
  <p className="scope-note">저장 버전 {detail.latest_revision}의 변수 치환과 자료 접근을 확인합니다. 조합 검증은 모델을 호출하지 않습니다. 아래에서 별도로 시험 실행할 수 있습니다.</p>
  {dirty&&<p role="status">수정한 초안을 저장한 뒤 검증해 주세요.</p>}
  {names.map(name=><div key={name}><label htmlFor={inputId+name}>변수 {name}</label><input id={inputId+name} disabled={disabled} maxLength={2000} value={values[name]??''} onChange={e=>{setResult(null);setValues({...values,[name]:e.target.value});}}/></div>)}
  {!names.length&&<p className="muted">변수를 사용하려면 지시문에 {'{{audience}}'} 형식으로 입력하세요.</p>}
  {!profile&&detail.config.execution_kind==='rules_rag'&&<ReadableDocuments tenantId={tenant.tenant_id} selected={refs} onChange={rows=>{setResult(null);setRefs(rows);}} disabled={disabled} emptyScope="none"/>}
  <button type="button" className="secondary" disabled={disabled||names.some(name=>!values[name]?.trim())} onClick={()=>void preview()}>{busy?'조합 확인 중':'저장 버전 조합 검증'}</button>
  {error&&<p role="alert" className="error-message">{error}</p>}
  {result&&<section aria-label="조합 검증 결과"><p role="status">조합 검증 완료 · 모델 호출 없음</p><p>저장 버전 {result.revision} · 접근 가능한 선택 자료 {result.sources.length}개</p>{result.messages?result.messages.map((message,index)=><div key={index}><h4>{message.role==='system'?'시스템':message.role==='developer'?'개발자':'사용자'} 프롬프트</h4><pre style={{whiteSpace:'pre-wrap',overflowWrap:'anywhere'}}>{message.content}</pre></div>):<><h4>치환된 지시문</h4><pre style={{whiteSpace:'pre-wrap',overflowWrap:'anywhere'}}>{result.instructions}</pre></>}<p className="scope-note">조합 지문 <code>{result.composition_hash}</code></p></section>}
  {profile&&<BuilderTrial detail={detail} tenant={tenant} user={user} values={values} invalid={names.some(name=>!values[name]?.trim())} dirty={dirty} onLock={setTrialLocked} onApply={setValues} documentRefs={profile.document_refs}/>}
 </section>;
}
