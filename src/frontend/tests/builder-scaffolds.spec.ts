import {test,expect,type Page} from '@playwright/test';
import {control,password,fixture} from './support';
import {loadEnvironment} from '../scripts/environment.mjs';
const env=loadEnvironment(),admin=env.admin.origin!+env.admin.entry;
const proposal={
 config:{name:'복리후생 안내 Agent',description:'사내 제도를 안내합니다.',instructions:'{{audience}}에게 복리후생 규정을 근거와 함께 안내합니다.',execution_kind:'general' as const},
 profile:{schema_version:1 as const,system_prompt:'{{audience}}에게 복리후생 규정을 근거와 함께 안내합니다.',developer_prompt:'최신 규정만 근거로 답하고 불확실하면 담당 부서를 안내합니다.',user_template:'질문: {{question}}',model_ref:'default_general',document_refs:[]},
 missing_questions:['적용할 규정의 기준일을 정해 주세요.'],warnings:['<img src=x onerror=alert(1)> 외부 자료를 연결하기 전에 접근 권한을 확인하세요.']
};
async function start(page:Page){
 await page.goto(admin+'/builder');await page.getByLabel('로그인 ID',{exact:true}).fill('a-adm');await page.getByLabel('비밀번호',{exact:true}).fill(password('A-ADM'));await page.getByRole('button',{name:'로그인',exact:true}).click();await expect(page.getByRole('button',{name:'로그아웃',exact:true})).toBeVisible();await page.getByLabel('현재 조직',{exact:true}).selectOption(fixture().tenants.A);await page.locator('#portal-navigation').getByRole('button',{name:'Agent Builder',exact:true}).click();await page.getByRole('button',{name:'빠른 시작',exact:true}).click();
}
test.beforeEach(()=>{control('case-start');});
test.afterEach(()=>{control('release-provider');});
test('D11_12_agent_proposal_is_reviewed_and_applied_without_implicit_save_or_execution',async({page})=>{
 await start(page);let postBody:any;let deletes=0;const proposalId='00000000-0000-4000-8000-000000000123';
 let forbiddenPosts=0;page.on('request',request=>{if(request.method()==='POST'&&request.url().includes('/api/v1/admin/')&&!request.url().includes('/builder/scaffolds'))forbiddenPosts++;});
 await page.route('**/api/v1/admin/builder/scaffolds*',async route=>{
  if(route.request().method()==='POST'){postBody=route.request().postDataJSON();await route.fulfill({status:201,contentType:'application/json',body:JSON.stringify({data:{proposal_id:proposalId,state:'ready',revision:1,proposal},meta:{tenant_id:fixture().tenants.A,request_id:'scaffold-contract'}})});return;}
  if(route.request().method()==='DELETE'){deletes++;await route.fulfill({status:200,contentType:'application/json',body:JSON.stringify({data:{proposal_id:proposalId,state:'discarded',revision:2},meta:{tenant_id:fixture().tenants.A,request_id:'scaffold-discard'}})});return;}
  await route.continue();
 });
 const panel=page.getByRole('region',{name:'업무 설명으로 Agent 초안 만들기'});
 await panel.getByLabel('어떤 업무를 돕는 Agent인가요?').fill('복리후생 질문에 답하고 관련 규정 근거를 안내');await panel.getByLabel('주로 누가 사용하나요?').fill('전 임직원');await panel.getByLabel('어떤 질문이나 정보를 받나요?').fill('제도 적용 질문');await panel.getByLabel('어떤 답변이나 결과가 필요하나요?').fill('적용 절차와 근거 조항');
 await panel.getByRole('button',{name:'Agent 초안 제안 만들기',exact:true}).click();await expect(panel.getByRole('region',{name:'Agent 초안 제안 검토'})).toBeVisible();
 expect(postBody).toMatchObject({target:'agent',intent:'복리후생 질문에 답하고 관련 규정 근거를 안내',answers:{audience:'전 임직원',inputs:'제도 적용 질문',outputs:'적용 절차와 근거 조항'}});
 await expect(panel).toContainText('적용할 규정의 기준일을 정해 주세요.');await expect(panel).toContainText('외부 자료를 연결하기 전에 접근 권한을 확인하세요.');await expect(panel.locator('img')).toHaveCount(0);
 await panel.getByLabel('Agent 이름').fill('수정한 복리후생 안내');await page.getByRole('button',{name:'단계별 제작',exact:true}).click();await page.getByRole('button',{name:'빠른 시작',exact:true}).click();await expect(panel.getByLabel('Agent 이름')).toHaveValue('수정한 복리후생 안내');
 await expect(page.getByLabel('자산 이름',{exact:true})).toHaveValue('');await expect(page.getByRole('button',{name:'저장 버전 조합 검증',exact:true})).toHaveCount(0);expect(forbiddenPosts).toBe(0);expect(deletes).toBe(0);
 await panel.getByRole('button',{name:'이 제안으로 편집 시작',exact:true}).click();await expect(page.getByLabel('자산 이름',{exact:true})).toHaveValue('수정한 복리후생 안내');await expect(page.getByLabel('자산 지시문',{exact:true})).toHaveValue(proposal.config.instructions);expect(forbiddenPosts).toBe(0);expect(deletes).toBe(0);
 await panel.getByRole('button',{name:'제안 삭제',exact:true}).click();await expect(panel.getByText('제안 내용을 삭제했습니다.')).toBeVisible();expect(deletes).toBe(1);expect(forbiddenPosts).toBe(0);
});

