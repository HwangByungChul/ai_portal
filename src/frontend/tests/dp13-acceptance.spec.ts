import {test,expect,type Page} from '@playwright/test';
import {control,fixture,login,selectTenant} from './support';

test.beforeEach(()=>control('case-start'));
test.afterEach(async()=>{control('release-provider');await expect.poll(()=>control('b05-counts').active,{timeout:6000}).toBe(0);});

test('D13_01_admin_models_registry_view',async({page})=>{
  await login(page,'P-A');
  await page.goto('/manage/admin/models');
  await expect(page.getByRole('heading',{name:'AI 모델 레지스트리',exact:true})).toBeVisible();
  await expect(page.getByText('보안 원칙:')).toBeVisible();
  await expect(page.getByText('gpt-4o-mini')).toBeVisible();
  await expect(page.getByText('mock-disabled')).toBeVisible();
  await expect(page.getByText('비활성')).toBeVisible();
});


test('D13_03_admin_model_registry_renders_database_rows_without_credentials',async({page})=>{
  let requestedTenant:string|undefined;
  await page.route('**/api/v1/admin/models',async route=>{
    requestedTenant=route.request().headers()['x-tenant-id'];
    await route.fulfill({status:200,contentType:'application/json',body:JSON.stringify({data:{items:[
      {model_id:'db-model-display',provider_key:'openai',model_name:'engine-display',display_name:'DB Display Name',context_window:128000,max_output:8192,is_default:true,active:true,capabilities:['chat','rag'],price_input_usd:'0.15',price_out_usd:'0.60',credential_ref:'DO_NOT_RENDER_CREDENTIAL_REF'},
      {model_id:'db-model-id-fallback',provider_key:'mock',model_name:'db-engine-id',context_window:undefined,max_output:undefined,is_default:false,active:false,capabilities:[],price_input_usd:null,price_out_usd:null,credential_ref:'DO_NOT_RENDER_CREDENTIAL_REF'}
    ]},meta:{tenant_id:requestedTenant,request_id:'mock-db-models'}})});
  });
  await login(page,'P-A');
  await selectTenant(page,'A');
  await page.goto('/manage/admin/models');

  await expect(page.getByRole('heading',{name:'AI 모델 레지스트리',exact:true})).toBeVisible();
  expect(requestedTenant).toBe(fixture().tenants.A);
  const cards=page.locator('.model-card');
  await expect(cards).toHaveCount(2);
  const displayCard=cards.filter({hasText:'DB Display Name'});
  await expect(displayCard).toContainText('엔진: engine-display');
  await expect(displayCard).toContainText('운영 허용');
  await expect(displayCard).toContainText('가격표 버전: 정보 없음');
  await expect(displayCard).toContainText('입력 $0.15 / 출력 $0.60');
  await expect(displayCard).toContainText('128,000 토큰');
  await expect(displayCard).toContainText('출력 최대 8,192');

  const fallbackCard=cards.filter({hasText:'db-model-id-fallback'});
  await expect(fallbackCard).toContainText('비활성');
  await expect(fallbackCard).toContainText('가격표 버전: 정보 없음');
  await expect(fallbackCard).toContainText('입력 정보 없음 / 출력 정보 없음');
  await expect(fallbackCard).toContainText('문맥 한도: 정보 없음');
  await expect(fallbackCard).toContainText('출력 최대 정보 없음');
  await expect(page.locator('body')).not.toContainText('DO_NOT_RENDER_CREDENTIAL_REF');
  await expect(page.locator('body')).not.toContainText(/undefined|NaN/);
  await expect(page.getByText('실제 API 키와 제공자 비밀 값은 서버에서만 참조·사용하며 이 화면에는 표시하지 않습니다.')).toBeVisible();
});

test('D13_02_disabled_models_hidden_from_general_users',async({page})=>{
  await login(page,'A-U1');
  const res = await page.request.get('/api/v1/models',{
    headers:{'X-Tenant-ID':fixture().tenants.A}
  });
  expect(res.status()).toBe(200);
  const data = (await res.json()).data;
  const modelIds = data.items.map((m:any)=>m.model_id);
  expect(modelIds).toContain('gpt-4o-mini');
  expect(modelIds).not.toContain('mock-disabled');
});
