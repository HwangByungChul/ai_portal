import { useState } from 'react';
import { api,ApiError } from './api';
import { session } from './session';
export function LoginPage({notice}:{notice:string|null}){
 const [loginId,setLoginId]=useState('');const [password,setPassword]=useState('');const [busy,setBusy]=useState(false);const [error,setError]=useState<string|null>(null);
 async function submit(event:React.FormEvent){event.preventDefault();if(busy)return;setBusy(true);setError(null);const secret=password;setPassword('');
  try{await api.request('/auth/login',{method:'POST',body:{login_id:loginId,password:secret}});await session.restore();}
  catch(error){setError(error instanceof ApiError?error.message:'로그인 정보를 확인해 주세요.');}
  finally{setBusy(false);}
 }
 return <main className="login-layout"><section className="welcome-panel"><div className="brand-mark">AI</div><p className="eyebrow">AI PLATFORM</p>
  <h1>조직에 맞는 <br/>AI 업무 공간.</h1><p className="welcome-description">하나의 포털에서 로그인하고,<br/>허용된 조직의 업무와 사용자를 관리합니다.</p>
  <div className="welcome-features"><span>01 <strong>사용자 인증</strong></span><span>02 <strong>조직별 권한</strong></span><span>03 <strong>사용자 관리</strong></span></div>
  <p className="welcome-footer">개인 학습 · AI 플랫폼 MVP</p></section>
  <section className="login-panel"><div className="login-card"><p className="eyebrow teal">WELCOME BACK</p><h2>AI 통합 포털 로그인</h2><p className="muted">계정으로 로그인해 업무 공간을 확인하세요.</p>
  {notice&&<p role="status" className="notice">{notice}</p>}
  <form onSubmit={submit}><label htmlFor="login-id">로그인 ID</label><input id="login-id" autoComplete="username" required maxLength={64} value={loginId} onChange={e=>setLoginId(e.target.value)} disabled={busy}/>
  <label htmlFor="password">비밀번호</label><input id="password" type="password" autoComplete="current-password" required maxLength={128} value={password} onChange={e=>setPassword(e.target.value)} disabled={busy}/>
  {error&&<p role="alert" className="error-message">{error}</p>}
  <button className="primary full" disabled={busy}>{busy?'로그인 확인 중':'로그인'}</button></form>
  <p className="login-note">계정과 조직 권한은 관리자에게 확인해 주세요.</p></div></section></main>;
}
