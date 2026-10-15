import {AssetDeploymentRequest} from './AssetDeploymentRequest';
import {useEffect,useRef,useState} from 'react';
import {api} from './api';
import {useScope} from './scoped';
import type {Tenant,User} from './types';
type Row={share_id:string;status:string;revision:number;requester_id:string;created_at:string;asset_binding:{revision:number;version_id:string}};
type Detail={share_id:string;status:string;revision:number;requester_id:string;created_at:string;can_withdraw:boolean;snapshot:Record<string,unknown>|null;current_conditions:Record<string,boolean>|null;snapshot_hash:string|null};
export function SharedEvidenceReview({tenant,user}:{tenant:Tenant;user:User}){
 const scope=useScope(),seq=useRef(0),chosen=useRef(''),alive=useRef(true),lock=useRef(false);
 const [rows,setRows]=useState<Row[]>([]),[cursor,setCursor]=useState<string|null>(null),[detail,setDetail]=useState<Detail|null>(null),[busy,setBusy]=useState(false),[error,setError]=useState<string|null>(null),[notice,setNotice]=useState<string|null>(null);
 useEffect(()=>{alive.current=true;return()=>{alive.current=false;seq.current++;};},[]);
 async function fail(problem:unknown){const message=await scope.fail(problem,()=>{setRows([]);setCursor(null);setDetail(null);});if(alive.current&&scope.current())setError(message);}
 async function list(more=false){if(lock.current)return;lock.current=true;setBusy(true);setError(null);setDetail(null);chosen.current='';const current=++seq.current;
  try{const result=await api.request<{items:Row[];next_cursor:string|null}>('/admin/builder/evidence-shares'+(more&&cursor?'?cursor='+cursor:''),{tenantId:tenant.tenant_id,signal:scope.signal});if(alive.current&&scope.current()&&seq.current===current){setRows(old=>more?[...old,...result.items]:result.items);setCursor(result.next_cursor);}}
  catch(problem){if(seq.current===current){setRows([]);setCursor(null);await fail(problem);}}finally{if(alive.current&&scope.current()){lock.current=false;setBusy(false);}}
 }
 async function read(id:string,poll=false){if(lock.current&&!poll)return;const current=++seq.current;chosen.current=id;setError(null);if(!poll)setDetail(null);
  try{const result=await api.request<Detail>('/admin/builder/evidence-shares/'+id,{tenantId:tenant.tenant_id,signal:scope.signal});if(alive.current&&scope.current()&&seq.current===current&&chosen.current===id)setDetail(result);}
  catch(problem){if(seq.current===current){setDetail(null);await fail(problem);}}
 }
 useEffect(()=>{void list();},[scope.signal]);
 useEffect(()=>{if(!detail||detail.status!=='submitted'||busy)return;const id=detail.share_id;const timer=window.setInterval(()=>void read(id,true),5000);return()=>window.clearInterval(timer);},[detail?.share_id,detail?.status,busy,scope.signal]);
 async function withdraw(row:Row|Detail){if(lock.current)return;lock.current=true;setBusy(true);setNotice(null);setDetail(null);seq.current++;
  try{await api.request('/admin/builder/evidence-shares/'+row.share_id+'/withdraw',{method:'POST',tenantId:tenant.tenant_id,csrf:user.csrf_token,body:{expected_revision:row.revision},signal:scope.signal});if(alive.current&&scope.current())setNotice('증적 공유를 철회했습니다. 검토자에게 상세 증적이 제공되지 않습니다.');}
  catch(problem){await fail(problem);}
  finally{if(alive.current&&scope.current()){lock.current=false;setBusy(false);await list();await read(row.share_id);}}
 }
 return <section aria-label="Builder 시험 증적"><div className="page-heading"><h2>Builder 시험 증적</h2><button className="secondary" disabled={busy} onClick={()=>void list()}>증적 목록 새로고침</button></div><p>본인이 제출한 증적 또는 현재 조직에서 승인 담당자로 조회 가능한 증적입니다. 이 목록의 제출 상태는 승인·게시 완료를 의미하지 않습니다.</p>{error&&<p role="alert" className="error-message">{error}</p>}{notice&&<p role="status">{notice}</p>}<div className="approval-layout"><section className="approval-list" aria-label="공유 증적 목록">{rows.map(row=><div key={row.share_id}><button className="approval-row" disabled={busy} aria-pressed={chosen.current===row.share_id} onClick={()=>void read(row.share_id)}><strong>버전 {row.asset_binding.revision} · {row.status==='submitted'?'증적 제출 · 미승인':'공유 철회'}</strong><span>{new Date(row.created_at).toLocaleString('ko-KR')}</span><span>증적 {row.share_id.slice(0,8)}</span></button>{row.status==='submitted'&&row.requester_id===user.user_id&&<button className="secondary" disabled={busy} onClick={()=>void withdraw(row)}>증적 공유 철회</button>}</div>)}{!rows.length&&!busy&&<p>조회할 증적이 없습니다.</p>}{cursor&&<button disabled={busy} onClick={()=>void list(true)}>증적 더 보기</button>}</section><section className="card approval-detail" aria-label="공유 증적 상세">{detail?<><h3>{detail.status==='submitted'?'제출된 시험 증적':'철회된 증적'}</h3>{detail.snapshot?<><p>개인 질문·답변 원문·기대 문구는 공유되지 않습니다. 자동 조건 충족은 업무 품질 또는 배포 승인 판정이 아닙니다.</p><p>시험 모드: {detail.snapshot.execution_mode==='mock'?'모의 제공자':'실제 제공자'}</p><ul>{Object.entries(detail.current_conditions??{}).map(([name,passed])=><li key={name}>{({latest_version:'현재 최신 버전',same_profile:'프롬프트 지문',same_mode:'실행 모드',same_policy:'운영 정책 revision'} as Record<string,string>)[name]}: {passed?'일치':'변경됨 · 재검토 필요'}</li>)}</ul>{detail.can_withdraw&&detail.status==='submitted'&&detail.current_conditions&&Object.values(detail.current_conditions).every(Boolean)&&<AssetDeploymentRequest key={detail.share_id} shareId={detail.share_id} assetId={(detail.snapshot.asset_binding as {asset_id:string}).asset_id} tenant={tenant} user={user}/>}<details><summary>공유된 최소 증적과 지문</summary><pre style={{whiteSpace:'pre-wrap',overflowWrap:'anywhere'}}>{JSON.stringify({snapshot:detail.snapshot,snapshot_hash:detail.snapshot_hash},null,2)}</pre></details></>:<p>공유가 철회되어 상세 증적이 제공되지 않습니다.</p>}</>:<p>목록에서 증적을 선택하세요.</p>}</section></div></section>;
}
