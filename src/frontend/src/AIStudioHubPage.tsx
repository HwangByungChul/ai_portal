import {useState, useEffect} from 'react';
import type {Tenant, User} from './types';
import {AssetsPage} from './AssetsPage';
import {WorkflowCanvasPage} from './WorkflowCanvasPage';

export function AIStudioHubPage({
  tenant,
  user,
  initialTab = 'builder',
  onLegacy = () => {}
}: {
  tenant: Tenant;
  user: User;
  initialTab?: 'builder' | 'workflow';
  onLegacy?: () => void;
}) {
  const [mode, setMode] = useState<'quick' | 'guided'>('guided');
  const [activeTab, setActiveTab] = useState<'builder' | 'workflow'>(() => {
    const params = new URLSearchParams(window.location.search);
    const tabParam = params.get('tab');
    if (tabParam === 'workflow') return 'workflow';
    if (tabParam === 'builder' || tabParam === 'agent') return 'builder';
    return initialTab;
  });

  const setTab = (nextTab: 'builder' | 'workflow') => {
    if (activeTab === nextTab) return;
    setActiveTab(nextTab);
    const url = new URL(window.location.href);
    url.searchParams.set('tab', nextTab);
    window.history.pushState(null, '', url.pathname + url.search);
  };

  useEffect(() => {
    const handlePopState = () => {
      const params = new URLSearchParams(window.location.search);
      const tabParam = params.get('tab');
      if (tabParam === 'workflow') setActiveTab('workflow');
      else if (tabParam === 'builder' || tabParam === 'agent') setActiveTab('builder');
    };
    window.addEventListener('popstate', handlePopState);
    return () => window.removeEventListener('popstate', handlePopState);
  }, []);

  return (
    <div className="ai-studio-hub-container" style={{maxWidth: 1600, margin: '0 auto', padding: '16px 24px'}}>
      {/* 상단 통합 안내 및 서브 탭 헤더 */}
      <div
        style={{
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'center',
          flexWrap: 'wrap',
          gap: 16,
          background: '#FFFFFF',
          padding: '16px 20px',
          borderRadius: 12,
          border: '1px solid #E2E8F0',
          boxShadow: '0 2px 8px rgba(15, 23, 42, 0.04)',
          marginBottom: 20
        }}
      >
        <div>
          <h1 style={{margin: '0 0 4px 0', fontSize: 22, fontWeight: 800, color: '#0F172A', display: 'flex', alignItems: 'center', gap: 8}}>
            <span>✨</span> 생성형 AI 플랫폼 · AI Studio
          </h1>
          <p style={{margin: 0, fontSize: 13, color: '#64748B'}}>
            Agent와 Workflow를 한 Studio에서 만들고, 저장 전 제안을 검토하거나 단계별로 직접 구성합니다.
          </p>
        </div>

        {/* 상단 탭 전환기 */}
        <div style={{display: 'flex', gap: 6, background: '#F1F5F9', padding: 4, borderRadius: 8}}>
          <button
            type="button"
            onClick={() => setTab('builder')}
            style={{
              padding: '8px 18px',
              fontSize: 13,
              fontWeight: 700,
              borderRadius: 6,
              border: 'none',
              cursor: 'pointer',
              transition: 'all 0.15s ease',
              background: activeTab === 'builder' ? '#4F46E5' : 'transparent',
              color: activeTab === 'builder' ? '#FFFFFF' : '#475569',
              boxShadow: activeTab === 'builder' ? '0 2px 8px rgba(79,70,229,0.25)' : 'none'
            }}
          >
            🤖 Agent Builder
          </button>
          <button
            type="button"
            onClick={() => setTab('workflow')}
            style={{
              padding: '8px 18px',
              fontSize: 13,
              fontWeight: 700,
              borderRadius: 6,
              border: 'none',
              cursor: 'pointer',
              transition: 'all 0.15s ease',
              background: activeTab === 'workflow' ? '#4F46E5' : 'transparent',
              color: activeTab === 'workflow' ? '#FFFFFF' : '#475569',
              boxShadow: activeTab === 'workflow' ? '0 2px 8px rgba(79,70,229,0.25)' : 'none'
            }}
          >
            ⚡ Workflow Canvas
          </button>
        </div>
      </div>

      <section aria-labelledby="studio-start-title" className="card" style={{marginBottom: 20}}>
        <div className="page-heading">
          <div>
            <p className="eyebrow teal">작업 방식</p>
            <h2 id="studio-start-title">어떻게 시작할까요?</h2>
            <p className="muted">자연어로 초안을 제안받거나, 편집 화면에서 직접 구성할 수 있습니다.</p>
          </div>
          <div role="group" aria-label="시작 방식" className="tab-list">
            <button type="button" className={mode === 'quick' ? 'primary' : 'secondary'} aria-pressed={mode === 'quick'} onClick={() => setMode('quick')}>
              빠른 시작
            </button>
            <button type="button" className={mode === 'guided' ? 'primary' : 'secondary'} aria-pressed={mode === 'guided'} onClick={() => setMode('guided')}>
              단계별 제작
            </button>
          </div>
        </div>
        {mode === 'quick' ? (
          <div className="confirmation" role="status">
            <strong>{activeTab === 'builder' ? 'Agent 빠른 시작' : 'Workflow 빠른 시작'}</strong>
            <p>업무 목적과 필요한 입력·결과를 설명하면 검토 가능한 초안을 제안합니다. 생성만으로 저장하거나 실행하지 않습니다.</p>
            <p className="muted">자연어 초안 생성 연결을 준비 중입니다. 아래 편집 화면에서 단계별 제작을 계속할 수 있습니다.</p>
            <button type="button" className="secondary" onClick={() => setMode('guided')}>단계별 제작으로 이동</button>
          </div>
        ) : (
          <p className="scope-note">기존 편집기에서 설정을 직접 작성하고, 저장·시험·승인은 각각 명시적으로 진행합니다.</p>
        )}
      </section>

      {/* 탭별 컨텍스트 연계 안내 배너 */}
      {activeTab === 'builder' ? (
        <div>
          <div
            style={{
              background: '#EEF2FF',
              border: '1px solid #C7D2FE',
              borderRadius: 8,
              padding: '10px 16px',
              marginBottom: 16,
              display: 'flex',
              justifyContent: 'space-between',
              alignItems: 'center',
              fontSize: 13,
              color: '#3730A3'
            }}
          >
            <span>
              💡 <strong>연결 안내:</strong> Workflow에서는 승인·게시된 정확한 Agent 버전과 현재 권한이 있는 Tool만 지원 노드로 선택할 수 있습니다. 저장 전 Agent 제안은 Workflow에서 자동으로 실행되지 않습니다.
            </span>
            <button
              type="button"
              onClick={() => setTab('workflow')}
              style={{
                background: '#4F46E5',
                color: '#FFFFFF',
                border: 'none',
                padding: '5px 12px',
                borderRadius: 6,
                fontSize: 12,
                fontWeight: 600,
                cursor: 'pointer'
              }}
            >
              Workflow Canvas로 이동 →
            </button>
          </div>
          <AssetsPage builder tenant={tenant} user={user} onLegacy={onLegacy} />
        </div>
      ) : (
        <div>
          <div
            style={{
              background: '#F0FDF4',
              border: '1px solid #BBF7D0',
              borderRadius: 8,
              padding: '10px 16px',
              marginBottom: 16,
              display: 'flex',
              justifyContent: 'space-between',
              alignItems: 'center',
              fontSize: 13,
              color: '#166534'
            }}
          >
            <span>
              💡 <strong>연결 안내:</strong> Agent 제안은 별도 검토·저장 과정을 거칩니다. Workflow에서 사용할 때는 승인·게시된 정확한 버전을 선택해야 합니다.
            </span>
            <button
              type="button"
              onClick={() => setTab('builder')}
              style={{
                background: '#059669',
                color: '#FFFFFF',
                border: 'none',
                padding: '5px 12px',
                borderRadius: 6,
                fontSize: 12,
                fontWeight: 600,
                cursor: 'pointer'
              }}
            >
              ← Agent Builder로 이동
            </button>
          </div>
          <WorkflowCanvasPage tenant={tenant} user={user} />
        </div>
      )}
    </div>
  );
}
