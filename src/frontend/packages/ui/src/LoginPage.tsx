import { useState } from 'react';
import { api,ApiError } from '../../api-contract/src/api';
import { session } from '../../api-contract/src/session';

export function LoginPage({site='user',notice}:{site?:'user'|'admin';notice:string|null}){
 const [loginId,setLoginId]=useState('');
 const [password,setPassword]=useState('');
 const [busy,setBusy]=useState(false);
 const [error,setError]=useState<string|null>(null);

 async function submit(event:React.FormEvent){
  event.preventDefault();
  if(busy)return;
  setBusy(true);
  setError(null);
  const secret=password;
  setPassword('');
  try{
   await api.request('/auth/login',{method:'POST',body:{login_id:loginId,password:secret}});
   await session.restore();
  }
  catch(error){
   setError(error instanceof ApiError?error.message:'로그인 정보를 확인해 주세요.');
  }
  finally{
   setBusy(false);
  }
 }

 const isAdmin = site === 'admin';

 return (
  <main className={'login-layout ' + (isAdmin ? 'admin-login-layout' : 'user-login-layout')}>
   <section className={'welcome-panel ' + (isAdmin ? 'admin-welcome-panel' : 'user-welcome-panel')}>
    {isAdmin ? (
     <>
      <div className="admin-badge-logo">
       <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.4" aria-hidden="true">
        <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/>
       </svg>
       <span>ADMIN CONSOLE</span>
      </div>
      <p className="eyebrow admin-eyebrow">ENTERPRISE GOVERNANCE</p>
      <h1>엔터프라이즈 AI 거버넌스,<br/>운영 통제 센터.</h1>
      <p className="welcome-description admin-welcome-desc">
       AI 자산 배포 승인, 모델 라우팅, 보안 가드레일 및<br/>
       조직별 사용량과 비용을 안전하게 통합 관제합니다.
      </p>
      <div className="admin-features-box">
       <div className="admin-feature-row">
        <span className="admin-feature-bullet" aria-hidden="true">
         <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2"><path d="M9 11l3 3L22 4"/><path d="M21 12v7a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11"/></svg>
        </span>
        <span><strong>Agent 배포 심사</strong> 다단계 승인·검증 워크플로우</span>
       </div>
       <div className="admin-feature-row">
        <span className="admin-feature-bullet" aria-hidden="true">
         <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2"><circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1 0 2.83 2 2 0 0 1-2.83 0l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-2 2 2 2 0 0 1-2-2v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83 0 2 2 0 0 1 0-2.83l.06-.06a1.65 1.65 0 0 0 .33-1.82 1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1-2-2 2 2 0 0 1 2-2h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 0-2.83 2 2 0 0 1 2.83 0l.06.06a1.65 1.65 0 0 0 1.82.33H9a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 2-2 2 2 0 0 1 2 2v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 0 2 2 0 0 1 0 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82V9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 2 2 2 2 0 0 1-2 2h-.09a1.65 1.65 0 0 0-1.51 1z"/></svg>
        </span>
        <span><strong>운영 지표 관제</strong> 실시간 호출 통계 및 조직별 토큰 한도</span>
       </div>
       <div className="admin-feature-row">
        <span className="admin-feature-bullet" aria-hidden="true">
         <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2"><path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/><line x1="12" y1="8" x2="12" y2="12"/><line x1="12" y1="16" x2="12.01" y2="16"/></svg>
        </span>
        <span><strong>보안 가드레일</strong> 데이터 반입 심사 및 안전 정책</span>
       </div>
      </div>
      <p className="welcome-footer">생성형 AI 플랫폼 관리 콘솔 v1.2</p>
     </>
    ) : (
     <>
      <div className="user-badge-logo">
       <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" aria-hidden="true">
        <path d="m12 3-1.9 5.8a2 2 0 0 1-1.3 1.3L3 12l5.8 1.9a2 2 0 0 1 1.3 1.3L12 21l1.9-5.8a2 2 0 0 1 1.3-1.3L21 12l-5.8-1.9a2 2 0 0 1-1.3-1.3z"/>
       </svg>
       <span>AI WORKSPACE</span>
      </div>
      <p className="eyebrow">AI PLATFORM</p>
      <h1>스마트한 업무의 시작,<br/>생성형 AI 플랫폼.</h1>
      <p className="welcome-description">
       사내 표준 Agent와 안전한 문서 분석을 통해<br/>
       일상 업무의 생산성과 혁신을 경험하세요.
      </p>
      <div className="welcome-features">
       <span>01 <strong>스마트 AI 대화 & 보고서 작성</strong></span>
       <span>02 <strong>표준 업무 Agent 카탈로그</strong></span>
       <span>03 <strong>안전한 사내 문서 요약 분석</strong></span>
      </div>
      <p className="welcome-footer">생성형 AI 플랫폼</p>
     </>
    )}
   </section>

   <section className={'login-panel ' + (isAdmin ? 'admin-login-panel' : 'user-login-panel')}>
    <div className="login-card">
     {isAdmin ? (
      <>
       <div className="admin-tag-badge">
        <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" aria-hidden="true">
         <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/>
        </svg>
        <span>OPERATIONS CONSOLE</span>
       </div>
       <h2>관리자 콘솔 인증</h2>
       <p className="muted">플랫폼 및 조직 관리자 전용 인증 공간입니다.</p>
       <div className="security-alert-box" role="note">
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden="true">
         <path d="m21.73 18-8-14a2 2 0 0 0-3.48 0l-8 14A2 2 0 0 0 4 21h16a2 2 0 0 0 1.73-3Z"/><line x1="12" y1="9" x2="12" y2="13"/><line x1="12" y1="17" x2="12.01" y2="17"/>
        </svg>
        <span>관리 기능 접근은 로그인 후 계정의 관리자 권한에 따라 결정됩니다.</span>
       </div>
      </>
     ) : (
      <>
       <p className="eyebrow teal">WELCOME BACK · USER WORKSPACE</p>
       <h2>임직원 로그인</h2>
       <p className="muted">계정으로 로그인해 AI 업무 공간을 확인하세요.</p>
      </>
     )}

     {notice && <p role="status" className="notice">{notice}</p>}

     <form onSubmit={submit}>
      <label htmlFor="login-id">{isAdmin ? '관리자 계정 ID' : '로그인 ID'}</label>
      <input
       id="login-id"
       autoComplete="username"
       required
       maxLength={64}
       value={loginId}
       onChange={e=>setLoginId(e.target.value)}
       disabled={busy}
       placeholder={isAdmin ? '관리자 계정을 입력하세요' : '사번 또는 계정 ID'}
      />
      <label htmlFor="password">비밀번호</label>
      <input
       id="password"
       type="password"
       autoComplete="current-password"
       required
       maxLength={128}
       value={password}
       onChange={e=>setPassword(e.target.value)}
       disabled={busy}
       placeholder="비밀번호"
      />
      {error && <p role="alert" className="error-message">{error}</p>}
      <button className={'primary full ' + (isAdmin ? 'admin-primary-btn' : 'user-primary-btn')} disabled={busy}>
       {busy ? '인증 확인 중...' : (isAdmin ? '관리자 인증 및 로그인' : '로그인')}
      </button>
     </form>

     <p className="login-note">
      {isAdmin ? '관리자 권한 신청 및 보안 세션 문의는 시스템 운영팀에 문의하세요.' : '계정과 조직 권한은 부서 관리자에게 확인해 주세요.'}
     </p>
    </div>
   </section>
  </main>
 );
}
