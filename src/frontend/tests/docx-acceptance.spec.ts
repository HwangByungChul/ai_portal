import {test,expect} from '@playwright/test';
import {resolve} from 'node:path';
import {readFileSync} from 'node:fs';
import {control,login,fixture} from './support';
test.beforeEach(()=>{control('case-start');control('c05-enable');});
test.afterEach(async()=>{control('release-provider');await expect.poll(()=>control('c05-counts').active,{timeout:7000}).toBe(0);});
const paragraph=resolve('tests/fixtures/docx-paragraph.docx');
const table=resolve('tests/fixtures/docx-table.docx');
test('DX6_01_personal_docx_rag_paragraph_original_download',async({page,browser})=>{
 test.setTimeout(35000);await login(page,'A-U1');await page.getByRole('button',{name:'내 자료',exact:true}).click();await page.getByLabel('문서 제목',{exact:true}).fill('DOCX 개인 규정');await page.getByLabel('문서 파일',{exact:true}).setInputFiles(paragraph);await page.locator('.document-upload').getByRole('button',{name:'문서 접수',exact:true}).click();await expect(page.getByRole('region',{name:'문서 처리 상태'})).toContainText('게시: 게시됨');
 await page.getByRole('button',{name:'AI 업무',exact:true}).click();await page.getByLabel('Agent',{exact:true}).selectOption('rules_rag');await page.getByLabel('DOCX 개인 규정 · v1 · 개인',{exact:true}).check();await page.getByLabel('질문',{exact:true}).fill('여신심사 담당 부서는?');const accepted=page.waitForResponse(r=>r.request().method()==='POST'&&r.url().endsWith('/api/v1/runs'));await page.getByRole('button',{name:'질문 보내기',exact:true}).click();const run=(await (await accepted).json()).data.run_id;await expect(page.getByText('완료 · 저장 확인됨',{exact:true})).toBeVisible();await expect(page.locator('.message.assistant')).toContainText('DOCX심사팀');await page.getByRole('button',{name:'근거 보기',exact:true}).click();await expect(page.getByRole('region',{name:'답변 근거'})).toContainText('본문 1문단');
 const download=page.waitForEvent('download');await page.getByRole('button',{name:'원문 내려받기',exact:true}).click();const item=await download;expect(item.suggestedFilename()).toBe('document.docx');expect(readFileSync((await item.path())!)).toEqual(readFileSync(paragraph));
 const source='/api/v1/runs/'+run+'/evidence/0/source';
 for(const actor of ['A-U2','B-U1']){const ctx=await browser.newContext();try{const other=await ctx.newPage();await login(other,actor);expect((await other.request.get(source,{headers:{'X-Tenant-ID':fixture().tenants[actor==='B-U1'?'B':'A']}})).status()).toBe(404);}finally{await ctx.close();}}
 await page.getByRole('button',{name:'내 자료',exact:true}).click();await page.getByRole('button',{name:'문서 삭제',exact:true}).click();await page.getByRole('button',{name:'문서 삭제 확인',exact:true}).click();await expect.poll(async()=>{await page.getByRole('button',{name:'문서 새로고침',exact:true}).click();return page.locator('.document-card').innerText();}).toContain('삭제 정리: 완료');expect((await page.request.get(source,{headers:{'X-Tenant-ID':fixture().tenants.A}})).status()).toBe(404);

});
test('DX6_02_sensitive_document_rejected_without_job_or_call',async({page})=>{
 await login(page,'A-U1');await page.getByRole('button',{name:'내 자료',exact:true}).click();await page.getByLabel('문서 제목',{exact:true}).fill('수집 검사');await page.getByLabel('문서 파일',{exact:true}).setInputFiles(resolve('tests/fixtures/docx-sensitive.docx'));await page.locator('.document-upload').getByRole('button',{name:'문서 접수',exact:true}).click();await expect(page.getByRole('alert')).toContainText('개인정보 후보');expect(control('c05-counts').documents).toBe(0);expect(control('c05-counts').embed_document).toBe(0);
});
test('DX6_03_admin_docx_table_and_filename_mismatch',async({page})=>{
 await login(page,'A-ADM');await page.getByRole('button',{name:'문서 관리',exact:true}).click();await page.getByLabel('문서 제목',{exact:true}).fill('공통 DOCX');await page.getByLabel('문서 파일',{exact:true}).setInputFiles(table);await page.locator('.document-upload').getByRole('button',{name:'문서 접수',exact:true}).click();await expect(page.getByRole('region',{name:'문서 처리 상태'})).toContainText('게시: 게시됨');
 const me=(await (await page.request.get('/api/v1/auth/me')).json()).data;const headers={'X-Tenant-ID':fixture().tenants.A,Origin:'http://127.0.0.1:5173','X-Requested-With':'ai-portal','X-CSRF-Token':me.csrf_token};
 const reply=await page.request.post('/api/v1/admin/documents',{headers,multipart:{metadata:JSON.stringify({client_upload_id:crypto.randomUUID(),title:'위장 DOCX',media_type:'application/vnd.openxmlformats-officedocument.wordprocessingml.document'}),file:{name:'wrong.txt',mimeType:'application/vnd.openxmlformats-officedocument.wordprocessingml.document',buffer:readFileSync(table)}}});expect(reply.status()).toBe(422);expect(control('c05-counts').documents).toBe(1);
 await page.getByRole('button',{name:'AI 업무',exact:true}).click();await page.getByLabel('Agent',{exact:true}).selectOption('rules_rag');await page.getByLabel('공통 DOCX · v1 · 조직',{exact:true}).check();await page.getByLabel('질문',{exact:true}).fill('여신심사 담당 부서는?');await page.getByRole('button',{name:'질문 보내기',exact:true}).click();await expect(page.getByText('완료 · 저장 확인됨',{exact:true})).toBeVisible();await page.getByRole('button',{name:'근거 보기',exact:true}).click();await expect(page.getByRole('region',{name:'답변 근거'})).toContainText('표 1 · 1행 1열');
 const download=page.waitForEvent('download');await page.getByRole('button',{name:'원문 내려받기',exact:true}).click();const item=await download;expect(item.suggestedFilename()).toBe('document.docx');expect(readFileSync((await item.path())!)).toEqual(readFileSync(table));

});
