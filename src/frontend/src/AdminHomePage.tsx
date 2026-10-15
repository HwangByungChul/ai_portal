import {useMemo} from 'react';
import {useRemote,blockReason} from './scoped';
import type {Tenant,Usage,AdminOverview,PendingRequestSummary,ApprovalPage} from './types';

const svcLabel:Record<string,string>={observed_ok:'정상',degraded:'성능 저하',unavailable:'중단',unknown:'상태 미수집'};
const svcColor:Record<string,{bg:string;color:string}>={
  observed_ok:{bg:'#ebf8f0',color:'#1d6a3c'},
  degraded:{bg:'#fffbe6',color:'#7a5700'},
  unavailable:{bg:'#fde8e8',color:'#9b1c1c'},
  unknown:{bg:'#edf2f7',color:'#4a5568'},
};

function BarChart({data,maxVal}:{data:{date:string;calls:number}[];maxVal:number}){
  return <div aria-label="일별 호출 추이 막대 차트" style={{display:'flex',alignItems:'flex-end',gap:'4px',height:'80px',padding:'0 4px'}}>
    {data.map(d=>{
      const pct=maxVal>0?Math.round((d.calls/maxVal)*100):0;
      const label=d.date.slice(5)+' · '+d.calls+'건';
      return <div key={d.date} title={label} aria-label={label} style={{flex:1,display:'flex',flexDirection:'column',alignItems:'center',gap:'2px'}}>
        <div style={{width:'100%',background:'#c3dafe',borderRadius:'3px 3px 0 0',height:pct+'%',minHeight:d.calls>0?'4px':'0',transition:'height .3s'}}/>
        <span style={{fontSize:'9px',color:'#6b7280',writingMode:'vertical-rl',transform:'rotate(180deg)',maxHeight:'40px',overflow:'hidden'}}>{d.date.slice(8)}</span>
      </div>;
    })}
  </div>;
}

function PendingRow({item,onApprovals}:{item:PendingRequestSummary;onApprovals:(id:string,kind:string)=>void}){
  return <button type="button" className="recent-item-row" onClick={()=>onApprovals(item.request_id,item.kind)}>
    <div className="recent-item-info">
      <strong>{item.asset_name}</strong>
      <span>{({dynamic:'동적 Agent',settings:'설정 변경',tool:'Tool 승인',workflow:'Workflow 승인',evidence:'시험 증적'})[item.kind]} · {new Date(item.created_at).toLocaleDateString('ko-KR')}</span>
    </div>
    <span className="agent-status-badge">검토 대기 →</span>
  </button>;
}

