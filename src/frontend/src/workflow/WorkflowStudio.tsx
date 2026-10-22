import React, {useState, useRef, useCallback, useEffect} from 'react';
import {
  ReactFlow,
  ReactFlowProvider,
  Background,
  Controls,
  MiniMap,
  addEdge,
  useNodesState,
  useEdgesState,
  useReactFlow,
  type Connection,
  type Edge,
  type Node,
  BackgroundVariant
} from '@xyflow/react';
import '@xyflow/react/dist/style.css';
import './workflowStudio.css';

import {nodeTypes} from './WorkflowCustomNodes';
import {CanvasWorkflowApprovalRequest} from '../CanvasWorkflowApprovalRequest';
import {WorkflowPalette} from './WorkflowPalette';
import {WorkflowInspector} from './WorkflowInspector';
import {WorkflowScaffoldPanel} from '../WorkflowScaffoldPanel';
import {
  flowToBackendNodes,
  flowToBackendEdges,
  backendToFlowGraph,
  validateDAG,
  workflowProposalToCanvas,
  type WorkflowProposal
} from './workflowAdapter';
import type {ComponentPaletteItem, StudioNodeData} from './workflowTypes';
import type {
  Tenant,
  User,
  ToolInfo,
  WorkflowNodeInfo,
  WorkflowEdgeInfo,
  ApprovedWorkflowSummary,
  WorkflowExecutionRun
} from '../types';
import {api} from '../api';
import {useScope, modeLabel} from '../scoped';

const WIZARD_STEPS = [
  {id: 1, label: '1. 기본 정보'},
  {id: 2, label: '2. 데이터 소스'},
  {id: 3, label: '3. 노드 배치'},
  {id: 4, label: '4. 파라미터 설정'},
  {id: 5, label: '5. 테스트 & 디버그'},
  {id: 6, label: '6. 검증 & 평가'},
  {id: 7, label: '7. 배포 & 게시'}
];

const INITIAL_NODES: WorkflowNodeInfo[] = [
  {node_id: 'step1_input', node_type: 'input', title: '고객 질의 입력', config: {studio_category: 'trigger', input_key: 'query', position: {x: 80, y: 160}}},
  {node_id: 'step2_rag', node_type: 'read_tool', title: '여신 규정 검색', config: {studio_category: 'knowledge', knowledge_base: 'kb-credit-guideline', top_k: 3, position: {x: 360, y: 160}}},
  {node_id: 'step3_tool', node_type: 'read_tool', title: '신용도 및 한도 조회', config: {studio_category: 'tool', tool_id: 'financial_product_lookup', position: {x: 640, y: 160}}},
  {node_id: 'step4_llm', node_type: 'llm', title: '심사 AI 요약 추론', config: {studio_category: 'llm', model_id: 'mock-fast', temperature: 0.2, position: {x: 920, y: 160}}},
  {node_id: 'step5_output', node_type: 'output', title: '심사 결과 통보', config: {studio_category: 'response', output_format: 'markdown', position: {x: 1200, y: 160}}}
];

const INITIAL_EDGES: WorkflowEdgeInfo[] = [
  {source_node: 'step1_input', target_node: 'step2_rag'},
  {source_node: 'step2_rag', target_node: 'step3_tool'},
  {source_node: 'step3_tool', target_node: 'step4_llm'},
  {source_node: 'step4_llm', target_node: 'step5_output'}
];

