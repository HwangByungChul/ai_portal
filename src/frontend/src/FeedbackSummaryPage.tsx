import {useId,useState} from 'react';
import {modeLabel,useRemote} from './scoped';
import type {FeedbackSummary,Tenant} from './types';

export function FeedbackSummaryPage({tenant}:{tenant:Tenant}){
 const monthId=useId(),agentId=useId();const remote=useRemote<FeedbackSummary>('/admin/feedback/summary',tenant.tenant_id);
 const [month,setMonth]=useState(''),[agent,setAgent]=useState('');
 async function search(){remote.setError(null);const p=new URLSearchParams();if(month)p.set('period',month+'-01');if(agent)p.set('agent_key',agent);await remote.load('/admin/feedback/summary'+(p.size?'?'+p.toString():''));}
 return <section className="page-section"><div className="page-title"><p className="eyebrow">조직 관리</p><h1>답변 평가</h1><p className="muted">현재 조직의 활성 평가를 확인합니다.</p></div>
  <form className="card feedback-filter" onSubmit={e=>{e.preventDefault();void search();}}><div className="feedback-filter-field"><label htmlFor={monthId}>평가 집계 월</label><input id={monthId} type="month" min="2000-01" max="2100-12" value={month} onChange={e=>setMonth(e.target.value)}/></div><div className="feedback-filter-field"><label htmlFor={agentId}>평가 Agent</label><select id={agentId} value={agent} onChange={e=>setAgent(e.target.value)}><option value="">전체 Agent</option><option value="general">일반 대화</option><option value="rules_rag">규정 RAG</option></select></div><button className="secondary" disabled={remote.loading}>집계 조회</button></form>
  {remote.loading?<p role="status">집계 확인 중</p>:remote.data&&<section className="card"><p>{remote.data.period.slice(0,7)} · {modeLabel(remote.data.execution_mode)}</p><p className="scope-note">Agent별 참여자가 {remote.data.minimum_participants}명 이상일 때 건수를 표시합니다. 개인 질문·답변·원문 의견은 제공하지 않습니다.</p>
   <div className="feedback-summary-grid">{remote.data.items.map(item=><article className="feedback-summary-item" key={item.agent_key}><h2>{item.agent_key==='general'?'일반 대화':'규정 RAG'}</h2>{item.status==='suppressed'?<p>참여자가 적어 평가 건수를 표시하지 않습니다.</p>:item.status==='empty'?<p>해당 월의 활성 평가가 없습니다.</p>:<dl><div><dt>도움 됐어요</dt><dd>{item.positive_count}건</dd></div><div><dt>아쉬워요</dt><dd>{item.negative_count}건</dd></div><div><dt>전체 평가</dt><dd>{item.total_count}건</dd></div></dl>}</article>)}</div>
  </section>}
  {remote.error&&<p role="alert">{remote.error}</p>}
 </section>;
}
