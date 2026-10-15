import {test,expect,type Page} from '@playwright/test';
import {control,fixture,login,selectTenant} from './support';
async function enter(page:Page,actor:string){await login(page,actor);await page.goto('/user/home');await expect(page.getByRole('button',{name:'로그아웃',exact:true})).toBeVisible();}
async function navigate(page:Page,label:string){
 await expect(page.locator('#portal-navigation')).toBeAttached();
 if(!await page.locator('#portal-navigation').getByRole('button',{name:label,exact:true,includeHidden:true}).count()){
  const link=page.locator('#portal-navigation').getByRole('link',{name:label==='Agent 관리'?'관리자 사이트':'사용자 사이트',exact:true});
  if(!await link.isVisible())await page.getByRole('button',{name:'메뉴 열기',exact:true}).click();await link.click();
 }
 const button=page.locator('#portal-navigation').getByRole('button',{name:label,exact:true,includeHidden:true});
 await expect(button).toBeAttached();
 if(!await button.isVisible())await page.getByRole('button',{name:'메뉴 열기',exact:true}).click();await button.click();
}
test.beforeEach(()=>control('case-start'));
test.afterEach(async()=>{control('release-provider');await expect.poll(()=>control('b05-counts').active,{timeout:6000}).toBe(0);});

test('D10_01_catalog_favorite_persists_and_launch_binds_asset',async({page})=>{
 await enter(page,'A-U1');await navigate(page,'AI 카탈로그');await expect(page.getByRole('heading',{name:'AI 카탈로그',exact:true})).toBeVisible();
 await page.getByLabel('도우미 검색').fill('no-match');await page.getByRole('button',{name:'검색',exact:true}).click();await expect(page.getByText('검색 조건에 맞는 이용 가능한 도우미가 없습니다.')).toBeVisible();
 await page.getByLabel('도우미 검색').fill('');await page.getByLabel('업무 구분').selectOption('general');await page.getByRole('button',{name:'검색',exact:true}).click();
 await expect(page.getByRole('button',{name:'일반 대화 즐겨찾기 추가',exact:true})).toBeVisible();await page.screenshot({path:'/private/tmp/portal-catalog-20261012/catalog-desktop.png',fullPage:true});await page.getByRole('button',{name:'일반 대화 즐겨찾기 추가',exact:true}).click();await expect(page.getByRole('status').filter({hasText:'즐겨찾기를 저장했습니다.'})).toBeVisible();
 await navigate(page,'My Agent');await expect(page.getByRole('button',{name:'일반 대화 즐겨찾기 해제',exact:true})).toBeVisible();await page.reload();await expect(page.getByRole('button',{name:'일반 대화 즐겨찾기 해제',exact:true})).toBeVisible();
 await page.locator('.hub-agent').filter({hasText:'일반 대화'}).click();await page.getByRole('button',{name:'이 도우미로 업무 시작'}).click();await page.getByLabel('질문',{exact:true}).fill('카탈로그 실행 합성 질문');
 const response=page.waitForResponse(r=>r.request().method()==='POST'&&r.url().endsWith('/api/v1/runs'));await page.getByRole('button',{name:'질문 보내기',exact:true}).click();const reply=await response;expect(reply.request().postDataJSON().asset_id).toBe((await reply.json()).data.asset_binding.asset_id);await expect(page.getByText('완료 · 저장 확인됨',{exact:true})).toBeVisible();
});

test('D10_02_admin_revoke_hides_user_favorite_and_blocks_run',async({page,browser})=>{
 await enter(page,'A-U1');await navigate(page,'AI 카탈로그');await page.getByRole('button',{name:'일반 대화 즐겨찾기 추가',exact:true}).click();await expect(page.getByRole('status').filter({hasText:'즐겨찾기를 저장했습니다.'})).toBeVisible();
 const context=await browser.newContext();const admin=await context.newPage();try{
  await enter(admin,'A-ADM');await navigate(admin,'Agent 관리');const region=admin.getByRole('region',{name:'일반 대화 이용 대상',exact:true});await region.getByLabel('이용 범위').selectOption('restricted');await region.getByRole('button',{name:'이용 대상 변경',exact:true}).click();await region.getByRole('button',{name:'이용 대상 변경 확인',exact:true}).click();await expect(region.getByRole('status').filter({hasText:'이용 대상이 저장되었습니다.'})).toBeVisible();
  await navigate(page,'My Agent');await expect(page.getByText('이용 가능한 즐겨찾기가 없습니다. AI 카탈로그에서 추가해 주세요.')).toBeVisible();await navigate(page,'홈');await expect(page.getByText('일반 대화 이용 권한이 없습니다. AI 카탈로그에서 이용 가능한 도우미를 확인해 주세요.')).toBeVisible();await page.getByLabel('시작할 업무 질문').fill('제한된 업무 초안');await expect(page.getByRole('button',{name:'AI 채팅에서 시작',exact:true})).toBeDisabled();await navigate(page,'My Agent');const csrf=(await (await page.request.get('/api/v1/auth/me')).json()).data.csrf_token;
  const reply=await page.request.post('/api/v1/runs',{headers:{'X-Tenant-ID':fixture().tenants.A,Origin:'http://127.0.0.1:5173','X-Requested-With':'ai-portal','X-CSRF-Token':csrf},data:{client_send_id:crypto.randomUUID(),agent_key:'general',prompt:'거부될 합성 질문'}});expect(reply.status()).toBe(403);expect(control('b05-counts').provider_calls).toBe(0);
  await region.getByLabel('이용 범위').selectOption('all');await region.getByRole('button',{name:'이용 대상 변경',exact:true}).click();await region.getByRole('button',{name:'이용 대상 변경 확인',exact:true}).click();await expect(region.getByRole('status').filter({hasText:'이용 대상이 저장되었습니다.'})).toBeVisible();await page.getByRole('button',{name:'새로고침',exact:true}).click();await expect(page.getByRole('button',{name:'일반 대화 즐겨찾기 해제',exact:true})).toBeVisible();
 }finally{await context.close();}
});

