import {useEffect,useRef,useState} from 'react';
import {ToolApprovalRequest} from './ToolApprovalRequest';
import {WorkflowApprovalRequest} from './WorkflowApprovalRequest';
import {api} from './api';
import {useScope,modeLabel} from './scoped';
import type {Tenant,User,ToolInfo,WorkflowNodeInfo,WorkflowEdgeInfo,ApprovedWorkflowSummary,WorkflowExecutionRun} from './types';

const DEFAULT_NODES: WorkflowNodeInfo[] = [
  {node_id:'step1',node_type:'input',title:'사용자 입력(질문)',config:{input_key:'query'}},
  {node_id:'step2',node_type:'read_tool',title:'금융 상품 조회(Tool)',config:{tool_id:'financial_product_lookup',arguments:{category:'deposit'}}},
  {node_id:'step3',node_type:'llm',title:'AI 모델 추론 요약',config:{model_id:'mock-fast',system_prompt:'금융 전문 상담 AI',user_template:'{{query}}에 대한 추천'}},
  {node_id:'step4',node_type:'validate',title:'출력 조건 검증',config:{target_key:'llm_output'}},
  {node_id:'step5',node_type:'output',title:'최종 응답 반환',config:{}}
];

const DEFAULT_EDGES: WorkflowEdgeInfo[] = [
  {source_node:'step1',target_node:'step2'},
  {source_node:'step2',target_node:'step3'},
  {source_node:'step3',target_node:'step4'},
  {source_node:'step4',target_node:'step5'}
];

const NODE_ICONS: Record<string,string> = {
  input: '📥',
  read_tool: '🛠️',
  llm: '🧠',
  validate: '🛡️',
  output: '📤'
};

const NODE_COLORS: Record<string,{bg:string;border:string;badge:string}> = {
  input: {bg:'#F0FDF4',border:'#86EFAC',badge:'#15803D'},
  read_tool: {bg:'#EFF6FF',border:'#93C5FD',badge:'#1D4ED8'},
  llm: {bg:'#FAF5FF',border:'#D8B4FE',badge:'#7E22CE'},
  validate: {bg:'#FFFBEB',border:'#FDE68A',badge:'#B45309'},
  output: {bg:'#F8FAFC',border:'#CBD5E1',badge:'#334155'}
};

import {WorkflowStudio} from './workflow/WorkflowStudio';

