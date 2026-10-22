import {test,expect} from '@playwright/test';
import type {WorkflowNodeInfo,WorkflowEdgeInfo} from '../src/types';
import {validateWorkflowProposal,workflowProposalToCanvas,type WorkflowProposal} from '../src/workflow/workflowAdapter';
import {control,fixture,login} from './support';

function proposal(nodes:WorkflowNodeInfo[]=[
 {node_id:'input',node_type:'input',title:'질문 입력',config:{input_key:'query'}},
 {node_id:'agent',node_type:'llm',title:'AI 답변',config:{}},
 {node_id:'output',node_type:'output',title:'응답 반환',config:{}}
],edges:WorkflowEdgeInfo[]=[{source_node:'input',target_node:'agent'},{source_node:'agent',target_node:'output'}]):WorkflowProposal{
 return {name:'규정 안내',description:'입력을 확인해 안내합니다.',nodes,edges,missing_questions:[],warnings:[]};
}

test('workflow proposal mapping accepts only a safe connected proposal and maps supported types',()=>{
 const value=proposal();
 expect(validateWorkflowProposal(value)).toBeNull();
 const graph=workflowProposalToCanvas(value);
 expect(graph.nodes.map(node=>node.id)).toEqual(['input','agent','output']);
 expect(graph.edges.map(edge=>[edge.source,edge.target])).toEqual([['input','agent'],['agent','output']]);
 const withTool=proposal([
  {node_id:'input',node_type:'input',title:'질문 입력',config:{input_key:'query'}},
  {node_id:'lookup',node_type:'read_tool',title:'자료 조회',config:{}},
  {node_id:'agent',node_type:'llm',title:'AI 답변',config:{}},
  {node_id:'output',node_type:'output',title:'응답 반환',config:{}}
 ],[{source_node:'input',target_node:'lookup'},{source_node:'lookup',target_node:'agent'},{source_node:'agent',target_node:'output'}]);
 expect(validateWorkflowProposal(withTool)).toBeNull();
 expect(workflowProposalToCanvas(withTool).nodes.map(node=>(node.data as {nodeType:string}).nodeType)).toEqual(['input','read_tool','llm','output']);
});

test('workflow proposal rejects missing endpoints, cycles, unsupported nodes and forged references',()=>{
 expect(validateWorkflowProposal(proposal(undefined,[{source_node:'input',target_node:'missing'},{source_node:'agent',target_node:'output'}]))).toContain('연결');
 expect(validateWorkflowProposal(proposal(undefined,[{source_node:'input',target_node:'agent'},{source_node:'agent',target_node:'output'},{source_node:'output',target_node:'agent'}]))).toContain('순환');
 expect(validateWorkflowProposal(proposal([{node_id:'input',node_type:'trigger' as never,title:'입력',config:{input_key:'query'}}, {node_id:'agent',node_type:'llm',title:'AI',config:{}},{node_id:'output',node_type:'output',title:'출력',config:{}}]))).toContain('지원하지 않는');
 expect(validateWorkflowProposal(proposal([{node_id:'input',node_type:'input',title:'입력',config:{input_key:'query'}},{node_id:'agent',node_type:'llm',title:'AI',config:{agent_id:'forged-agent'}},{node_id:'output',node_type:'output',title:'출력',config:{}}]))).toContain('ID');
 expect(validateWorkflowProposal(proposal([{node_id:'input',node_type:'input',title:'입력',config:{input_key:'query'}},{node_id:'agent',node_type:'read_tool',title:'도구',config:{tool_id:'forged-tool'}},{node_id:'output',node_type:'output',title:'출력',config:{}}]))).toContain('ID');
});

test('workflow proposal rejects secrets, URLs, invalid bounds and malformed notices',()=>{
 expect(validateWorkflowProposal(proposal([{node_id:'input',node_type:'input',title:'https://internal.example',config:{input_key:'query'}},{node_id:'agent',node_type:'llm',title:'AI',config:{}},{node_id:'output',node_type:'output',title:'출력',config:{}}]))).toContain('비밀');
 const tooManyNodes=Array.from({length:21},(_,index)=>({node_id:`n${index}`,node_type:index===0?'input':index===20?'output':index===1?'llm':'validate',title:`노드 ${index}`,config:index===0?{input_key:'query'}:{}})) as WorkflowNodeInfo[];
 const tooManyEdges=tooManyNodes.slice(1).map((node,index)=>({source_node:tooManyNodes[index].node_id,target_node:node.node_id}));
 expect(validateWorkflowProposal(proposal(tooManyNodes,tooManyEdges))).toContain('개수가');
 const nodes=Array.from({length:9},(_,index)=>({node_id:`m${index}`,node_type:index===0?'input':index===1?'llm':index===8?'output':'validate',title:`노드 ${index}`,config:index===0?{input_key:'query'}:{}})) as WorkflowNodeInfo[];
 const edges=nodes.flatMap((source,index)=>nodes.slice(index+1).map(target=>({source_node:source.node_id,target_node:target.node_id}))).slice(0,31);
 expect(validateWorkflowProposal(proposal(nodes,edges))).toContain('개수가');
 const normal=proposal();normal.warnings=['api_key=sk-12345678901234567890'];expect(validateWorkflowProposal(normal)).toContain('안내 문구');
});

