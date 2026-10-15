import {test,expect} from '@playwright/test';
import {control,login} from './support';
test.beforeEach(()=>control('case-start'));
test.afterEach(async()=>{control('release-provider');await expect.poll(()=>control('b05-counts').active,{timeout:6000}).toBe(0);});

// Actual DB/API approval/admission/settlement is verified in test_meeting_workflow.py.
// This test uses HTTP stubs only for the scoped UI's asynchronous execution contract.
test('WF_03_meeting_ui_scoped_execution_and_structured_result_contract',async({page})=>{
 await login(page,'A-U1');
 const tenant='10000000-0000-4000-8000-00000000000a',version='30000000-0000-4000-8000-000000000001',run='30000000-0000-4000-8000-000000000002';
 const envelope=(data:unknown)=>({data,meta:{tenant_id:tenant,request_id:'30000000-0000-4000-8000-000000000003'}});
 await page.route('**/api/v1/use-cases',async route=>{
  expect(route.request().headers()['x-tenant-id']).toBe(tenant);
  await route.fulfill({json:envelope({items:[{use_case_id:'AGENT_03',name:'회의록 및 액션아이템 Agent',category:'document',description:'계약 대역',approved_asset_version:'manifest',approved_version_id:version,execution_ready:true,required_tools:[],role_scope:['USER','PADMIN'],auto_decision_prohibited:false,disclaimer:null,example_queries:[]}]})});
 });
 let submitted:Record<string,unknown>|undefined;
 const record={run_id:run,version_id:version,workflow_id:version,state:'accepted',revision:1,is_terminal:false,execution_mode:'mock',steps:[],result_access:'unavailable',result:null,error_code:null,replayed:false};
 await page.route('**/api/v1/use-cases/AGENT_03/execute',async route=>{
  expect(route.request().headers()['x-tenant-id']).toBe(tenant);expect(route.request().headers()['x-csrf-token']).toBeTruthy();
  submitted=route.request().postDataJSON();await route.fulfill({status:202,json:envelope(record)});
 });
 await page.route('**/api/v1/use-cases/AGENT_03/runs/'+run,async route=>route.fulfill({json:envelope({...record,state:'completed',revision:3,is_terminal:true,result_access:'final',result:{decisions:[{text:'자료 검토',quote:'자료를 검토하기로 했다.'}],unresolved:[],actions:[{text:'후속 검토',quote:'후속 검토를 하기로 했다.',assignee:null,due_date:null}]}})}));
 await page.goto('/user/use-cases');
 await page.getByLabel('회의 메모',{exact:true}).fill('자료를 검토하기로 했다.');
 await page.getByRole('button',{name:'Agent 실행 및 초안 생성',exact:true}).click();
 await expect(page.getByRole('heading',{name:'검증된 회의록 초안',exact:true})).toBeVisible();
 await expect(page.getByText('담당자: 미정 · 기한: 미정',{exact:true})).toBeVisible();
 expect(submitted).toMatchObject({prompt:'자료를 검토하기로 했다.'});
 expect(submitted?.client_request_id).toMatch(/^[0-9a-f-]{36}$/);
 expect(submitted).not.toHaveProperty('context_data');expect(submitted).not.toHaveProperty('version_id');
});
