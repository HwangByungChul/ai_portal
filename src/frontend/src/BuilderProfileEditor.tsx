import {useEffect,useRef,useState,useId} from 'react';
import {ReadableDocuments} from './ReadableDocuments';
import {get,useScope} from './scoped';
import {api} from './api';
import type {AssetDetail,AssetConfig,DocumentRef,ModelInfo} from './types';

export type BuilderProfile = {
  schema_version: 1;
  system_prompt: string;
  developer_prompt: string;
  user_template: string;
  model_ref: string;
  document_refs: DocumentRef[];
};

export type BuilderVersion = {
  asset_id: string;
  revision: number;
  version_id: string;
  config: AssetConfig;
  config_hash: string;
  profile: BuilderProfile;
  profile_hash: string;
  profile_source: 'stored' | 'legacy-derived';
  parent_version_id: string | null;
};

export const emptyProfile = (rag: boolean = false): BuilderProfile => ({
  schema_version: 1,
  system_prompt: '',
  developer_prompt: '',
  user_template: '{{question}}',
  model_ref: rag ? 'default_rules_rag' : 'default_general',
  document_refs: []
});

export function BuilderProfileEditor({
  profile,
  onChange,
  rag,
  tenantId,
  disabled
}: {
  profile: BuilderProfile;
  onChange: (value: BuilderProfile) => void;
  rag: boolean;
  tenantId: string;
  disabled: boolean;
}) {
  const id = useId();
  const scope = useScope();
  const [models, setModels] = useState<ModelInfo[]>([]);

  useEffect(() => {
    let active = true;
    async function loadModels() {
      try {
        const data = await api.request<ModelInfo[]>('/models', { signal: scope.signal });
        if (active && scope.current()) setModels(data);
      } catch {
        // Fallback: models remain empty, default options still work
      }
    }
    void loadModels();
    return () => { active = false; };
  }, [scope.signal]);

  const selectedModel = models.find(m => m.model_id === profile.model_ref);
  const ragIncompatible = selectedModel && rag && !selectedModel.capabilities.includes('rag');

  return (
    <section aria-label="구조화 프롬프트 편집" className="confirmation">
      <h3>프롬프트 구성 및 실행 모델</h3>
      <p className="scope-note">
        자산 지시문을 시스템 프롬프트로 저장합니다. 역할별 지시문과 실행할 AI 모델을 선택해 주세요.
      </p>

      <label htmlFor={id + ':developer'}>개발자 프롬프트</label>
      <textarea
        id={id + ':developer'}
        rows={3}
        maxLength={2000}
        disabled={disabled}
        value={profile.developer_prompt}
        onChange={e => onChange({ ...profile, developer_prompt: e.target.value })}
      />

      <label htmlFor={id + ':user'}>사용자 질문 템플릿</label>
      <textarea
        id={id + ':user'}
        rows={3}
        maxLength={2000}
        disabled={disabled}
        value={profile.user_template}
        onChange={e => onChange({ ...profile, user_template: e.target.value })}
      />

      <div style={{ marginTop: '12px', marginBottom: '16px' }}>
        <label htmlFor={id + ':model'}>실행 모델 선택</label>
        <select
          id={id + ':model'}
          disabled={disabled}
          value={profile.model_ref}
          onChange={e => onChange({ ...profile, model_ref: e.target.value })}
          style={{ width: '100%', padding: '8px 12px', borderRadius: '6px', border: '1px solid #CBD5E1', marginTop: '4px' }}
        >
          <option value={rag ? 'default_rules_rag' : 'default_general'}>
            시스템 기본 모델 ({rag ? '규정 검색: GPT-4o Mini' : '일반 대화: GPT-4o Mini'})
          </option>
          {models.map(m => (
            <option key={m.model_id} value={m.model_id}>
              {m.model_name} ({m.provider_key.toUpperCase()}) — 입력 ${m.input_usd_per_million} / 출력 ${m.output_usd_per_million} per 1M
            </option>
          ))}
        </select>

        {selectedModel ? (
          <div style={{ marginTop: '8px', padding: '10px 12px', background: '#F8FAFC', borderRadius: '6px', border: '1px solid #E2E8F0', fontSize: '13px' }}>
            <div style={{ display: 'flex', gap: '16px', flexWrap: 'wrap', alignItems: 'center' }}>
              <span><strong>제공자:</strong> {selectedModel.provider_key.toUpperCase()}</span>
              <span><strong>문맥 한도:</strong> {selectedModel.context_window.toLocaleString()} 토큰</span>
              <span><strong>최대 출력:</strong> {selectedModel.max_output_tokens.toLocaleString()} 토큰</span>
              <span><strong>단가:</strong> 입력 ${selectedModel.input_usd_per_million} / 출력 ${selectedModel.output_usd_per_million} (1M당)</span>
            </div>
            <div style={{ marginTop: '6px', display: 'flex', gap: '6px', alignItems: 'center' }}>
              <span style={{ color: '#64748B' }}>지원 기능:</span>
              {selectedModel.capabilities.map(cap => (
                <span key={cap} style={{ background: '#E0F2FE', color: '#0369A1', padding: '1px 6px', borderRadius: '4px', fontSize: '11px', fontWeight: 600 }}>
                  {cap}
                </span>
              ))}
            </div>
            {ragIncompatible && (
              <p role="alert" style={{ color: '#DC2626', marginTop: '6px', marginBottom: 0, fontWeight: 500 }}>
                ⚠️ 주의: 선택한 모델은 RAG(문서 검색) 기능을 공식 지원하지 않습니다.
              </p>
            )}
          </div>
        ) : (
          <p className="scope-note" style={{ marginTop: '4px' }}>
            {rag ? '문서 근거 검색 기본 파이프라인으로 실행됩니다.' : '일반 대화 기본 파이프라인으로 실행됩니다.'}
          </p>
        )}
      </div>

      {rag && (
        <ReadableDocuments
          tenantId={tenantId}
          selected={profile.document_refs}
          onChange={rows => onChange({ ...profile, document_refs: rows })}
          disabled={disabled}
          emptyScope="none"
          clearOnLoad={false}
        />
      )}
    </section>
  );
}

