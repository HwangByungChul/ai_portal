import {test,expect} from '@playwright/test';
import {control,login} from './support';

test.beforeEach(()=>control('case-start'));
test.afterEach(async()=>{control('release-provider');await expect.poll(()=>control('b05-counts').active,{timeout:6000}).toBe(0);});

test('BM_01_builder_model_selection_and_spec_display',async({page})=>{
  await login(page,'P-A');
  await page.goto('/manage/assets');
  await expect(page.getByRole('heading',{name:'AI 자산 및 Agent 관리',exact:false})).toBeVisible();

  // 초안 작성에서 프롬프트 구성 및 실행 모델 섹션 확인
  await expect(page.getByRole('heading',{name:'프롬프트 구성 및 실행 모델',exact:false})).toBeVisible();
  const select = page.getByLabel('실행 모델 선택');
  await expect(select).toBeVisible();

  // 기본 모델 옵션 확인
  await expect(select).toContainText('시스템 기본 모델');
  await expect(select).toContainText('gpt-4o');

  // 모델 선택 변경 시 스펙/단가 정보 노출 확인
  await select.selectOption('gpt-4o');
  await expect(page.getByText('문맥 한도:')).toBeVisible();
  await expect(page.getByText('최대 출력:')).toBeVisible();
  await expect(page.getByText('단가:')).toBeVisible();
});
