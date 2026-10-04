import { test,expect } from '@playwright/test';
import { redact } from './safe-reporter';
import { control,fixture,login,members,password,row,selectTenant } from './support';
const pageErrors=new Map<string,number>();
test.beforeEach(({context},info)=>{
 control('case-start');pageErrors.set(info.title,0);
 context.on('page',page=>page.on('pageerror',()=>pageErrors.set(info.title,(pageErrors.get(info.title)??0)+1)));
});
test.afterEach(({},info)=>{expect(pageErrors.get(info.title)??0).toBe(0);});

test('A05_01_user_login_restore_and_direct_denial',async({page})=>{
 await login(page,'A-U1');await expect(page.getByText('대화 기능 준비중')).toBeVisible();
 await expect(page.getByRole('button',{name:'사용자 관리',exact:true})).toHaveCount(0);
 const reply=await page.request.get('/api/v1/admin/memberships',{headers:{'X-Tenant-ID':fixture().tenants.A}});
 expect(reply.status()).toBe(403);await page.reload();await expect(page.getByRole('button',{name:'로그아웃',exact:true})).toBeVisible();
 await page.goto('/admin/members');await expect(page.getByText('대화 기능 준비중')).toBeVisible();await expect(page.locator('tbody tr')).toHaveCount(0);
 const empty=await page.evaluate(()=>localStorage.length===0&&sessionStorage.length===0);expect(empty).toBe(true);
});

test('A05_02_generic_login_failure_and_password_clear',async({page})=>{
 await page.goto('/login');await page.getByLabel('로그인 ID',{exact:true}).fill('a-u1');await page.getByLabel('비밀번호').fill('incorrect');
 await page.getByRole('button',{name:'로그인',exact:true}).click();await expect(page.getByRole('alert')).toHaveText('로그인 정보를 확인해 주세요.');
 await expect(page.getByLabel('비밀번호')).toHaveValue('');
 await page.getByLabel('로그인 ID',{exact:true}).fill('unknown-user');await page.getByLabel('비밀번호').fill('incorrect');
 await page.getByRole('button',{name:'로그인',exact:true}).click();await expect(page.getByRole('alert')).toHaveText('로그인 정보를 확인해 주세요.');
});

test('A05_03_tadmin_active_changes_and_protected_rows',async({page})=>{
 await login(page,'A-ADM');await members(page);await expect(row(page,'A-ADM').getByRole('button')).toHaveCount(0);await expect(row(page,'P-A').getByRole('button')).toHaveCount(0);
 await expect(row(page).getByLabel('변경할 역할')).toHaveCount(0);
 await row(page).getByRole('button',{name:'비활성화',exact:true}).click();await expect(row(page).getByText('비활성',{exact:true})).toBeVisible();
 await row(page).getByRole('button',{name:'활성화',exact:true}).click();await expect(row(page).getByText('활성',{exact:true})).toBeVisible();
 expect(control('counts').revision).toBe(3);expect(control('counts').audits).toBe(2);
});

test('A05_04_padmin_role_changes',async({page})=>{
 await login(page,'P-A');await members(page);
 await row(page).getByLabel('변경할 역할').selectOption('TADMIN');await row(page).getByRole('button',{name:'역할 저장',exact:true}).click();
 await expect(row(page).locator('.role-text')).toHaveText('조직 관리자');
 await row(page).getByLabel('변경할 역할').selectOption('USER');await row(page).getByRole('button',{name:'역할 저장',exact:true}).click();
 await expect(row(page).locator('.role-text')).toHaveText('일반 사용자');expect(control('counts').revision).toBe(3);
});

test('A05_05_no_members_has_no_organization',async({page})=>{
 await login(page,'NO_MEMBERS');await expect(page.getByRole('heading',{name:'사용 가능한 조직이 없습니다.'})).toBeVisible();
 await expect(page.getByLabel('현재 조직')).toBeDisabled();await expect(page.getByRole('button',{name:'사용자 관리',exact:true})).toHaveCount(0);
});

test('A05_06_global_permission_does_not_enable_tenant_admin',async({page})=>{
 await login(page,'P_READ_ONLY');await expect(page.locator('.role-badge')).toHaveText('일반 사용자');
 await expect(page.getByRole('button',{name:'사용자 관리',exact:true})).toHaveCount(0);
});

