import {test,expect,type Page} from '@playwright/test';
import {control,fixture,login,selectTenant} from './support';
const output='모의 AI 응답입니다. 실제 모델 호출 없이 실행·권한·사용량 흐름을 검증했습니다.';
const errors=new Map<string,number>();
test.beforeEach(({context},info)=>{control('case-start');errors.set(info.title,0);context.on('page',page=>page.on('pageerror',()=>errors.set(info.title,(errors.get(info.title)??0)+1)));});
test.afterEach(async({},info)=>{control('release-provider');await expect.poll(()=>control('b05-counts').active,{timeout:6000}).toBe(0);expect(errors.get(info.title)??0).toBe(0);});
async function question(page:Page,prompt='합성 업무 질문'){
 await page.getByLabel('질문',{exact:true}).fill(prompt);await expect(page.getByRole('button',{name:'질문 보내기',exact:true})).toBeEnabled();
 await page.getByRole('button',{name:'질문 보내기',exact:true}).click();
}
async function completed(page:Page){await expect(page.getByText('완료 · 저장 확인됨',{exact:true})).toBeVisible();await expect(page.getByText(output,{exact:true})).toBeVisible();}
async function csrf(page:Page){return (await (await page.request.get('/api/v1/auth/me')).json()).data.csrf_token as string;}
async function headers(page:Page,tenant='A'){return {'X-Tenant-ID':fixture().tenants[tenant],Origin:'http://127.0.0.1:5173','X-Requested-With':'ai-portal','X-CSRF-Token':await csrf(page)};}

