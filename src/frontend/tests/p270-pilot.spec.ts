import {test,expect,type Page,type Browser} from '@playwright/test';
import {control,fixture,login} from './support';

test.setTimeout(60000);
const errors=new Map<string,number>();
function track(page:Page){const title=test.info().title;page.on('pageerror',()=>errors.set(title,(errors.get(title)??0)+1));}
test.beforeEach(({context},info)=>{control('case-start');control('c05-enable');errors.set(info.title,0);context.on('page',track);});
async function tracked(browser:Browser,mobile=false){const ctx=await browser.newContext(mobile?{viewport:{width:390,height:844}}:{});ctx.on('page',track);return ctx;}
test.afterEach(async({},info)=>{control('release-provider');await expect.poll(()=>control('c05-counts').active,{timeout:7000}).toBe(0);expect(errors.get(info.title)??0).toBe(0);});
async function upload(page:Page,title:string,content:string){
 await page.getByLabel('문서 제목',{exact:true}).fill(title);
 await page.getByLabel('문서 파일',{exact:true}).setInputFiles({name:'pilot.txt',mimeType:'text/plain',buffer:Buffer.from(content)});
 await page.locator('.document-upload').getByRole('button',{name:/문서 접수|새 버전 접수/}).click();
 await expect(page.getByRole('region',{name:'문서 처리 상태'})).toContainText('게시: 게시됨');
 await expect(page.locator('.document-card').first()).toContainText('게시됨');
}
async function ask(page:Page,prompt:string){await page.getByLabel('질문',{exact:true}).fill(prompt);await page.getByRole('button',{name:'질문 보내기',exact:true}).click();await expect(page.getByText('완료 · 저장 확인됨',{exact:true})).toBeVisible();}
async function headers(page:Page,tenant='A'){
 const csrf=(await (await page.request.get('/api/v1/auth/me')).json()).data.csrf_token;
 return {'X-Tenant-ID':fixture().tenants[tenant],Origin:'http://127.0.0.1:5173','X-Requested-With':'ai-portal','X-CSRF-Token':csrf};
}

test('P270_01_admin_user_saved_rag_journey',async({page,browser})=>{
 let user;
 try{
  await test.step('P270_STEP_01_admin_publish',async()=>{await login(page,'A-ADM');await page.getByRole('button',{name:'문서 관리',exact:true}).click();await upload(page,'파일럿 합성 규정','여신심사의 담당 부서는 심사1팀이다.');});
  user=await tracked(browser);const u=await user.newPage();
  await test.step('P270_STEP_02_general_usage_history',async()=>{
   await login(u,'A-U1');await ask(u,'일반 업무 리허설');await expect(u.getByText('모의 AI 응답입니다. 실제 모델 호출 없이 실행·권한·사용량 흐름을 검증했습니다.',{exact:true})).toBeVisible();
   await u.getByRole('button',{name:'내 사용량',exact:true}).click();await expect(u.getByText('확인된 사용량의 추정 금액',{exact:true})).toBeVisible();
   await u.getByRole('button',{name:'AI 업무',exact:true}).click();await u.reload();await u.locator('.conversation-link').filter({hasText:'완료'}).click();await expect(u.getByText('완료 · 저장 확인됨',{exact:true})).toBeVisible();
  });
  await test.step('P270_STEP_03_rag_source_download',async()=>{
   await u.getByRole('button',{name:'새 대화',exact:true}).click();await u.getByLabel('Agent',{exact:true}).selectOption('rules_rag');
   await u.getByLabel('파일럿 합성 규정 · v1 · 조직',{exact:true}).check();await ask(u,'여신심사 담당 부서는?');await expect(u.locator('.message.assistant')).toContainText('심사1팀');
   await u.getByRole('button',{name:'근거 보기',exact:true}).click();await expect(u.getByRole('region',{name:'답변 근거'})).toContainText('여신심사의 담당 부서는 심사1팀이다.');
   const response=u.waitForResponse(r=>r.url().includes('/source')&&r.request().method()==='GET');const downloaded=u.waitForEvent('download');await u.getByRole('button',{name:'원문 내려받기',exact:true}).click();
   const raw=await response;expect(raw.status()).toBe(200);expect(raw.headers()['cache-control']).toBe('no-store');const verified=await u.request.get(raw.url(),{headers:{'X-Tenant-ID':fixture().tenants.A}});expect(await verified.text()).toBe('여신심사의 담당 부서는 심사1팀이다.');await downloaded;
   expect(control('c05-counts').embed_document).toBe(1);expect(control('c05-counts').embed_query).toBe(1);expect(control('c05-counts').generate_rag).toBe(1);
  });
 }finally{await user?.close();}
});

