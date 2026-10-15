import {test,expect,type Page} from '@playwright/test';
import {control,password,fixture} from './support';
import {loadEnvironment} from '../scripts/environment.mjs';
const env=loadEnvironment(),admin=env.admin.origin!+env.admin.entry;
async function signIn(page:Page,actor='A-ADM'){
 await page.goto(admin+'/builder');await page.getByLabel('로그인 ID',{exact:true}).fill(actor.toLowerCase());await page.getByLabel('비밀번호',{exact:true}).fill(password(actor));await page.getByRole('button',{name:'로그인',exact:true}).click();await expect(page.getByRole('button',{name:'로그아웃',exact:true})).toBeVisible();await page.getByLabel('현재 조직',{exact:true}).selectOption(fixture().tenants.A);await page.locator('#portal-navigation').getByRole('button',{name:'Agent Builder',exact:true}).click();
}
async function draft(page:Page){
 await page.getByRole('button',{name:'새 Agent 초안',exact:true}).click();await page.getByLabel('자산 이름',{exact:true}).fill('Builder 합성 검증');await page.getByLabel('자산 지시문',{exact:true}).fill('설명 대상 {{audience}}');await page.getByRole('button',{name:'초안 등록',exact:true}).click();await expect(page.getByText('초안 버전 1 저장됨 · 운영 활성화 전',{exact:true})).toBeVisible();
}
test.beforeEach(()=>{control('case-start');});
test('D11_01_saved_template_preview_dirty_and_reload',async({page})=>{
 await signIn(page);await draft(page);await page.getByLabel('변수 audience',{exact:true}).fill('<script>{{secret}}</script>');await page.getByLabel('변수 question',{exact:true}).fill('절차');await page.getByRole('button',{name:'저장 버전 조합 검증',exact:true}).click();await expect(page.getByRole('region',{name:'조합 검증 결과'})).toContainText('설명 대상 <script>{{secret}}</script>');await expect(page.getByText('조합 검증 완료 · 모델 호출 없음',{exact:true})).toBeVisible();
 await page.getByLabel('자산 이름',{exact:true}).fill('Builder 수정');await expect(page.getByRole('region',{name:'조합 검증 결과'})).toHaveCount(0);await expect(page.getByRole('button',{name:'저장 버전 조합 검증',exact:true})).toBeDisabled();
 await page.getByRole('button',{name:'새 초안 버전 저장',exact:true}).click();await expect(page.getByText('초안 버전 2 저장됨 · 운영 활성화 전',{exact:true})).toBeVisible();await page.reload();await page.locator('.approval-row').filter({hasText:'Builder 수정'}).click();await expect(page.getByLabel('자산 지시문',{exact:true})).toHaveValue('설명 대상 {{audience}}');await expect(page.getByLabel('변수 audience',{exact:true})).toHaveValue('');
});
test('D11_02_malformed_template_and_empty_rag_scope',async({page})=>{
 await signIn(page);await page.getByRole('button',{name:'새 Agent 초안',exact:true}).click();await page.getByLabel('자산 이름',{exact:true}).fill('잘못된 템플릿');await page.getByLabel('자산 지시문',{exact:true}).fill('설명 {{wrong name}}');await page.getByRole('button',{name:'초안 등록',exact:true}).click();await expect(page.getByRole('alert')).toContainText('템플릿 형식');
 await page.getByLabel('자산 지시문',{exact:true}).fill('자료 근거로 답하세요.');await page.getByLabel('사용자 질문 템플릿',{exact:true}).fill('문서 질문');await page.getByLabel('실행 방식',{exact:true}).selectOption('rules_rag');await page.getByRole('button',{name:'초안 등록',exact:true}).click();await expect(page.getByText('초안 버전 1 저장됨 · 운영 활성화 전',{exact:true})).toBeVisible();await expect(page.getByRole('region',{name:'읽을 수 있는 자료'})).toBeVisible();await page.getByRole('button',{name:'저장 버전 조합 검증',exact:true}).click();await expect(page.getByRole('region',{name:'조합 검증 결과'})).toContainText('선택 자료 0개');
});
test('D11_03_late_preview_cannot_cross_organization',async({page})=>{
 await signIn(page,'DUAL-ADM');await draft(page);await page.getByLabel('변수 audience',{exact:true}).fill('조직 A 전용 검증');await page.getByLabel('변수 question',{exact:true}).fill('절차');let finish!:()=>void;const held=new Promise<void>(r=>finish=r);
 await page.route('**/admin/builder/assets/*/versions/*/preview',async route=>{const response=await route.fetch();const body=await response.body(),headers=response.headers(),status=response.status();await held;await route.fulfill({status,headers,body});});await page.getByRole('button',{name:'저장 버전 조합 검증',exact:true}).click();await page.getByLabel('현재 조직',{exact:true}).selectOption(fixture().tenants.B);finish();await expect(page.getByRole('region',{name:'프롬프트 조합 검증'})).toHaveCount(0);await expect(page.getByText('조직 A 전용 검증',{exact:true})).toHaveCount(0);
});
