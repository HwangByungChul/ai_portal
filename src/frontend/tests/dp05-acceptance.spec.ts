import {test,expect,type Page} from '@playwright/test';
import {control,fixture,login,selectTenant} from './support';
const raw='여신심사의 담당 부서는 개인심사팀이다.';
test.beforeEach(()=>{control('case-start');control('c05-enable');});
test.afterEach(async()=>{control('release-provider');await expect.poll(()=>control('c05-counts').active,{timeout:7000}).toBe(0);});
async function mine(page:Page,actor='A-U1'){await login(page,actor);if(actor==='DUAL')await selectTenant(page,'A');await page.getByRole('button',{name:'내 자료',exact:true}).click();await expect(page.getByRole('heading',{name:'개인 문서 등록',exact:true})).toBeVisible();}
async function upload(page:Page,title='내 개인 규정'){await page.getByLabel('문서 제목',{exact:true}).fill(title);await page.getByLabel('문서 파일',{exact:true}).setInputFiles({name:'private.md',mimeType:'text/markdown',buffer:Buffer.from(raw)});await page.locator('.document-upload').getByRole('button',{name:'문서 접수',exact:true}).click();}
async function published(page:Page){await expect(page.getByRole('region',{name:'문서 처리 상태'})).toContainText('게시: 게시됨');await expect(page.locator('.document-card').first()).toContainText('게시됨');}
async function h(page:Page,tenant='A'){const csrf=(await (await page.request.get('/api/v1/auth/me')).json()).data.csrf_token;return {'X-Tenant-ID':fixture().tenants[tenant],Origin:'http://127.0.0.1:5173','X-Requested-With':'ai-portal','X-CSRF-Token':csrf};}

test('D05_01_private_upload_processing_attach_evidence_feedback_delete',async({page})=>{
 await mine(page);await expect(page.getByLabel('공개 범위',{exact:true})).toHaveCount(0);await expect(page.getByRole('button',{name:'새 버전',exact:true})).toHaveCount(0);
 control('slow-index-provider');await upload(page);await expect(page.getByText('접수됐습니다. 처리·게시 상태를 확인해 주세요.',{exact:true})).toBeVisible();await expect(page.locator('.document-card')).toContainText('내 개인 규정');await expect(page.getByRole('region',{name:'문서 처리 상태'})).toContainText('아직 게시되지 않음');
 await expect(page.getByText('내 개인 규정 · v1 · 개인',{exact:true})).toHaveCount(0);control('release-provider');await published(page);
 await page.getByRole('button',{name:'AI 업무',exact:true}).click();await page.getByLabel('Agent',{exact:true}).selectOption('rules_rag');await page.getByLabel('내 개인 규정 · v1 · 개인',{exact:true}).check();let body:any;page.on('request',req=>{if(req.method()==='POST'&&req.url().endsWith('/runs'))body=req.postDataJSON();});await page.getByLabel('질문',{exact:true}).fill('여신심사 담당 부서는?');await page.getByRole('button',{name:'질문 보내기',exact:true}).click();await expect(page.getByText('완료 · 저장 확인됨',{exact:true})).toBeVisible();expect(body.document_refs).toHaveLength(1);await expect(page.locator('.message.assistant')).toContainText('개인심사팀');
 await page.getByRole('button',{name:'근거 보기',exact:true}).click();await expect(page.getByRole('region',{name:'답변 근거'})).toContainText(raw);const download=page.waitForEvent('download');await page.getByRole('button',{name:'원문 내려받기',exact:true}).click();expect((await download).suggestedFilename()).toBe('document.txt');
 await page.getByRole('button',{name:'도움 됐어요',exact:true}).click();await page.getByRole('button',{name:'평가 저장',exact:true}).click();await expect(page.getByText('평가를 저장했습니다.',{exact:true})).toBeVisible();
 const before=control('c05-counts');await page.getByRole('button',{name:'내 자료',exact:true}).click();await page.getByRole('button',{name:'문서 삭제',exact:true}).click();await page.getByRole('button',{name:'문서 삭제 확인',exact:true}).click();await expect(page.locator('.document-card')).toContainText('삭제됨');await expect.poll(async()=>{await page.getByRole('button',{name:'문서 새로고침',exact:true}).click();return page.locator('.document-card').innerText();}).toContain('삭제 정리: 완료');
 await page.getByRole('button',{name:'AI 업무',exact:true}).click();await page.locator('.conversation-link').first().click();await expect(page.getByText('답변을 표시할 수 없습니다.',{exact:false})).toBeVisible();await expect(page.getByRole('region',{name:'답변 평가'})).toHaveCount(0);expect(control('c05-counts').embed_document).toBe(before.embed_document);expect(control('c05-counts').generate_rag).toBe(before.generate_rag);
});

