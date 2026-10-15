import {useState, useMemo} from 'react';
import {useRemote} from './scoped';
import type {AgentSummary,Conversation,PageResult,Tenant,User,ChatLaunch} from './types';

type DynamicFav={asset_id:string;name:string;description:string;revision:number;available:boolean;safe_block_reason:string|null;favorite:boolean;favorite_revision:number};

export function HomePage({tenant,user,onChat,onDocuments,onSummary,onCatalog,onMine,onUseCases}:{tenant:Tenant;user:User;onChat:(launch:ChatLaunch)=>void;onDocuments:()=>void;onSummary:()=>void;onCatalog:()=>void;onMine:()=>void;onUseCases?:()=>void}){
 const agents=useRemote<PageResult<AgentSummary>>('/agents',tenant.tenant_id);
 const recent=useRemote<PageResult<Conversation>>('/conversations?limit=5',tenant.tenant_id);
 const dynFavs=useRemote<{items:DynamicFav[];next_cursor:string|null}>('/published-agents?mine=true',tenant.tenant_id);
 const [prompt,setPrompt]=useState('');

 const currentDateStr = useMemo(() => {
  return new Date().toLocaleDateString('ko-KR', {
   year: 'numeric',
   month: 'long',
   day: 'numeric',
   weekday: 'long'
  });
 }, []);

 return <section className="home-a-container" aria-labelledby="home-greeting-heading">
  {/* 1단: 환영 인사 및 일자 헤더 */}
  <header className="home-greeting-bar">
   <div>
    <h1 id="home-greeting-heading">안녕하세요, {user.display_name}님. 오늘 어떤 업무를 도와드릴까요?</h1>
    <p className="muted" style={{marginTop: '4px', fontSize: '13px'}}>{tenant.display_name} 전용 업무 공간</p>
   </div>
   <div className="home-date-badge">{currentDateStr}</div>
  </header>

  {/* 2단: 분할 업무 시작 카드 (7:3 비율) */}
  <section className="home-split-hero" aria-label="업무 질문 및 시작 안내">
   <div className="home-prompt-card">
    <form onSubmit={e=>{e.preventDefault(); if(prompt.trim()) onChat({prompt,agentKey:'general'});}}>
     <div className="home-prompt-header-row">
      <label htmlFor="home-prompt">시작할 업무 질문</label>
      <span className="home-guardrail-pill" title="사내 보안 정책 준수">
       <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/></svg>
       사내 보안 가드레일 작동 중
      </span>
     </div>
     <textarea
      id="home-prompt"
      maxLength={4000}
      rows={3}
      value={prompt}
      onChange={e=>setPrompt(e.target.value)}
      placeholder="회의 안건을 정리하거나 규정 확인, 보고서 초안 작성 내용을 입력해 주세요. (Shift+Enter 줄바꿈)"
     />
     {agents.data&&!agents.data.items.some(a=>a.agent_key==='general')&&<p className="scope-note">일반 대화 이용 권한이 없습니다. 카탈로그에서 사용 가능한 도우미를 확인해 주세요.</p>}
     <div className="home-prompt-footer">
      <div className="home-examples-chips" aria-label="추천 업무 예시">
       <span className="chips-label">추천 예시:</span>
       {['사내 규정 질의','업무 보고서 초안','회의 안건 정리','데이터 분석 보조'].map(text=><button type="button" className="home-chip-btn" key={text} onClick={()=>setPrompt(text)}>{text}</button>)}
      </div>
      <div className="home-prompt-actions">
       <div className="home-scope-pill" title="현재 조직에 허가된 지식만 안전하게 활용">
        <span>자료 범위: 사내 승인 문서</span>
       </div>
       <button type="button" className="secondary" onClick={onDocuments}>문서 첨부·관리</button>
       <button type="submit" className="primary home-start-chat-btn" disabled={!prompt.trim()||!agents.data?.items.some(a=>a.agent_key==='general')}>대화 시작 →</button>
      </div>
     </div>
    </form>
   </div>

   <div className="home-guide-card">
    <div className="guide-card-header">
     <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><circle cx="12" cy="12" r="10"/><path d="M9.09 9a3 3 0 0 1 5.83 1c0 2-3 3-3 3"/><line x1="12" y1="17" x2="12.01" y2="17"/></svg>
     <h3>3분 이용 가이드</h3>
    </div>
    <ul>
     <li>질문창에 업무 내용을 입력하면 최적의 에이전트와 대화를 시작합니다.</li>
     <li>문서 등록·관리에서 업무 문서를 등록하고 AI 근거로 활용하세요.</li>
     <li>표준 업무 Agent의 설명과 업무 예시를 확인하세요.</li>
     <li>AI 카탈로그에서 조직 맞춤형 전문 도우미를 탐색할 수 있습니다.</li>
    </ul>
    <div style={{marginTop: 'auto', paddingTop: '10px'}}>
     <button type="button" className="quiet small guide-link-btn" onClick={onCatalog}>카탈로그 전체 보기 →</button>
    </div>
   </div>
  </section>

  {/* 10대 표준 업무 Agent 배너 카드 */}
  {onUseCases&&<div style={{background:'linear-gradient(135deg, #eff6ff 0%, #f0fdf4 100%)',border:'1px solid #bfdbfe',borderRadius:'12px',padding:'1.1rem 1.4rem',display:'flex',justifyContent:'space-between',alignItems:'center',gap:'1rem',marginTop:'0.5rem',marginBottom:'1.5rem'}}>
   <div>
    <div style={{display:'flex',alignItems:'center',gap:'0.5rem',marginBottom:'0.25rem'}}>
     <span style={{background:'#2563eb',color:'#fff',fontSize:'0.75rem',fontWeight:700,padding:'0.15rem 0.5rem',borderRadius:'12px'}}>준비 중</span>
     <strong style={{fontSize:'1.05rem',color:'#1e3a8a'}}>🏢 표준 업무 Agent 안내</strong>
    </div>
    <p style={{fontSize:'0.88rem',color:'#2563eb',margin:0}}>
     규정, 문서, 상품 비교 등 10종의 업무 도우미를 검토하고 있습니다. 실행 기능은 준비 후 제공됩니다.
    </p>
   </div>
   <button type="button" className="primary" onClick={onUseCases} style={{whiteSpace:'nowrap',padding:'0.55rem 1.1rem',fontSize:'0.9rem',fontWeight:600}}>
    업무 Agent 열기 →
   </button>
  </div>}

  {/* 3단: 업무별 AI 도우미 가로 4열 카드 그리드 */}
  <section className="home-agents-section" aria-label="업무별 AI 도우미">
   <div className="section-header">
    <div style={{display: 'flex', alignItems: 'center', gap: '12px'}}>
     <h2>업무별 AI 도우미</h2>
     <button type="button" className="quiet small" onClick={()=>{void agents.load();void dynFavs.load();}}>새로고침</button>
    </div>
    <button type="button" className="see-all-link" onClick={onCatalog}>전체 에이전트 보기 →</button>
   </div>

   {agents.loading&&<p role="status">도우미 목록 확인 중...</p>}
   {agents.error&&<p role="alert" className="error-message">{agents.error}</p>}

   <div className="home-agent-grid-4col">
    {agents.data?.items.map(agent=><article key={agent.agent_key} className="agent-card-a">
     <div className="agent-card-top">
      <div className="agent-icon-box">
       {agent.agent_key==='general'?(
        <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d="m12 3-1.9 5.8a2 2 0 0 1-1.3 1.3L3 12l5.8 1.9a2 2 0 0 1 1.3 1.3L12 21l1.9-5.8a2 2 0 0 1 1.3-1.3L21 12l-5.8-1.9a2 2 0 0 1-1.3-1.3z"/></svg>
       ):(
        <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d="M4 19.5v-15A2.5 2.5 0 0 1 6.5 2H20v20H6.5a2.5 2.5 0 0 1-2.5-2.5Z"/><path d="M6 6h10"/><path d="M6 10h10"/></svg>
       )}
      </div>
      <span className="agent-category-tag">{agent.agent_key==='general'?'일반 어시스턴트':'규정/업무지원'}</span>
     </div>
     <div className="agent-info-box">
      <h3>{agent.name}</h3>
      <p>{agent.description}</p>
     </div>
     <div className="agent-card-bottom">
      <span className="agent-status-badge">● {agent.available?'운영 중':'실행 제한'}</span>
      <button type="button" className="agent-start-btn" onClick={()=>onChat({prompt,agentKey:agent.agent_key})}>시작하기</button>
     </div>
    </article>)}
    {dynFavs.data?.items.map(fav=><article key={fav.asset_id} className="agent-card-a">
     <div className="agent-card-top">
      <div className="agent-icon-box">
       <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><polygon points="12 2 15.09 8.26 22 9.27 17 14.14 18.18 21.02 12 17.77 5.82 21.02 7 14.14 2 9.27 8.91 8.26 12 2"/></svg>
      </div>
      <span className="agent-category-tag">동적 Agent</span>
     </div>
     <div className="agent-info-box">
      <h3>{fav.name}</h3>
      <p>{fav.description||'승인된 동적 업무 도우미'}</p>
     </div>
     <div className="agent-card-bottom">
      <span className="agent-status-badge">● {fav.available?'운영 중':'실행 제한'}</span>
      <button type="button" className="agent-start-btn" onClick={onMine}>My Agent</button>
     </div>
    </article>)}
    {agents.data&&!agents.data.items.length&&(!dynFavs.data||!dynFavs.data.items.length)&&<p className="muted" style={{gridColumn: '1 / -1'}}>사용 가능한 도우미가 없습니다.</p>}
   </div>
  </section>

  {/* 4단: 하단 2열 분할 (최근 업무 + 공지사항/리소스) */}
  <section className="home-bottom-columns" aria-label="최근 업무 및 소식">
   <div className="home-recent-card">
    <div className="section-header">
     <h2>최근 업무</h2>
     <button type="button" className="quiet small" onClick={()=>onChat({})}>전체 대화</button>
    </div>
    {recent.loading&&<p role="status">최근 업무 확인 중...</p>}
    {recent.error&&<><p role="alert" className="error-message">{recent.error}</p><button type="button" className="secondary small" onClick={()=>void recent.load()}>다시 조회</button></>}
    <div className="home-recent-list">
     {recent.data?.items.map(conversation=><button key={conversation.conversation_id} type="button" className="recent-item-row" onClick={()=>onChat({conversation})}>
      <div className="recent-item-info">
       <strong>{conversation.title}</strong>
       <span>{new Date(conversation.updated_at).toLocaleString('ko-KR')}</span>
      </div>
      <span style={{fontSize: '12px', color: '#12635c', fontWeight: 600}}>이어서 대화 →</span>
     </button>)}
     {recent.data&&!recent.data.items.length&&<p className="hub-empty">아직 대화 이력이 없습니다. 첫 업무를 시작해 보세요.</p>}
    </div>
   </div>

   <div className="home-notice-card">
    <div className="section-header">
     <h2>도움말 및 이용 리소스</h2>
     <span className="muted" style={{fontSize: '12px'}}>플랫폼 안내</span>
    </div>
    <div className="home-notice-list">
     <div className="notice-item-row">
      <span>업무별 AI 도우미 및 10대 표준 업무 Agent 활용 안내</span>
      <span className="muted" style={{fontSize: '11px'}}>가이드</span>
     </div>
     <div className="notice-item-row">
      <span>사내 문서 등록 및 RAG 지식 검색 권한 관리 기준</span>
      <span className="muted" style={{fontSize: '11px'}}>보안정책</span>
     </div>
     <div className="notice-item-row">
      <span>개인정보(PII) 가드레일 자동 보호 및 필터링 안내</span>
      <span className="muted" style={{fontSize: '11px'}}>컴플라이언스</span>
     </div>
    </div>
    <div className="hub-actions" style={{marginTop: '16px'}}>
     {onUseCases&&<button type="button" className="primary small" onClick={onUseCases}>🏢 표준 업무 Agent</button>}
     <button type="button" className="secondary small" onClick={onCatalog}>AI 카탈로그</button>
     <button type="button" className="secondary small" onClick={onMine}>My Agent</button>
     <button type="button" className="secondary small" onClick={onDocuments}>내 자료실</button>
     <button type="button" className="secondary small" onClick={onSummary}>문서 요약</button>
    </div>
    <p className="scope-note" style={{marginTop: '12px'}}>현재 조직에서 본인에게 허용된 자료와 대화만 안전하게 조회됩니다.</p>
   </div>
  </section>
 </section>;
}
