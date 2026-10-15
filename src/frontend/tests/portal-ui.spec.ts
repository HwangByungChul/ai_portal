import {test,expect} from '@playwright/test';
import {control,fixture,login,navigate,selectTenant} from './support';
test.beforeEach(()=>control('case-start'));
test('U11_01_home_launch_preserves_prompt_without_sending',async({page})=>{
 let posts=0;page.on('request',r=>{if(r.method()==='POST'&&r.url().endsWith('/runs'))posts++;});
 await login(page,'A-U1');await page.goto('/');await expect(page.getByRole('heading',{name:'업무 홈',exact:true})).toBeVisible();
 await expect(page.getByText('생성형 AI 플랫폼',{exact:true}).first()).toBeVisible();
 await page.getByLabel('시작할 업무 질문',{exact:true}).fill('검토할 업무 질문');await page.getByRole('button',{name:'AI 채팅에서 시작',exact:true}).click();
 await expect(page.getByLabel('질문',{exact:true})).toHaveValue('검토할 업무 질문');expect(posts).toBe(0);
 await page.getByRole('button',{name:'질문 보내기',exact:true}).click();await expect(page.getByText('완료 · 저장 확인됨',{exact:true})).toBeVisible();
 await navigate(page,'홈');await page.locator('.hub-recent').first().click();await expect(page.getByRole('article').filter({hasText:'내 질문'})).toContainText('검토할 업무 질문');expect(posts).toBe(1);
});
test('U11_02_admin_home_and_real_request_approval',async({page,browser})=>{
 await login(page,'A-ADM');await page.goto('http://127.0.0.1:5174/manage/admin');await selectTenant(page,'A');await navigate(page,'운영 현황');await expect(page.getByRole('heading',{name:'운영 현황',exact:true})).toBeVisible();await expect(page.getByText('집계 기간 AI 호출',{exact:true})).toBeVisible();
 await navigate(page,'Agent 관리');const editor=page.getByRole('region',{name:'일반 대화 설정'});
 await editor.getByLabel('이름',{exact:true}).fill('U11 배포 요청');await editor.getByLabel('변경 목적',{exact:true}).fill('실제 저장 승인 검증');await editor.getByRole('button',{name:'배포 승인 요청',exact:true}).click();await expect(editor.getByRole('status')).toContainText('배포 요청이 저장되었습니다.');
 await navigate(page,'승인·검증');await page.getByRole('button').filter({hasText:'U11 배포 요청'}).click();await expect(page.getByRole('button',{name:'배포 승인',exact:true})).toHaveCount(0);
 const context=await browser.newContext();const approver=await context.newPage();
 try{await login(approver,'P-A');await approver.goto('http://127.0.0.1:5174/manage/admin');await selectTenant(approver,'A');await navigate(approver,'승인·검증');await approver.locator('.approval-row').filter({hasText:'U11 배포 요청'}).click();await approver.getByRole('button',{name:'변경 사항',exact:true}).click();await expect(approver.locator('.approval-detail')).toContainText('U11 배포 요청');
  await approver.getByLabel('검토 의견',{exact:true}).fill('변경 사항 검토 완료');await approver.getByRole('button',{name:'배포 승인',exact:true}).click();await approver.getByRole('button',{name:'검토 결정 저장',exact:true}).click();await expect(approver.locator('.approval-detail')).toContainText('승인·설정 반영 완료');
  await navigate(approver,'Agent 관리');await expect(approver.getByRole('region',{name:'일반 대화 설정'}).getByLabel('이름',{exact:true})).toHaveValue('U11 배포 요청');
 }finally{await context.close();}
});
test('U11_03_direct_denial_and_mobile_navigation',async({page})=>{
 const errors:string[]=[];page.on('pageerror',e=>errors.push(e.name));await page.setViewportSize({width:390,height:844});await login(page,'A-U1');await page.goto('/admin/approvals');await expect(page.getByRole('heading',{name:'업무 홈',exact:true})).toBeVisible();await expect(page.locator('.approval-detail')).toHaveCount(0);
 await navigate(page,'내 자료');await expect(page.getByRole('heading',{name:'내 자료',exact:true})).toBeVisible();
 await navigate(page,'홈');expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);expect(errors).toEqual([]);
});
test('U11_04_org_switch_discards_request_and_prompt',async({page})=>{
 await login(page,'DUAL-ADM');await selectTenant(page,'A');await navigate(page,'홈');await page.getByLabel('시작할 업무 질문',{exact:true}).fill('이전 조직 초안');await selectTenant(page,'B');await expect(page.getByLabel('시작할 업무 질문',{exact:true})).toHaveValue('');
 await navigate(page,'승인·검증');await expect(page.locator('.approval-list')).not.toContainText('이전 조직');expect((await page.request.get('/api/v1/admin/agent-deployments',{headers:{'X-Tenant-ID':fixture().tenants.B}})).status()).toBe(200);
});
test('U11_05_empty_filter_and_pending_submission_recovery',async({page})=>{
 await login(page,'A-ADM');await navigate(page,'승인·검증');await expect(page.getByText('조건에 맞는 배포 요청이 없습니다.',{exact:true})).toBeVisible();await page.getByLabel('요청 상태',{exact:true}).selectOption('rejected');await expect(page.getByText('조건에 맞는 배포 요청이 없습니다.',{exact:true})).toBeVisible();
 await navigate(page,'Agent 관리');const editor=page.getByRole('region',{name:'일반 대화 설정'});await editor.getByLabel('이름',{exact:true}).fill('U11 응답 유실 요청');await editor.getByLabel('변경 목적',{exact:true}).fill('재전송 멱등성');let count=0;
 await page.route('**/api/v1/admin/agent-deployments',async route=>{if(route.request().method()==='POST'&&++count===1){await route.fetch();await route.abort('failed');}else await route.continue();});
 await editor.getByRole('button',{name:'배포 승인 요청',exact:true}).click();await expect(editor.getByRole('alert')).toContainText('배포 요청 결과 확인 필요');await editor.getByRole('button',{name:'같은 배포 요청 확인',exact:true}).click();await expect(editor.getByRole('status')).toContainText('배포 요청이 저장되었습니다.');
 await navigate(page,'승인·검증');await expect(page.locator('.approval-row').filter({hasText:'U11 응답 유실 요청'})).toHaveCount(1);
});
test('U11_06_responsive_keyboard_and_private_visual_evidence',async({page})=>{
 const {mkdirSync,chmodSync}=await import('node:fs');const {resolve}=await import('node:path');
 const folder=resolve('.runtime/U11-views');mkdirSync(folder,{recursive:true,mode:0o700});chmodSync(folder,0o700);
 await page.setViewportSize({width:1600,height:1000});await login(page,'A-ADM');await navigate(page,'홈');
 await page.getByLabel('시작할 업무 질문',{exact:true}).focus();await page.keyboard.press('Tab');await expect(page.getByRole('button',{name:'문서 등록·관리',exact:true})).toBeFocused();
 expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);
 const home=resolve(folder,'user-home.png');await page.screenshot({path:home,fullPage:true});chmodSync(home,0o600);
 await navigate(page,'운영 현황');await expect(page.getByText('집계 기간 AI 호출',{exact:true})).toBeVisible();
 const admin=resolve(folder,'admin-home.png');await page.screenshot({path:admin,fullPage:true});chmodSync(admin,0o600);
 await page.setViewportSize({width:390,height:844});await navigate(page,'승인·검증');await expect(page.getByText('조건에 맞는 배포 요청이 없습니다.',{exact:true})).toBeVisible();
 expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);
 const mobile=resolve(folder,'approval-mobile.png');await page.screenshot({path:mobile,fullPage:true});chmodSync(mobile,0o600);
});
