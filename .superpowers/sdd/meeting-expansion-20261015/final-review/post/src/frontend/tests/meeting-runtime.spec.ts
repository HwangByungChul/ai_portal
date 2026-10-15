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
 await page.route('**/api/v1/use-cases/AGENT_03/documents?*',r=>r.fulfill({json:envelope({items:[],next_cursor:null})}));await page.route('**/api/v1/use-cases/AGENT_03/runs/'+run+'/quality',r=>r.fulfill({status:404,json:{error:{code:'RESOURCE_NOT_FOUND'}}}));
 await page.goto('/user/use-cases');
 await page.getByLabel('회의 메모',{exact:true}).fill('자료를 검토하기로 했다.');
 await page.getByRole('button',{name:'Agent 실행 및 초안 생성',exact:true}).click();
 await expect(page.getByRole('heading',{name:'원문 근거를 검사한 회의록 초안',exact:true})).toBeVisible();
 await expect(page.getByText(/담당자: 미정 · 기한: 미확정/)).toBeVisible();
 expect(submitted).toMatchObject({prompt:'자료를 검토하기로 했다.'});
 expect(submitted?.client_request_id).toMatch(/^[0-9a-f-]{36}$/);
 expect(submitted).not.toHaveProperty('context_data');expect(submitted).not.toHaveProperty('version_id');
});

test('WF_12_HTTP_stub_full_receipt_pagination_quality_replay_CAS',async({page})=>{
 await login(page,'A-U1');const tenant='10000000-0000-4000-8000-00000000000a',id='30000000-0000-4000-8000-000000000012';const envelope=(data:unknown)=>({data,meta:{tenant_id:tenant,request_id:id}});const doc=(n:number)=>({document_id:id.slice(0,-2)+String(n).padStart(2,'0'),version_id:id.slice(0,-2)+String(n+10).padStart(2,'0'),version_no:1,title:'합성 자료 '+n,character_length:20,source_sha256:'a'.repeat(64),ready:n!==4,unavailable_reason:n===4?'source_unavailable':null});
 let revoked=false,listingFailure=false;await page.route('**/api/v1/use-cases',r=>r.fulfill({json:envelope({items:[{use_case_id:'AGENT_03',name:'회의록',category:'document',description:'합성',execution_ready:true}]})}));await page.route('**/api/v1/use-cases/AGENT_03/documents?*',r=>listingFailure?r.abort('failed'):r.fulfill({json:envelope(r.request().url().includes('cursor')?{items:revoked?[doc(4)]:[doc(3),doc(4)],next_cursor:null}:{items:[doc(1),doc(2)],next_cursor:id})}));
 const result={decisions:[{text:'합성 결정',quote:'검토한다',source_ref:'memo'}],unresolved:[],actions:[]};const run={run_id:id,version_id:id,workflow_id:id,state:'completed',revision:3,is_terminal:true,execution_mode:'mock',steps:[],result_access:'final',result,error_code:null,meeting_context:{meeting_date:'2026-10-15',documents:[]}};let writes:any[]=[];await page.route('**/api/v1/use-cases/AGENT_03/execute',async r=>{writes.push(r.request().postDataJSON());if(writes.length===1)await r.abort('failed');else await r.fulfill({json:envelope(run)});});
 let reviews:any[]=[];let revision=0;const quality=()=>({run_id:id,run_revision:3,result_digest:'a'.repeat(64),review_revision:revision,history_limit:20,human_review_required:true,structural:{evidence_valid:true,item_count:1,unresolved_deadlines:0,past_deadlines:0,error:null,human_review_required:true},items:[]});await page.route('**/api/v1/use-cases/AGENT_03/runs/'+id+'/quality',async r=>{if(r.request().method()==='GET')return r.fulfill({json:envelope(quality())});reviews.push(r.request().postDataJSON());if(reviews.length===1){revision=1;return r.abort('failed');}if(reviews.length===2)return r.fulfill({json:envelope(quality())});return r.fulfill({status:409,json:{error:{code:'REVISION_CONFLICT'},meta:{tenant_id:tenant,request_id:id}}});});
 await page.goto('/user/use-cases');await page.getByRole('checkbox',{name:/합성 자료 1/}).check();await page.getByRole('button',{name:'자료 더 보기'}).click();await page.getByRole('checkbox',{name:/합성 자료 2/}).check();await page.getByRole('checkbox',{name:/합성 자료 3/}).check();await expect(page.getByRole('checkbox',{name:/합성 자료 4/})).toBeDisabled();await expect(page.getByText(/선택 유지:/)).toContainText('합성 자료 1');await page.getByRole('button',{name:'자료 새로고침 · 선택 재확인'}).click();await expect(page.getByRole('checkbox',{name:/합성 자료 3/})).toBeChecked();listingFailure=true;await page.getByRole('button',{name:'자료 새로고침 · 선택 재확인'}).click();await expect(page.getByRole('alert')).toContainText('확인되지 않은 선택은 유지');await expect(page.getByRole('checkbox',{name:/합성 자료 3/})).toBeChecked();listingFailure=false;await page.getByRole('button',{name:'자료 새로고침 · 선택 재확인'}).click();await expect(page.getByRole('checkbox',{name:/합성 자료 3/})).toBeChecked();await page.getByLabel('회의일 (선택 · 한국 업무 날짜)').fill('2026-10-15');await page.getByLabel('회의 메모',{exact:true}).fill('검토한다');await page.getByRole('button',{name:'Agent 실행 및 초안 생성'}).click();await expect(page.getByRole('alert')).toBeVisible();await page.getByRole('button',{name:'Agent 실행 및 초안 생성'}).click();await expect(page.getByRole('heading',{name:'원문 근거를 검사한 회의록 초안'})).toBeVisible();expect(writes[0]).toEqual(writes[1]);expect(writes[1].document_refs).toHaveLength(3);revoked=true;await page.getByRole('button',{name:'자료 새로고침 · 선택 재확인'}).click();await expect(page.getByRole('alert')).toContainText('선택에서 제외');await expect(page.getByText(/선택 유지:/)).not.toContainText('합성 자료 3');
 await page.getByLabel('회의일 (선택 · 한국 업무 날짜)').fill('2026-10-20');await expect(page.getByText('봉인된 회의일: 2026-10-15',{exact:true})).toBeVisible();await page.getByLabel('검토 의견 (필수 · 1~500자)').fill('합성 검토');await page.getByRole('button',{name:'평가 이력 추가'}).click();await expect(page.getByRole('region',{name:'회의록 사람 품질 검토'}).getByRole('alert')).toBeVisible();await page.getByRole('button',{name:'평가 이력 추가'}).click();await expect(page.getByText('검토 기록이 추가되었습니다.')).toBeVisible();expect(reviews[0]).toEqual(reviews[1]);await page.getByLabel('검토 의견 (필수 · 1~500자)').fill('새 검토');await page.getByRole('button',{name:'평가 이력 추가'}).click();await expect(page.getByRole('button',{name:'최신 상태에서 새 검토 시작'})).toBeVisible();await expect(page.getByRole('button',{name:'평가 이력 추가'})).toBeDisabled();
});