export function BuilderVersionPanel({
  detail,
  tenantId,
  disabled,
  onClone
}: {
  detail: AssetDetail;
  tenantId: string;
  disabled: boolean;
  onClone: (version: string) => void;
}) {
  const scope = useScope();
  const seq = useRef(0);
  const id = useId();
  const [chosen, setChosen] = useState('');
  const [value, setValue] = useState<BuilderVersion | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  async function read(version: string) {
    const query = ++seq.current;
    setChosen(version);
    setValue(null);
    setError(null);
    if (!version) return;
    setLoading(true);
    try {
      const data = await get<BuilderVersion>(
        '/admin/builder/assets/' + detail.asset_id + '/versions/' + version,
        { tenantId, signal: scope.signal }
      );
      if (scope.current() && query === seq.current) setValue(data);
    } catch (problem) {
      const message = await scope.fail(problem, () => setValue(null));
      if (scope.current() && query === seq.current) setError(message);
    } finally {
      if (scope.current() && query === seq.current) setLoading(false);
    }
  }

  return (
    <section aria-label="저장 버전 조회와 복제" className="confirmation">
      <h3>저장 버전 조회·복제</h3>
      <label htmlFor={id + ':version'}>조회할 저장 버전</label>
      <select
        id={id + ':version'}
        disabled={disabled || loading}
        value={chosen}
        onChange={e => void read(e.target.value)}
      >
        <option value="">버전을 선택하세요</option>
        {detail.versions.map(x => (
          <option key={x.version_id} value={x.version_id}>
            버전 {x.revision}
          </option>
        ))}
      </select>
      {loading && <p role="status">저장 버전 확인 중</p>}
      {error && <p role="alert">{error}</p>}
      {value && (
        <>
          <p>
            버전 {value.revision} · {value.profile_source === 'stored' ? '구조화 프롬프트' : '기존 지시문에서 구성'} · 모델:{' '}
            <strong>{value.profile.model_ref}</strong>
          </p>
          {value.parent_version_id && (
            <p className="scope-note">원본 저장 버전에서 복제한 자산입니다.</p>
          )}
          <h4>시스템 프롬프트</h4>
          <pre style={{ whiteSpace: 'pre-wrap' }}>{value.profile.system_prompt}</pre>
          <h4>개발자 프롬프트</h4>
          <pre style={{ whiteSpace: 'pre-wrap' }}>{value.profile.developer_prompt || '없음'}</pre>
          <h4>사용자 질문 템플릿</h4>
          <pre style={{ whiteSpace: 'pre-wrap' }}>{value.profile.user_template}</pre>
          <p>선택 자료 {value.profile.document_refs.length}개</p>
          <p className="scope-note">
            구성 지문 <code>{value.profile_hash}</code>
          </p>
          <button
            type="button"
            className="secondary"
            disabled={disabled}
            onClick={() => onClone(value.version_id)}
          >
            이 버전으로 새 초안 복제
          </button>
        </>
      )}
    </section>
  );
}
