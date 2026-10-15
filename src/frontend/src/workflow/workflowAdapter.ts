import type {Node, Edge} from '@xyflow/react';
import type {WorkflowNodeInfo, WorkflowEdgeInfo} from '../types';
import type {StudioNodeData, StudioNodeCategory} from './workflowTypes';

export function flowToBackendNodes(nodes: Node[]): WorkflowNodeInfo[] {
  return nodes.map((node) => {
    const data = node.data as unknown as StudioNodeData;
    let nodeType: 'input' | 'read_tool' | 'validate' | 'output' | 'llm' = 'llm';
    if (data.category === 'trigger') nodeType = 'input';
    else if (data.category === 'tool') nodeType = 'read_tool';
    else if (data.category === 'logic') nodeType = 'validate';
    else if (data.category === 'response') nodeType = 'output';
    else if (data.category === 'knowledge') nodeType = 'read_tool';

    return {
      node_id: node.id,
      node_type: nodeType,
      title: data.label || node.id,
      config: {
        ...(data.config || {}),
        position: {x: Math.round(node.position.x), y: Math.round(node.position.y)},
        studio_category: data.category,
        description: data.description
      }
    };
  });
}

export function flowToBackendEdges(edges: Edge[]): WorkflowEdgeInfo[] {
  return edges.map((edge) => ({
    source_node: edge.source,
    target_node: edge.target
  }));
}

export function backendToFlowGraph(
  backendNodes: WorkflowNodeInfo[],
  backendEdges: WorkflowEdgeInfo[],
  callbacks: {
    onSelectNode?: (nodeId: string) => void;
    onDeleteNode?: (nodeId: string) => void;
    onDuplicateNode?: (nodeId: string) => void;
  }
): {nodes: Node[]; edges: Edge[]} {
  const nodes: Node[] = backendNodes.map((bn, index) => {
    const config = bn.config || {};
    const pos = config.position || {x: 100 + index * 260, y: 150 + (index % 2) * 50};
    
    let category: StudioNodeCategory = 'llm';
    if (config.studio_category) {
      category = config.studio_category as StudioNodeCategory;
    } else {
      if (bn.node_type === 'input') category = 'trigger';
      else if (bn.node_type === 'read_tool') category = 'tool';
      else if (bn.node_type === 'validate') category = 'logic';
      else if (bn.node_type === 'output') category = 'response';
      else if (bn.node_type === 'llm') category = 'llm';
    }

    const nodeData: StudioNodeData = {
      nodeId: bn.node_id,
      nodeType: bn.node_type,
      category,
      label: bn.title || bn.node_id,
      description: config.description,
      config: config,
      status: 'idle',
      ...callbacks
    };

    return {
      id: bn.node_id,
      type: 'customStudioNode',
      position: pos,
      data: nodeData
    };
  });

  const edges: Edge[] = backendEdges.map((be, index) => ({
    id: `edge-${be.source_node}-${be.target_node}-${index}`,
    source: be.source_node,
    target: be.target_node,
    animated: true,
    style: {stroke: '#6366F1', strokeWidth: 2}
  }));

  return {nodes, edges};
}

export function validateDAG(nodes: Node[], edges: Edge[]): {isValid: boolean; error?: string; executionOrder: string[]} {
  if (nodes.length === 0) {
    return {isValid: false, error: '캔버스에 최소 하나 이상의 노드가 필요합니다.', executionOrder: []};
  }

  // 1. 인접 리스트 및 In-degree 계산
  const inDegree: Record<string, number> = {};
  const adj: Record<string, string[]> = {};

  nodes.forEach((n) => {
    inDegree[n.id] = 0;
    adj[n.id] = [];
  });

  for (const e of edges) {
    if (adj[e.source] && inDegree[e.target] !== undefined) {
      adj[e.source].push(e.target);
      inDegree[e.target]++;
    }
  }

  // 2. Kahn's Algorithm (Topological Sort)
  const queue: string[] = [];
  nodes.forEach((n) => {
    if (inDegree[n.id] === 0) {
      queue.push(n.id);
    }
  });

  const order: string[] = [];
  while (queue.length > 0) {
    const u = queue.shift()!;
    order.push(u);

    for (const v of adj[u]) {
      inDegree[v]--;
      if (inDegree[v] === 0) {
        queue.push(v);
      }
    }
  }

  if (order.length !== nodes.length) {
    return {
      isValid: false,
      error: '순환 참조(Cycle)가 발견되었습니다. 워크플로우는 단방향 비순환 그래프(DAG)여야 합니다.',
      executionOrder: []
    };
  }

  return {isValid: true, executionOrder: order};
}
