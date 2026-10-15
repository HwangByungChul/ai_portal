import {useState,useEffect,useCallback} from 'react';
import type {Tenant,User,GuardrailPolicy,GuardrailViolation} from './types';

const RULE_LABELS:Record<string,string>={
  PII_RRN:'주민등록번호',PII_PHONE:'전화번호',PII_EMAIL:'이메일',PII_ACCOUNT:'계좌번호',
  PROMPT_INJECTION:'프롬프트 인젝션',FORBIDDEN_CONTENT:'금지 콘텐츠',
};
const SEVERITY_LABELS:Record<string,string>={block:'차단',warn:'경고',log:'기록만'};
const DIRECTION_LABELS:Record<string,string>={input:'입력',output:'출력'};

export function GuardrailPolicyPage({tenant,user}:{tenant:Tenant;user:User}){
  const [policy,setPolicy]=useState<GuardrailPolicy|null>(null);
  const [violations,setViolations]=useState<GuardrailViolation[]>([]);
  const [totalCount,setTotalCount]=useState(0);
  const [loading,setLoading]=useState(true);
  const [saving,setSaving]=useState(false);
  const [error,setError]=useState<string|null>(null);
  const [tab,setTab]=useState<'policy'|'violations'>('policy');

  const fetchPolicy=useCallback(async()=>{
    try{
      const res=await fetch('/api/v1/admin/guardrails/policies',{credentials:'include',headers:{'X-Requested-With':'ai-portal'}});
      if(!res.ok)throw new Error('FETCH_FAILED');
      const json=await res.json();setPolicy(json.data);
    }catch{setError('정책을 불러올 수 없습니다.');}
  },[]);

  const fetchViolations=useCallback(async()=>{
    try{
      const res=await fetch('/api/v1/admin/guardrails/violations',{credentials:'include',headers:{'X-Requested-With':'ai-portal'}});
      if(!res.ok)throw new Error('FETCH_FAILED');
      const json=await res.json();setViolations(json.data.items);setTotalCount(json.data.total_count);
    }catch{setError('위반 이력을 불러올 수 없습니다.');}
  },[]);

  useEffect(()=>{setLoading(true);Promise.all([fetchPolicy(),fetchViolations()]).finally(()=>setLoading(false));},[fetchPolicy,fetchViolations]);

  const updateField=async(field:string,value:any)=>{
    if(!policy)return;
    setSaving(true);setError(null);
    try{
      const res=await fetch('/api/v1/admin/guardrails/policies',{method:'PUT',credentials:'include',
        headers:{'Content-Type':'application/json','X-Requested-With':'ai-portal','X-CSRF-Token':user.csrf_token},
        body:JSON.stringify({expected_revision:policy.revision,[field]:value})});
      if(!res.ok){const j=await res.json().catch(()=>null);throw new Error(j?.error?.code||'UPDATE_FAILED');}
      const json=await res.json();setPolicy((p:GuardrailPolicy|null)=>p?{...p,...json.data}:p);
    }catch(e:any){setError(e.message==='REVISION_CONFLICT'?'다른 변경이 반영되었습니다. 새로고침해 주세요.':'정책 변경에 실패했습니다.');}
    finally{setSaving(false);}
  };

  if(loading)return <section className="workspace-empty"><p>보호 정책을 불러오는 중…</p></section>;

  return <div className="admin-a-container">
    <header style={{display:'flex',justifyContent:'space-between',alignItems:'center',marginBottom:'1.2rem'}}>
      <div><h1 style={{fontSize:'1.5rem',fontWeight:700,margin:0}}>🛡️ 보호 정책 (가드레일)</h1>
        <p style={{color:'var(--color-text-secondary)',margin:'0.3rem 0 0'}}>AI 입출력 전 과정의 콘텐츠 보호 규칙을 관리합니다.</p></div>
      {policy&&<span className="badge" style={{background:'var(--color-surface-hover)',padding:'0.3rem 0.8rem',borderRadius:'6px',fontSize:'0.82rem'}}>엔진 {policy.engine_revision} · 정책 rev.{policy.revision}</span>}
    </header>
    {error&&<div role="alert" style={{background:'#fef2f2',border:'1px solid #fca5a5',borderRadius:'8px',padding:'0.75rem 1rem',marginBottom:'1rem',color:'#991b1b',fontSize:'0.9rem'}}>{error}</div>}
    <div style={{display:'flex',gap:'0.5rem',marginBottom:'1.5rem'}}>
      <button onClick={()=>setTab('policy')} className={tab==='policy'?'btn-primary':'btn-secondary'} style={{padding:'0.5rem 1.2rem',borderRadius:'8px',border:'none',cursor:'pointer',fontWeight:tab==='policy'?600:400}}>정책 설정</button>
      <button onClick={()=>{setTab('violations');fetchViolations();}} className={tab==='violations'?'btn-primary':'btn-secondary'} style={{padding:'0.5rem 1.2rem',borderRadius:'8px',border:'none',cursor:'pointer',fontWeight:tab==='violations'?600:400}}>위반 이력 ({totalCount})</button>
    </div>
    {tab==='policy'&&policy&&<div style={{display:'grid',gap:'1rem'}}>
      <div className="admin-chart-card" style={{padding:'1.5rem'}}>
        <h3 style={{fontSize:'1.1rem',fontWeight:600,marginBottom:'1rem'}}>입력 가드레일</h3>
        <div style={{display:'flex',alignItems:'center',gap:'1rem',marginBottom:'1rem'}}>
          <label style={{fontWeight:500}}>입력 검사</label>
          <button onClick={()=>updateField('input_enabled',!policy.input_enabled)} disabled={saving}
            style={{padding:'0.4rem 1rem',borderRadius:'6px',border:'1px solid var(--color-border)',cursor:'pointer',
              background:policy.input_enabled?'var(--color-primary)':'var(--color-surface)',color:policy.input_enabled?'#fff':'inherit'}}>
            {policy.input_enabled?'활성':'비활성'}
          </button>
        </div>
        <div style={{display:'flex',flexWrap:'wrap',gap:'0.5rem'}}>
          {policy.input_rules.map((r:string)=><span key={r} style={{background:'var(--color-surface-hover)',padding:'0.3rem 0.7rem',borderRadius:'16px',fontSize:'0.82rem'}}>
            {RULE_LABELS[r]||r}
          </span>)}
        </div>
        <div style={{marginTop:'1rem',display:'flex',gap:'1.5rem'}}>
          <div><label style={{fontSize:'0.85rem',color:'var(--color-text-secondary)'}}>PII 심각도</label>
            <select value={policy.pii_severity} onChange={e=>updateField('pii_severity',e.target.value)} disabled={saving}
              style={{display:'block',marginTop:'0.3rem',padding:'0.35rem 0.6rem',borderRadius:'6px',border:'1px solid var(--color-border)'}}>
              {Object.entries(SEVERITY_LABELS).map(([k,v])=><option key={k} value={k}>{v}</option>)}
            </select></div>
          <div><label style={{fontSize:'0.85rem',color:'var(--color-text-secondary)'}}>인젝션 심각도</label>
            <select value={policy.injection_severity} onChange={e=>updateField('injection_severity',e.target.value)} disabled={saving}
              style={{display:'block',marginTop:'0.3rem',padding:'0.35rem 0.6rem',borderRadius:'6px',border:'1px solid var(--color-border)'}}>
              {Object.entries(SEVERITY_LABELS).map(([k,v])=><option key={k} value={k}>{v}</option>)}
            </select></div>
        </div>
      </div>
      <div className="admin-chart-card" style={{padding:'1.5rem'}}>
        <h3 style={{fontSize:'1.1rem',fontWeight:600,marginBottom:'1rem'}}>출력 가드레일</h3>
        <div style={{display:'flex',alignItems:'center',gap:'1rem',marginBottom:'1rem'}}>
          <label style={{fontWeight:500}}>출력 검사</label>
          <button onClick={()=>updateField('output_enabled',!policy.output_enabled)} disabled={saving}
            style={{padding:'0.4rem 1rem',borderRadius:'6px',border:'1px solid var(--color-border)',cursor:'pointer',
              background:policy.output_enabled?'var(--color-primary)':'var(--color-surface)',color:policy.output_enabled?'#fff':'inherit'}}>
            {policy.output_enabled?'활성':'비활성'}
          </button>
        </div>
        <div style={{display:'flex',flexWrap:'wrap',gap:'0.5rem',marginBottom:'1rem'}}>
          {policy.output_rules.map((r:string)=><span key={r} style={{background:'var(--color-surface-hover)',padding:'0.3rem 0.7rem',borderRadius:'16px',fontSize:'0.82rem'}}>
            {RULE_LABELS[r]||r}
          </span>)}
        </div>
        <div><label style={{fontSize:'0.85rem',color:'var(--color-text-secondary)'}}>PII 출력 처리</label>
          <select value={policy.output_pii_action} onChange={e=>updateField('output_pii_action',e.target.value)} disabled={saving}
            style={{display:'block',marginTop:'0.3rem',padding:'0.35rem 0.6rem',borderRadius:'6px',border:'1px solid var(--color-border)'}}>
            <option value="mask">마스킹 (***)</option><option value="block">전면 차단</option>
          </select></div>
      </div>
      <div className="admin-chart-card" style={{padding:'1.5rem',background:'var(--color-surface-hover)'}}>
        <h3 style={{fontSize:'1.05rem',fontWeight:600,marginBottom:'0.6rem'}}>🔗 DRM/DLP 어댑터</h3>
        <p style={{color:'var(--color-text-secondary)',fontSize:'0.9rem',margin:0}}>기관 DRM/DLP 연동 인터페이스는 계약 수준으로 정의되어 있습니다. 실제 연동은 기관 환경 확보 후 별도 구현합니다.</p>
        <span style={{display:'inline-block',marginTop:'0.5rem',background:'#fef3c7',color:'#92400e',padding:'0.25rem 0.7rem',borderRadius:'12px',fontSize:'0.8rem',fontWeight:500}}>후속 연동 예정</span>
      </div>
    </div>}
    {tab==='violations'&&<div className="admin-chart-card" style={{padding:'1.5rem'}}>
      <h3 style={{fontSize:'1.1rem',fontWeight:600,marginBottom:'1rem'}}>위반 이력 (최근 50건)</h3>
      {violations.length===0?<p style={{color:'var(--color-text-secondary)',textAlign:'center',padding:'2rem'}}>기록된 위반이 없습니다.</p>:
      <div style={{overflowX:'auto'}}><table style={{width:'100%',borderCollapse:'collapse',fontSize:'0.88rem'}}>
        <thead><tr style={{borderBottom:'2px solid var(--color-border)'}}>
          <th style={{textAlign:'left',padding:'0.5rem'}}>시각</th>
          <th style={{textAlign:'left',padding:'0.5rem'}}>방향</th>
          <th style={{textAlign:'left',padding:'0.5rem'}}>규칙</th>
          <th style={{textAlign:'left',padding:'0.5rem'}}>콘텐츠 해시 (앞 16자)</th>
        </tr></thead>
        <tbody>{violations.map(v=><tr key={v.violation_id} style={{borderBottom:'1px solid var(--color-border)'}}>
          <td style={{padding:'0.5rem',whiteSpace:'nowrap'}}>{new Date(v.created_at).toLocaleString('ko-KR')}</td>
          <td style={{padding:'0.5rem'}}><span style={{background:v.direction==='input'?'#dbeafe':'#fce7f3',padding:'0.15rem 0.5rem',borderRadius:'8px',fontSize:'0.8rem'}}>{DIRECTION_LABELS[v.direction]}</span></td>
          <td style={{padding:'0.5rem'}}>{v.rule_ids.map((r:string)=>RULE_LABELS[r]||r).join(', ')}</td>
          <td style={{padding:'0.5rem',fontFamily:'monospace',fontSize:'0.8rem'}}>{v.content_hash.slice(0,16)}…</td>
        </tr>)}</tbody>
      </table></div>}
    </div>}
  </div>;
}
