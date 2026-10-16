import type {Node, Edge} from '@xyflow/react';
import type {WorkflowNodeInfo, WorkflowEdgeInfo} from '../types';
import type {ApprovedWorkflow,ApprovedNode,PublishedWorkflowAsset,ToolSupportItem,WorkflowBinding} from '../types';
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

export type AssetInputBinding = {source:'input'} | {source:'literal';value:string} | {source:'tool';nodeId:string;path:string[]};

/** Converts only the linear subset whose execution semantics are represented by the approved server contract. */
export function flowToApprovedWorkflow(
  nodes:Node[], edges:Edge[], workflowId:string, name:string, description:string,
  asset:PublishedWorkflowAsset, tools:ToolSupportItem[], bindings:Record<string,AssetInputBinding>
):ApprovedWorkflow {
  const dag=validateDAG(nodes,edges);
  if(!dag.isValid)throw new Error(dag.error||'캔버스 DAG를 검증할 수 없습니다.');
  if(nodes.length<3||nodes.length>20||edges.length!==nodes.length-1)throw new Error('승인 전환은 입력부터 출력까지 단일 경로인 3~20개 노드만 지원합니다.');
  if(!name.trim()||name.trim().length>120||name.includes('\0'))throw new Error('Workflow 이름은 1~120자여야 합니다.');
  if(description.length>500)throw new Error('설명은 500자 이내여야 합니다.');
  const positions=new Map(dag.executionOrder.map((id,index)=>[id,index]));
  if(dag.executionOrder.some((id,index)=>index>0&&edges.filter(e=>e.target===id).length!==1)||dag.executionOrder.slice(0,-1).some(id=>edges.filter(e=>e.source===id).length!==1))
    throw new Error('분기·병합 그래프는 승인 정의로 변환할 수 없습니다.');
  const ordered=dag.executionOrder.map(id=>nodes.find(node=>node.id===id)!);
  const data=ordered.map(node=>node.data as unknown as StudioNodeData);
  const inputIndexes=data.flatMap((item,index)=>item.category==='trigger'?[index]:[]);
  const agentIndexes=data.flatMap((item,index)=>item.category==='llm'?[index]:[]);
  const outputIndexes=data.flatMap((item,index)=>item.category==='response'?[index]:[]);
  if(inputIndexes.length!==1||inputIndexes[0]!==0||agentIndexes.length!==1||outputIndexes.length!==1||outputIndexes[0]!==ordered.length-1)
    throw new Error('승인 Workflow에는 시작 입력 1개, 게시 Agent 1개, 마지막 출력 1개가 필요합니다.');
  if(!asset?.asset_id||!asset.version_id||!asset.publication_revision)throw new Error('현재 접근 가능한 게시 Agent의 정확한 버전을 선택하세요.');
  const inputData=data[0],inputKey=String(inputData.config.input_key??'query');
  if(!/^[A-Za-z][A-Za-z0-9_]{0,39}$/.test(inputKey))throw new Error('입력 키 형식이 승인 schema와 맞지 않습니다.');
  const idMap=new Map(ordered.map((node,index)=>[node.id,`n${index+1}`]));
  const approved:ApprovedNode[]=[];
  ordered.forEach((node,index)=>{
    const item=data[index],id=idMap.get(node.id)!;
    if(item.category==='trigger')approved.push({node_id:id,node_type:'input',title:item.label,config:{input_key:inputKey}});
    else if(item.category==='tool'){
      const toolId=String(item.config.tool_id??'');
      const tool=tools.find(value=>value.tool_id===toolId&&value.enabled&&value.current_head?.enabled&&value.current_head.descriptor.digest===value.descriptor.digest);
      if(!tool)throw new Error(`현재 승인되고 사용 가능한 Tool이 아닙니다: ${toolId||item.label}`);
      const raw=item.config.arguments??{};
      if(!raw||typeof raw!=='object'||Array.isArray(raw))throw new Error(`Tool 인수 형식을 확인하세요: ${item.label}`);
      const args:Record<string,WorkflowBinding>={};
      for(const [key,value] of Object.entries(raw)){
        if(!/^[A-Za-z][A-Za-z0-9_]{0,39}$/.test(key)||typeof value!=='string'||value.length>4000)throw new Error(`Tool 인수는 문자열 상수만 지원합니다: ${item.label}`);
        args[key]=value;
      }
      approved.push({node_id:id,node_type:'read_tool',title:item.label,config:{tool_id:toolId,version_digest:tool.descriptor.digest,arguments:args}});
    } else if(item.category==='llm'){
      const values:Record<string,WorkflowBinding>={};
      for(const variable of asset.variables){
        if(!/^[A-Za-z][A-Za-z0-9_]{0,39}$/.test(variable))throw new Error(`게시 Agent 변수 이름이 승인 schema와 맞지 않습니다: ${variable}`);
        const binding=bindings[variable];
        if(!binding)throw new Error(`Agent 입력 변수를 연결하세요: ${variable}`);
        if(binding.source==='literal'){
          if(!binding.value.trim()||binding.value.length>4000)throw new Error(`Agent 상수값을 확인하세요: ${variable}`);
          values[variable]=binding.value;
        }else if(binding.source==='input')values[variable]={node_id:idMap.get(ordered[0].id)!,path:[]};
        else{
          const sourceIndex=positions.get(binding.nodeId);
          if(sourceIndex===undefined||sourceIndex>=index||binding.path.length>4||binding.path.some(part=>!part||part.length>40))throw new Error(`Agent 입력 참조가 유효하지 않습니다: ${variable}`);
          values[variable]={node_id:idMap.get(binding.nodeId)!,path:binding.path};
        }
      }
      approved.push({node_id:id,node_type:'llm',title:item.label,config:{asset_id:asset.asset_id,version_id:asset.version_id,publication_revision:asset.publication_revision,values}});
    } else if(item.category==='response'){
      if(index===0)throw new Error('출력 노드 앞에 실행 노드가 필요합니다.');
      approved.push({node_id:id,node_type:'output',title:item.label,config:{source:{node_id:idMap.get(ordered[index-1].id)!,path:[]}}});
    } else throw new Error(`현재 승인 schema에서 지원하지 않는 노드입니다: ${item.label} (${item.category})`);
  });
  const approvedEdges=edges.map(edge=>({source_node:idMap.get(edge.source)!,target_node:idMap.get(edge.target)!}));
  return {workflow_id:workflowId,name:name.trim(),description:description.trim(),nodes:approved,edges:approvedEdges,max_steps:20};
}
