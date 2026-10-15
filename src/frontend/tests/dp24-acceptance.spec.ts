import {test,expect} from '@playwright/test';
import {control,login} from './support';

test.beforeEach(()=>control('case-start'));
test.afterEach(async()=>{control('release-provider');await expect.poll(()=>control('b05-counts').active,{timeout:6000}).toBe(0);});

test('DP24_01_use_case_workspace_page_10_agents_and_safety_badges',async({page})=>{
  await login(page,'A-ADM');
  await page.goto('/user/use-cases');

  // 헤더 및 10종 뱃지
  await expect(page.getByRole('heading',{name:'10대 표준 업무 Agent 워크스페이스',exact:true})).toBeVisible();
  await expect(page.getByText('업무 정의 10종 · 현재 이용 가능 0종')).toBeVisible();

  // Agent 목록 카드 확인
  await expect(page.getByText('AGENT_01')).toBeVisible();
  await expect(page.getByText('규정 책무 관리 Agent')).toBeVisible();
  await expect(page.getByText('AGENT_08')).toBeVisible();
  await expect(page.getByText('여신 심사 보조 Agent')).toBeVisible();

  // 금융 결정 자동확정 금지 배너 표시 확인
  await expect(page.getByText('자동확정 금지').first()).toBeVisible();

  // 실행 버튼 확인
  await expect(page.getByRole('button',{name:'Agent 실행 및 초안 생성',exact:true})).toBeDisabled();
});
