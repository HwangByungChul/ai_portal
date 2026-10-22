import {useState, useEffect} from 'react';
import {api} from './api';
import type {Tenant, User, AdminModelRegistryItem} from './types';

type ModelDisplay = {
  model_id: string;
  display_name: string;
  model_name: string;
  provider_key: string;
  active: boolean | null;
  pricing_version?: string;
  input_price?: string;
  output_price?: string;
  context_window?: number;
  max_output?: number;
  capabilities: string[];
};

function finiteNumber(value: unknown): number | undefined {
  if (typeof value !== 'number' && typeof value !== 'string') return undefined;
  if (typeof value === 'string' && !value.trim()) return undefined;
  const parsed = Number(value);
  return Number.isFinite(parsed) && parsed >= 0 ? parsed : undefined;
}

function safeText(value: unknown): string | undefined {
  if (typeof value === 'string' && value.trim() && !/^(undefined|null|nan)$/i.test(value.trim())) return value.trim();
  if (typeof value === 'number' && Number.isFinite(value)) return String(value);
  return undefined;
}

function normalizeModels(items: unknown): ModelDisplay[] {
  if (!Array.isArray(items)) return [];
  return (items as unknown[]).filter((item): item is AdminModelRegistryItem =>
    !!item && typeof item === 'object' && safeText((item as {model_id?: unknown}).model_id) !== undefined
  ).map(item => {
    const dbBacked = 'active' in item;
    const maxOutput = finiteNumber(dbBacked ? item.max_output : item.max_output_tokens);
    return {
      model_id: item.model_id,
      display_name: safeText('display_name' in item ? item.display_name : undefined) ?? item.model_id,
      model_name: safeText(item.model_name) ?? item.model_id,
      provider_key: safeText(item.provider_key) ?? '정보 없음',
      active: dbBacked ? item.active : item.enabled,
      pricing_version: safeText('pricing_version' in item ? item.pricing_version : undefined),
      input_price: safeText(dbBacked ? item.price_input_usd : item.input_usd_per_million),
      output_price: safeText(dbBacked ? item.price_out_usd : item.output_usd_per_million),
      context_window: finiteNumber(item.context_window),
      max_output: maxOutput,
      capabilities: Array.isArray(item.capabilities) ? item.capabilities.filter((cap): cap is string => typeof cap === 'string') : []
    };
  });
}

export function ModelAdminPage({tenant, user}: {tenant: Tenant | null; user: User}) {
  const [models, setModels] = useState<ModelDisplay[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const loadModels = async () => {
    if (!tenant) return;
    setLoading(true);
    setError(null);
    try {
      // Platform admin uses the admin registry; other roles see the public active list.
      const endpoint = tenant.effective_role === 'PADMIN' ? '/admin/models' : '/models';
      const res = await api.request<{items?: unknown}>(endpoint, {tenantId: tenant.tenant_id});
      setModels(normalizeModels(res?.items));
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
            <h1 style={{fontSize: '24px', fontWeight: 700, margin: '0 0 8px 0'}}>AI 모델 레지스트리</h1>
            <p style={{color: 'var(--text-muted, #64748b)', margin: 0}}>
              플랫폼에 등록된 LLM 모델, 문맥 한도, 제공된 가격 정보 및 지원 기능을 확인합니다.
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
          <strong>보안 원칙:</strong> 실제 API 키와 제공자 비밀 값은 서버에서만 참조·사용하며 이 화면에는 표시하지 않습니다.
          허가된 모델 외 임의 페이로드는 실행 전 게이트웨이에서 차단됩니다.
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
          {models.map(model => (
            <div
              key={model.model_id}
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
                  <h3 style={{fontSize: '18px', fontWeight: 600, margin: '0 0 4px 0'}}>{model.display_name}</h3>
                  <span style={{fontSize: '12px', color: '#64748b'}}>엔진: {model.model_name}</span>
                </div>
                <div style={{display: 'flex', gap: '6px'}}>
                  <span
                    style={{
                      fontSize: '11px',
                      fontWeight: 600,
                      padding: '2px 8px',
                      borderRadius: '12px',
                      background: model.provider_key === 'openai' ? '#e0f2fe' : '#f1f5f9',
                      color: model.provider_key === 'openai' ? '#0369a1' : '#475569',
                      textTransform: 'uppercase'
                    }}
                  >
                    {model.provider_key}
                  </span>
                  <span
                    style={{
                      fontSize: '11px',
                      fontWeight: 600,
                      padding: '2px 8px',
                      borderRadius: '12px',
                      background: model.active === true ? '#dcfce7' : model.active === false ? '#fee2e2' : '#f1f5f9',
                      color: model.active === true ? '#15803d' : model.active === false ? '#b91c1c' : '#475569'
                    }}
                  >
                    {model.active === true ? '운영 허용' : model.active === false ? '비활성' : '상태 정보 없음'}
                  </span>
                </div>
              </div>

              <div style={{background: '#f8fafc', padding: '12px', borderRadius: '6px', fontSize: '13px', display: 'flex', flexDirection: 'column', gap: '6px'}}>
                <div style={{display: 'flex', justifyContent: 'space-between'}}>
                  <span style={{color: '#64748b'}}>가격표 버전:</span>
                  <span style={{fontWeight: 500}}>{model.pricing_version ?? '정보 없음'}</span>
                </div>
                <div style={{display: 'flex', justifyContent: 'space-between'}}>
                  <span style={{color: '#64748b'}}>토큰 단가 (1M):</span>
                  <span>입력 {model.input_price !== undefined ? `$${model.input_price}` : '정보 없음'} / 출력 {model.output_price !== undefined ? `$${model.output_price}` : '정보 없음'}</span>
                </div>
                <div style={{display: 'flex', justifyContent: 'space-between'}}>
                  <span style={{color: '#64748b'}}>문맥 한도:</span>
                  <span>{model.context_window !== undefined ? `${model.context_window.toLocaleString()} 토큰` : '정보 없음'} (출력 최대 {model.max_output !== undefined ? model.max_output.toLocaleString() : '정보 없음'})</span>
                </div>
              </div>

              <div>
                <span style={{fontSize: '12px', color: '#64748b', display: 'block', marginBottom: '6px'}}>지원 기능:</span>
                <div style={{display: 'flex', flexWrap: 'wrap', gap: '6px'}}>
                  {model.capabilities.length ? model.capabilities.map(cap => (
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
                  )) : <span>정보 없음</span>}
                </div>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