async function mockExplicitSave(page:Page,failSave:boolean,events:string[]){
 const proposalId='00000000-0000-4000-8000-000000000123',assetId='00000000-0000-4000-8000-000000000234',versionId='00000000-0000-4000-8000-000000000345';
 const detail={asset_id:assetId,owner_id:'00000000-0000-4000-8000-000000000001',kind:'agent',latest_revision:1,created_at:'2026-10-22T00:00:00Z',legacy_agent_key:null,version_id:versionId,config_hash:'a'.repeat(64),state:'draft',name:proposal.config.name,description:proposal.config.description,execution_kind:'general',config:proposal.config,versions:[],history_more:false};
 const version={asset_id:assetId,revision:1,version_id:versionId,config:proposal.config,config_hash:'a'.repeat(64),profile:proposal.profile,profile_hash:'b'.repeat(64),profile_source:'stored',parent_version_id:null};
 await page.route('**/api/v1/admin/**',async route=>{
  const request=route.request(),url=new URL(request.url()),path=url.pathname,method=request.method();
  const respond=(status:number,data:unknown)=>route.fulfill({status,contentType:'application/json',body:JSON.stringify(status>=400?{error:{code:'REQUEST_INVALID'},meta:{tenant_id:fixture().tenants.A,request_id:'mock-error'}}:{data,meta:{tenant_id:fixture().tenants.A,request_id:'mock-builder'}})});
  if(path==='/api/v1/admin/builder/scaffolds'&&method==='POST'){events.push('proposal');await respond(201,{proposal_id:proposalId,state:'ready',revision:1,proposal});return;}
  if(path==='/api/v1/admin/builder/scaffolds/'+proposalId&&method==='DELETE'){events.push('discard');await respond(200,{proposal_id:proposalId,state:'discarded',revision:2});return;}
  if(path==='/api/v1/admin/builder/assets'&&method==='POST'){events.push('save');await respond(failSave?422:201,failSave?null:{asset_id:assetId,revision:1,version_id:versionId,config_hash:'a'.repeat(64),replayed:false});return;}
  if(path==='/api/v1/admin/assets'&&method==='GET'){await respond(200,{items:[],next_cursor:null});return;}
  if(path==='/api/v1/admin/assets/'+assetId&&method==='GET'){await respond(200,detail);return;}
  if(path==='/api/v1/admin/builder/assets/'+assetId+'/versions/'+versionId&&method==='GET'){await respond(200,version);return;}
  await route.continue();
 });
 await page.route('**/api/v1/models',route=>route.fulfill({status:200,contentType:'application/json',body:JSON.stringify({data:[],meta:{tenant_id:fixture().tenants.A,request_id:'mock-models'}})}));
}
async function generateAndApply(page:Page){
 const panel=page.getByRole('region',{name:'업무 설명으로 Agent 초안 만들기'});
 await panel.getByLabel('어떤 업무를 돕는 Agent인가요?').fill('복리후생 질문에 답하고 근거를 안내');await panel.getByRole('button',{name:'Agent 초안 제안 만들기',exact:true}).click();await expect(panel.getByRole('region',{name:'Agent 초안 제안 검토'})).toBeVisible();await panel.getByRole('button',{name:'이 제안으로 편집 시작',exact:true}).click();
 return panel;
}
test('D11_13_only_explicit_save_creates_version_then_discards_proposal',async({page})=>{
 await start(page);const events:string[]=[];await mockExplicitSave(page,false,events);const panel=await generateAndApply(page);
 expect(events.filter(event=>event==='save')).toHaveLength(0);await page.getByRole('button',{name:'초안 등록',exact:true}).click();
 await expect(page.getByText('초안 버전 1 저장됨 · 제안 내용 삭제 완료',{exact:true})).toBeVisible();expect(events).toEqual(['proposal','save','discard']);expect(events.filter(event=>event==='save')).toHaveLength(1);
});
test('D11_14_failed_explicit_save_keeps_proposal_without_discard',async({page})=>{
 await start(page);const events:string[]=[];await mockExplicitSave(page,true,events);const panel=await generateAndApply(page);
 await page.getByRole('button',{name:'초안 등록',exact:true}).click();await expect(page.getByRole('alert')).toBeVisible();expect(events).toEqual(['proposal','save']);expect(events).not.toContain('discard');await expect(panel.getByRole('button',{name:'제안 삭제',exact:true})).toBeEnabled();
});