function WorkflowStudioInner({tenant, user, quickStart=false}: {tenant: Tenant; user: User; quickStart?:boolean}) {
  const scope = useScope();
  const options = {tenantId: tenant.tenant_id, csrf: user.csrf_token, signal: scope.signal};
  const reactFlowWrapper = useRef<HTMLDivElement>(null);
  const {screenToFlowPosition, fitView} = useReactFlow();

  // 워크플로우 메타데이터
  const [workflowMeta, setWorkflowMeta] = useState({
    name: '고객 여신 한도 심사 자동화 워크플로우',
    version: '1.0.0',
    description: '고객 질의와 신용 정보를 종합하여 금융 여신 심사를 자동 수행하는 파이프라인'
  });

  const [activeStep, setActiveStep] = useState(3);
  const [selectedNodeId, setSelectedNodeId] = useState<string | null>(null);

  // 실행 및 API 상태
  const [tools, setTools] = useState<ToolInfo[]>([]);
  const [versions, setVersions] = useState<ApprovedWorkflowSummary[]>([]);
  const [drafts, setDrafts] = useState<{draft_id:string;revision:number;name:string;description:string}[]>([]);
  const [draftId, setDraftId] = useState<string>(() => crypto.randomUUID());
  const [draftRevision, setDraftRevision] = useState(0);
  const [savedFingerprint, setSavedFingerprint] = useState('');
  const [showApprovalRequest, setShowApprovalRequest] = useState(false);
  const [draftBusy, setDraftBusy] = useState(false);
  const [selectedDraft, setSelectedDraft] = useState('');
  const [selectedVersion, setSelectedVersion] = useState<string>('');
  const [queryInput, setQueryInput] = useState('개인사업자 운전자금 5천만원 한도 심사 요청');
  const [run, setRun] = useState<WorkflowExecutionRun | null>(null);
  const [busy, setBusy] = useState(false);
  const [validating, setValidating] = useState(false);
  const [statusMessage, setStatusMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [showConsole, setShowConsole] = useState(false);
  const [pendingScaffoldProposal,setPendingScaffoldProposal]=useState<WorkflowProposal|null>(null);

  const requestRef = useRef<{version: string; query: string; client: string} | null>(null);
  const draftRequestRef = useRef<{fingerprint:string;client:string}|null>(null);

  // 노드 조작 콜백
  const handleDeleteNode = useCallback((id: string) => {
    setNodes((nds) => nds.filter((n) => n.id !== id));
    setEdges((eds) => eds.filter((e) => e.source !== id && e.target !== id));
    setSelectedNodeId((cur) => (cur === id ? null : cur));
  }, []);

  const handleDuplicateNode = useCallback((id: string) => {
    setNodes((nds) => {
      const target = nds.find((n) => n.id === id);
      if (!target) return nds;
      const newId = `${target.id}_copy_${Math.floor(Math.random() * 1000)}`;
      const newNode: Node = {
        ...target,
        id: newId,
        position: {x: target.position.x + 40, y: target.position.y + 40},
        data: {
          ...(target.data as StudioNodeData),
          nodeId: newId,
          label: `${(target.data as StudioNodeData).label} (복사본)`,
          onDeleteNode: handleDeleteNode,
          onDuplicateNode: handleDuplicateNode
        }
      };
      return [...nds, newNode];
    });
  }, [handleDeleteNode]);

  const initialGraph = backendToFlowGraph(INITIAL_NODES, INITIAL_EDGES, {
    onDeleteNode: handleDeleteNode,
    onDuplicateNode: handleDuplicateNode
  });

  const [nodes, setNodes, onNodesChange] = useNodesState(initialGraph.nodes);
  const [edges, setEdges, onEdgesChange] = useEdgesState(initialGraph.edges);

  // 초기 카탈로그 및 툴 로드
  useEffect(() => {
    async function loadData() {
      try {
        const [catalogRes, toolsRes, draftsRes] = await Promise.all([
          api.request<{items: ApprovedWorkflowSummary[]}>('/workflows/catalog', options),
          api.request<{items: ToolInfo[]}>('/tools', options),
          api.request<{items: {draft_id:string;revision:number;name:string;description:string}[]}>('/workflows/drafts', options)
        ]);
        if (scope.current()) {
          setVersions(catalogRes.items);
          setTools(toolsRes.items);
          setDrafts(draftsRes.items);
          if (catalogRes.items.length > 0) {
            setSelectedVersion(catalogRes.items[0].version_id);
          }
        }
      } catch (e) {
        // 백엔드 연동 폴백 허용
      }
    }
    void loadData();
  }, []);

  const editorGraph = {nodes: flowToBackendNodes(nodes), edges: flowToBackendEdges(edges)};
  const editorFingerprint = JSON.stringify({name:workflowMeta.name,description:workflowMeta.description,graph:editorGraph});
  const isCurrentDraftSaved = draftRevision > 0 && savedFingerprint === editorFingerprint;
  useEffect(()=>{if(!isCurrentDraftSaved)setShowApprovalRequest(false);},[isCurrentDraftSaved]);

  async function refreshDrafts() {
    const result = await api.request<{items: {draft_id:string;revision:number;name:string;description:string}[]}>('/workflows/drafts', options);
    if (scope.current()) setDrafts(result.items);
  }

  async function saveDraft() {
    if (draftBusy) return;
    setDraftBusy(true); setError(null);
    try {
      const fingerprint = JSON.stringify({draftId,expected_revision:draftRevision,name:workflowMeta.name,description:workflowMeta.description,graph:editorGraph});
      if (draftRequestRef.current?.fingerprint !== fingerprint) draftRequestRef.current={fingerprint,client:crypto.randomUUID()};
      const result = await api.request<{revision:number}>('/workflows/drafts', {
        ...options, method: 'POST',
        body: {draft_id:draftId,client_request_id:draftRequestRef.current.client,expected_revision:draftRevision,
          name:workflowMeta.name,description:workflowMeta.description,graph:editorGraph}
      });
      if (scope.current()) {
        draftRequestRef.current=null;
        setDraftRevision(result.revision);
        setSavedFingerprint(editorFingerprint);
        setSelectedDraft(draftId);
        await refreshDrafts();
        setStatusMessage(`초안 ${result.revision}차 버전을 저장했습니다. 승인·실행 상태가 아닙니다.`);
      }
    } catch (problem: any) {
      if (scope.current()) setError(problem?.message || '초안 저장에 실패했습니다. 최신 버전을 다시 불러오세요.');
    } finally { if (scope.current()) setDraftBusy(false); }
  }

  async function loadDraft(id: string) {
    if (!id || draftBusy) return;
    setDraftBusy(true); setError(null);
    try {
      const result = await api.request<{draft_id:string;revision:number;name:string;description:string;graph:{nodes:WorkflowNodeInfo[];edges:WorkflowEdgeInfo[]}}>(`/workflows/drafts/${id}`, options);
      if (!scope.current()) return;
      const graph = backendToFlowGraph(result.graph.nodes,result.graph.edges,{onDeleteNode:handleDeleteNode,onDuplicateNode:handleDuplicateNode});
      setNodes(graph.nodes); setEdges(graph.edges);
      setWorkflowMeta(current=>({...current,name:result.name,description:result.description}));
      setDraftId(result.draft_id); setDraftRevision(result.revision); setSelectedDraft(id);
      setSavedFingerprint(JSON.stringify({name:result.name,description:result.description,graph:{nodes:flowToBackendNodes(graph.nodes),edges:flowToBackendEdges(graph.edges)}}));
      setStatusMessage(`초안 ${result.revision}차 버전을 불러왔습니다. 승인·실행 전용 버전은 아닙니다.`);
    } catch (problem: any) { if (scope.current()) setError(problem?.message || '초안을 불러오지 못했습니다.'); }
    finally { if (scope.current()) setDraftBusy(false); }
  }

  // 엣지 연결 이벤트
  const onConnect = useCallback(
    (params: Connection) => {
      setEdges((eds) =>
        addEdge(
          {
            ...params,
            animated: true,
            style: {stroke: '#6366F1', strokeWidth: 2}
          },
          eds
        )
      );
    },
    [setEdges]
  );

  // 드래그 앤 드롭으로 신규 노드 추가
  const onDragOver = useCallback((event: React.DragEvent) => {
    event.preventDefault();
    event.dataTransfer.dropEffect = 'move';
  }, []);

  const onDrop = useCallback(
    (event: React.DragEvent) => {
      event.preventDefault();
      const rawData = event.dataTransfer.getData('application/reactflow');
      if (!rawData) return;

      try {
        const item: ComponentPaletteItem = JSON.parse(rawData);
        const position = screenToFlowPosition({
          x: event.clientX,
          y: event.clientY
        });

        const nodeId = `node_${item.type}_${Date.now()}`;
        const newNode: Node = {
          id: nodeId,
          type: 'customStudioNode',
          position,
          data: {
            nodeId,
            nodeType: item.type,
            category: item.category,
            label: item.name,
            description: item.description,
            config: {...item.defaultConfig},
            status: 'idle',
            onDeleteNode: handleDeleteNode,
            onDuplicateNode: handleDuplicateNode
          } as StudioNodeData
        };

        setNodes((nds) => [...nds, newNode]);
        setSelectedNodeId(nodeId);
      } catch (err) {
        console.error('Failed to parse dropped node', err);
      }
    },
    [screenToFlowPosition, handleDeleteNode, handleDuplicateNode, setNodes]
  );

  // 클릭으로 팔레트에서 노드 추가
  const handleAddFromPalette = (item: ComponentPaletteItem) => {
    const nodeId = `node_${item.type}_${Date.now()}`;
    const newNode: Node = {
      id: nodeId,
      type: 'customStudioNode',
      position: {x: 200 + Math.random() * 200, y: 150 + Math.random() * 100},
      data: {
        nodeId,
        nodeType: item.type,
        category: item.category,
        label: item.name,
        description: item.description,
        config: {...item.defaultConfig},
        status: 'idle',
        onDeleteNode: handleDeleteNode,
        onDuplicateNode: handleDuplicateNode
      } as StudioNodeData
    };
    setNodes((nds) => [...nds, newNode]);
    setSelectedNodeId(nodeId);
  };

  // 노드 선택
  const onNodeClick = (_: React.MouseEvent, node: Node) => {
    setSelectedNodeId(node.id);
  };

  const onPaneClick = () => {
    setSelectedNodeId(null);
  };

  // 속성 업데이트
  const handleUpdateNodeData = (nodeId: string, updates: Partial<StudioNodeData>) => {
    setNodes((nds) =>
      nds.map((n) => {
        if (n.id !== nodeId) return n;
        const currentData = n.data as unknown as StudioNodeData;
        return {
          ...n,
          data: {
            ...currentData,
            ...updates,
            config: updates.config ? {...currentData.config, ...updates.config} : currentData.config
          }
        };
      })
    );
  };

  const handleUpdateMeta = (key: string, value: string) => {
    setWorkflowMeta((m) => ({...m, [key]: value}));
  };

  // 자동 정렬 (Auto-layout)
  const handleAutoLayout = () => {
    const sorted = validateDAG(nodes, edges);
    if (!sorted.isValid) {
      setError(sorted.error || '자동 정렬 실패');
      return;
    }
    const order = sorted.executionOrder;
    setNodes((nds) =>
      nds.map((n) => {
        const idx = order.indexOf(n.id);
        const col = idx >= 0 ? idx : 0;
        return {
          ...n,
          position: {x: 80 + col * 280, y: 180 + (col % 2) * 40}
        };
      })
    );
    setTimeout(() => fitView({duration: 300}), 50);
  };

  // DAG 구조 유효성 검증
  const handleValidateDAG = async () => {
    setValidating(true);
    setError(null);
    setStatusMessage(null);

    const clientValidation = validateDAG(nodes, edges);
    if (!clientValidation.isValid) {
      setError(clientValidation.error ?? '유효하지 않은 워크플로우입니다.');
      setValidating(false);
      return;
    }

    try {
      const backendNodes = flowToBackendNodes(nodes);
      const backendEdges = flowToBackendEdges(edges);
      const res = await api.request<{node_count: number; execution_order: string[]}>(
        '/workflows/validate',
        {
          ...options,
          method: 'POST',
          body: {
            workflow_id: 'wf-studio-preview',
            name: workflowMeta.name,
            nodes: backendNodes,
            edges: backendEdges
          }
        }
      );
      setStatusMessage(
        `✅ 워크플로우 DAG 검증 성공: 총 ${res.node_count}개 노드, 실행 순서: [${res.execution_order.join(' → ')}]`
      );
      setActiveStep(5);
    } catch (e: any) {
      setStatusMessage(
        `✅ 로컬 DAG 검증 통과: 총 ${nodes.length}개 노드 정상 연결. (백엔드 승인 검증은 별도입니다)`
      );
    } finally {
      setValidating(false);
    }
  };

  function commitScaffoldProposal(proposal:WorkflowProposal){
    try{
      const graph=workflowProposalToCanvas(proposal,{onSelectNode:setSelectedNodeId,onDeleteNode:handleDeleteNode,onDuplicateNode:handleDuplicateNode});
      const validation=validateDAG(graph.nodes,graph.edges);
      if(!validation.isValid){setError(validation.error??'Workflow 그래프가 유효하지 않습니다.');return;}
      setNodes(graph.nodes);setEdges(graph.edges);setSelectedNodeId(null);
      setWorkflowMeta(current=>({...current,name:proposal.name,description:proposal.description}));
      setDraftId(crypto.randomUUID());setDraftRevision(0);setSelectedDraft('');setSavedFingerprint('');draftRequestRef.current=null;
      setActiveStep(3);setStatusMessage('제안을 Canvas에 가져왔습니다. 노드와 미연결 Agent·Tool 참조를 확인한 뒤 초안 저장을 눌러야 저장됩니다.');setError(null);
    }catch(problem){setError(problem instanceof Error?problem.message:'Workflow 제안을 Canvas에 가져오지 못했습니다.');}
  }

  function applyScaffoldProposal(proposal:WorkflowProposal){
    if(nodes.length>0){setPendingScaffoldProposal(proposal);return;}
    commitScaffoldProposal(proposal);
  }

  // 워크플로우 실행
  const handleRunWorkflow = async () => {
    if (!queryInput.trim() || busy || !selectedVersion) return;
    setBusy(true);
    setError(null);
    setShowConsole(true);

    // 노드 상태를 running으로 전환 애니메이션
    setNodes((nds) =>
      nds.map((n) => ({
        ...n,
        data: {...(n.data as unknown as StudioNodeData), status: 'running'}
      }))
    );

    const versionToRun = selectedVersion;
    const query = queryInput.trim();
    if (!requestRef.current || requestRef.current.query !== query) {
      requestRef.current = {
        version: versionToRun,
        query,
        client: crypto.randomUUID()
      };
    }

    try {
      const selectedDefinition = versions.find(version => version.version_id === versionToRun);
      if (!selectedDefinition?.input_key) throw new Error('승인 Workflow 입력 키 정보를 다시 불러오세요.');
      const res = await api.request<WorkflowExecutionRun>('/workflows/run', {
        ...options,
        method: 'POST',
        body: {
          version_id: versionToRun,
          client_request_id: requestRef.current.client,
          inputs: {[selectedDefinition.input_key]:query}
        }
      });
      if (scope.current()) {
        setRun(res);
      }
    } catch (err: any) {
      if (scope.current()) {
        setNodes((nds) => nds.map((n) => ({
          ...n,
          data: {...(n.data as unknown as StudioNodeData), status: 'idle'}
        })));
        setError(err?.message || '승인된 Workflow 실행 요청에 실패했습니다.');
      }
    } finally {
      setBusy(false);
    }
  };

  // 실행 폴링
  useEffect(() => {
    if (!run || run.is_terminal) return;
    let active = true;
    let timer: ReturnType<typeof setTimeout>;

    async function poll() {
      try {
        const val = await api.request<WorkflowExecutionRun>(
          `/workflows/runs/${run!.run_id}`,
          options
        );
        if (active && scope.current()) {
          setRun(val);
          // 노드 상태 업데이트
          setNodes((nds) =>
            nds.map((n) => {
              const step = val.steps.find((s) => s.node_id === n.id);
              if (step) {
                const s = step.state === 'succeeded' ? 'completed' : step.state === 'running' ? 'running' : 'pending';
                return {...n, data: {...(n.data as unknown as StudioNodeData), status: s}};
              }
              return n;
            })
          );
          if (!val.is_terminal) timer = setTimeout(() => void poll(), 800);
        }
      } catch (e) {
        if (active) setRun(null);
      }
    }
    timer = setTimeout(() => void poll(), 800);
    return () => {
      active = false;
      clearTimeout(timer);
    };
  }, [run?.run_id, run?.is_terminal]);

  const selectedNode = nodes.find((n) => n.id === selectedNodeId) || null;

  return (
    <div className="workflow-studio-root">
      {/* 1. 상단 헤더 & 컨트롤 바 */}
      <header className="workflow-studio-header">
        <div className="workflow-studio-header-top">
          <div className="workflow-studio-title-area">
            <span style={{fontSize: 22}}>⚡</span>
            <input
              type="text"
              className="workflow-studio-title-input"
              value={workflowMeta.name}
              onChange={(e) => handleUpdateMeta('name', e.target.value)}
            />
            <span className="workflow-studio-badge">v{workflowMeta.version}</span>
            <span
              className="workflow-studio-badge"
              style={{background: '#ECFDF5', color: '#059669', borderColor: '#A7F3D0'}}
            >
              초안 편집 모드
            </span>
          </div>

          <div className="workflow-studio-actions">
            <label className="workflow-btn workflow-btn-secondary" style={{display:'flex',alignItems:'center',gap:6}}>
              저장된 초안
              <select aria-label="불러올 Workflow 초안" value={selectedDraft} disabled={draftBusy} onChange={e=>void loadDraft(e.target.value)}>
                <option value="">초안 선택</option>
                {drafts.map(draft=><option key={draft.draft_id} value={draft.draft_id}>{draft.name} · r{draft.revision}</option>)}
              </select>
            </label>
            <button type="button" className="workflow-btn workflow-btn-secondary" disabled={draftBusy} onClick={()=>{setDraftId(crypto.randomUUID());setDraftRevision(0);setSelectedDraft('');setStatusMessage('새 초안 편집 중입니다. 저장하면 개인 초안으로 보관됩니다.');}}>
              새 초안
            </button>
            <button type="button" className="workflow-btn workflow-btn-primary" disabled={draftBusy} onClick={()=>void saveDraft()}>
              {draftBusy ? '초안 처리 중...' : `초안 저장 · r${draftRevision}`}
            </button>
            <button type="button" className="workflow-btn workflow-btn-secondary" disabled={!isCurrentDraftSaved||draftBusy} onClick={()=>setShowApprovalRequest(true)} title={isCurrentDraftSaved?'저장된 revision을 승인 요청으로 변환합니다.':'현재 편집 내용을 먼저 저장하세요.'}>
              승인 요청 준비
            </button>
            <label className="workflow-btn workflow-btn-secondary" style={{display: 'flex', alignItems: 'center', gap: 6}}>
              승인 버전
              <select
                aria-label="실행할 승인 Workflow 버전"
                value={selectedVersion}
                onChange={(e) => setSelectedVersion(e.target.value)}
                disabled={busy || versions.length === 0}
              >
                <option value="">승인된 버전 없음</option>
                {versions.map((version) => (
                  <option key={version.version_id} value={version.version_id}>
                    {version.name} · r{version.revision}{version.execution_ready ? '' : ' · 실행 준비 안 됨'}
                  </option>
                ))}
              </select>
            </label>
            <button
              type="button"
              className="workflow-btn workflow-btn-secondary"
              onClick={handleAutoLayout}
              title="노드를 흐름에 맞춰 자동 정렬합니다"
            >
              📐 자동 정렬
            </button>
            <button
              type="button"
              className="workflow-btn workflow-btn-secondary"
              onClick={() => void handleValidateDAG()}
              disabled={validating}
            >
              {validating ? '검증 중...' : '🛡️ 구조 검증'}
            </button>
            <button
              type="button"
              className="workflow-btn workflow-btn-secondary"
              onClick={() => setShowConsole(!showConsole)}
            >
              📊 실행 모니터링 {showConsole ? '▲' : '▼'}
            </button>
            <button
              type="button"
              className="workflow-btn workflow-btn-primary"
              onClick={() => void handleRunWorkflow()}
              disabled={busy || !selectedVersion}
            >
              {busy ? '실행 중...' : '▶ 승인 버전 실행'}
            </button>
          </div>
        </div>

        {/* 7단계 위저드 스텝 */}
        <div className="workflow-wizard-steps">
          {WIZARD_STEPS.map((step) => {
            const isCompleted = step.id < activeStep;
            const isActive = step.id === activeStep;
            return (
              <div
                key={step.id}
                className={`workflow-wizard-step ${isActive ? 'active' : ''} ${isCompleted ? 'completed' : ''}`}
                onClick={() => setActiveStep(step.id)}
                style={{cursor: 'pointer'}}
              >
                <span>{isCompleted ? '✓' : step.id}</span>
                <span>{step.label}</span>
              </div>
            );
          })}
        </div>
      </header>

      {quickStart&&(tenant.effective_role==='TADMIN'||tenant.effective_role==='PADMIN'
        ?<WorkflowScaffoldPanel tenant={tenant} user={user} onApplyProposal={applyScaffoldProposal} />
        :<section className="card" aria-label="빠른 시작 사용 권한"><h2>자연어 Workflow 초안 제안</h2><p className="scope-note">현업 제작자 전용 권한이 준비되기 전까지는 승인된 Agent Builder 관리자 역할에서만 사용할 수 있습니다.</p></section>)}
      {pendingScaffoldProposal&&<div role="alertdialog" aria-modal="true" aria-labelledby="scaffold-replace-title" className="confirmation">
        <h2 id="scaffold-replace-title">현재 Canvas 내용을 바꿀까요?</h2>
        <p>현재 노드와 연결을 지우고 “{pendingScaffoldProposal.name}” 제안을 가져옵니다. 저장되지 않은 편집 내용도 사라집니다.</p>
        <div className="button-row">
          <button type="button" className="secondary" onClick={()=>setPendingScaffoldProposal(null)}>취소</button>
          <button type="button" className="primary" onClick={()=>{const proposal=pendingScaffoldProposal;setPendingScaffoldProposal(null);commitScaffoldProposal(proposal);}}>현재 Canvas 교체 후 가져오기</button>
        </div>
      </div>}

      {/* 상태 메시지 알림 바 */}
      {(statusMessage || error) && (
        <div
          style={{
            padding: '8px 20px',
            fontSize: 13,
            fontWeight: 600,
            background: error ? '#FEF2F2' : '#F0FDF4',
            color: error ? '#B91C1C' : '#15803D',
            borderBottom: '1px solid',
            borderColor: error ? '#FCA5A5' : '#86EFAC',
            display: 'flex',
            justifyContent: 'space-between',
            alignItems: 'center'
          }}
        >
          <span>{error || statusMessage}</span>
          <button
            type="button"
            style={{background: 'none', border: 'none', cursor: 'pointer', fontWeight: 700}}
            onClick={() => {
              setError(null);
              setStatusMessage(null);
            }}
          >
            ✕
          </button>
        </div>
      )}
      <div role="note" style={{padding: '8px 20px', fontSize: 12, color: '#475569', background: '#F8FAFC', borderBottom: '1px solid #E2E8F0'}}>
        캔버스는 개인 초안으로 저장·불러올 수 있습니다. 초안은 승인을 받거나 실행되지 않으며, 실행은 선택한 승인 버전에만 적용됩니다.
      </div>

      {showApprovalRequest&&isCurrentDraftSaved&&<div style={{padding:16}}><CanvasWorkflowApprovalRequest tenant={tenant} user={user} draft={{draft_id:draftId,revision:draftRevision}} name={workflowMeta.name} description={workflowMeta.description} nodes={nodes} edges={edges} onClose={()=>setShowApprovalRequest(false)}/></div>}

      {/* 2. 메인 3-Pane 작업 영역 */}
      <div className="workflow-studio-body" ref={reactFlowWrapper}>
        {/* 좌측 팔레트 */}
        <WorkflowPalette onAddNode={handleAddFromPalette} />

        {/* 중앙 인터랙티브 캔버스 */}
        <main className="workflow-canvas-container">
          <ReactFlow
            nodes={nodes}
            edges={edges}
            onNodesChange={onNodesChange}
            onEdgesChange={onEdgesChange}
            onConnect={onConnect}
            onDrop={onDrop}
            onDragOver={onDragOver}
            onNodeClick={onNodeClick}
            onPaneClick={onPaneClick}
            nodeTypes={nodeTypes}
            fitView
          >
            <Background variant={BackgroundVariant.Dots} gap={16} size={1} color="#CBD5E1" />
            <Controls position="bottom-left" />
            <MiniMap
              position="bottom-right"
              nodeStrokeWidth={3}
              zoomable
              pannable
              style={{
                background: '#FFFFFF',
                borderRadius: 8,
                border: '1px solid #E2E8F0',
                boxShadow: '0 2px 8px rgba(0,0,0,0.06)'
              }}
            />
          </ReactFlow>
        </main>

        {/* 우측 속성 인스펙터 */}
        <WorkflowInspector
          selectedNode={selectedNode}
          workflowMeta={workflowMeta}
          tools={tools}
          onUpdateMeta={handleUpdateMeta}
          onUpdateNodeData={handleUpdateNodeData}
          onDeleteNode={handleDeleteNode}
        />
      </div>

      {/* 3. 하단 실행 모니터링 & 테스트 콘솔 (접기/펼치기) */}
      {showConsole && (
        <section
          style={{
            background: '#FFFFFF',
            borderTop: '1px solid #CBD5E1',
            padding: 16,
            maxHeight: 280,
            overflowY: 'auto',
            boxShadow: '0 -4px 12px rgba(0,0,0,0.05)',
            zIndex: 10
          }}
          aria-label="실행 모니터링 콘솔"
        >
          <div style={{display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 12}}>
            <h3 style={{margin: 0, fontSize: 14, fontWeight: 700, display: 'flex', alignItems: 'center', gap: 6}}>
              <span>📊</span> 실행 모니터링 &amp; 체크포인트
            </h3>
            <button
              type="button"
              className="workflow-btn-secondary"
              style={{padding: '2px 8px', fontSize: 11}}
              onClick={() => setShowConsole(false)}
            >
              콘솔 닫기
            </button>
          </div>

          <div style={{display: 'flex', gap: 12, alignItems: 'center', marginBottom: 10}}>
            <label htmlFor="wf-test-query" style={{fontSize: 12, fontWeight: 600}}>
              테스트 입력 질의:
            </label>
            <input
              id="wf-test-query"
              type="text"
              style={{flex: 1, padding: '6px 10px', fontSize: 12, border: '1px solid #CBD5E1', borderRadius: 6}}
              value={queryInput}
              onChange={(e) => setQueryInput(e.target.value)}
              placeholder="워크플로우에 전달할 질문을 입력하세요"
            />
            <button
              type="button"
              className="workflow-btn workflow-btn-primary"
              onClick={() => void handleRunWorkflow()}
              disabled={busy}
            >
              {busy ? '실행 중' : '실행'}
            </button>
          </div>

          {run && (
            <div style={{fontSize: 12, color: '#334155'}}>
              <div style={{display: 'flex', gap: 16, marginBottom: 8}}>
                <span><strong>실행 ID:</strong> {run.run_id}</span>
                <span><strong>상태:</strong> {run.state}</span>
                <span><strong>모드:</strong> {modeLabel(run.execution_mode)}</span>
              </div>
              <ol style={{margin: 0, paddingLeft: 20}}>
                {run.steps.map((step) => (
                  <li key={step.node_id} style={{margin: '4px 0'}}>
                    <strong>{step.node_id}</strong>: {step.state}
                    {step.child_run_id && <span style={{marginLeft: 8, color: '#6366F1'}}>Agent: {step.child_run_id}</span>}
                    {step.tool_client_id && <span style={{marginLeft: 8, color: '#059669'}}>Tool: {step.tool_client_id}</span>}
                  </li>
                ))}
              </ol>
              {Boolean(run.result) && (
                <div style={{marginTop: 8, padding: 8, background: '#F8FAFC', borderRadius: 6}}>
                  <strong>최종 출력 결과:</strong>
                  <pre style={{margin: '4px 0 0 0', whiteSpace: 'pre-wrap', fontSize: 11}}>
                    {typeof run.result === 'string' ? run.result : JSON.stringify(run.result, null, 2)}
                  </pre>
                </div>
              )}
            </div>
          )}
          {!run && <p style={{margin: 0, fontSize: 12, color: '#94A3B8'}}>실행 버튼을 누르면 각 노드별 상태와 로그가 여기에 기록됩니다.</p>}
        </section>
      )}
    </div>
  );
}

export function WorkflowStudio({tenant, user, quickStart=false}: {tenant: Tenant; user: User; quickStart?:boolean}) {
  return (
    <ReactFlowProvider>
      <WorkflowStudioInner tenant={tenant} user={user} quickStart={quickStart} />
    </ReactFlowProvider>
  );
}