export function AdminHomePage({tenant,onApprovals,onUsage,onAssets,onMembers}:{tenant:Tenant;onApprovals:(id?:string,kind?:string)=>void;onUsage:()=>void;onAssets:()=>void;onMembers:()=>void}){
  const ov=useRemote<AdminOverview>('/admin/overview',tenant.tenant_id);
  const toolApprovals=useRemote<ApprovalPage>('/admin/tool-approvals?status=pending&limit=5',tenant.tenant_id);
  const workflowApprovals=useRemote<ApprovalPage>('/admin/workflow-approvals?status=pending&limit=5',tenant.tenant_id);
  const usage=useRemote<Usage>('/admin/usage',tenant.tenant_id);

  const currentDateStr=useMemo(()=>new Date().toLocaleDateString('ko-KR',{year:'numeric',month:'long',day:'numeric',weekday:'long'}),[]);

  const maxCalls=useMemo(()=>ov.data?Math.max(...ov.data.daily_calls.map(d=>d.calls),1):1,[ov.data]);
  const totalCalls=ov.data?.metrics.calls??0;
  const confirmedAmt=ov.data?.metrics.confirmed_amount??0;
  const unknownCalls=ov.data?.metrics.unknown_calls??0;
  const pendingTotal=ov.data&&toolApprovals.data&&workflowApprovals.data?ov.data.pending.total+toolApprovals.data.total_pending+workflowApprovals.data.total_pending:null;

  return <section className="admin-a-container" aria-labelledby="admin-home-title">
   <header className="admin-header-row">
    <div>
     <h1 id="admin-home-title">운영 현황</h1>
     <p className="muted" style={{marginTop:'4px',fontSize:'13px'}}>{tenant.display_name} · 플랫폼 운영 현황 및 리소스 모니터링</p>
    </div>
    <div style={{display:'flex',alignItems:'center',gap:'12px'}}>
     <span className="muted" style={{fontSize:'13px'}}>{currentDateStr}</span>
     <button className="secondary small" disabled={ov.loading||usage.loading} onClick={()=>{ov.setError(null);usage.setError(null);void ov.load();void usage.load();void toolApprovals.load();void workflowApprovals.load();}}>운영 현황 새로고침</button>
    </div>
   </header>

   {(ov.error||usage.error||toolApprovals.error||workflowApprovals.error)&&<p role="alert" className="error-message">{ov.error||usage.error||toolApprovals.error||workflowApprovals.error}</p>}
   {(ov.loading||usage.loading)&&<p role="status">운영 지표 확인 중...</p>}

   {/* 운영 알림 - usage 기존 블록 정보 */}
   {usage.data?.blocked&&<div className="blocked-note" role="alert" style={{margin:'0 0 12px 0'}}>
    <strong>운영 경보</strong>: {blockReason[usage.data.safe_block_reason??'']??'현재 조직 호출 제한 상태'}
   </div>}

   {/* 조회 기준 안내 */}
   {ov.data&&<div className="admin-scope-banner">
    <div><strong>집계 기준</strong>: {ov.data.period.from} ~ {ov.data.period.to} · 조회 기준 {new Date(ov.data.as_of).toLocaleTimeString('ko-KR',{hour:'2-digit',minute:'2-digit'})}</div>
    <div style={{fontSize:'12px'}}>공급자 최종 청구액과 다를 수 있습니다.</div>
   </div>}

   {/* 4대 핵심 지표 카드 */}
   <section className="admin-metrics-4col" aria-label="주요 운영 지표">
    <div className="metric-card-a">
     <span>집계 기간 AI 호출</span>
     {ov.data
       ? <strong>{totalCalls.toLocaleString()} 건</strong>
       : <strong className="muted">—</strong>}
     <small>전체 에이전트 누적 호출</small>
    </div>
    <div className="metric-card-a">
     <span>확인된 사용 추정 금액</span>
     {ov.data
       ? <strong>{Number(confirmedAmt).toLocaleString()} 원</strong>
       : <strong className="muted">—</strong>}
     <small>{ov.data?`예약 중: ${Number(ov.data.metrics.reserved_amount).toLocaleString()} 원`:'자료 없음'}</small>
    </div>
    <div className="metric-card-a">
     <span>전체 승인 대기 요청</span>
     {ov.data
       ? <strong>{pendingTotal===null?'조회 필요':pendingTotal.toLocaleString()+' 건'}</strong>
       : <strong className="muted">—</strong>}
     <small>{toolApprovals.data&&workflowApprovals.data?'Tool·Workflow 내가 검토 가능한 대기 '+(toolApprovals.data.actionable_pending+workflowApprovals.data.actionable_pending)+'건':'Tool·Workflow 검토 가능 대기 조회 필요'}</small>
    </div>
    <div className="metric-card-a">
     <span>사용량 확인 필요</span>
     {ov.data
       ? <strong>{unknownCalls.toLocaleString()} 건</strong>
       : <strong className="muted">—</strong>}
     <small>불명 사용량 0원 미확정 보존</small>
    </div>
   </section>

   {/* 중간 영역: 호출 추이 + 우선 승인 대기 요청 */}
   <section className="admin-mid-columns">
    {/* 좌측: 호출 추이 시계열 차트 영역 */}
    <div className="admin-chart-card">
     <div className="panel-heading">
      <h2>기간별 AI 호출 추이</h2>
      <span className="muted" style={{fontSize:'12px'}}>{ov.data?`${ov.data.period.from} ~ ${ov.data.period.to}`:'자료 없음'}</span>
     </div>
     {ov.loading&&<p role="status" style={{padding:'16px',textAlign:'center'}}>호출 추이 집계 중...</p>}
     {ov.data&&ov.data.daily_calls.length>0&&totalCalls===0&&
      <div style={{padding:'36px 16px',textAlign:'center',background:'#f8fafb',borderRadius:'8px',margin:'12px 0'}}>
       <p className="muted" style={{fontSize:'13px',margin:0}}>집계 기간 내 AI 호출 기록 없음</p>
       <small style={{color:'#718797',fontSize:'11px',marginTop:'4px',display:'block'}}>호출이 발생하면 이 화면에 자동으로 표시됩니다.</small>
      </div>}
     {ov.data&&totalCalls>0&&<BarChart data={ov.data.daily_calls} maxVal={maxCalls}/>}
     {!ov.data&&!ov.loading&&
      <div style={{padding:'36px 16px',textAlign:'center',background:'#f8fafb',borderRadius:'8px',margin:'12px 0'}}>
       <p className="muted" style={{fontSize:'13px',margin:0}}>시계열 호출 추이 모니터링 자료 없음</p>
       <small style={{color:'#718797',fontSize:'11px',marginTop:'4px',display:'block'}}>자료 조회 중 오류가 발생했습니다.</small>
      </div>}
     <p className="scope-note" style={{margin:0}}>상단 4대 핵심 지표 카드의 실측 집계 수치를 참조해 주세요.</p>
    </div>

    {/* 우측: 우선 검토 승인 요청 목록 */}
    <div className="admin-requests-card">
     <div className="panel-heading">
      <h2>우선 검토 승인 요청</h2>
      <button type="button" className="secondary small" onClick={()=>onApprovals()}>승인·검증 열기</button>
     </div>
     {ov.loading&&<p role="status">승인 요청 확인 중...</p>}
     <div className="home-recent-list">
      {toolApprovals.data?.items.map(item=>'tool_id' in item&&<PendingRow key={item.request_id} item={{kind:'tool',request_id:item.request_id,requester_id:item.requester_id,asset_name:item.tool_id,base_version:item.revision,created_at:item.created_at}} onApprovals={onApprovals}/>)}
      {workflowApprovals.data?.items.map(item=>'definition' in item&&<PendingRow key={item.version_id} item={{kind:'workflow',request_id:item.version_id,requester_id:item.created_by,asset_name:item.definition.name,base_version:item.revision,created_at:item.created_at}} onApprovals={onApprovals}/>)}
      {ov.data?.pending.items.map(item=><PendingRow key={item.request_id} item={item} onApprovals={onApprovals}/>)}
      {ov.data&&!ov.data.pending.items.length&&<p className="hub-empty">표시할 운영 설정·동적 Agent 배포 대기 요청이 없습니다.</p>}
     </div>
     {ov.data&&ov.data.pending.total>ov.data.pending.items.length&&
      <p className="scope-note" style={{margin:0}}>불러온 5건 외 추가 요청이 있습니다. 승인·검증 메뉴에서 확인하세요.</p>}
    </div>
   </section>

   {/* 하단 영역: 서비스 운영 상태 + 관리 바로가기 */}
   <section className="admin-mid-columns">
    {/* 좌측: 플랫폼 서비스 관측 상태 */}
    <div className="admin-service-status-card">
     <div className="panel-heading">
      <h2>공통 서비스 관측 상태</h2>
      <span className="service-status-badge" style={{background:'#edf2f7',color:'#4a5568'}}>관측 연동 준비 중</span>
     </div>
     <div className="service-status-list">
      {ov.data?.services.map(svc=>{
        const c=svcColor[svc.status]??svcColor.unknown;
        return <div className="service-status-row" key={svc.service_name}>
          <span>{svc.service_name}</span>
          <span className="service-status-badge" style={c}>{svcLabel[svc.status]??'알 수 없음'}</span>
        </div>;
      })}
      {!ov.data&&<>
        <div className="service-status-row"><span>AI Inference API Gateway</span><span className="service-status-badge" style={svcColor.unknown}>상태 미수집</span></div>
        <div className="service-status-row"><span>LLM Serving Cluster (vLLM / Ollama)</span><span className="service-status-badge" style={svcColor.unknown}>상태 미수집</span></div>
        <div className="service-status-row"><span>Vector Database (pgvector / Supabase)</span><span className="service-status-badge" style={svcColor.unknown}>상태 미수집</span></div>
      </>}
     </div>
    </div>

    {/* 우측: 관리 업무 바로가기 */}
    <div className="card" style={{margin:0}}>
     <div className="panel-heading">
      <h2>관리 업무 바로가기</h2>
      <span className="muted" style={{fontSize:'12px'}}>빠른 실행</span>
     </div>
     <div className="admin-shortcuts">
      <button type="button" className="secondary" onClick={onAssets}>AI 자산 및 Agent 설정 관리</button>
      <button type="button" className="secondary" onClick={onMembers}>조직 사용자 및 권한 관리</button>
      <button type="button" className="secondary" onClick={onUsage}>조직별 세부 사용량 및 과금 조회</button>
     </div>
     <p className="scope-note" style={{marginTop:'16px'}}>조직 전환 시 지표와 배포 요청을 현재 권한으로 다시 조회합니다.</p>
    </div>
   </section>
  </section>;
}
