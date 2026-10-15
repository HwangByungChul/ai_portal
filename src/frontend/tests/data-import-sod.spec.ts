import {test,expect} from '@playwright/test';
import {control,login} from './support';

test.beforeEach(()=>control('case-start'));
test.afterEach(async()=>{control('release-provider');await expect.poll(()=>control('b05-counts').active,{timeout:6000}).toBe(0);});

test('DI_01_admin_data_import_review_page_view_and_sod_banner',async({page})=>{
  await login(page,'P-A');
  await page.goto('/manage/admin/data-imports');
  
  await expect(page.getByRole('heading',{name:'데이터 Scope 반입 심사 (DP-16 / DP-17)',exact:true})).toBeVisible();
  await expect(page.getByText('보안 및 직무 분리(SOD) 원칙:')).toBeVisible();
  await expect(page.getByText('반입 요청 건수')).toBeVisible();
  await expect(page.getByRole('button',{name:'전체 요청',exact:true})).toBeVisible();
  await expect(page.getByRole('button',{name:'승인 대기',exact:true})).toBeVisible();
});
