import {test,expect} from '@playwright/test';
import {login,selectTenant,control} from './support';
test.beforeEach(()=>control('case-start'));
test.afterEach(async()=>{control('release-provider');await expect.poll(()=>control('b05-counts').active,{timeout:6000}).toBe(0);});
async function question(page:import('@playwright/test').Page){await page.getByLabel('질문',{exact:true}).fill('합성 이력 관리 질문');await page.getByRole('button',{name:'질문 보내기',exact:true}).click();await expect(page.getByText('완료 · 저장 확인됨',{exact:true})).toBeVisible();}

test('owner renames pins searches and deletes without removing cost',async({page})=>{
 await login(page,'A-U1');await question(page);const row=page.locator('.history-row').first();
 await row.getByRole('button',{name:/제목 변경$/}).click();await page.getByLabel('새 대화 제목',{exact:true}).fill('개인 합성 보고서');await page.getByRole('button',{name:'제목 저장',exact:true}).click();
 await expect(page.locator('.conversation-link').filter({hasText:'개인 합성 보고서'})).toBeVisible();
 await page.locator('.history-row').filter({hasText:'개인 합성 보고서'}).getByRole('button',{name:/ 핀$/}).click();
 await expect(page.getByRole('button',{name:'개인 합성 보고서 핀 해제',exact:true})).toBeVisible();
 await page.getByLabel('핀한 대화만',{exact:true}).check();await expect(page.locator('.history-row')).toHaveCount(1);
 await page.getByLabel('대화 제목 검색',{exact:true}).fill('검색 결과 없음');await page.getByRole('button',{name:'검색',exact:true}).click();await expect(page.getByText('조건에 맞는 대화가 없습니다.',{exact:true})).toBeVisible();
 await page.getByLabel('대화 제목 검색',{exact:true}).fill('합성');await page.getByRole('button',{name:'검색',exact:true}).click();await expect(page.locator('.history-row')).toHaveCount(1);
 const before=control('b05-counts');await page.getByRole('button',{name:'개인 합성 보고서 삭제',exact:true}).click();await expect(page.getByText('사용량과 감사 기록은 보존됩니다.',{exact:false})).toBeVisible();await page.getByRole('button',{name:'삭제 확인',exact:true}).click();await expect(page.locator('.history-row')).toHaveCount(0);await expect(page.getByText('저장된 답변',{exact:true})).toHaveCount(0);expect(control('b05-counts').provider_calls).toBe(before.provider_calls);
 await page.reload();await expect(page.locator('.conversation-link').filter({hasText:'개인 합성 보고서'})).toHaveCount(0);
});

test('mobile controls and tenant change cannot mix history',async({page})=>{
 await page.setViewportSize({width:390,height:844});await login(page,'DUAL');await selectTenant(page,'A');await question(page);await page.getByRole('button',{name:'목록 열기',exact:true}).click();await expect(page.locator('.history-row')).toHaveCount(2);
 await page.locator('.history-row').first().getByRole('button',{name:/제목 변경$/}).click();await page.getByLabel('새 대화 제목',{exact:true}).fill('조직 A 전용 이력');await page.getByRole('button',{name:'제목 저장',exact:true}).click();await expect(page.locator('.conversation-link').first()).toContainText('조직 A 전용 이력');
 await selectTenant(page,'B');await page.getByRole('button',{name:'목록 열기',exact:true}).click();await expect(page.getByText('조직 A 전용 이력',{exact:false})).toHaveCount(0);
 await expect.poll(()=>page.evaluate(()=>document.documentElement.scrollWidth<=window.innerWidth)).toBe(true);
});

test('running answer must finish or cancel before deletion',async({page})=>{
 control('slow-provider');await login(page,'A-U1');await page.getByLabel('질문',{exact:true}).fill('합성 진행 질문');await page.getByRole('button',{name:'질문 보내기',exact:true}).click();await expect(page.locator('.history-row')).toHaveCount(2);
 await page.locator('.history-row').first().getByRole('button',{name:/ 삭제$/}).click();await page.getByRole('button',{name:'삭제 확인',exact:true}).click();await expect(page.getByText('답변이 진행 중입니다. 취소하거나 완료된 뒤 삭제해 주세요.',{exact:true})).toBeVisible();await expect(page.locator('.history-row')).toHaveCount(2);
 control('release-provider');await expect(page.getByText('완료 · 저장 확인됨',{exact:true})).toBeVisible();await page.getByRole('button',{name:'삭제 확인',exact:true}).click();await expect(page.locator('.history-row')).toHaveCount(1);
});
