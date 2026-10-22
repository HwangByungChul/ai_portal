import {test,expect} from '@playwright/test';
import {control,login} from './support';

test.beforeEach(()=>control('case-start'));
test.afterEach(async()=>{control('release-provider');await expect.poll(()=>control('b05-counts').active,{timeout:6000}).toBe(0);});

test('BM_01_builder_model_selection_handles_database_registry_shape',async({page})=>{
  await page.route('**/api/v1/models',route=>route.fulfill({status:200,contentType:'application/json',body:JSON.stringify({data:{items:[{
    model_id:'db-model-1',provider_key:'example',model_name:'engine-x',display_name:'Example Model X',
    context_window:64000,max_output:4096,is_default:true,active:true,capabilities:['chat','rag']
  }]},meta:{tenant_id:null,request_id:'mock-models'}})}));
  await login(page,'P-A');
  await page.goto('/manage/assets');
  await expect(page.getByRole('heading',{name:'AI 자산 및 Agent 관리',exact:false})).toBeVisible();

  // 초안 작성에서 프롬프트 구성 및 실행 모델 섹션 확인
  await expect(page.getByRole('heading',{name:'프롬프트 구성 및 실행 모델',exact:false})).toBeVisible();
  const select = page.getByLabel('실행 모델 선택');
  await expect(select).toBeVisible();

  // 기본 모델 옵션 확인
  await expect(select).toContainText('시스템 기본 모델');
  await expect(select).toContainText('Example Model X');

  // 모델 선택 변경 시 스펙/단가 정보 노출 확인
  await select.selectOption('db-model-1');
  await expect(page.getByText('제공자: EXAMPLE')).toBeVisible();
  await expect(page.getByText('문맥 한도: 64,000 토큰')).toBeVisible();
  await expect(page.getByText('최대 출력: 4,096 토큰')).toBeVisible();
  await expect(page.getByText('단가: 정보 없음')).toBeVisible();
  await expect(page.getByText(/undefined/)).toHaveCount(0);
});

test('BM_02_builder_model_selection_keeps_legacy_pricing_and_specs',async({page})=>{
  await page.route('**/api/v1/models',route=>route.fulfill({status:200,contentType:'application/json',body:JSON.stringify({data:{items:[{
    model_id:'legacy-model-1',provider_key:'legacy-provider',model_name:'Legacy Model',pricing_version:'2026-01',
    input_usd_per_million:'0.25',output_usd_per_million:'1.50',context_window:32000,max_output_tokens:2048,enabled:true,capabilities:['chat']
  }]},meta:{tenant_id:null,request_id:'mock-models-legacy'}})}));
  await login(page,'P-A');
  await page.goto('/manage/assets');
  const select=page.getByLabel('실행 모델 선택');
  await expect(select).toContainText('Legacy Model');
  await select.selectOption('legacy-model-1');
  await expect(page.getByText('문맥 한도: 32,000 토큰')).toBeVisible();
  await expect(page.getByText('최대 출력: 2,048 토큰')).toBeVisible();
  await expect(page.getByText('단가: 입력 $0.25 / 출력 $1.50 (1M당)')).toBeVisible();
});

test('BM_03_empty_or_failed_model_registry_keeps_default_usable',async({page})=>{
  let status=200;
  await page.route('**/api/v1/models',route=>route.fulfill({status,contentType:'application/json',body:JSON.stringify(status===200
    ?{data:{items:[]},meta:{tenant_id:null,request_id:'mock-models-empty'}}
    :{error:{code:'STORAGE_UNAVAILABLE'},meta:{tenant_id:null,request_id:'mock-models-failed'}})}));
  await login(page,'P-A');
  await page.goto('/manage/assets');
  let select=page.getByLabel('실행 모델 선택');
  await expect(select).toContainText('시스템 기본 모델');
  await expect(select.locator('option')).toHaveCount(1);
  await select.selectOption('default_general');
  await expect(select).toHaveValue('default_general');

  status=503;
  await page.reload();
  select=page.getByLabel('실행 모델 선택');
  await expect(select).toContainText('시스템 기본 모델');
  await expect(select.locator('option')).toHaveCount(1);
  await select.selectOption('default_general');
  await expect(select).toHaveValue('default_general');
});

test('BM_04_rag_incompatible_model_stays_warned_when_selected',async({page})=>{
  await page.route('**/api/v1/models',route=>route.fulfill({status:200,contentType:'application/json',body:JSON.stringify({data:{items:[{
    model_id:'chat-only-model',provider_key:'example',model_name:'Chat Only',display_name:'Chat Only Model',
    context_window:16000,max_output:2048,is_default:false,active:true,capabilities:['chat']
  }]},meta:{tenant_id:null,request_id:'mock-models-rag'}})}));
  await login(page,'P-A');
  await page.goto('/manage/assets');
  await page.getByLabel('실행 방식').selectOption('rules_rag');
  const select=page.getByLabel('실행 모델 선택');
  await select.selectOption('chat-only-model');
  await expect(select).toHaveValue('chat-only-model');
  await expect(page.getByRole('alert')).toContainText('RAG(문서 검색) 기능을 공식 지원하지 않습니다');
});
