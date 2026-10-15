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
  const [activeTab, setActiveTab] = useState<'builder' | 'workflow'>(() => {
    const params = new URLSearchParams(window.location.search);
    const tabParam = params.get('tab');
    if (tabParam === 'workflow') return 'workflow';
    if (tabParam === 'builder' || tabParam === 'agent') return 'builder';
    return initialTab;
  });

  const setTab = (nextTab: 'builder' | 'workflow') => {
    setActiveTab(nextTab);
    const url = new URL(window.location.href);
    url.searchParams.set('tab', nextTab);
    window.history.replaceState(null, '', url.pathname + url.search);
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
            <span>✨</span> AI Studio (통합 제작 허브)
          </h1>
          <p style={{margin: 0, fontSize: 13, color: '#64748B'}}>
            독립된 <strong>단일 에이전트(부품)</strong>를 제작하거나, 이들을 엮어 <strong>다단계 자동화 워크플로우(완성품)</strong>를 조립합니다.
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
            🤖 단일 Agent 빌더
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
            ⚡ 다단계 Workflow 캔버스
          </button>
        </div>
      </div>

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
              💡 <strong>안내:</strong> 여기서 제작한 단일 에이전트는 [Workflow 캔버스]에서 부품 노드로 불러와 기간계 시스템(Tool/API) 및 조건 분기와 결합할 수 있습니다.
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
              Workflow 캔버스로 이동 →
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
              💡 <strong>안내:</strong> 새로운 특화 상담/분석 에이전트가 필요하신가요? [단일 Agent 빌더]에서 에이전트를 먼저 제작한 후 본 캔버스에 배치하세요.
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
              ← 단일 Agent 빌더로 이동
            </button>
          </div>
          <WorkflowCanvasPage tenant={tenant} user={user} />
        </div>
      )}
    </div>
  );
}
