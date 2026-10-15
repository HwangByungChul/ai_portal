import React from 'react';
import type {Node} from '@xyflow/react';
import {CATEGORY_COLORS, type StudioNodeData} from './workflowTypes';
import type {ToolInfo} from '../types';

interface WorkflowInspectorProps {
  selectedNode: Node | null;
  workflowMeta: {
    name: string;
    version: string;
    description: string;
  };
  tools: ToolInfo[];
  onUpdateMeta: (key: string, value: string) => void;
  onUpdateNodeData: (nodeId: string, updates: Partial<StudioNodeData>) => void;
  onDeleteNode: (nodeId: string) => void;
}

export function WorkflowInspector({
  selectedNode,
  workflowMeta,
  tools,
  onUpdateMeta,
  onUpdateNodeData,
  onDeleteNode
}: WorkflowInspectorProps) {
  if (!selectedNode) {
    return (
      <aside className="workflow-inspector" aria-label="워크플로우 기본 설정">
        <div className="workflow-inspector-header">
          <h3>
            <span>⚙️</span> 워크플로우 속성
          </h3>
        </div>
        <div className="workflow-inspector-body">
          <div className="workflow-inspector-section">
            <label htmlFor="wf-meta-name">워크플로우 명칭</label>
            <input
              id="wf-meta-name"
              type="text"
              className="workflow-inspector-input"
              value={workflowMeta.name}
              onChange={(e) => onUpdateMeta('name', e.target.value)}
              placeholder="예: 고객 여신 한도 자동 심사 흐름"
            />
          </div>

          <div className="workflow-inspector-section">
            <label htmlFor="wf-meta-version">버전 태그</label>
            <input
              id="wf-meta-version"
              type="text"
              className="workflow-inspector-input"
              value={workflowMeta.version}
              onChange={(e) => onUpdateMeta('version', e.target.value)}
              placeholder="예: 1.0.0"
            />
          </div>

          <div className="workflow-inspector-section">
            <label htmlFor="wf-meta-desc">워크플로우 설명</label>
            <textarea
              id="wf-meta-desc"
              rows={4}
              className="workflow-inspector-textarea"
              value={workflowMeta.description}
              onChange={(e) => onUpdateMeta('description', e.target.value)}
              placeholder="워크플로우의 목적과 흐름에 대해 상세히 기재합니다."
            />
          </div>

          <div style={{marginTop: 20, padding: 12, background: '#F1F5F9', borderRadius: 8, fontSize: 12, color: '#475569'}}>
            💡 캔버스에서 노드를 클릭하면 노드별 상세 파라미터를 설정할 수 있습니다.
          </div>
        </div>
      </aside>
    );
  }

  const nodeData = selectedNode.data as unknown as StudioNodeData;
  const config = nodeData.config ?? {};
  const category = nodeData.category ?? 'llm';
  const colors = CATEGORY_COLORS[category] ?? CATEGORY_COLORS.llm;

  const updateConfig = (key: string, value: any) => {
    onUpdateNodeData(selectedNode.id, {
      config: {...config, [key]: value}
    });
  };

  return (
    <aside className="workflow-inspector" aria-label="노드 속성 설정">
      <div className="workflow-inspector-header">
        <h3>
          <span style={{color: colors.badge}}>●</span> {nodeData.label}
        </h3>
        <button
          type="button"
          className="workflow-btn-secondary"
          style={{padding: '4px 8px', fontSize: 12, color: '#DC2626'}}
          onClick={() => onDeleteNode(selectedNode.id)}
          title="노드 삭제"
        >
          삭제
        </button>
      </div>

      <div className="workflow-inspector-body">
        {/* 노드 공통 메타 */}
        <div className="workflow-inspector-section">
          <label htmlFor="node-prop-label">노드 라벨</label>
          <input
            id="node-prop-label"
            type="text"
            className="workflow-inspector-input"
            value={nodeData.label}
            onChange={(e) => onUpdateNodeData(selectedNode.id, {label: e.target.value})}
          />
        </div>

        <div className="workflow-inspector-section">
          <label htmlFor="node-prop-id">노드 고유 ID</label>
          <input
            id="node-prop-id"
            type="text"
            className="workflow-inspector-input"
            value={selectedNode.id}
            disabled
            style={{background: '#F1F5F9', cursor: 'not-allowed'}}
          />
        </div>

        <div className="workflow-inspector-section">
          <label htmlFor="node-prop-desc">설명</label>
          <input
            id="node-prop-desc"
            type="text"
            className="workflow-inspector-input"
            value={nodeData.description ?? ''}
            onChange={(e) => onUpdateNodeData(selectedNode.id, {description: e.target.value})}
            placeholder="노드 동작 설명"
          />
        </div>

        <hr style={{border: 'none', borderTop: '1px solid #E2E8F0', margin: '4px 0'}} />

        {/* 카테고리별 상세 설정 */}
        {category === 'trigger' && (
          <div className="workflow-inspector-section">
            <label htmlFor="node-cfg-inputkey">입력 키 (Input Key)</label>
            <input
              id="node-cfg-inputkey"
              type="text"
              className="workflow-inspector-input"
              value={config.input_key ?? 'query'}
              onChange={(e) => updateConfig('input_key', e.target.value)}
              placeholder="예: query, customer_id"
            />
          </div>
        )}

        {category === 'prompt' && (
          <div className="workflow-inspector-section">
            <label htmlFor="node-cfg-prompt">프롬프트 템플릿</label>
            <textarea
              id="node-cfg-prompt"
              rows={8}
              className="workflow-inspector-textarea"
              value={config.template ?? ''}
              onChange={(e) => updateConfig('template', e.target.value)}
              placeholder="{{query}}, {{context}} 등 변수 표기법을 사용하세요."
            />
            <small style={{color: '#64748B', fontSize: 11}}>
              이전 노드의 출력 값을 <code>{'{{변수명}}'}</code>으로 치환할 수 있습니다.
            </small>
          </div>
        )}

        {category === 'llm' && (
          <>
            <div className="workflow-inspector-section">
              <label htmlFor="node-cfg-model">추론 AI 모델</label>
              <select
                id="node-cfg-model"
                className="workflow-inspector-select"
                value={config.model_id ?? 'mock-fast'}
                onChange={(e) => updateConfig('model_id', e.target.value)}
              >
                <option value="mock-fast">내부 금융 특화 모델 (mock-fast)</option>
                <option value="mock-creative">범용 생성형 모델 (mock-creative)</option>
                <option value="solar-10.7b">Upstage Solar (Internal)</option>
                <option value="gpt-4o-mini">Azure OpenAI GPT-4o-mini</option>
              </select>
            </div>

            <div className="workflow-inspector-section">
              <div style={{display: 'flex', justifyContent: 'space-between'}}>
                <label htmlFor="node-cfg-temp">온도 (Temperature)</label>
                <span style={{fontSize: 12, fontWeight: 700}}>{config.temperature ?? 0.2}</span>
              </div>
              <input
                id="node-cfg-temp"
                type="range"
                min="0"
                max="1"
                step="0.05"
                value={config.temperature ?? 0.2}
                onChange={(e) => updateConfig('temperature', parseFloat(e.target.value))}
              />
            </div>

            <div className="workflow-inspector-section">
              <label htmlFor="node-cfg-sysprompt">시스템 프롬프트 (System Prompt)</label>
              <textarea
                id="node-cfg-sysprompt"
                rows={3}
                className="workflow-inspector-textarea"
                value={config.system_prompt ?? ''}
                onChange={(e) => updateConfig('system_prompt', e.target.value)}
              />
            </div>
          </>
        )}

        {category === 'knowledge' && (
          <>
            <div className="workflow-inspector-section">
              <label htmlFor="node-cfg-kb">지식베이스 (Knowledge Base)</label>
              <select
                id="node-cfg-kb"
                className="workflow-inspector-select"
                value={config.knowledge_base ?? 'kb-credit-guideline'}
                onChange={(e) => updateConfig('knowledge_base', e.target.value)}
              >
                <option value="kb-credit-guideline">여신 규정 및 신용 심사 가이드라인</option>
                <option value="kb-products">금융 수신/여신 상품 매뉴얼</option>
                <option value="kb-compliance">금융소비자보호법 준수 지침</option>
              </select>
            </div>

            <div className="workflow-inspector-section">
              <label htmlFor="node-cfg-topk">검색 문서 수 (Top-K)</label>
              <input
                id="node-cfg-topk"
                type="number"
                min="1"
                max="10"
                className="workflow-inspector-input"
                value={config.top_k ?? 3}
                onChange={(e) => updateConfig('top_k', parseInt(e.target.value, 10))}
              />
            </div>
          </>
        )}

        {category === 'tool' && (
          <div className="workflow-inspector-section">
            <label htmlFor="node-cfg-tool">호출 대상 표준 도구 (Tool)</label>
            <select
              id="node-cfg-tool"
              className="workflow-inspector-select"
              value={config.tool_id ?? 'financial_product_lookup'}
              onChange={(e) => updateConfig('tool_id', e.target.value)}
            >
              {tools.length === 0 && (
                <option value="financial_product_lookup">금융 상품 조회(Tool)</option>
              )}
              {tools.map((t) => (
                <option key={t.tool_id} value={t.tool_id}>
                  {t.name} ({t.tool_id})
                </option>
              ))}
            </select>
          </div>
        )}

        {category === 'logic' && (
          <div className="workflow-inspector-section">
            <label htmlFor="node-cfg-condition">분기/검증 조건식</label>
            <input
              id="node-cfg-condition"
              type="text"
              className="workflow-inspector-input"
              value={config.condition ?? 'score >= 70'}
              onChange={(e) => updateConfig('condition', e.target.value)}
              placeholder="예: score >= 70"
            />
          </div>
        )}

        {category === 'response' && (
          <div className="workflow-inspector-section">
            <label htmlFor="node-cfg-format">출력 포맷 (Output Format)</label>
            <select
              id="node-cfg-format"
              className="workflow-inspector-select"
              value={config.output_format ?? 'markdown'}
              onChange={(e) => updateConfig('output_format', e.target.value)}
            >
              <option value="markdown">마크다운 텍스트 (Markdown)</option>
              <option value="json">정형 JSON 객체</option>
              <option value="plain">단순 텍스트 (Plain Text)</option>
            </select>
          </div>
        )}
      </div>
    </aside>
  );
}