test('D05_02_other_user_and_tenant_private_title_job_delete_hidden',async({page,browser})=>{
 await mine(page);await upload(page,'비공개 제목 D05');await published(page);const ids=(await (await page.request.get('/api/v1/documents/mine',{headers:await h(page)})).json()).data.items[0];const jobs=(await (await page.request.get('/api/v1/document-jobs',{headers:await h(page)})).json()).data.items;
 for(const actor of ['A-U2','B-U1','A-ADM']){const ctx=await browser.newContext();try{const other=await ctx.newPage();await mine(other,actor);await expect(other.getByText('비공개 제목 D05',{exact:false})).toHaveCount(0);const headers=await h(other,actor==='B-U1'?'B':'A');expect((await other.request.get('/api/v1/document-jobs/'+jobs[0].job_id,{headers})).status()).toBe(404);expect((await other.request.delete('/api/v1/documents/'+ids.document_id,{headers,data:{expected_revision:1}})).status()).toBe(404);}finally{await ctx.close();}}
});

test('D05_03_mobile_tenant_switch_discards_personal_rows_and_late_reply',async({page})=>{
 await page.setViewportSize({width:390,height:844});await mine(page,'DUAL');await selectTenant(page,'A');await upload(page,'A 개인 제목');await published(page);expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);
 await page.addInitScript(()=>{const original=window.fetch;window.fetch=(input,options)=>String(input).includes('/api/v1/documents/mine')?original(input,{...options,signal:undefined}):original(input,options);});
 let release!:()=>void;const gate=new Promise<void>(r=>release=r);let held=false;await page.route('**/api/v1/documents/mine',async route=>{if(route.request().headers()['x-tenant-id']!==fixture().tenants.A)return route.continue();const response=await route.fetch();held=true;await gate;try{await route.fulfill({response});}catch{}});
 await page.reload();await selectTenant(page,'A');await page.getByRole('button',{name:'내 자료',exact:true}).click();await expect.poll(()=>held).toBe(true);await selectTenant(page,'B');release();await expect(page.getByText('등록된 문서가 없습니다.',{exact:true})).toBeVisible();await expect(page.getByText('A 개인 제목',{exact:false})).toHaveCount(0);expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);expect(await page.evaluate(()=>localStorage.length+sessionStorage.length)).toBe(0);
});

test('D05_04_lost_personal_upload_confirmation_replays_same_id_once',async({page})=>{
 await mine(page);const metadata:string[]=[];let lost=true;await page.route('**/api/v1/documents',async route=>{if(route.request().method()!=='POST')return route.continue();metadata.push(route.request().postDataBuffer()!.toString().match(/\{[^\r\n]+\}/)![0]);if(lost){lost=false;await route.fetch();await route.abort('failed');}else await route.continue();});await upload(page);await expect(page.getByRole('button',{name:'문서 접수 확인',exact:true})).toBeEnabled();await page.getByRole('button',{name:'문서 접수 확인',exact:true}).click();await published(page);expect(metadata).toHaveLength(2);expect(metadata[0]).toBe(metadata[1]);expect(JSON.parse(metadata[0]).visibility).toBeUndefined();expect(control('c05-counts').documents).toBe(1);expect(control('c05-counts').embed_document).toBe(1);
});

test('D05_05_unknown_personal_index_has_no_retry_or_question_attachment',async({page})=>{
 control('unknown-index-provider');await mine(page);await upload(page,'보류 자료');await expect(page.getByText('예약을 유지합니다. 자동으로 다시 호출하지 않습니다.',{exact:true})).toBeVisible();await expect(page.getByRole('button',{name:'처리 재시도',exact:true})).toHaveCount(0);await page.getByRole('button',{name:'처리 상태 새로고침',exact:true}).click();expect(control('c05-counts').embed_document).toBe(1);await page.getByRole('button',{name:'AI 업무',exact:true}).click();await page.getByLabel('Agent',{exact:true}).selectOption('rules_rag');await expect(page.getByLabel('보류 자료 · v1 · 개인',{exact:true})).toHaveCount(0);
});