test('B05_01_chat_surface',async({page})=>{
 await login(page,'A-U1');await expect(page.getByRole('heading',{name:'AI 업무',exact:true})).toBeVisible();await expect(page.getByLabel('질문',{exact:true})).toBeVisible();
 await page.getByLabel('Agent',{exact:true}).selectOption('rules_rag');await page.getByLabel('질문',{exact:true}).fill('검색 질문');
 await expect(page.getByRole('button',{name:'질문 보내기',exact:true})).toBeDisabled();expect(control('b05-counts').provider_calls).toBe(0);
});
test('B05_02_save_reload_history',async({page})=>{
 await login(page,'A-U1');await question(page);await completed(page);expect(control('b05-counts').provider_calls).toBe(1);
 await page.reload();await page.locator('.conversation-link').filter({hasText:'완료'}).click();await completed(page);
 expect(control('b05-counts').provider_calls).toBe(1);expect(await page.evaluate(()=>localStorage.length+sessionStorage.length)).toBe(0);
});
test('B05_03_lost_acceptance_one_provider_call',async({page})=>{
 await login(page,'A-U1');let posts=0;
 await page.route('**/api/v1/runs',async route=>{posts++;await route.fetch();await route.abort('failed');});
 await question(page);await completed(page);expect(posts).toBe(1);expect(control('b05-counts').provider_calls).toBe(1);expect(control('b05-counts').runs).toBe(1);
});
test('B05_04_missing_acceptance_replays_identical_payload_once',async({page})=>{
 await login(page,'A-U1');const payloads:string[]=[];
 await page.route('**/api/v1/runs',async route=>{payloads.push(route.request().postData()??'');if(payloads.length===1)await route.abort('failed');else await route.continue();});
 await question(page);await completed(page);expect(payloads).toHaveLength(2);expect(payloads[0]).toBe(payloads[1]);expect(control('b05-counts').provider_calls).toBe(1);
});
test('B05_05_double_click_one_admission',async({page})=>{
 await login(page,'A-U1');await page.getByLabel('질문',{exact:true}).fill('중복 클릭 검증');await expect(page.getByRole('button',{name:'질문 보내기',exact:true})).toBeEnabled();
 await page.getByRole('button',{name:'질문 보내기',exact:true}).evaluate((button:HTMLButtonElement)=>{button.click();button.click();});await completed(page);
 expect(control('b05-counts').runs).toBe(1);expect(control('b05-counts').provider_calls).toBe(1);
});
test('B05_06_stream_eof_queries_saved_state',async({page})=>{
 control('slow-provider');await login(page,'A-U1');let streams=0;
 await page.route('**/api/v1/runs/*/events',route=>{streams++;return route.fulfill({status:200,contentType:'text/event-stream',body:''});});
 await question(page);await expect.poll(()=>streams).toBe(1);await expect(page.getByText('완료 · 저장 확인됨',{exact:true})).toHaveCount(0);
 control('release-provider');await completed(page);expect(control('b05-counts').provider_calls).toBe(1);
});
test('B05_07_actual_stream_draft_and_cancel',async({page})=>{
 control('slow-provider');await login(page,'A-U1');await question(page);await expect(page.getByText('저장 전 모의 초안',{exact:true})).toBeVisible();
 await expect(page.getByText('작성 중 · 저장 미확정',{exact:true})).toBeVisible();await expect(page.getByText('저장된 답변',{exact:true})).toHaveCount(0);
 await page.getByRole('button',{name:'답변 취소 요청',exact:true}).click();await expect(page.getByText('취소됨',{exact:true})).toBeVisible();
 await expect(page.getByText('저장 전 모의 초안',{exact:true})).toHaveCount(0);expect(control('b05-counts').provider_calls).toBe(1);
});
test('B05_08_two_tabs_independent_conversation_scopes',async({page,context})=>{
 await login(page,'DUAL');await selectTenant(page,'A');await question(page,'A 전용 합성 질문');await completed(page);
 const second=await context.newPage();await second.goto('/');await selectTenant(second,'B');await question(second,'B 전용 합성 질문');await completed(second);
 await expect(page.getByLabel('현재 조직')).toHaveValue(fixture().tenants.A);await expect(second.getByLabel('현재 조직')).toHaveValue(fixture().tenants.B);
 await expect(page.getByText('B 전용 합성 질문',{exact:true})).toHaveCount(0);await expect(second.getByText('A 전용 합성 질문',{exact:true})).toHaveCount(0);
 expect(control('b05-counts').provider_calls).toBe(2);
});
test('B05_09_late_A_stream_discarded_after_switch',async({page})=>{
 control('slow-provider');const org=fixture().tenants.A;
 await page.addInitScript(()=>{const original=window.fetch;window.fetch=(input,options)=>String(input).includes('/events')?original(input,{...options,signal:undefined}):original(input,options);});
 await login(page,'DUAL');await selectTenant(page,'A');let release!:()=>void,ready!:()=>void,delivered!:()=>void;
 const gate=new Promise<void>(r=>release=r),started=new Promise<void>(r=>ready=r),finished=new Promise<void>(r=>delivered=r);
 await page.route('**/api/v1/runs/*/events',async route=>{
  const runId=route.request().url().split('/').at(-2)!;
  const reply=await page.request.get('/api/v1/runs/'+runId,{headers:{'X-Tenant-ID':org}});const view=(await reply.json()).data;
  const base={tenant_id:org,run_id:runId,execution_epoch:1};ready();await gate;
  try{await route.fulfill({status:200,contentType:'text/event-stream',body:'event: snapshot\ndata: '+JSON.stringify({...base,sequence:1,data:view})+'\n\nevent: draft_delta\ndata: '+JSON.stringify({...base,sequence:2,data:{text:'늦은 A 전용 초안',draft_sequence:1,replace:true}})+'\n\n'});}finally{delivered();}
 });
 await question(page,'A 전용 초안 질문');await started;await selectTenant(page,'B');await expect(page.getByLabel('질문',{exact:true})).toHaveValue('');release();await finished;
 await page.evaluate(()=>new Promise<void>(r=>requestAnimationFrame(()=>requestAnimationFrame(()=>r()))));
 await expect(page.getByText('늦은 A 전용 초안',{exact:true})).toHaveCount(0);await expect(page.getByText('A 전용 초안 질문',{exact:true})).toHaveCount(0);
 control('release-provider');expect(control('b05-counts').provider_calls).toBe(1);
});
test('B05_10_user_admin_routes_and_APIs_denied',async({page})=>{
 await login(page,'A-U1');for(const name of ['Agent 관리','조직 사용량','플랫폼 운영'])await expect(page.getByRole('button',{name,exact:true})).toHaveCount(0);
 for(const path of ['/admin/agents/general','/admin/usage','/admin/budget'])expect((await page.request.get('/api/v1'+path,{headers:{'X-Tenant-ID':fixture().tenants.A}})).status()).toBe(403);
 await page.goto('/admin/agents');await expect(page.getByRole('heading',{name:'AI 업무',exact:true})).toBeVisible();await expect(page.getByLabel('기본 지시문')).toHaveCount(0);
});
test('B05_11_agent_conflict_no_automatic_overwrite',async({page})=>{
 await login(page,'A-ADM');await page.getByRole('button',{name:'Agent 관리',exact:true}).click();const editor=page.getByRole('region',{name:'일반 대화 설정'});
 await expect(editor.getByLabel('이름',{exact:true})).toHaveValue('일반 대화');
 expect((await page.request.patch('/api/v1/admin/agents/general',{headers:await headers(page),data:{name:'먼저 저장된 설정',expected_revision:1}})).status()).toBe(200);
 let writes=0;page.on('request',request=>{if(request.method()==='PATCH')writes++;});await editor.getByLabel('이름',{exact:true}).fill('덮어쓸 초안');await editor.getByRole('button',{name:'설정 저장',exact:true}).click();
 await expect(editor.getByRole('alert')).toContainText('다른 변경이 먼저 적용되었습니다.');await expect(editor.getByLabel('이름',{exact:true})).toHaveValue('먼저 저장된 설정');expect(writes).toBe(1);
 await editor.getByLabel('이름',{exact:true}).fill('명시적 재편집');await editor.getByRole('button',{name:'설정 저장',exact:true}).click();await expect(editor.getByText('저장되었습니다.',{exact:true})).toBeVisible();expect(writes).toBe(2);
});
test('B05_12_agent_stop_blocks_new_provider_calls',async({page})=>{
 await login(page,'A-ADM');await page.getByRole('button',{name:'Agent 관리',exact:true}).click();const editor=page.getByRole('region',{name:'일반 대화 설정'});
 await editor.getByRole('button',{name:'Agent 중지',exact:true}).click();await editor.getByRole('button',{name:'운영 변경 확인',exact:true}).click();await expect(editor.getByText('저장되었습니다.',{exact:true})).toBeVisible();
 await page.getByRole('button',{name:'AI 업무',exact:true}).click();await page.getByLabel('질문',{exact:true}).fill('중지 후 질문');await expect(page.getByRole('button',{name:'질문 보내기',exact:true})).toBeDisabled();
 const reply=await page.request.post('/api/v1/runs',{headers:await headers(page),data:{client_send_id:crypto.randomUUID(),agent_key:'general',prompt:'직접 중지 우회'}});expect(reply.status()).toBe(409);expect(control('b05-counts').provider_calls).toBe(0);
});
test('B05_13_platform_writer_only_no_usage_read',async({page})=>{
 let summaries=0;page.on('request',req=>{if(req.url().includes('/platform/summary'))summaries++;});await login(page,'P_WRITE_ONLY');await page.getByRole('button',{name:'플랫폼 운영',exact:true}).click();
 await page.getByRole('button',{name:'프로젝트 전체 중지',exact:true}).click();await page.getByRole('button',{name:'프로젝트 운영 변경 확인',exact:true}).click();
 await expect(page.getByText('프로젝트 전체 운영 중지',{exact:true})).toBeVisible();await expect(page.getByText('확인된 사용량의 추정 금액',{exact:true})).toHaveCount(0);expect(summaries).toBe(0);
 await page.getByRole('button',{name:'AI 업무',exact:true}).click();await page.getByLabel('질문',{exact:true}).fill('공통 중지 확인');await expect(page.getByRole('button',{name:'질문 보내기',exact:true})).toBeDisabled();expect(control('b05-counts').provider_calls).toBe(0);
});
test('B05_14_platform_reader_only_no_write',async({page})=>{
 await login(page,'P_READ_ONLY');await page.getByRole('button',{name:'플랫폼 운영',exact:true}).click();await expect(page.getByText('확인된 사용량의 추정 금액',{exact:true})).toBeVisible();
 await expect(page.getByRole('button',{name:'프로젝트 전체 중지',exact:true})).toHaveCount(0);
});
test('B05_15_tadmin_local_cap_and_no_allocation',async({page})=>{
 await login(page,'A-ADM');await page.getByRole('button',{name:'조직 사용량',exact:true}).click();await page.getByLabel('조직 제한 금액 (원)').fill('12000');await page.getByRole('button',{name:'조직 제한 저장',exact:true}).click();
 await expect(page.getByText('한도가 저장되었습니다.',{exact:true})).toBeVisible();await expect(page.getByLabel('현재 조직 상위 배정 (원)')).toHaveCount(0);
 const reply=await page.request.put('/api/v1/platform/tenant-budgets/'+fixture().tenants.A,{headers:await headers(page),data:{allocated_cap_krw:'12000',expected_revision:2}});expect(reply.status()).toBe(403);
});
test('B05_16_padmin_current_managed_allocation_only',async({page})=>{
 await login(page,'P-A');await page.getByRole('button',{name:'조직 사용량',exact:true}).click();await page.getByLabel('현재 조직 상위 배정 (원)').fill('12300');await page.getByRole('button',{name:'상위 배정 저장',exact:true}).click();
 await expect(page.getByText('한도가 저장되었습니다.',{exact:true})).toBeVisible();expect((await page.request.get('/api/v1/admin/budget',{headers:{'X-Tenant-ID':fixture().tenants.B}})).status()).toBe(403);
 const reply=await page.request.put('/api/v1/platform/tenant-budgets/'+fixture().tenants.B,{headers:await headers(page,'B'),data:{allocated_cap_krw:'12000',expected_revision:1}});expect(reply.status()).toBe(403);
});
test('B05_17_unknown_usage_reservation_preserved',async({page})=>{
 control('unknown-provider');await login(page,'A-U1');await question(page);await expect(page.getByText('사용량 확인 필요 · 예약 유지',{exact:true})).toBeVisible();expect(control('b05-counts').unknown).toBe(1);
 await page.getByRole('button',{name:'내 사용량',exact:true}).click();await expect(page.getByText('3.640000 원',{exact:true})).toBeVisible();await expect(page.getByText('1 건',{exact:true})).toBeVisible();
 await expect(page.getByText('사용량 확인 필요 · 예약 유지. 비용을 0원으로 확정하지 않습니다.',{exact:true})).toBeVisible();expect(control('b05-counts').provider_calls).toBe(1);
});
test('B05_18_expired_session_removes_stream_body',async({page})=>{
 control('slow-provider');await login(page,'A-U1');await question(page);await expect(page.getByText('저장 전 모의 초안',{exact:true})).toBeVisible();control('expire','A-U1');
 await expect(page.getByLabel('로그인 ID',{exact:true})).toBeVisible();await expect(page.getByText('저장 전 모의 초안',{exact:true})).toHaveCount(0);
});
test('B05_19_platform_permission_revoked_clears_summary',async({page})=>{
 await login(page,'P_READ_ONLY');await page.getByRole('button',{name:'플랫폼 운영',exact:true}).click();await expect(page.getByText('확인된 사용량의 추정 금액',{exact:true})).toBeVisible();
 control('revoke-platform','P_READ_ONLY');await page.getByRole('button',{name:'운영 상태 새로고침',exact:true}).click();await expect(page.getByText('확인된 사용량의 추정 금액',{exact:true})).toHaveCount(0);
 await expect(page.getByRole('button',{name:'프로젝트 전체 중지',exact:true})).toHaveCount(0);await expect(page.getByRole('button',{name:'플랫폼 운영',exact:true})).toHaveCount(0);
});
test('B05_20_mobile_chat_no_page_overflow',async({page})=>{
 await page.setViewportSize({width:390,height:844});await login(page,'P-A');await expect(page.locator('.conversation-link')).toHaveCount(0);await page.getByRole('button',{name:'목록 열기',exact:true}).click();await expect(page.getByText('저장된 대화가 없습니다.',{exact:true})).toBeVisible();await page.getByRole('button',{name:'목록 닫기',exact:true}).click();await question(page);await completed(page);await expect(page.locator('.conversation-link').first()).toBeHidden();await page.getByRole('button',{name:'목록 열기',exact:true}).click();await expect(page.locator('.conversation-link').first()).toBeVisible();await page.getByRole('button',{name:'목록 닫기',exact:true}).click();
 expect(await page.evaluate(()=>document.documentElement.scrollWidth<=window.innerWidth)).toBe(true);await page.getByRole('button',{name:'조직 사용량',exact:true}).click();await expect(page.getByLabel('현재 조직 상위 배정 (원)')).toBeVisible();
 expect(await page.evaluate(()=>document.documentElement.scrollWidth<=window.innerWidth)).toBe(true);
});
test('B05_21_conversation_cursor_uses_real_server_pages',async({page})=>{
 await login(page,'A-U1');const h=await headers(page);
 for(let i=0;i<21;i++)expect((await page.request.post('/api/v1/conversations',{headers:h,data:{agent_key:'general',client_conversation_id:crypto.randomUUID()}})).status()).toBe(201);
 await page.getByRole('button',{name:'업무 새로고침',exact:true}).click();await expect(page.locator('.conversation-link')).toHaveCount(20);await page.getByRole('button',{name:'대화 더 보기',exact:true}).click();
 // Prior disposable cases create conversations but never leak their bodies: inspect server count.
 const first=(await (await page.request.get('/api/v1/conversations',{headers:{'X-Tenant-ID':fixture().tenants.A}})).json()).data;
 expect(first.items).toHaveLength(20);await expect(page.locator('.conversation-link')).not.toHaveCount(20);
 expect(control('b05-counts').provider_calls).toBe(0);
});
test('B05_22_GET_retry_bounded_no_new_generation',async({page})=>{
 let reads=0;await page.route('**/api/v1/conversations',async route=>{reads++;if(reads<3)await route.fulfill({status:503,json:{error:{code:'STORAGE_UNAVAILABLE'}}});else await route.continue();});
 await login(page,'A-U1');await expect(page.locator('.conversation-link').first()).toBeVisible();expect(reads).toBe(3);expect(control('b05-counts').provider_calls).toBe(0);
});
for(const [number,kind] of [[23,'gap'],[24,'epoch'],[25,'org'],[26,'size']] as const){
 test('B05_'+number+'_invalid_stream_'+kind+'_canonical_recovery',async({page})=>{
  control('slow-provider');await login(page,'A-U1');let frames=0;
  await page.route('**/api/v1/runs/*/events',async route=>{
   const runId=route.request().url().split('/').at(-2)!;const actual=(await (await page.request.get('/api/v1/runs/'+runId,{headers:{'X-Tenant-ID':fixture().tenants.A}})).json()).data;
   const base={tenant_id:fixture().tenants.A,run_id:runId,execution_epoch:1};const snapshot={...base,sequence:1,data:actual};
   const draft={...base,tenant_id:kind==='org'?fixture().tenants.B:base.tenant_id,execution_epoch:kind==='epoch'?2:1,sequence:kind==='gap'?3:2,data:{replace:true,draft_sequence:1,text:kind==='size'?'x'.repeat(66000):'표시하면 안 되는 잘못된 초안'}};
   frames++;await route.fulfill({status:200,contentType:'text/event-stream',body:'event: snapshot\ndata: '+JSON.stringify(snapshot)+'\n\nevent: draft_delta\ndata: '+JSON.stringify(draft)+'\n\n'});
  });
  await question(page);await expect.poll(()=>frames).toBe(1);await expect(page.getByText('표시하면 안 되는 잘못된 초안',{exact:true})).toHaveCount(0);control('release-provider');await completed(page);expect(control('b05-counts').provider_calls).toBe(1);
 });
}

