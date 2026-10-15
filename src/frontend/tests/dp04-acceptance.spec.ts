import {writeFileSync} from 'node:fs';
import {resolve} from 'node:path';
import {test,expect,type Page} from '@playwright/test';
import {login,selectTenant,control,fixture,navigate} from './support';
test.beforeEach(()=>control('case-start'));
test.afterEach(async({page},info)=>{if(info.status!==info.expectedStatus)writeFileSync(resolve('.runtime',info.title+'-ui-private.txt'),await page.locator('main').innerText().catch(()=>'no main'),{mode:0o600});control('release-provider');await expect.poll(()=>control('b05-counts').active,{timeout:6000}).toBe(0);});
async function switchActor(page:Page,actor:string){if(await page.getByRole('button',{name:'로그아웃',exact:true}).isVisible()){await page.getByRole('button',{name:'로그아웃',exact:true}).click();await expect(page.getByLabel('로그인 ID',{exact:true})).toBeVisible();}await login(page,actor);}
async function question(page:Page){await page.getByLabel('질문',{exact:true}).fill('합성 답변 평가 질문');await page.getByRole('button',{name:'질문 보내기',exact:true}).click();await expect(page.getByText('완료 · 저장 확인됨',{exact:true})).toBeVisible();await expect(page.getByRole('region',{name:'답변 평가'})).toHaveCount(1);await expect(page.getByRole('button',{name:'도움 됐어요',exact:true})).toBeVisible();}
async function rate(page:Page,comment='합성 비공개 평가 의견'){await page.getByRole('button',{name:'도움 됐어요',exact:true}).click();await page.getByLabel('평가 의견 (선택)',{exact:true}).fill(comment);await page.getByRole('button',{name:'평가 저장',exact:true}).click();await expect(page.getByText('평가를 저장했습니다.',{exact:true})).toBeVisible();}

test('D04_01_owner_save_change_withdraw_recreate_reload_no_provider',async({page})=>{
 await login(page,'A-U1');await question(page);const before=control('b05-counts');await rate(page,'비공개 합성 의견 <script>owner marker</script>');
 await page.reload();await page.locator('.conversation-link').first().click();await expect(page.getByLabel('평가 의견 (선택)',{exact:true})).toHaveValue('비공개 합성 의견 <script>owner marker</script>');await expect(page.getByRole('button',{name:'도움 됐어요',exact:true})).toHaveAttribute('aria-pressed','true');
 await page.getByRole('button',{name:'아쉬워요',exact:true}).click();await page.getByLabel('평가 의견 (선택)',{exact:true}).fill('수정 의견');await page.getByRole('button',{name:'평가 저장',exact:true}).click();await expect(page.getByText('평가를 저장했습니다.',{exact:true})).toBeVisible();
 await page.getByRole('button',{name:'평가 철회',exact:true}).click();await expect(page.getByText('평가를 철회했습니다.',{exact:true})).toBeVisible();await expect(page.getByLabel('평가 의견 (선택)',{exact:true})).toHaveValue('');await expect(page.getByRole('button',{name:'평가 철회',exact:true})).toHaveCount(0);
 await rate(page,'재등록 의견');expect(control('b05-counts').provider_calls).toBe(before.provider_calls);
 expect(await page.evaluate(()=>JSON.stringify({...localStorage,...sessionStorage}))).not.toContain('재등록 의견');
});

test('D04_02_mobile_switch_tenant_clears_private_feedback',async({page})=>{
 await page.setViewportSize({width:390,height:844});await login(page,'DUAL');await selectTenant(page,'A');await question(page);await rate(page,'조직 A 평가 의견');
 await selectTenant(page,'B');await expect(page.getByLabel('평가 의견 (선택)',{exact:true})).toHaveCount(0);await question(page);await expect(page.getByLabel('평가 의견 (선택)',{exact:true})).toHaveValue('');
 await expect.poll(()=>page.evaluate(()=>document.documentElement.scrollWidth<=window.innerWidth)).toBe(true);
});

test('D04_03_admin_aggregate_no_private_content_and_threshold',async({page})=>{
 await login(page,'A-U1');await question(page);await rate(page,'never-show-summary');await expect(page.getByRole('button',{name:'답변 평가',exact:true})).toHaveCount(0);
 await switchActor(page,'A-ADM');await navigate(page,'답변 평가');await expect(page.getByText('참여자가 적어 평가 건수를 표시하지 않습니다.',{exact:true})).toBeVisible();await expect(page.getByText('never-show-summary',{exact:false})).toHaveCount(0);
 await switchActor(page,'A-U2');await question(page);await rate(page,'second-private');
 await switchActor(page,'A-ADM');await question(page);await rate(page,'admin-own-private');await navigate(page,'답변 평가');await expect(page.getByText('전체 평가',{exact:true})).toBeVisible();await expect(page.locator('.feedback-summary-item').first()).toContainText('3건');await expect(page.getByText('admin-own-private',{exact:false})).toHaveCount(0);
 await page.getByLabel('평가 Agent',{exact:true}).selectOption('rules_rag');await page.getByRole('button',{name:'집계 조회',exact:true}).click();await expect(page.locator('.feedback-summary-item')).toHaveCount(1);await expect(page.getByText('해당 월의 활성 평가가 없습니다.',{exact:true})).toBeVisible();
});

test('D04_04_conflict_loads_current_feedback_without_overwrite',async({page})=>{
 await login(page,'A-U1');await question(page);await rate(page,'original');
 const h={'X-Tenant-ID':fixture().tenants.A};const me=await (await page.request.get('/api/v1/auth/me')).json();const conversations=await (await page.request.get('/api/v1/conversations',{headers:h})).json();const messages=await (await page.request.get('/api/v1/conversations/'+conversations.data.items[0].conversation_id+'/messages',{headers:h})).json();const run=messages.data.items.find((x:{role:string})=>x.role==='assistant').run_id;
 const reply=await page.request.put('/api/v1/runs/'+run+'/feedback',{headers:{...h,Origin:'http://127.0.0.1:5173','X-Requested-With':'ai-portal','X-CSRF-Token':me.data.csrf_token},data:{rating:'negative',comment:'server current',expected_revision:1}});expect(reply.status()).toBe(200);
 await page.getByLabel('평가 의견 (선택)',{exact:true}).fill('stale local');await page.getByRole('button',{name:'평가 저장',exact:true}).click();await expect(page.getByText('다른 변경이 반영되었습니다. 최신 평가를 확인한 뒤 다시 저장해 주세요.',{exact:true})).toBeVisible();await expect(page.getByLabel('평가 의견 (선택)',{exact:true})).toHaveValue('server current');
});


test('D04_05_late_previous_tenant_feedback_is_discarded',async({page})=>{
 await login(page,'DUAL');await selectTenant(page,'A');await question(page);await rate(page,'private delayed A comment');
 let release!:()=>void;const gate=new Promise<void>(resolve=>{release=resolve;});let held=false;
 await page.route('**/api/v1/runs/*/feedback',async route=>{const response=await route.fetch();held=true;await gate;try{await route.fulfill({response});}catch{}});
 await page.reload();await selectTenant(page,'A');await page.locator('.conversation-link').first().click();await expect.poll(()=>held).toBe(true);
 await selectTenant(page,'B');release();await page.unroute('**/api/v1/runs/*/feedback');await expect(page.getByLabel('평가 의견 (선택)',{exact:true})).toHaveCount(0);
 await question(page);await expect(page.getByLabel('평가 의견 (선택)',{exact:true})).toHaveValue('');await expect(page.getByText('private delayed A comment',{exact:false})).toHaveCount(0);
});