test('A05_07_two_tabs_independent_tenants',async({page,context})=>{
 await login(page,'DUAL-ADM');await expect(page.getByRole('heading',{name:'업무 조직을 선택해 주세요.'})).toBeVisible();
 await selectTenant(page,'A');await members(page);const second=await context.newPage();await second.goto('/');
 await selectTenant(second,'B');await members(second);await expect(row(second,'B-U1')).toBeVisible();await expect(row(second,'A-U1')).toHaveCount(0);
 await expect(page.getByLabel('현재 조직')).toHaveValue(fixture().tenants.A);await expect(row(page,'A-U1')).toBeVisible();
 await expect(second.getByLabel('현재 조직')).toHaveValue(fixture().tenants.B);
});

test('A05_08_late_actual_A_response_discarded',async({page})=>{
 const orgA=fixture().tenants.A;
 await page.addInitScript((org)=>{const original=window.fetch;window.fetch=(input,options)=>{
  if(String(input).includes('/admin/memberships')&&new Headers(options?.headers).get('X-Tenant-ID')===org)return original(input,{...options,signal:undefined});
  return original(input,options);
 };},orgA);
 await login(page,'DUAL-ADM');await selectTenant(page,'A');
 let release!:()=>void;let fetched!:()=>void;let delivered!:()=>void;
 const gate=new Promise<void>(r=>{release=r;});const ready=new Promise<void>(r=>{fetched=r;});const completed=new Promise<void>(r=>{delivered=r;});
 await page.route('**/api/v1/admin/memberships*',async route=>{
  if(route.request().headers()['x-tenant-id']!==orgA){await route.continue();return;}
  const actual=await route.fetch();fetched();await gate;try{await route.fulfill({response:actual});}finally{delivered();}
 });
 await page.getByRole('button',{name:'사용자 관리',exact:true}).click();await ready;
 await selectTenant(page,'B');await expect(row(page,'B-U1')).toBeVisible();release();await completed;
 await page.evaluate(()=>new Promise<void>(r=>requestAnimationFrame(()=>requestAnimationFrame(()=>r()))));
 await expect(row(page,'A-U1')).toHaveCount(0);await expect(row(page,'B-U1')).toBeVisible();
});

test('A05_09_membership_revoked_A_keeps_B_and_session',async({page})=>{
 await login(page,'DUAL-ADM');await selectTenant(page,'A');await members(page);control('revoke','DUAL-ADM','A');
 await page.getByRole('button',{name:'목록 새로고침'}).click();await expect(page.getByLabel('현재 조직')).toHaveValue(fixture().tenants.B);
 expect((await page.request.get('/api/v1/auth/me')).status()).toBe(200);
 await expect(row(page,'A-U1')).toHaveCount(0);await expect(page.locator('#tenant-choice option[value="'+fixture().tenants.A+'"]')).toHaveCount(0);
});

test('A05_10_demoted_admin_menu_and_rows_removed',async({page})=>{
 await login(page,'A-ADM');await members(page);control('demote','A-ADM');await page.getByRole('button',{name:'목록 새로고침'}).click();
 await expect(page.getByRole('button',{name:'사용자 관리',exact:true})).toHaveCount(0);await expect(page.locator('tbody tr')).toHaveCount(0);
 await expect(page.locator('.role-badge')).toHaveText('일반 사용자');
});

test('A05_11_expired_session_clears_content',async({page})=>{
 await login(page,'A-ADM');await members(page);control('expire','A-ADM');await page.getByRole('button',{name:'목록 새로고침'}).click();
 await expect(page.getByLabel('로그인 ID',{exact:true})).toBeVisible();await expect(page.locator('tbody tr')).toHaveCount(0);
});

test('A05_12_conflict_refresh_without_auto_mutation',async({page})=>{
 await login(page,'P-A');await members(page);
 const me=await page.request.get('/api/v1/auth/me');const csrf=(await me.json()).data.csrf_token;
 const changed=await page.request.patch('/api/v1/admin/memberships/'+fixture().actors['A-U1'],{headers:{'X-Tenant-ID':fixture().tenants.A,
  Origin:'http://127.0.0.1:5173','X-Requested-With':'ai-portal','X-CSRF-Token':csrf},data:{active:false,expected_revision:1}});
 expect(changed.status()).toBe(200);await row(page).getByRole('button',{name:'비활성화',exact:true}).click();
 await expect(page.getByRole('alert')).toContainText('다른 변경이 먼저 적용되었습니다.');await expect(row(page).getByText('비활성',{exact:true})).toBeVisible();
 expect(control('counts').revision).toBe(2);expect(control('counts').audits).toBe(1);
});

