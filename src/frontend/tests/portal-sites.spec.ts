import {test,expect,type Page} from '@playwright/test';
import {control,password,selectTenant,fixture} from './support';
async function loginSite(page:Page,actor:string,path='/user/home'){
 await page.goto(path);await page.getByLabel('로그인 ID',{exact:true}).fill(actor.toLowerCase());await page.getByLabel('비밀번호',{exact:true}).fill(password(actor));await page.getByRole('button',{name:'로그인',exact:true}).click();await expect(page.getByRole('button',{name:'로그아웃',exact:true})).toBeVisible();
}
async function nav(page:Page,label:string){const button=page.locator('#portal-navigation').getByRole('button',{name:label,exact:true});if(!await button.isVisible())await page.getByRole('button',{name:'메뉴 열기',exact:true}).click();await button.click();}
async function changeSite(page:Page,label:string){const link=page.locator('#portal-navigation').getByRole('link',{name:label,exact:true});if(!await link.isVisible())await page.getByRole('button',{name:'메뉴 열기',exact:true}).click();await link.click();}
test.beforeEach(()=>control('case-start'));
test('U12_01_user_artifact_chat_and_history',async({page})=>{
 const problems:string[]=[];let posts=0;page.on('pageerror',e=>problems.push(e.name));page.on('request',r=>{if(r.method()==='POST'&&r.url().endsWith('/runs'))posts++;});
 await loginSite(page,'A-U1');await expect(page.locator('[data-portal-site=user]')).toBeVisible();await expect(page.getByRole('heading',{name:'업무 홈',exact:true})).toBeVisible();await expect(page.getByRole('link',{name:'관리자 사이트',exact:true})).toHaveCount(0);
 await page.getByLabel('시작할 업무 질문',{exact:true}).fill('독립 사용자 앱 확인');await page.getByRole('button',{name:'AI 채팅에서 시작',exact:true}).click();await expect(page).toHaveURL(/\/user\/workspace$/);await expect(page.getByLabel('질문',{exact:true})).toHaveValue('독립 사용자 앱 확인');expect(posts).toBe(0);
 await page.getByRole('button',{name:'질문 보내기',exact:true}).click();await expect(page.getByText('완료 · 저장 확인됨',{exact:true})).toBeVisible();await page.reload();await expect(page.locator('[data-portal-site=user]')).toBeVisible();await page.locator('.conversation-link').first().click();await expect(page.getByRole('article').filter({hasText:'내 질문'})).toContainText('독립 사용자 앱 확인');expect(problems).toEqual([]);
});
test('U12_02_admin_artifact_approval_and_site_switch',async({page,browser})=>{
 await loginSite(page,'A-ADM','/manage/admin');await expect(page.locator('[data-portal-site=admin]')).toBeVisible();await expect(page.getByRole('heading',{name:'운영 현황',exact:true})).toBeVisible();
 await nav(page,'Agent 관리');const edit=page.getByRole('region',{name:'일반 대화 설정'});await edit.getByLabel('이름',{exact:true}).fill('독립 앱 승인 Agent');await edit.getByLabel('변경 목적',{exact:true}).fill('양쪽 산출물 검증');await edit.getByRole('button',{name:'배포 승인 요청',exact:true}).click();await expect(edit.getByRole('status')).toContainText('배포 요청이 저장되었습니다.');
 await nav(page,'승인·검증');await page.locator('.approval-row').filter({hasText:'독립 앱 승인 Agent'}).click();await expect(page.getByRole('button',{name:'배포 승인',exact:true})).toHaveCount(0);
 const context=await browser.newContext(),approver=await context.newPage();try{
 await loginSite(approver,'P-A','/manage/admin/approvals');await approver.locator('.approval-row').filter({hasText:'독립 앱 승인 Agent'}).click();await approver.getByLabel('검토 의견',{exact:true}).fill('독립 관리자 앱 처리');await approver.getByRole('button',{name:'배포 승인',exact:true}).click();await approver.getByRole('button',{name:'검토 결정 저장',exact:true}).click();await expect(approver.locator('.approval-detail')).toContainText('승인·설정 반영 완료');
 }finally{await context.close();}
 await changeSite(page,'사용자 사이트');await expect(page).toHaveURL(/\/user\/home$/);await expect(page.locator('[data-portal-site=user]')).toBeVisible();await expect(page.locator('.hub-agent')).toContainText(['독립 앱 승인 Agent','규정 검색']);await changeSite(page,'관리자 사이트');await expect(page.getByRole('heading',{name:'운영 현황',exact:true})).toBeVisible();
});
test('U12_03_direct_admin_denial_and_global_scope',async({page})=>{
 let adminReads=0;page.on('request',r=>{if(r.url().includes('/api/v1/admin/'))adminReads++;});await loginSite(page,'A-U1','/manage/admin/approvals');await expect(page.getByRole('heading',{name:'관리자 접근 권한이 없습니다.',exact:true})).toBeVisible();expect(adminReads).toBe(0);
 await page.getByRole('link',{name:'업무 홈으로 이동',exact:true}).click();await expect(page.getByRole('heading',{name:'업무 홈',exact:true})).toBeVisible();await page.goto('/user/admin/approvals');await expect(page.getByRole('heading',{name:'업무 홈',exact:true})).toBeVisible();await expect(page.locator('.approval-detail')).toHaveCount(0);expect(adminReads).toBe(0);
 await page.getByRole('button',{name:'로그아웃',exact:true}).click();await expect(page.getByLabel('로그인 ID',{exact:true})).toBeVisible();await loginSite(page,'P_READ_ONLY','/manage/admin');await expect(page).toHaveURL(/\/manage\/platform$/);await expect(page.getByRole('button',{name:'사용자 관리',exact:true})).toHaveCount(0);await page.goto('/manage/admin/approvals');await expect(page.getByRole('heading',{name:'관리자 접근 권한이 없습니다.',exact:true})).toBeVisible();expect(adminReads).toBe(0);
});
test('U12_04_user_private_document_has_no_admin_requests',async({page})=>{
 control('c05-enable');const adminRequests:string[]=[];page.on('request',r=>{if(r.url().includes('/api/v1/admin/'))adminRequests.push(r.method());});await loginSite(page,'A-U1','/user/documents');
 await expect(page.getByRole('heading',{name:'개인 문서 등록',exact:true})).toBeVisible();await expect(page.getByLabel('공개 범위',{exact:true})).toHaveCount(0);await page.getByLabel('문서 제목',{exact:true}).fill('독립 앱 개인 자료');await page.getByLabel('문서 파일',{exact:true}).setInputFiles({name:'private.md',mimeType:'text/markdown',buffer:Buffer.from('합성 개인 자료의 담당자는 심사팀이다.')});await page.locator('.document-upload').getByRole('button',{name:'문서 접수',exact:true}).click();await expect(page.getByRole('region',{name:'문서 처리 상태'})).toContainText('게시: 게시됨');await expect(page.locator('.document-card').first()).toContainText('게시됨');await expect(page.getByRole('button',{name:'버전 공유 관리',exact:true})).toHaveCount(0);await expect(page.getByRole('button',{name:'처리 재시도',exact:true})).toHaveCount(0);
 await nav(page,'내 사용량');await expect(page.getByRole('heading',{name:'내 사용량',exact:true})).toBeVisible();await expect(page.getByRole('button',{name:'조직 제한 저장',exact:true})).toHaveCount(0);expect(adminRequests).toEqual([]);
});
test('U12_05_org_change_and_cross_port_server_logout',async({page,context})=>{
 await loginSite(page,'DUAL-ADM');await selectTenant(page,'A');await page.getByLabel('시작할 업무 질문',{exact:true}).fill('이전 조직 초안');await selectTenant(page,'B');await expect(page.getByLabel('시작할 업무 질문',{exact:true})).toHaveValue('');
 await changeSite(page,'관리자 사이트');await expect(page.getByLabel('현재 조직',{exact:true})).toHaveValue(fixture().tenants.B);await expect(page.getByRole('heading',{name:'운영 현황',exact:true})).toBeVisible();await changeSite(page,'사용자 사이트');await expect(page.getByLabel('현재 조직',{exact:true})).toHaveValue(fixture().tenants.B);
 const other=await context.newPage();await other.goto('http://127.0.0.1:5174/manage/admin');await selectTenant(other,'A');await nav(other,'승인·검증');await expect(other.getByText('조건에 맞는 배포 요청이 없습니다.',{exact:true})).toBeVisible();await expect(page.getByLabel('현재 조직',{exact:true})).toHaveValue(fixture().tenants.B);
 await page.getByRole('button',{name:'로그아웃',exact:true}).click();await expect(page.getByLabel('로그인 ID',{exact:true})).toBeVisible();await other.reload();await expect(other.getByLabel('로그인 ID',{exact:true})).toBeVisible();
});
test('U12_06_mobile_keyboard_and_artifact_visuals',async({page})=>{
 const {mkdirSync,chmodSync}=await import('node:fs');const {resolve}=await import('node:path');const dir=resolve('.runtime/U12-views');mkdirSync(dir,{recursive:true,mode:0o700});chmodSync(dir,0o700);
 await page.setViewportSize({width:390,height:844});await loginSite(page,'A-ADM');await page.getByRole('button',{name:'메뉴 열기',exact:true}).focus();await page.keyboard.press('Enter');await page.locator('#portal-navigation').getByRole('link',{name:'관리자 사이트',exact:true}).focus();await page.keyboard.press('Enter');await expect(page.getByRole('heading',{name:'운영 현황',exact:true})).toBeVisible();await nav(page,'승인·검증');await expect(page.getByText('조건에 맞는 배포 요청이 없습니다.',{exact:true})).toBeVisible();expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);const mobile=resolve(dir,'admin-mobile.png');await page.screenshot({path:mobile,fullPage:true});chmodSync(mobile,0o600);
 await page.setViewportSize({width:1600,height:1000});await changeSite(page,'사용자 사이트');await expect(page.getByRole('heading',{name:'업무 홈',exact:true})).toBeVisible();expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);const desktop=resolve(dir,'user-desktop.png');await page.screenshot({path:desktop,fullPage:true});chmodSync(desktop,0o600);
});

test('U12_07_tenant_hint_cannot_grant_management',async({page})=>{
 let adminReads=0;page.on('request',r=>{if(r.url().includes('/api/v1/admin/'))adminReads++;});await loginSite(page,'A-U1','/manage/admin/approvals?tenant='+fixture().tenants.B);await expect(page.getByRole('heading',{name:'관리자 접근 권한이 없습니다.',exact:true})).toBeVisible();await expect(page.getByLabel('현재 조직',{exact:true})).toHaveValue(fixture().tenants.A);await expect(page).toHaveURL(/\/manage\/admin\/approvals$/);expect(adminReads).toBe(0);
 await page.goto('/user/home?tenant=untrusted');await expect(page.getByRole('heading',{name:'업무 홈',exact:true})).toBeVisible();await expect(page.getByLabel('현재 조직',{exact:true})).toHaveValue(fixture().tenants.A);await expect(page).toHaveURL(/\/user\/home$/);expect(adminReads).toBe(0);
});
