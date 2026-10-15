import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { execFileSync } from 'node:child_process';
import { expect,type Page } from '@playwright/test';
export interface Fixture {database:string;actors:Record<string,string>;tenants:Record<string,string>;secret_path:string}
export function fixture():Fixture{return JSON.parse(readFileSync(resolve('../backend/.runtime/A05-fixture.json'),'utf8'));}
export function password(actor:string):string{return JSON.parse(readFileSync(fixture().secret_path,'utf8')).passwords[actor];}
export function control(action:string,actor='A-U1',tenant='A'):Record<string,unknown>{
 return JSON.parse(execFileSync(resolve('../backend/.venv/bin/python'),['-m','scripts.portal_test_control',action,actor,tenant],
  {cwd:resolve('../backend'),stdio:['ignore','pipe','pipe'],encoding:'utf8'}));
}
export async function login(page:Page,actor:string){
 await page.goto('/login');await page.getByLabel('로그인 ID',{exact:true}).fill(actor.toLowerCase());
 await page.getByLabel('비밀번호',{exact:true}).fill(password(actor));await page.getByRole('button',{name:'로그인',exact:true}).click();
 await expect(page.getByRole('button',{name:'로그아웃',exact:true})).toBeVisible();
 // Historical feature tests enter the workspace explicitly; portal tests cover the default home.
 await page.goto('/workspace');
}
export async function selectTenant(page:Page,tenant='A'){await page.getByLabel('현재 조직',{exact:true}).selectOption(fixture().tenants[tenant]);}
export async function members(page:Page){await navigate(page,'사용자 관리');await expect(page.locator('tbody tr').first()).toBeVisible();}
export function row(page:Page,actor='A-U1'){return page.locator(`tr[data-user-id="${fixture().actors[actor]}"]`);}

export async function navigate(page:Page,label:string){
 await expect(page.locator('#portal-navigation')).toBeAttached();
 const admin=['운영 현황','승인·검증','사용자 관리','Agent 관리','조직 사용량','문서 관리','답변 평가','플랫폼 운영'].includes(label);
 async function click(name:string){const button=page.locator('#portal-navigation').getByRole('button',{name,exact:true,includeHidden:true});if(await button.count()&&!await button.isVisible())await page.getByRole('button',{name:'메뉴 열기',exact:true}).click();await button.click();}
 if(!await page.locator('#portal-navigation').getByRole('button',{name:label,exact:true,includeHidden:true}).count())await click(admin?'관리자 사이트':'사용자 사이트');
 await click(label);
}
