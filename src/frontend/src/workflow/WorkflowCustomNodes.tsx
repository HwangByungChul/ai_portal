import React, {memo} from 'react';
import {Handle, Position, type NodeProps} from '@xyflow/react';
import {CATEGORY_COLORS, type StudioNodeData} from './workflowTypes';

export const CustomStudioNode = memo(({id, data, selected}: NodeProps<any>) => {
  const nodeData = data as StudioNodeData;
  const category = nodeData.category ?? 'llm';
  const colors = CATEGORY_COLORS[category] ?? CATEGORY_COLORS.llm;
  const isTrigger = category === 'trigger';
  const isResponse = category === 'response';

  return (
    <div
      className={`custom-flow-node ${selected ? 'selected' : ''}`}
      style={{borderColor: selected ? colors.badge : colors.border}}
    >
      {/* Target Handle (Left) - Trigger 노드는 입력 핸들 불필요 */}
      {!isTrigger && (
        <Handle
          type="target"
          position={Position.Left}
          style={{background: colors.badge}}
        />
      )}

      {/* 노드 헤더 */}
      <div
        className="custom-flow-node-header"
        style={{background: colors.bg, borderColor: colors.border}}
      >
        <div className="custom-flow-node-title">
          <span style={{color: colors.badge, fontWeight: 700}}>
            {nodeData.label}
          </span>
        </div>
        <div className="custom-flow-node-actions">
          {nodeData.onDuplicateNode && (
            <button
              type="button"
              className="custom-flow-node-btn"
              title="노드 복제"
              onClick={(e) => {
                e.stopPropagation();
                nodeData.onDuplicateNode?.(id);
              }}
            >
              📋
            </button>
          )}
          {nodeData.onDeleteNode && (
            <button
              type="button"
              className="custom-flow-node-btn"
              title="노드 삭제"
              onClick={(e) => {
                e.stopPropagation();
                nodeData.onDeleteNode?.(id);
              }}
            >
              ✕
            </button>
          )}
        </div>
      </div>

      {/* 노드 본문 */}
      <div className="custom-flow-node-body">
        {nodeData.description && (
          <div style={{color: '#64748B', fontSize: 11}}>
            {nodeData.description}
          </div>
        )}

        {/* 타입별 요약 정보 */}
        {nodeData.config?.model_id && (
          <div style={{fontWeight: 600, color: '#334155'}}>
            모델: <span style={{color: colors.text}}>{nodeData.config.model_id}</span>
          </div>
        )}
        {nodeData.config?.tool_id && (
          <div style={{fontWeight: 600, color: '#334155'}}>
            도구: <span style={{color: colors.text}}>{nodeData.config.tool_id}</span>
          </div>
        )}
        {nodeData.config?.knowledge_base && (
          <div style={{fontWeight: 600, color: '#334155'}}>
            지식DB: <span style={{color: colors.text}}>{nodeData.config.knowledge_base}</span>
          </div>
        )}
        {nodeData.config?.condition && (
          <div style={{fontWeight: 600, color: '#334155'}}>
            조건: <code style={{fontSize: 11}}>{nodeData.config.condition}</code>
          </div>
        )}
        {nodeData.config?.input_key && (
          <div style={{fontWeight: 600, color: '#334155'}}>
            입력키: <code>{nodeData.config.input_key}</code>
          </div>
        )}

        {/* 실행 상태 배지 */}
        {nodeData.status && nodeData.status !== 'idle' && (
          <div className={`custom-flow-node-status ${nodeData.status}`}>
            {nodeData.status === 'running' && '⏳ 실행 중...'}
            {nodeData.status === 'completed' && '✅ 완료'}
            {nodeData.status === 'failed' && '❌ 실패'}
            {nodeData.status === 'pending' && '대기 중'}
          </div>
        )}
      </div>

      {/* Source Handle (Right) - Response 노드는 출력 핸들 불필요 */}
      {!isResponse && (
        <Handle
          type="source"
          position={Position.Right}
          style={{background: colors.badge}}
        />
      )}
    </div>
  );
});

import type {NodeTypes} from '@xyflow/react';

CustomStudioNode.displayName = 'CustomStudioNode';

export const nodeTypes: NodeTypes = {
  customStudioNode: CustomStudioNode as any
};

