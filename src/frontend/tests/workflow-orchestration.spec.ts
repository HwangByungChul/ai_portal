import {test,expect} from '@playwright/test';
import {control,login} from './support';

test.beforeEach(()=>control('case-start'));
test.afterEach(async()=>{control('release-provider');await expect.poll(()=>control('b05-counts').active,{timeout:6000}).toBe(0);});

test('WF_01_workflow_canvas_copy_controls_and_responsive_panels',async({page})=>{
  await login(page,'P-A');
  const envelope=(data:unknown)=>({data,meta:{tenant_id:'10000000-0000-4000-8000-00000000000a',request_id:'workflow-layout-contract'}});
  await page.route('**/api/v1/workflows/catalog',route=>route.fulfill({json:envelope({items:[]})}));
  await page.route('**/api/v1/workflows/validate',route=>route.fulfill({json:envelope({node_count:5,execution_order:['step1_input','step2_rag','step3_tool','step4_llm','step5_output']})}));
  await page.goto('/manage/admin/workflows');
  await expect(page.getByRole('heading',{name:'Workflow Canvas',exact:true})).toBeVisible();
  await expect(page.locator('.workflow-canvas-page')).not.toContainText(/DP-20|DP-23|제안 시안|4\.4-03|배포 & 게시/);
  await expect(page.getByRole('button',{name:'▶ 승인 버전 실행',exact:true})).toBeDisabled();
  await expect(page.getByRole('note').filter({hasText:'편집 내용은 개인 초안으로 저장됩니다.'})).toBeVisible();
  await expect(page.locator('.react-flow__node')).toHaveCount(5);
  await page.getByRole('button',{name:'🛡️ 구조 검증',exact:true}).click();
  await expect(page.getByRole('status')).toContainText('총 5개 노드');

  for(const width of [1440,1024,768,390]){
    await page.setViewportSize({width,height:1000});
    const root=page.locator('.workflow-studio-root');
    const layout=await root.evaluate(element=>{
      const bounds=element.getBoundingClientRect();
      const canvas=element.querySelector('.workflow-canvas-container')!.getBoundingClientRect();
      const palette=element.querySelector('.workflow-palette')!.getBoundingClientRect();
      const inspector=element.querySelector('.workflow-inspector')!.getBoundingClientRect();
      const controls=Array.from(element.querySelectorAll('.workflow-studio-actions > button,.workflow-studio-actions select'));
      return {
        pageFits:document.documentElement.scrollWidth<=innerWidth,
        canvasHeight:canvas.height,
        controlsFit:controls.every(control=>{const rect=control.getBoundingClientRect();return rect.width>0&&rect.left>=bounds.left&&rect.right<=bounds.right&&control.scrollWidth<=control.clientWidth+1;}),
        stacked:palette.bottom<=canvas.top+1&&canvas.bottom<=inspector.top+1
      };
    });
    expect(layout.pageFits,`document overflow at ${width}px`).toBe(true);
    expect(layout.controlsFit,`toolbar clipping at ${width}px`).toBe(true);
    expect(layout.canvasHeight).toBeGreaterThanOrEqual(480);
    if(width<=1024)expect(layout.stacked,`stacked panels at ${width}px`).toBe(true);
    await page.getByLabel('워크플로우 명칭',{exact:true}).fill(`화면 폭 ${width} 초안`);
    await expect(page.getByLabel('Workflow 이름',{exact:true})).toHaveValue(`화면 폭 ${width} 초안`);
    const filters=page.locator('.workflow-palette-filters');
    expect(await filters.locator('button').evaluateAll(buttons=>buttons.every(button=>getComputedStyle(button).flexShrink==='0'&&getComputedStyle(button).whiteSpace==='nowrap'))).toBe(true);
    await filters.evaluate(element=>{element.scrollLeft=element.scrollWidth;});
    if(width<=1024){
      const cards=page.locator('.workflow-palette-list');
      expect(await cards.evaluate(element=>{element.scrollLeft=element.scrollWidth;return element.scrollLeft>0;})).toBe(true);
    }
  }
  await page.getByRole('button',{name:/실행 모니터링/}).click();
  await page.getByLabel('승인 버전 실행 질문:',{exact:true}).fill('질문 입력 유지');
  await expect(page.getByLabel('승인 버전 실행 질문:',{exact:true})).toHaveValue('질문 입력 유지');
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
  await page.getByRole('button',{name:'⚡ 승인·실행 관리',exact:true}).click();
  await expect(page.locator('.workflow-canvas-page')).not.toContainText(/DAG|revision|체크포인트|제안 시안|4\.4-03/);
  await page.getByLabel('실행 질문',{exact:true}).fill('승인 버전 질문');
  await page.getByRole('button',{name:'Workflow 실행',exact:true}).click();
  await expect(page.getByRole('heading',{name:'최종 결과',exact:true})).toBeVisible();
  await expect(page.getByText('계약 검증 최종 결과',{exact:true})).toBeVisible();
  expect(submitted).toMatchObject({version_id:version,inputs:{query:'승인 버전 질문'}});
  expect(submitted).not.toHaveProperty('workflow');
  expect((submitted as unknown as {client_request_id:string}).client_request_id).toMatch(/^[0-9a-f-]{36}$/);
  await page.getByRole('button',{name:'Workflow 실행',exact:true}).click();
  await expect(page.getByRole('alert')).toBeVisible();
  await expect(page.getByRole('alert').getByRole('button')).toHaveCount(0);
  await expect(page.getByRole('button',{name:'알림 닫기'})).toBeVisible();
  await page.getByRole('button',{name:'Workflow 실행',exact:true}).click();
  await expect(page.getByRole('heading',{name:'최종 결과',exact:true})).toBeVisible();
  expect(submissions).toHaveLength(3);
  expect(submissions[1].client_request_id).toBe(submissions[2].client_request_id);
  expect(submissions[0].client_request_id).not.toBe(submissions[1].client_request_id);
});
