import {test,expect} from '@playwright/test';
import {control,login} from './support';

test.beforeEach(()=>control('case-start'));
test.afterEach(async()=>{control('release-provider');await expect.poll(()=>control('b05-counts').active,{timeout:6000}).toBe(0);});

test('ADMIN_01_operations_overview_metrics_cards_and_daily_chart',async({page})=>{
  await login(page,'A-ADM');
  await page.goto('/manage/admin');

  // 운영 현황 헤더 확인
  await expect(page.getByRole('heading',{name:'운영 현황',exact:true})).toBeVisible();

  // 4대 핵심 지표 카드 영역 확인
  await expect(page.getByText('집계 기간 AI 호출')).toBeVisible();
  await expect(page.getByText('확인된 사용 추정 금액')).toBeVisible();
  await expect(page.getByText('승인 대기 배포 요청')).toBeVisible();
  await expect(page.getByText('사용량 확인 필요')).toBeVisible();

  // 공통 서비스 관측 상태 및 차트/새로고침 버튼 확인
  await expect(page.getByText('공통 서비스 관측 상태')).toBeVisible();
  await expect(page.getByRole('button',{name:'운영 현황 새로고침'})).toBeVisible();
});