test('P270_02_mobile_shared_version_revoke_journey',async({page,browser})=>{
 let recipient;let requestBody:any;let runId='';let sourceUrl='';
 try{
  await test.step('P270_STEP_04_share_version_and_update',async()=>{
   await login(page,'A-ADM');await page.getByRole('button',{name:'문서 관리',exact:true}).click();await upload(page,'파일럿 공유 규정','여신심사의 담당 부서는 심사1팀이다.');
   await page.getByRole('button',{name:'버전 공유 관리',exact:true}).click();await page.getByLabel('수신 조직').selectOption(fixture().tenants.B);await page.getByRole('button',{name:'이 버전 공유',exact:true}).click();await expect(page.getByRole('region',{name:'버전 공유'})).toContainText('공유 중');
   await page.getByRole('button',{name:'새 버전',exact:true}).click();await upload(page,'파일럿 미공유 v2','여신심사의 담당 부서는 숨김2팀이다.');
  });
  recipient=await tracked(browser,true);const b=await recipient.newPage();
  await test.step('P270_STEP_05_mobile_v1_evidence',async()=>{
   await login(b,'B-U1');b.on('request',req=>{if(req.method()==='POST'&&new URL(req.url()).pathname==='/api/v1/runs')requestBody=req.postDataJSON();});await b.getByLabel('Agent',{exact:true}).selectOption('rules_rag');await b.getByLabel('파일럿 공유 규정 · v1 · 공유',{exact:true}).check();const admitted=b.waitForResponse(r=>new URL(r.url()).pathname==='/api/v1/runs'&&r.request().method()==='POST');await ask(b,'여신심사 담당 부서는?');runId=(await (await admitted).json()).data.run_id;const evidence=(await (await b.request.get('/api/v1/runs/'+runId+'/evidence',{headers:{'X-Tenant-ID':fixture().tenants.B}})).json()).data;sourceUrl=evidence.items[0].source_url;expect((await b.request.get(sourceUrl,{headers:{'X-Tenant-ID':fixture().tenants.B}})).status()).toBe(200);
   await expect(b.locator('.message.assistant')).toContainText('심사1팀');await expect(b.getByText('숨김2팀',{exact:false})).toHaveCount(0);await expect(b.getByText('파일럿 미공유 v2',{exact:false})).toHaveCount(0);
   await b.getByRole('button',{name:'근거 보기',exact:true}).click();await expect(b.getByRole('region',{name:'답변 근거'})).toContainText('여신심사의 담당 부서는 심사1팀이다.');expect(await b.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);
  });
  await test.step('P270_STEP_06_revoke_prior_result_and_source',async()=>{
   await page.getByRole('button',{name:'공유 회수',exact:true}).click();await expect(page.getByRole('region',{name:'버전 공유'})).toContainText('회수됨');
   await expect(b.getByText('심사1팀',{exact:false})).toHaveCount(0,{timeout:10000});await expect(b.getByText('답변을 표시할 수 없습니다.',{exact:false})).toBeVisible();
   expect((await b.request.get(sourceUrl,{headers:{'X-Tenant-ID':fixture().tenants.B}})).status()).toBe(404);expect((await b.request.post('/api/v1/runs',{headers:await headers(b,'B'),data:{...requestBody,client_send_id:crypto.randomUUID()}})).status()).toBe(404);
   expect(control('c05-counts').embed_query).toBe(1);expect(control('c05-counts').generate_rag).toBe(1);
  });
 }finally{await recipient?.close();}
});

test('P270_03_private_owner_and_stop_journey',async({page,browser})=>{
 let owner;
 try{
  await login(page,'A-ADM');
  await test.step('P270_STEP_07_private_owner_API_and_admin_redaction',async()=>{
   const metadata={client_upload_id:crypto.randomUUID(),title:'개인 파일럿 자료',visibility:'private',owner_user_id:fixture().actors['A-U1'],reader_ids:[],media_type:'text/plain'};
   const reply=await page.request.post('/api/v1/admin/documents',{headers:await headers(page),multipart:{metadata:JSON.stringify(metadata),file:{name:'private.txt',mimeType:'text/plain',buffer:Buffer.from('가상사용자의 개인 시연 리허설은 수요일 정오에 진행한다.')}}});expect(reply.status()).toBe(202);
   const job=(await reply.json()).data.job_id;await expect.poll(async()=>(await (await page.request.get('/api/v1/admin/jobs/'+job,{headers:{'X-Tenant-ID':fixture().tenants.A}})).json()).data.state).toBe('completed');
   await page.getByRole('button',{name:'문서 관리',exact:true}).click();await expect(page.locator('.document-card')).toContainText('개인 문서');await expect(page.getByText('개인 파일럿 자료',{exact:false})).toHaveCount(0);await expect(page.getByRole('button',{name:'버전 공유 관리',exact:true})).toHaveCount(0);
  });
  owner=await tracked(browser);const u=await owner.newPage();
  await test.step('P270_STEP_08_owner_personal_evidence',async()=>{
   await login(u,'A-U1');await u.getByLabel('Agent',{exact:true}).selectOption('rules_rag');await u.getByLabel('개인 파일럿 자료 · v1 · 개인',{exact:true}).check();await ask(u,'내 개인 리허설 일정은?');await expect(u.locator('.message.assistant')).toContainText('수요일 정오');
  });
  await test.step('P270_STEP_09_stop_prevents_admission',async()=>{
   await page.getByRole('button',{name:'Agent 관리',exact:true}).click();const region=page.getByRole('region',{name:'일반 대화 설정'});await region.getByRole('button',{name:'Agent 중지',exact:true}).click();await region.getByRole('button',{name:'운영 변경 확인',exact:true}).click();await expect(region.getByText('저장되었습니다.',{exact:true})).toBeVisible();
   const before=control('b05-counts').provider_calls;const response=await u.request.post('/api/v1/runs',{headers:await headers(u),data:{client_send_id:crypto.randomUUID(),agent_key:'general',prompt:'중지 후 접수'}});expect(response.status()).toBe(409);expect(control('b05-counts').provider_calls).toBe(before);
  });
 }finally{await owner?.close();}
});
