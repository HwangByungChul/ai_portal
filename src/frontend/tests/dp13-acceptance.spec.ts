import {test,expect,type Page} from '@playwright/test';
import {control,fixture,login,selectTenant} from './support';

test.beforeEach(()=>control('case-start'));
test.afterEach(async()=>{control('release-provider');await expect.poll(()=>control('b05-counts').active,{timeout:6000}).toBe(0);});

test('D13_01_admin_models_registry_view',async({page})=>{
  await login(page,'P-A');
  await page.goto('/manage/admin/models');
  await expect(page.getByRole('heading',{name:'AI 모델 레지스트리 (DP-13)',exact:true})).toBeVisible();
  await expect(page.getByText('보안 원칙:')).toBeVisible();
  await expect(page.getByText('gpt-4o-mini')).toBeVisible();
  await expect(page.getByText('mock-disabled')).toBeVisible();
  await expect(page.getByText('비활성')).toBeVisible();
});

test('D13_02_disabled_models_hidden_from_general_users',async({page})=>{
  await login(page,'A-U1');
  const res = await page.request.get('/api/v1/models',{
    headers:{'X-Tenant-ID':fixture().tenants.A}
  });
  expect(res.status()).toBe(200);
  const data = (await res.json()).data;
  const modelIds = data.items.map((m:any)=>m.model_id);
  expect(modelIds).toContain('gpt-4o-mini');
  expect(modelIds).not.toContain('mock-disabled');
});