test.describe('Workflow proposal UI contract',()=>{
 test.beforeEach(()=>control('case-start'));
 test.afterEach(()=>control('release-provider'));
 test('proposal is tenant scoped, stays unsaved until explicit draft save, and never validates or runs',async({page})=>{
  await login(page,'P-A');
  const tenant=fixture().tenants.A,proposalId='40000000-0000-4000-8000-000000000001';
  const envelope=(data:unknown)=>({data,meta:{tenant_id:tenant,request_id:'workflow-scaffold-contract'}});
  const events:string[]=[];const draftClients:string[]=[];let proposalBody:any=null,draftBody:any=null;
  await page.route('**/api/v1/workflows/catalog',route=>route.fulfill({json:envelope({items:[]})}));
  await page.route('**/api/v1/tools',route=>route.fulfill({json:envelope({items:[]})}));
  await page.route('**/api/v1/workflows/drafts',async route=>{
   const req=route.request();expect(req.headers()['x-tenant-id']).toBe(tenant);
   if(req.method()==='GET'){await route.fulfill({json:envelope({items:[]})});return;}
   events.push('draft-save');draftBody=req.postDataJSON();draftClients.push(draftBody.client_request_id);expect(req.headers()['x-csrf-token']).toBeTruthy();
   if(draftClients.length===1){await route.fulfill({status:503,json:{error:{code:'TEMPORARY_FAILURE',message:'일시적인 저장 오류'},meta:{tenant_id:tenant,request_id:'draft-retry'}}});return;}
   await route.fulfill({status:201,json:envelope({draft_id:draftBody.draft_id,revision:1,name:draftBody.name,description:draftBody.description})});
  });
  await page.route('**/api/v1/admin/builder/scaffolds*',async route=>{
   const req=route.request();expect(req.headers()['x-tenant-id']).toBe(tenant);
   if(req.method()==='POST'){events.push('proposal');proposalBody=req.postDataJSON();await route.fulfill({status:201,json:envelope({proposal_id:proposalId,state:'ready',revision:1,proposal:proposal()})});return;}
   await route.continue();
  });
  const forbidden:string[]=[];
  page.on('request',request=>{const path=new URL(request.url()).pathname;if(request.method()==='POST'&&/workflows\/(validate|run|approved)|tools\//.test(path))forbidden.push(path);});
  await page.goto('/manage/admin/workflows');
  const panel=page.getByRole('region',{name:'Workflow 초안 제안 검토'});
  await page.getByLabel('어떤 업무 흐름을 만들고 싶나요?').fill('직원 질문에 규정 근거를 찾아 답변합니다.');
  await page.getByLabel(/주 사용자는 누구인가요/).fill('현업 담당자');
  await page.getByRole('button',{name:'Workflow 제안 만들기',exact:true}).click();
  await expect(panel).toBeVisible();expect(proposalBody).toMatchObject({target:'workflow',intent:'직원 질문에 규정 근거를 찾아 답변합니다.',answers:{audience:'현업 담당자'}});
  await expect(panel).toContainText('게시 Agent 버전 미연결');await expect(panel).toContainText('도구 미연결');
  await page.getByRole('button',{name:'Canvas에 가져와 편집',exact:true}).click();
  const replace=page.getByRole('alertdialog',{name:'현재 Canvas 내용을 바꿀까요?'});await expect(replace).toBeVisible();
  await replace.getByRole('button',{name:'현재 Canvas 교체 후 가져오기',exact:true}).click();
  await expect(page.getByText(/미연결 Agent·Tool 참조/)).toBeVisible();
  expect(events).toEqual(['proposal']);expect(forbidden).toEqual([]);
  await page.getByRole('button',{name:'초안 저장 · r0',exact:true}).click();await expect(page.getByRole('alert')).toBeVisible();
  expect(events).toEqual(['proposal','draft-save']);
  await page.getByRole('button',{name:'초안 저장 · r0',exact:true}).click();await expect(page.getByRole('status')).toContainText('초안 1차 버전을 저장했습니다.');
  expect(events).toEqual(['proposal','draft-save','draft-save']);expect(draftClients[1]).toBe(draftClients[0]);
  expect(draftBody).toMatchObject({expected_revision:0,graph:{nodes:[{node_id:'input',node_type:'input'},{node_id:'agent',node_type:'llm'},{node_id:'output',node_type:'output'}],edges:[{source_node:'input',target_node:'agent'},{source_node:'agent',target_node:'output'}]}});
  expect(draftBody.client_request_id).toMatch(/^[0-9a-f-]{36}$/);expect(forbidden).toEqual([]);
 });
});
