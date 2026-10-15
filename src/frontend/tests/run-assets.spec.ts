import {test,expect} from '@playwright/test';
import {control,fixture,login,selectTenant} from './support';
test.beforeEach(()=>control('case-start'));
test.afterEach(async()=>{control('release-provider');await expect.poll(()=>control('b05-counts').active,{timeout:6000}).toBe(0);});

test('D09_07_run_binding_saved_and_reloaded',async({page})=>{
 await login(page,'A-U1');await page.getByLabel('질문',{exact:true}).fill('실행 버전 보존 합성 질문');
 const accepted=page.waitForResponse(r=>r.url().endsWith('/api/v1/runs')&&r.request().method()==='POST');
 await page.getByRole('button',{name:'질문 보내기',exact:true}).click();const first=(await (await accepted).json()).data;
 await expect(page.getByText('완료 · 저장 확인됨',{exact:true})).toBeVisible();
 await page.getByText('실행 버전 정보',{exact:true}).click();await expect(page.getByText(first.asset_binding.asset_id,{exact:true})).toBeVisible();await expect(page.getByText(first.asset_binding.version_id,{exact:true})).toBeVisible();await expect(page.getByText(first.asset_binding.config_hash,{exact:true})).toBeVisible();
 await page.reload();await page.locator('.conversation-link').filter({hasText:'완료'}).click();await expect(page.getByText('완료 · 저장 확인됨',{exact:true})).toBeVisible();await page.getByText('실행 버전 정보',{exact:true}).click();await expect(page.getByText(first.asset_binding.config_hash,{exact:true})).toBeVisible();expect(control('b05-counts').provider_calls).toBe(1);
});

test('D09_08_alias_replay_and_other_organization_rejected',async({page})=>{
 await login(page,'DUAL');await selectTenant(page,'A');
 const csrf=(await (await page.request.get('/api/v1/auth/me')).json()).data.csrf_token;
 const headers={'X-Tenant-ID':fixture().tenants.A,Origin:'http://127.0.0.1:5173','X-Requested-With':'ai-portal','X-CSRF-Token':csrf};
 const body={client_send_id:crypto.randomUUID(),agent_key:'general',prompt:'연결 자산 재시도 합성 질문'};
 const first=(await (await page.request.post('/api/v1/runs',{headers,data:body})).json()).data;
 await expect.poll(()=>control('b05-counts').active).toBe(0);
 const replay=await page.request.post('/api/v1/runs',{headers,data:{...body,asset_id:first.asset_binding.asset_id}});expect(replay.ok()).toBeTruthy();const same=(await replay.json()).data;expect(same.run_id).toBe(first.run_id);expect(same.asset_binding).toEqual(first.asset_binding);
 const before=control('b05-counts');
 for(const tenant of ['A','B']){const rejected=await page.request.post('/api/v1/runs',{headers:{...headers,'X-Tenant-ID':fixture().tenants[tenant]},data:{...body,client_send_id:crypto.randomUUID(),asset_id:tenant==='A'?crypto.randomUUID():first.asset_binding.asset_id}});expect(rejected.status()).toBe(404);}
 const after=control('b05-counts');expect(after.runs).toBe(before.runs);expect(after.provider_calls).toBe(before.provider_calls);
});

test('D09_09_historical_binding_missing_is_explicit',async({page})=>{
 await login(page,'A-U1');
 // Compatibility UI fixture; genuine historical DB preservation is tested in backend migration test.
 await page.route('**/api/v1/runs/*',async route=>{if(route.request().method()==='GET'&&!route.request().url().endsWith('/events')){const response=await route.fetch();const body=await response.json();if(body.data?.run_id)body.data.asset_binding=null;await route.fulfill({response,json:body});}else await route.continue();});
 await page.getByLabel('질문',{exact:true}).fill('이전 실행 표시 합성 질문');await page.getByRole('button',{name:'질문 보내기',exact:true}).click();await expect(page.getByText('완료 · 저장 확인됨',{exact:true})).toBeVisible();await page.getByText('실행 버전 정보',{exact:true}).click();await expect(page.getByText('실행 버전 정보가 기록되지 않은 기존 실행입니다.',{exact:true})).toBeVisible();
});