test('B05_27_unresolved_admission_blocks_new_requests',async({page})=>{
 await login(page,'A-U1');let posts=0;await page.route('**/api/v1/runs',route=>{posts++;return route.abort('failed');});await question(page);
 await expect(page.getByRole('button',{name:'접수 상태 확인',exact:true})).toBeVisible();expect(posts).toBe(2);
 await expect(page.getByRole('button',{name:'질문 보내기',exact:true})).toBeDisabled();await page.getByRole('button',{name:'접수 상태 확인',exact:true}).click();
 await expect(page.getByRole('button',{name:'접수 상태 확인',exact:true})).toBeEnabled();expect(posts).toBe(2);expect(control('b05-counts').provider_calls).toBe(0);
});
test('B05_28_chat_logout_clears_other_tab_draft',async({page,context})=>{
 control('slow-provider');await login(page,'A-U1');await question(page);await expect(page.getByText('저장 전 모의 초안',{exact:true})).toBeVisible();
 const second=await context.newPage();await second.goto('/');await expect(second.getByRole('button',{name:'로그아웃',exact:true})).toBeVisible();
 await second.getByRole('button',{name:'로그아웃',exact:true}).click();await expect(page.getByLabel('로그인 ID',{exact:true})).toBeVisible();await expect(page.getByText('저장 전 모의 초안',{exact:true})).toHaveCount(0);
});
test('B05_29_hidden_state_stops_poll_without_cancelling_run',async({page})=>{
 control('slow-provider');await login(page,'A-U1');await question(page);await expect(page.getByText('저장 전 모의 초안',{exact:true})).toBeVisible();let reads=0;
 page.on('request',req=>{if(/\/runs\/[^/]+$/.test(new URL(req.url()).pathname)&&req.method()==='GET')reads++;});
 await page.evaluate(()=>{Object.defineProperty(document,'visibilityState',{configurable:true,value:'hidden'});document.dispatchEvent(new Event('visibilitychange'));});
 await page.waitForTimeout(2300);expect(reads).toBe(0);expect(control('b05-counts').active).toBe(1);expect(control('b05-counts').provider_calls).toBe(1);
 control('release-provider');await page.evaluate(()=>{Object.defineProperty(document,'visibilityState',{configurable:true,value:'visible'});document.dispatchEvent(new Event('visibilitychange'));});
 const current=page.locator('.conversation-link').filter({hasText:/완료|답변 작성 중|접수됨/});await expect(current).toBeVisible();await current.click();await completed(page);
});