test('D10_03_mobile_navigation_and_organization_personal_scope',async({page})=>{
 const errors:string[]=[];page.on('pageerror',e=>errors.push(e.name));await page.setViewportSize({width:390,height:844});await enter(page,'DUAL');await selectTenant(page,'A');await navigate(page,'AI 카탈로그');await page.getByRole('button',{name:'일반 대화 즐겨찾기 추가',exact:true}).click();await expect(page.getByRole('status').filter({hasText:'즐겨찾기를 저장했습니다.'})).toBeVisible();await selectTenant(page,'B');await navigate(page,'My Agent');await expect(page.getByText('이용 가능한 즐겨찾기가 없습니다. AI 카탈로그에서 추가해 주세요.')).toBeVisible();await selectTenant(page,'A');await expect(page.getByRole('button',{name:'일반 대화 즐겨찾기 해제',exact:true})).toBeVisible();expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBeTruthy();expect(errors).toEqual([]);await page.screenshot({path:'/private/tmp/portal-catalog-20261012/my-agent-mobile.png',fullPage:true});
});

test('D10_04_uncertain_favorite_reuses_request_id_once',async({page})=>{
 await enter(page,'A-U1');await navigate(page,'AI 카탈로그');let first=true;const keys:string[]=[];await page.route('**/api/v1/catalog/assets/*/favorite',async route=>{keys.push(route.request().postDataJSON().client_request_id);if(first){first=false;await route.fetch();await route.abort('failed');}else await route.continue();});await page.getByRole('button',{name:'일반 대화 즐겨찾기 추가',exact:true}).click();await expect(page.getByRole('button',{name:'같은 즐겨찾기 요청 확인'})).toBeVisible();await expect(page.getByLabel('도우미 검색')).toBeDisabled();await page.getByRole('button',{name:'같은 즐겨찾기 요청 확인'}).click();await expect(page.getByRole('button',{name:'일반 대화 즐겨찾기 해제',exact:true})).toBeVisible();expect(keys.length).toBe(2);expect(keys[0]).toBe(keys[1]);
});


test('D10_05_conflict_refresh_requires_new_current_request',async({page})=>{
 await enter(page,'A-U1');await navigate(page,'AI 카탈로그');let first=true;const keys:string[]=[];
 await page.route('**/api/v1/catalog/assets/*/favorite',async route=>{const body=route.request().postDataJSON();keys.push(body.client_request_id);if(first){first=false;await route.fetch({postData:JSON.stringify({...body,client_request_id:crypto.randomUUID(),active:false})});}await route.continue();});
 await page.getByRole('button',{name:'일반 대화 즐겨찾기 추가',exact:true}).click();await expect(page.getByRole('alert')).toBeVisible();await expect(page.getByRole('button',{name:'같은 즐겨찾기 요청 확인'})).toHaveCount(0);await page.getByRole('button',{name:'일반 대화 즐겨찾기 추가',exact:true}).click();await expect(page.getByRole('button',{name:'일반 대화 즐겨찾기 해제',exact:true})).toBeVisible();expect(keys.length).toBe(2);expect(keys[0]).not.toBe(keys[1]);
});

test('D10_06_uncertain_admin_access_freezes_and_reconfirms',async({page})=>{
 await enter(page,'A-ADM');await navigate(page,'Agent 관리');const region=page.getByRole('region',{name:'일반 대화 이용 대상',exact:true});let first=true;const keys:string[]=[];
 await page.route('**/api/v1/admin/agent-access/general',async route=>{if(route.request().method()!=='PUT'){await route.continue();return;}keys.push(route.request().postDataJSON().client_request_id);if(first){first=false;await route.fetch();await route.abort('failed');}else await route.continue();});
 await region.getByLabel('이용 범위').selectOption('restricted');await region.getByRole('button',{name:'이용 대상 변경',exact:true}).click();await region.getByRole('button',{name:'이용 대상 변경 확인',exact:true}).click();await expect(region.getByRole('button',{name:'같은 이용 대상 요청 확인'})).toBeVisible();await expect(region.getByLabel('이용 범위')).toBeDisabled();await region.getByRole('button',{name:'같은 이용 대상 요청 확인'}).click();await expect(region.getByRole('status').filter({hasText:'이용 대상이 저장되었습니다.'})).toBeVisible();await expect(region.getByLabel('이용 범위')).toHaveValue('restricted');await page.screenshot({path:'/private/tmp/portal-catalog-20261012/admin-access-desktop.png',fullPage:true});expect(keys.length).toBe(2);expect(keys[0]).toBe(keys[1]);
});
