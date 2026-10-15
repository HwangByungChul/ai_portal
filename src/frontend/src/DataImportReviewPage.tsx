import {useEffect,useState} from 'react';
import {api,ApiError} from './api';
import {useScope} from './scoped';
import type {Tenant,User,DataImportItem} from './types';

export function DataImportReviewPage({tenant,user}:{tenant:Tenant;user:User}){
  const scope=useScope();
  const [items,setItems]=useState<DataImportItem[]>([]);
  const [selectedId,setSelectedId]=useState<string|null>(null);
  const [statusFilter,setStatusFilter]=useState<string>('all');
  const [comment,setComment]=useState('');
  const [loading,setLoading]=useState(false);
  const [busy,setBusy]=useState(false);
  const [error,setError]=useState<string|null>(null);
  const [notice,setNotice]=useState<string|null>(null);

  async function loadImports(){
    setLoading(true);setError(null);
    try{
      const query = statusFilter === 'all' ? '' : '?status=' + statusFilter;
      const data = await api.request<{items:DataImportItem[]}>('/admin/data-imports' + query,{
        tenantId:tenant.tenant_id,
        signal:scope.signal
      });
      if(scope.current()){
        setItems(data.items);
        if(!selectedId && data.items.length > 0){
          setSelectedId(data.items[0].import_id);
        }
      }
    }catch(problem){
      const msg = await scope.fail(problem,()=>setItems([]));
      if(scope.current()) setError(msg);
    }finally{
      if(scope.current()) setLoading(false);
    }
  }

  useEffect(()=>{
    void loadImports();
  },[statusFilter,tenant.tenant_id]);

  const selected = items.find(x => x.import_id === selectedId);
  const isRequester = selected?.requester_id === user.user_id;

  async function handleDecision(decision:'approved'|'rejected'){
    if(!selected || isRequester) return;
    setBusy(true);setError(null);setNotice(null);
    try{
      await api.request('/admin/data-imports/' + selected.import_id + '/decisions',{
        method:'POST',
        tenantId:tenant.tenant_id,
        csrf:user.csrf_token,
        body:{
          decision,
          comment,
          expected_revision:selected.revision
        }
      });
      setNotice(decision === 'approved' ? '데이터 반입이 승인되어 대상 스코프에 반영되었습니다.' : '데이터 반입이 반려되었습니다.');
      setComment('');
      await loadImports();
    }catch(problem){
      if(problem instanceof ApiError && problem.code === 'SELF_APPROVAL_FORBIDDEN'){
        setError('직무 분리(SOD) 규정에 따라 본인이 요청한 데이터 반입은 직접 승인할 수 없습니다.');
      } else {
        const msg = await scope.fail(problem,()=>{});
        setError(msg);
      }
    }finally{
      setBusy(false);
    }
  }

  const classBadges:Record<string,{label:string;color:string;bg:string}> = {
    internal:{label:'일반(내부)',color:'#0369A1',bg:'#E0F2FE'},
    confidential:{label:'대외비',color:'#B45309',bg:'#FEF3C7'},
    restricted:{label:'극비/기밀',color:'#B91C1C',bg:'#FEE2E2'}
  };

  const statusBadges:Record<string,{label:string;color:string;bg:string}> = {
    pending:{label:'승인 대기',color:'#D97706',bg:'#FEF3C7'},
    approved:{label:'승인 완료',color:'#059669',bg:'#D1FAE5'},
    rejected:{label:'반려됨',color:'#DC2626',bg:'#FEE2E2'}
  };

  return (
    <div className="admin-a-container" style={{maxWidth:'1440px',margin:'0 auto',padding:'24px 32px'}}>
      <header style={{marginBottom:'24px'}}>
        <div style={{display:'flex',justifyContent:'space-between',alignItems:'flex-start'}}>
          <div>
            <h1 style={{fontSize:'22px',fontWeight:700,color:'#0F172A',margin:'0 0 6px 0'}}>
              데이터 Scope 반입 심사 (DP-16 / DP-17)
            </h1>
            <p style={{fontSize:'14px',color:'#64748B',margin:0}}>
              조직·부서 대상 데이터 반입 요청을 검토하고, 내부통제 및 직무 분리(SOD) 규정에 따라 승인/반려합니다.
            </p>
          </div>
          <button type="button" className="secondary" onClick={()=>void loadImports()} disabled={loading}>
            새로고침
          </button>
        </div>
      </header>

      {/* 안내 배너 */}
      <div style={{background:'#F8FAFC',border:'1px solid #E2E8F0',borderRadius:'8px',padding:'14px 18px',marginBottom:'20px',fontSize:'13px',color:'#334155'}}>
        <strong>보안 및 직무 분리(SOD) 원칙:</strong>
        <span style={{marginLeft:'6px'}}>
          데이터 반입 요청자는 스스로 자신의 요청을 승인할 수 없으며(자가 승인 차단), 미승인 문서는 RAG 인덱스 및 검색에서 격리됩니다.
        </span>
      </div>

      {notice && <p role="status" style={{padding:'12px',background:'#D1FAE5',color:'#065F46',borderRadius:'6px',marginBottom:'16px'}}>{notice}</p>}
      {error && <p role="alert" style={{padding:'12px',background:'#FEE2E2',color:'#991B1B',borderRadius:'6px',marginBottom:'16px'}}>{error}</p>}

      {/* 상태 필터 탭 */}
      <div style={{display:'flex',gap:'8px',marginBottom:'16px'}}>
        {['all','pending','approved','rejected'].map(st=>(
          <button
            key={st}
            type="button"
            className={statusFilter===st?'primary':'secondary'}
            onClick={()=>setStatusFilter(st)}
            style={{padding:'6px 14px',fontSize:'13px',borderRadius:'20px'}}
          >
            {st==='all'?'전체 요청':statusBadges[st]?.label??st}
          </button>
        ))}
      </div>

      {/* 2열 분할 레이아웃 */}
      <div style={{display:'grid',gridTemplateColumns:'420px 1fr',gap:'24px',alignItems:'start'}}>
        {/* 좌측 목록 */}
        <section aria-label="반입 요청 목록" style={{background:'#FFFFFF',border:'1px solid #E2E8F0',borderRadius:'10px',overflow:'hidden'}}>
          <div style={{padding:'14px 18px',borderBottom:'1px solid #E2E8F0',background:'#F8FAFC',fontWeight:600,fontSize:'14px'}}>
            반입 요청 건수 ({items.length})
          </div>
          <div style={{maxHeight:'650px',overflowY:'auto'}}>
            {loading && <p style={{padding:'20px',textAlign:'center',color:'#64748B'}}>요청 목록 조회 중...</p>}
            {!loading && items.length===0 && (
              <p style={{padding:'32px',textAlign:'center',color:'#94A3B8'}}>해당 상태의 반입 요청이 없습니다.</p>
            )}
            {items.map(item=>{
              const isCur = item.import_id === selectedId;
              const cl = classBadges[item.classification] ?? {label:item.classification,color:'#334155',bg:'#F1F5F9'};
              const st = statusBadges[item.status] ?? {label:item.status,color:'#334155',bg:'#F1F5F9'};
              return (
                <div
                  key={item.import_id}
                  onClick={()=>setSelectedId(item.import_id)}
                  style={{
                    padding:'14px 18px',
                    borderBottom:'1px solid #F1F5F9',
                    cursor:'pointer',
                    background:isCur?'#F0FDFA':'#FFFFFF',
                    borderLeft:isCur?'4px solid #12635C':'4px solid transparent',
                    transition:'all 0.15s'
                  }}
                >
                  <div style={{display:'flex',justifyContent:'space-between',marginBottom:'6px'}}>
                    <span style={{fontSize:'12px',fontWeight:600,background:cl.bg,color:cl.color,padding:'2px 8px',borderRadius:'4px'}}>
                      {cl.label}
                    </span>
                    <span style={{fontSize:'12px',fontWeight:600,background:st.bg,color:st.color,padding:'2px 8px',borderRadius:'4px'}}>
                      {st.label}
                    </span>
                  </div>
                  <div style={{fontSize:'14px',fontWeight:600,color:'#1E293B',marginBottom:'4px'}}>
                    문서 ID: {item.document_id.slice(0,8)}...
                  </div>
                  <p style={{fontSize:'13px',color:'#64748B',margin:'0 0 6px 0',overflow:'hidden',textOverflow:'ellipsis',whiteSpace:'nowrap'}}>
                    {item.reason}
                  </p>
                  <div style={{fontSize:'11px',color:'#94A3B8',display:'flex',justifyContent:'space-between'}}>
                    <span>범위: {item.target_scope.toUpperCase()}</span>
                    <span>{new Date(item.created_at).toLocaleDateString()}</span>
                  </div>
                </div>
              );
            })}
          </div>
        </section>

        {/* 우측 상세 패널 */}
        <section aria-label="반입 요청 상세" style={{background:'#FFFFFF',border:'1px solid #E2E8F0',borderRadius:'10px',padding:'24px'}}>
          {!selected ? (
            <div style={{textAlign:'center',padding:'60px 20px',color:'#94A3B8'}}>
              좌측 목록에서 검토할 반입 요청을 선택해 주세요.
            </div>
          ) : (
            <div>
              <div style={{display:'flex',justifyContent:'space-between',alignItems:'center',marginBottom:'16px',borderBottom:'1px solid #E2E8F0',paddingBottom:'16px'}}>
                <div>
                  <h2 style={{fontSize:'18px',fontWeight:700,color:'#0F172A',margin:'0 0 4px 0'}}>
                    요청 식별자: {selected.import_id}
                  </h2>
                  <span style={{fontSize:'12px',color:'#64748B'}}>등록 일시: {new Date(selected.created_at).toLocaleString()}</span>
                </div>
                <div>
                  <span style={{
                    fontSize:'13px',
                    fontWeight:600,
                    padding:'4px 12px',
                    borderRadius:'6px',
                    background:statusBadges[selected.status]?.bg??'#F1F5F9',
                    color:statusBadges[selected.status]?.color??'#334155'
                  }}>
                    {statusBadges[selected.status]?.label??selected.status}
                  </span>
                </div>
              </div>

              <div style={{display:'grid',gridTemplateColumns:'repeat(2, 1fr)',gap:'16px',marginBottom:'20px'}}>
                <div style={{background:'#F8FAFC',padding:'12px',borderRadius:'6px'}}>
                  <span style={{fontSize:'12px',color:'#64748B',display:'block'}}>보안 등급 분류</span>
                  <strong style={{fontSize:'14px',color:'#1E293B'}}>{classBadges[selected.classification]?.label}</strong>
                </div>
                <div style={{background:'#F8FAFC',padding:'12px',borderRadius:'6px'}}>
                  <span style={{fontSize:'12px',color:'#64748B',display:'block'}}>대상 공개 Scope</span>
                  <strong style={{fontSize:'14px',color:'#1E293B'}}>{selected.target_scope.toUpperCase()} 범위</strong>
                </div>
                <div style={{background:'#F8FAFC',padding:'12px',borderRadius:'6px'}}>
                  <span style={{fontSize:'12px',color:'#64748B',display:'block'}}>대상 문서 식별자</span>
                  <code style={{fontSize:'12px',color:'#0369A1'}}>{selected.document_id}</code>
                </div>
                <div style={{background:'#F8FAFC',padding:'12px',borderRadius:'6px'}}>
                  <span style={{fontSize:'12px',color:'#64748B',display:'block'}}>대상 문서 버전</span>
                  <code style={{fontSize:'12px',color:'#0369A1'}}>{selected.version_id}</code>
                </div>
              </div>

              <div style={{marginBottom:'20px'}}>
                <h4 style={{fontSize:'14px',fontWeight:600,color:'#334155',margin:'0 0 6px 0'}}>반입 신청 사유</h4>
                <div style={{background:'#F8FAFC',padding:'14px',borderRadius:'6px',border:'1px solid #E2E8F0',fontSize:'14px',lineHeight:1.6}}>
                  {selected.reason}
                </div>
              </div>

              {selected.comment && (
                <div style={{marginBottom:'20px'}}>
                  <h4 style={{fontSize:'14px',fontWeight:600,color:'#334155',margin:'0 0 6px 0'}}>심사 의견</h4>
                  <div style={{background:'#F1F5F9',padding:'12px',borderRadius:'6px',fontSize:'13px',color:'#475569'}}>
                    {selected.comment}
                  </div>
                </div>
              )}

              {/* 심사 액션 구획 */}
              {selected.status === 'pending' && (
                <div style={{borderTop:'1px solid #E2E8F0',paddingTop:'20px',marginTop:'20px'}}>
                  <h3 style={{fontSize:'15px',fontWeight:700,color:'#0F172A',margin:'0 0 12px 0'}}>심사 결정</h3>
                  
                  {isRequester ? (
                    <div role="alert" style={{padding:'12px 16px',background:'#FFFBEB',border:'1px solid #FDE68A',color:'#B45309',borderRadius:'6px',fontSize:'13px'}}>
                      ⚠️ <strong>직무 분리(SOD) 제한:</strong> 본인이 요청한 데이터 반입 건입니다. 규정에 따라 타 관리자가 심사해야 합니다.
                    </div>
                  ) : (
                    <div>
                      <label htmlFor="import-comment" style={{display:'block',fontSize:'13px',fontWeight:600,color:'#334155',marginBottom:'6px'}}>
                        심사 의견 / 사유 (선택)
                      </label>
                      <textarea
                        id="import-comment"
                        rows={3}
                        value={comment}
                        onChange={e=>setComment(e.target.value)}
                        placeholder="승인 또는 반려 사유를 입력하세요."
                        style={{width:'100%',padding:'10px',borderRadius:'6px',border:'1px solid #CBD5E1',fontSize:'13px',marginBottom:'16px'}}
                        disabled={busy}
                      />
                      <div style={{display:'flex',gap:'12px'}}>
                        <button
                          type="button"
                          className="primary"
                          onClick={()=>void handleDecision('approved')}
                          disabled={busy}
                          style={{padding:'8px 20px',background:'#12635C',color:'#FFFFFF',borderRadius:'6px',fontWeight:600}}
                        >
                          반입 승인
                        </button>
                        <button
                          type="button"
                          className="secondary"
                          onClick={()=>void handleDecision('rejected')}
                          disabled={busy}
                          style={{padding:'8px 20px',color:'#DC2626',borderColor:'#FCA5A5',borderRadius:'6px',fontWeight:600}}
                        >
                          반입 반려
                        </button>
                      </div>
                    </div>
                  )}
                </div>
              )}
            </div>
          )}
        </section>
      </div>
    </div>
  );
}
