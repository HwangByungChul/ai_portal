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
}
export async function selectTenant(page:Page,tenant='A'){await page.getByLabel('현재 조직',{exact:true}).selectOption(fixture().tenants[tenant]);}
export async function members(page:Page){await page.getByRole('button',{name:'사용자 관리',exact:true}).click();await expect(page.locator('tbody tr').first()).toBeVisible();}
export function row(page:Page,actor='A-U1'){return page.locator(`tr[data-user-id="${fixture().actors[actor]}"]`);}