test('B05_30_fragmented_UTF8_CRLF_stream_parser',async({page})=>{
 await login(page,'A-U1');const result=await page.evaluate(async()=>{
  const modulePath='/src/stream.ts';const {subscribe}=await import(modulePath);
  const org='10000000-0000-4000-8000-00000000000a',run='20000000-0000-4000-8000-000000000001';
  const value={tenant_id:org,run_id:run,execution_epoch:1};
  const payload=': keepalive\r\n\r\nevent: snapshot\r\ndata: '+JSON.stringify({...value,sequence:1,data:{}})+'\r\n\r\nevent: draft_delta\r\ndata: '+JSON.stringify({...value,sequence:2,data:{text:'모의🙂 초안',draft_sequence:1,replace:true}})+'\r\n\r\n';
  const bytes=new TextEncoder().encode(payload);const original=window.fetch;let position=0;
  window.fetch=(input,options)=>String(input).endsWith('/events')?Promise.resolve(new Response(new ReadableStream({pull(controller){if(position===bytes.length){controller.close();return;}controller.enqueue(bytes.slice(position,++position));}}),{headers:{'Content-Type':'text/event-stream'}})):original(input,options);
  const events:{event:string;data:{text?:string}}[]=[];
  try{await subscribe(run,org,new AbortController().signal,(event:{event:string;data:{text?:string}})=>events.push(event));return {count:events.length,text:events.at(-1)?.data.text};}finally{window.fetch=original;}
 });
 expect(result).toEqual({count:2,text:'모의🙂 초안'});expect(control('b05-counts').provider_calls).toBe(0);
});
test('B05_31_saved_prompt_rendered_as_text_without_storage',async({page})=>{
 await login(page,'A-U1');await question(page,'<img src=x onerror="window.injected=true">');await completed(page);await expect(page.locator('.message img')).toHaveCount(0);
 expect(await page.evaluate(()=>localStorage.length+sessionStorage.length)).toBe(0);expect(page.url()).not.toContain('onerror');
 await page.getByRole('button',{name:'새 대화',exact:true}).click();await expect(page.getByLabel('질문',{exact:true})).toHaveValue('');await expect(page.locator('.message,.draft')).toHaveCount(0);
 const {resolve}=await import('node:path');const {chmodSync}=await import('node:fs');
 for(const [name,width,height] of [['desktop',1440,1000],['mobile',390,844]] as const){
  await page.setViewportSize({width,height});const path=resolve('.runtime/B05-chat-'+name+'.png');await page.screenshot({path,fullPage:true});chmodSync(path,0o600);
 }

});


