import {useState, useEffect} from 'react';
import {api} from './api';
import type {Tenant, User, ModelInfo} from './types';

export function ModelAdminPage({tenant, user}: {tenant: Tenant | null; user: User}) {
  const [models, setModels] = useState<ModelInfo[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const loadModels = async () => {
    if (!tenant) return;
    setLoading(true);
    setError(null);
    try {
      // Platform admin attempts admin endpoint, fallback to general models
      const endpoint = tenant.effective_role === 'PADMIN' ? '/admin/models' : '/models';
      const res = await api.request<{items: ModelInfo[]}>(endpoint, {tenantId: tenant.tenant_id});
      setModels(res.items || []);
    } catch (e: any) {
      setError(e.message || '모델 목록을 불러오지 못했습니다.');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadModels();
  }, [tenant?.tenant_id]);

  return (
    <div className="portal-page-container" style={{padding: '24px', maxWidth: '1200px', margin: '0 auto'}}>
      <header className="page-header" style={{marginBottom: '24px'}}>
        <div style={{display: 'flex', justifyContent: 'space-between', alignItems: 'center'}}>
          <div>
            <h1 style={{fontSize: '24px', fontWeight: 700, margin: '0 0 8px 0'}}>AI 모델 레지스트리 (DP-13)</h1>
            <p style={{color: 'var(--text-muted, #64748b)', margin: 0}}>
              플랫폼에 승인된 LLM 모델, 문맥 한도, 토큰 요금 스냅샷 및 지원 기능을 확인합니다.
            </p>
          </div>
          <button
            onClick={loadModels}
            disabled={loading}
            className="action-btn"
            style={{
              padding: '8px 16px',
              borderRadius: '6px',
              border: '1px solid var(--border-color, #e2e8f0)',
              background: 'var(--card-bg, #fff)',
              cursor: loading ? 'not-allowed' : 'pointer'
            }}
          >
            {loading ? '조회 중...' : '새로고침'}
          </button>
        </div>
      </header>

      <div
        className="security-notice-card"
        style={{
          background: 'rgba(59, 130, 246, 0.05)',
          border: '1px solid rgba(59, 130, 246, 0.2)',
          borderRadius: '8px',
          padding: '16px',
          marginBottom: '24px',
          display: 'flex',
          gap: '12px',
          alignItems: 'center'
        }}
      >
        <span style={{fontSize: '20px'}}>🛡️</span>
        <div style={{fontSize: '13px', color: '#1e3a8a'}}>
          <strong>보안 원칙:</strong> 모델 인증 정보(API Key/Credential)는 서버 환경변수 및 비밀 관리소에서만 참조되며,
          클라이언트에 노출되지 않습니다. 허가된 모델 외 임의 페이로드는 실행 전 게이트웨이에서 차단됩니다.
        </div>
      </div>

      {error && (
        <div className="error-alert" style={{color: '#dc2626', background: '#fee2e2', padding: '12px', borderRadius: '6px', marginBottom: '20px'}}>
          {error}
        </div>
      )}

      {loading && models.length === 0 ? (
        <div style={{textAlign: 'center', padding: '48px', color: '#64748b'}}>모델 레지스트리를 불러오는 중입니다...</div>
      ) : (
        <div className="models-grid" style={{display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(360px, 1fr))', gap: '20px'}}>
          {models.map(m => (
            <div
              key={m.model_id}
              className="model-card"
              style={{
                border: '1px solid var(--border-color, #e2e8f0)',
                borderRadius: '10px',
                padding: '20px',
                background: 'var(--card-bg, #ffffff)',
                boxShadow: '0 1px 3px rgba(0,0,0,0.05)',
                display: 'flex',
                flexDirection: 'column',
                gap: '12px'
              }}
            >
              <div style={{display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start'}}>
                <div>
                  <h3 style={{fontSize: '18px', fontWeight: 600, margin: '0 0 4px 0'}}>{m.model_id}</h3>
                  <span style={{fontSize: '12px', color: '#64748b'}}>엔진: {m.model_name}</span>
                </div>
                <div style={{display: 'flex', gap: '6px'}}>
                  <span
                    style={{
                      fontSize: '11px',
                      fontWeight: 600,
                      padding: '2px 8px',
                      borderRadius: '12px',
                      background: m.provider_key === 'openai' ? '#e0f2fe' : '#f1f5f9',
                      color: m.provider_key === 'openai' ? '#0369a1' : '#475569',
                      textTransform: 'uppercase'
                    }}
                  >
                    {m.provider_key}
                  </span>
                  <span
                    style={{
                      fontSize: '11px',
                      fontWeight: 600,
                      padding: '2px 8px',
                      borderRadius: '12px',
                      background: m.enabled ? '#dcfce7' : '#fee2e2',
                      color: m.enabled ? '#15803d' : '#b91c1c'
                    }}
                  >
                    {m.enabled ? '운영 허용' : '비활성'}
                  </span>
                </div>
              </div>

              <div style={{background: '#f8fafc', padding: '12px', borderRadius: '6px', fontSize: '13px', display: 'flex', flexDirection: 'column', gap: '6px'}}>
                <div style={{display: 'flex', justifyContent: 'space-between'}}>
                  <span style={{color: '#64748b'}}>가격표 버전:</span>
                  <span style={{fontWeight: 500}}>{m.pricing_version}</span>
                </div>
                <div style={{display: 'flex', justifyContent: 'space-between'}}>
                  <span style={{color: '#64748b'}}>토큰 단가 (1M):</span>
                  <span>입력 ${m.input_usd_per_million} / 출력 ${m.output_usd_per_million}</span>
                </div>
                <div style={{display: 'flex', justifyContent: 'space-between'}}>
                  <span style={{color: '#64748b'}}>문맥 한도:</span>
                  <span>{m.context_window.toLocaleString()} 토큰 (출력 최대 {m.max_output_tokens.toLocaleString()})</span>
                </div>
              </div>

              <div>
                <span style={{fontSize: '12px', color: '#64748b', display: 'block', marginBottom: '6px'}}>지원 기능:</span>
                <div style={{display: 'flex', flexWrap: 'wrap', gap: '6px'}}>
                  {m.capabilities.map(cap => (
                    <span
                      key={cap}
                      style={{
                        fontSize: '11px',
                        background: '#f1f5f9',
                        color: '#334155',
                        padding: '2px 8px',
                        borderRadius: '4px'
                      }}
                    >
                      {cap}
                    </span>
                  ))}
                </div>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
