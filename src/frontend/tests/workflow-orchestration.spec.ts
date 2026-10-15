import {test,expect} from '@playwright/test';
import {control,login} from './support';

test.beforeEach(()=>control('case-start'));
test.afterEach(async()=>{control('release-provider');await expect.poll(()=>control('b05-counts').active,{timeout:6000}).toBe(0);});

test('WF_01_workflow_canvas_page_view_and_dag_nodes',async({page})=>{
  await login(page,'P-A');
  const catalog=page.waitForResponse(reply=>reply.url().endsWith('/api/v1/workflows/catalog'));
  await page.goto('/manage/admin/workflows');
  expect((await catalog).status()).toBe(200);
  
  await expect(page.getByRole('heading',{name:'Workflow 오케스트레이션 Canvas (DP-20 ~ DP-23)',exact:true})).toBeVisible();
  await expect(page.getByText('다단계 실행 파이프라인 흐름 (DAG)')).toBeVisible();
  await expect(page.getByText('사용자 입력(질문)')).toBeVisible();
  await expect(page.getByText('금융 상품 조회(Tool)')).toBeVisible();
  await expect(page.getByText('AI 모델 추론 요약')).toBeVisible();
  await expect(page.getByText('출력 조건 검증')).toBeVisible();
  await expect(page.getByText('최종 응답 반환')).toBeVisible();

  await expect(page.getByRole('button',{name:'DAG 구조 검증',exact:true})).toBeVisible();
  await expect(page.getByRole('button',{name:'승인 Workflow 실행 준비 중',exact:true})).toBeDisabled();
  await expect(page.getByText('현재 조직의 승인된 Workflow 버전을 실행하고 Agent·Tool의 진행 상태를 확인합니다.')).toBeVisible();
  await expect(page.getByRole('alert')).toHaveCount(0);
  const validated=page.waitForResponse(reply=>reply.url().endsWith('/api/v1/workflows/validate'));
  await page.getByRole('button',{name:'DAG 구조 검증',exact:true}).click();
  expect((await validated).status()).toBe(200);
  await expect(page.getByRole('status')).toContainText('승인·실행 검증은 별도입니다.');
});

// The HTTP runtime and ledgers are tested against PostgreSQL in backend integration tests.
// This browser contract test verifies the real UI's tenant/CSRF/version-only request and polling.
test('WF_02_approved_version_runtime_ui_contract',async({page})=>{
  await login(page,'P-A');
  const tenant='10000000-0000-4000-8000-00000000000a';
  const version='30000000-0000-4000-8000-000000000001';
  const run='30000000-0000-4000-8000-000000000002';
  const envelope=(data:unknown)=>({data,meta:{tenant_id:tenant,request_id:'30000000-0000-4000-8000-000000000003'}});
  let submitted:Record<string,unknown>|null=null;
  const submissions:Record<string,unknown>[]=[];
  await page.route('**/api/v1/workflows/catalog',async route=>{
    expect(route.request().headers()['x-tenant-id']).toBe(tenant);
    await route.fulfill({json:envelope({items:[{workflow_id:version,version_id:version,revision:1,name:'승인 테스트 흐름',description:'브라우저 계약 대역',input_key:'query',execution_mode:'mock',execution_ready:true,node_count:3}]})});
  });
  const record={run_id:run,version_id:version,workflow_id:version,state:'accepted',revision:1,is_terminal:false,execution_mode:'mock',steps:[{node_id:'input',node_type:'input',state:'pending',child_run_id:null,tool_client_id:null,error_code:null},{node_id:'agent',node_type:'llm',state:'pending',child_run_id:null,tool_client_id:null,error_code:null},{node_id:'output',node_type:'output',state:'pending',child_run_id:null,tool_client_id:null,error_code:null}],result_access:'unavailable',result:null,error_code:null,replayed:false};
  await page.route('**/api/v1/workflows/run',async route=>{
    expect(route.request().headers()['x-tenant-id']).toBe(tenant);
    expect(route.request().headers()['x-csrf-token']).toBeTruthy();
    submitted=route.request().postDataJSON();
    submissions.push(submitted!);
    if(submissions.length===2){await route.abort('failed');return;}
    await route.fulfill({status:202,json:envelope(record)});
  });
  await page.route('**/api/v1/workflows/runs/'+run,async route=>route.fulfill({json:envelope({...record,state:'completed',revision:3,is_terminal:true,result_access:'final',result:'계약 검증 최종 결과',steps:record.steps.map(s=>({...s,state:'succeeded'}))})}));
  await page.goto('/manage/admin/workflows');
  await page.getByLabel('실행 질문',{exact:true}).fill('승인 버전 질문');
  await page.getByRole('button',{name:'Workflow 실행',exact:true}).click();
  await expect(page.getByRole('heading',{name:'최종 결과',exact:true})).toBeVisible();
  await expect(page.getByText('계약 검증 최종 결과',{exact:true})).toBeVisible();
  expect(submitted).toMatchObject({version_id:version,inputs:{query:'승인 버전 질문'}});
  expect(submitted).not.toHaveProperty('workflow');
  expect((submitted as unknown as {client_request_id:string}).client_request_id).toMatch(/^[0-9a-f-]{36}$/);
  await page.getByRole('button',{name:'Workflow 실행',exact:true}).click();
  await expect(page.getByRole('alert')).toBeVisible();
  await page.getByRole('button',{name:'Workflow 실행',exact:true}).click();
  await expect(page.getByRole('heading',{name:'최종 결과',exact:true})).toBeVisible();
  expect(submissions).toHaveLength(3);
  expect(submissions[1].client_request_id).toBe(submissions[2].client_request_id);
  expect(submissions[0].client_request_id).not.toBe(submissions[1].client_request_id);
});