export function WorkflowCanvasPage({tenant,user}:{tenant:Tenant;user:User}){
  const scope=useScope();
  const options={tenantId:tenant.tenant_id,csrf:user.csrf_token,signal:scope.signal};
  const [activeTab,setActiveTab]=useState<'studio'|'execution'>('studio');
  const [tools,setTools]=useState<ToolInfo[]>([]);
  const [versions,setVersions]=useState<ApprovedWorkflowSummary[]>([]);
  const [selected,setSelected]=useState('');
  const [queryInput,setQueryInput]=useState('');
  const [run,setRun]=useState<WorkflowExecutionRun|null>(null);
  const [loading,setLoading]=useState(true);
  const [busy,setBusy]=useState(false);
  const [validating,setValidating]=useState(false);
  const [validationMsg,setValidationMsg]=useState<string|null>(null);
  const [error,setError]=useState<string|null>(null);
  const request=useRef<{version:string;query:string;client:string}|null>(null);
  const active=Boolean(run&&!run.is_terminal);
  const version=versions.find(v=>v.version_id===selected);
  const states:Record<string,string>={accepted:'대기',running:'실행 중',completed:'완료',cancelled:'취소',failed:'실패',blocked:'권한·정책 차단',interrupted:'중단 · 확인 필요',pending:'대기',succeeded:'완료',skipped:'실행하지 않음'};

  async function fail(problem:unknown){
    const message=await scope.fail(problem,()=>{setRun(null);setVersions([]);});
    if(scope.current())setError(message);
  }
  async function load(){
    setLoading(true);setError(null);
    try{
      const [catalog,registered]=await Promise.all([api.request<{items:ApprovedWorkflowSummary[]}>('/workflows/catalog',options),api.request<{items:ToolInfo[]}>('/tools',options)]);
      if(scope.current()){setVersions(catalog.items);setTools(registered.items);setSelected(current=>catalog.items.some(v=>v.version_id===current)?current:catalog.items[0]?.version_id??'');}
    }catch(problem){await fail(problem);}
    finally{if(scope.current())setLoading(false);}
  }
  useEffect(()=>{void load();},[]);
  async function refreshRun(){
    if(!run)return;
    try{
      const value=await api.request<WorkflowExecutionRun>('/workflows/runs/'+run.run_id,options);
      if(scope.current()){setRun(value);setError(null);}
    }catch(problem){await fail(problem);}
  }
  useEffect(()=>{
    if(!run||run.is_terminal)return;
    let current=true;let timer:ReturnType<typeof setTimeout>;
    async function poll(){
      try{
        const value=await api.request<WorkflowExecutionRun>('/workflows/runs/'+run!.run_id,options);
        if(current&&scope.current()){setRun(value);if(!value.is_terminal)timer=setTimeout(()=>void poll(),800);}
      }catch(problem){if(current)await fail(problem);}
    }
    timer=setTimeout(()=>void poll(),800);
    return()=>{current=false;clearTimeout(timer);};
  },[run?.run_id,run?.is_terminal]);
  async function handleRun(){
    if(!version?.execution_ready||!queryInput.trim()||busy||active)return;
    setBusy(true);setError(null);
    const query=queryInput.trim();
    if(run?.is_terminal||request.current?.version!==selected||request.current?.query!==query)request.current={version:selected,query,client:crypto.randomUUID()};
    setRun(null);
    try{
      const value=await api.request<WorkflowExecutionRun>('/workflows/run',{...options,method:'POST',body:{version_id:selected,client_request_id:request.current!.client,inputs:{[version.input_key]:query}}});
      if(scope.current())setRun(value);
    }catch(problem){await fail(problem);}
    finally{if(scope.current())setBusy(false);}
  }
  async function cancel(){
    if(!run||busy)return;setBusy(true);setError(null);
    try{
      const value=await api.request<WorkflowExecutionRun>('/workflows/runs/'+run.run_id+'/cancel',{...options,method:'POST',body:{expected_revision:run.revision}});
      if(scope.current())setRun(value);
    }catch(problem){await fail(problem);}
    finally{if(scope.current())setBusy(false);}
  }
  async function handleValidate(){
    setValidating(true);setError(null);setValidationMsg(null);
    try{
      const value=await api.request<{node_count:number;execution_order:string[]}>('/workflows/validate',{...options,method:'POST',body:{workflow_id:'wf-financial-preview',name:'구조 검토 예시',nodes:DEFAULT_NODES,edges:DEFAULT_EDGES}});
      if(scope.current())setValidationMsg(`예시 DAG 구조 검증: ${value.node_count}개 노드, ${value.execution_order.join(' → ')}. 승인·실행 검증은 별도입니다.`);
    }catch(problem){await fail(problem);}
    finally{if(scope.current())setValidating(false);}
  }
  const panel={background:'#FFFFFF',border:'1px solid #E2E8F0',borderRadius:10,padding:20,marginBottom:20};
  return <div className="admin-a-container" style={{maxWidth:1600,margin:'0 auto',padding:24}}>
    <header style={{marginBottom:20,display:'flex',justifyContent:'space-between',alignItems:'flex-end',flexWrap:'wrap',gap:16}}>
      <div>
        <h1 style={{margin:'0 0 6px 0',fontSize:24,fontWeight:800}}>시각적 Workflow Studio &amp; 오케스트레이션 (DP-20 ~ DP-23)</h1>
        <p style={{margin:0,color:'#64748B'}}>제안 시안(4.4-03) 규격의 컴포넌트 라이브러리, 드래그 앤 드롭 비주얼 캔버스 및 실행 오케스트레이션을 제공합니다.</p>
      </div>
      <div style={{display:'flex',gap:8,background:'#F1F5F9',padding:4,borderRadius:8}}>
        <button
          type="button"
          onClick={()=>setActiveTab('studio')}
          style={{
            padding:'8px 16px',
            fontSize:13,
            fontWeight:700,
            borderRadius:6,
            border:'none',
            cursor:'pointer',
            background:activeTab==='studio'?'#4F46E5':'transparent',
            color:activeTab==='studio'?'#FFFFFF':'#475569',
            boxShadow:activeTab==='studio'?'0 2px 6px rgba(79,70,229,0.25)':'none'
          }}
        >
          🧩 시각적 UI Studio (Canvas)
        </button>
        <button
          type="button"
          onClick={()=>setActiveTab('execution')}
          style={{
            padding:'8px 16px',
            fontSize:13,
            fontWeight:700,
            borderRadius:6,
            border:'none',
            cursor:'pointer',
            background:activeTab==='execution'?'#4F46E5':'transparent',
            color:activeTab==='execution'?'#FFFFFF':'#475569',
            boxShadow:activeTab==='execution'?'0 2px 6px rgba(79,70,229,0.25)':'none'
          }}
        >
          ⚡ 승인 버전 실행 &amp; 체크포인트
        </button>
      </div>
    </header>

    {error&&<p role="alert">{error}</p>}
    {validationMsg&&<p role="status">{validationMsg}</p>}

    {activeTab==='studio'?(
      <section style={{marginBottom:24}} aria-label="시각적 블록 조립형 UI Studio">
        <WorkflowStudio tenant={tenant} user={user}/>
      </section>
    ):(
      <>
        <WorkflowApprovalRequest tenant={tenant} user={user}/><ToolApprovalRequest tenant={tenant} user={user}/>
        <section style={panel} aria-label="승인 Workflow 실행">
          <h2>승인 Workflow 실행</h2>
          <div style={{display:'flex',alignItems:'center',gap:12,flexWrap:'wrap'}}>
            <label htmlFor="workflow-approved-version">승인 버전</label>
            <select id="workflow-approved-version" value={selected} onChange={e=>setSelected(e.target.value)} disabled={busy||active||loading}>
              {!versions.length&&<option value="">승인된 Workflow가 없습니다</option>}
              {versions.map(v=><option key={v.version_id} value={v.version_id}>{v.name} · v{v.revision}</option>)}
            </select>
            <button type="button" className="secondary" onClick={()=>void load()} disabled={busy||active}>승인 목록 새로고침</button>
            {version&&<span>{modeLabel(version.execution_mode)}</span>}
          </div>
          {!loading&&!versions.length&&<p>현재 이용할 수 있는 승인 버전이 없습니다. 관리자 승인과 현재 Agent·Tool 권한을 확인해 주세요.</p>}
          <label htmlFor="wf-query-input" style={{display:'block',marginTop:16}}>실행 질문</label>
          <textarea id="wf-query-input" value={queryInput} onChange={e=>setQueryInput(e.target.value)} maxLength={4000} disabled={busy||active} rows={3} style={{width:'100%'}} placeholder="승인된 업무 흐름에 전달할 질문을 입력하세요."/>
          <button type="button" className="primary" onClick={()=>void handleRun()} disabled={busy||active||!version?.execution_ready||!queryInput.trim()}>
            {busy?'처리 중':version?.execution_ready?'Workflow 실행':'승인 Workflow 실행 준비 중'}
          </button>
          {active&&<button type="button" className="secondary" onClick={()=>void cancel()} disabled={busy}>Workflow 취소</button>}
        </section>
        <section style={panel} aria-label="실행 체크포인트">
          <h2>단계별 실행 체크포인트</h2>
          {!run?<p>승인 버전을 실행하면 단계 상태와 자식 실행 번호가 여기에 표시됩니다.</p>:<>
            <p role="status">{states[run.state]??run.state} · {modeLabel(run.execution_mode)}</p>
            <p style={{overflowWrap:'anywhere'}}>실행 번호: {run.run_id}</p>
            <button type="button" className="secondary" onClick={()=>void refreshRun()}>결과 새로고침</button>
            <ol>{run.steps.map(step=><li key={step.node_id} style={{margin:'10px 0',overflowWrap:'anywhere'}}>
              <strong>{step.node_id}</strong> · {states[step.state]??step.state}
              {step.child_run_id&&<small style={{display:'block'}}>Agent 실행: {step.child_run_id}</small>}
              {step.tool_client_id&&<small style={{display:'block'}}>Tool 요청: {step.tool_client_id}</small>}
            </li>)}</ol>
            {run.result_access==='final'&&<div><h3>최종 결과</h3><pre style={{whiteSpace:'pre-wrap',overflowWrap:'anywhere'}}>{typeof run.result==='string'?run.result:JSON.stringify(run.result,null,2)}</pre></div>}
            {run.is_terminal&&run.result_access!=='final'&&<p>최종 결과를 제공할 수 없습니다. 현재 승인·자료 권한 또는 실행 상태를 확인해 주세요.</p>}
          </>}
        </section>
        <section style={panel} aria-label="워크플로우 DAG 시각화">
          <h2>다단계 실행 파이프라인 흐름 (DAG)</h2>
          <p>아래 5개 노드는 구조 검토용 예시입니다. 선택한 승인 버전의 실행 결과는 위 체크포인트에 표시됩니다.</p>
          <button type="button" className="secondary" onClick={()=>void handleValidate()} disabled={validating}>DAG 구조 검증</button>
          <div style={{display:'flex',gap:12,overflowX:'auto',padding:'16px 0'}}>{DEFAULT_NODES.map(node=>{
            const color=NODE_COLORS[node.node_type];
            return <article key={node.node_id} style={{minWidth:190,padding:16,border:`1px solid ${color.border}`,background:color.bg,borderRadius:8}}>
              <span>{NODE_ICONS[node.node_type]} {node.node_type}</span><h3 style={{fontSize:14}}>{node.title}</h3><small>구조 예시</small>
            </article>;
          })}</div>
        </section>
        <section style={panel} aria-label="표준 도구 카탈로그">
          <h2>등록된 표준 읽기 도구 (Tool &amp; MCP Gateway)</h2>
          <div style={{display:'grid',gridTemplateColumns:'repeat(auto-fit,minmax(220px,1fr))',gap:16}}>{tools.map(tool=><article key={tool.tool_id}>
            <h3>{tool.name}</h3><p>{tool.description}</p><small>{tool.execution_ready?'현재 이용 가능':'승인 또는 연결 준비 필요'}</small>
          </article>)}</div>
        </section>
      </>
    )}
  </div>;
}