test('A05_13_logout_DB_failure_hidden_until_retry_confirmed',async({page})=>{
 await login(page,'P-A');await members(page);const cookies=await page.context().cookies();const old=cookies.find(c=>c.name==='ai_session_dev')!.value;
 control('fail-logout');await page.getByRole('button',{name:'로그아웃',exact:true}).click();
 await expect(page.getByRole('alert')).toContainText('로그아웃 확인이 필요합니다.');await expect(page.locator('tbody tr')).toHaveCount(0);
 await expect(page.getByLabel('현재 조직')).toHaveCount(0);control('restore-logout');await page.getByRole('button',{name:'로그아웃 다시 확인'}).click();
 await expect(page.getByLabel('로그인 ID',{exact:true})).toBeVisible();
 expect((await page.request.get('/api/v1/auth/me',{headers:{Cookie:'ai_session_dev='+old}})).status()).toBe(401);
});

test('A05_14_logout_network_failure_hidden_until_retry',async({page})=>{
 await login(page,'A-ADM');await members(page);await page.route('**/api/v1/auth/logout',route=>route.abort('failed'));
 await page.getByRole('button',{name:'로그아웃',exact:true}).click();await expect(page.getByRole('alert')).toContainText('로그아웃 확인이 필요합니다.');
 await expect(page.locator('tbody tr')).toHaveCount(0);await page.unroute('**/api/v1/auth/logout');await page.getByRole('button',{name:'로그아웃 다시 확인'}).click();
 await expect(page.getByLabel('로그인 ID',{exact:true})).toBeVisible();
});

test('A05_15_logout_broadcast_clears_other_tab',async({page,context})=>{
 await login(page,'A-U1');const second=await context.newPage();await second.goto('/');await expect(second.getByRole('button',{name:'로그아웃',exact:true})).toBeVisible();
 await page.getByRole('button',{name:'로그아웃',exact:true}).click();await expect(second.getByLabel('로그인 ID',{exact:true})).toBeVisible();
 await expect(second.getByText('대화 기능 준비중')).toHaveCount(0);
});

test('A05_16_read_storage_failure_and_retry',async({page})=>{
 await login(page,'P-A');await members(page);control('fail-read');await page.getByRole('button',{name:'목록 새로고침'}).click();
 await expect(page.getByRole('alert')).toContainText('처리 결과를 확인할 수 없습니다.');await expect(page.locator('tbody tr')).toHaveCount(0);
 control('restore-read');await page.getByRole('button',{name:'목록 새로고침'}).click();await expect(row(page)).toBeVisible();await expect(page.getByRole('alert')).toHaveCount(0);
});

test('A05_17_mobile_layout_real_management',async({page})=>{
 await page.setViewportSize({width:390,height:844});await login(page,'P-A');await members(page);await expect(row(page)).toBeVisible();
 expect(await page.evaluate(()=>document.documentElement.scrollWidth<=window.innerWidth)).toBe(true);
 await row(page).getByRole('button',{name:'비활성화',exact:true}).click();await expect(row(page).getByText('비활성',{exact:true})).toBeVisible();
});

test('A05_18_password_fill_failure_redacted',async({page})=>{
 await page.goto('/');const secret=password('A-U1');let message='';
 try{await page.locator('#missing-password').fill(secret,{timeout:150});}catch(error){message=String(error);}
 expect(message.length>0).toBe(true);expect(redact(message,[secret]).includes(secret)).toBe(false);
 const protectedValue='C'.repeat(43);expect(redact('s='+protectedValue,[protectedValue])).toBe('s=[REDACTED]');
});

test('A05_19_server_cursor_pagination',async({page})=>{
 const result=control('pagination');await login(page,'P-A');await members(page);await expect(page.locator('tbody tr')).toHaveCount(20);
 await page.getByRole('button',{name:'더 보기',exact:true}).click();await expect(page.locator('tbody tr')).toHaveCount(Number(result.members));
 await expect(page.getByRole('button',{name:'더 보기',exact:true})).toHaveCount(0);
});


test('A05_20_blank_login_visuals_no_credentials',async({page})=>{
 const {resolve}=await import('node:path');const dir=resolve('../../docs/Obsidain/200.프로젝트실행/260.테스트/evidence/A-auth');
 await page.setViewportSize({width:1440,height:960});await page.goto('/login');await expect(page.getByLabel('로그인 ID',{exact:true})).toBeVisible();
 await expect(page.getByLabel('비밀번호')).toHaveValue('');await expect(page.getByLabel('로그인 ID',{exact:true})).toHaveValue('');
 await page.screenshot({path:resolve(dir,'A05-login-desktop.png'),fullPage:true});
 await page.setViewportSize({width:390,height:844});await page.screenshot({path:resolve(dir,'A05-login-mobile.png'),fullPage:true});
});