test('B05_32_late_A_admin_settings_do_not_replace_B_form',async({page})=>{
 await login(page,'DUAL-ADM');await selectTenant(page,'A');
 let ready!:()=>void,release!:()=>void,done!:()=>void;
 const waiting=new Promise<void>(r=>ready=r),gate=new Promise<void>(r=>release=r),delivered=new Promise<void>(r=>done=r);
 await page.route('**/api/v1/admin/agents/general',async route=>{
  if(route.request().method()!=='GET'||route.request().headers()['x-tenant-id']!==fixture().tenants.A)return route.continue();
  const response=await route.fetch();const body=await response.json();body.data.name='A 이전 조직 보호 설정';ready();await gate;
  try{await route.fulfill({response,json:body});}catch{}finally{done();}
 });
 await page.getByRole('button',{name:'Agent 관리',exact:true}).click();await waiting;
 await selectTenant(page,'B');const editor=page.getByRole('region',{name:'일반 대화 설정'});
 await expect(editor.getByLabel('이름',{exact:true})).toHaveValue('일반 대화');release();await delivered;
 await expect(editor.getByLabel('이름',{exact:true})).toHaveValue('일반 대화');await expect(page.getByText('A 이전 조직 보호 설정',{exact:true})).toHaveCount(0);
 let savedTenant='';page.on('request',req=>{if(req.method()==='PATCH'&&req.url().endsWith('/admin/agents/general'))savedTenant=req.headers()['x-tenant-id'];});
 await editor.getByLabel('이름',{exact:true}).fill('B 현재 조직 설정');await editor.getByRole('button',{name:'설정 저장',exact:true}).click();
 await expect(editor.getByText('저장되었습니다.',{exact:true})).toBeVisible();expect(savedTenant).toBe(fixture().tenants.B);
});
