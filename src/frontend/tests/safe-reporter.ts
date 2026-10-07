import type { Reporter, TestCase, TestResult, FullResult, TestStep } from '@playwright/test/reporter';
import { mkdirSync,writeFileSync,readFileSync } from 'node:fs';
import { resolve } from 'node:path';
export function redact(value:string,secrets:string[]):string {
 return secrets.filter(x=>x.length>0).sort((a,b)=>b.length-a.length).reduce((s,x)=>s.split(x).join('[REDACTED]'),value);
}
export default class SafeReporter implements Reporter {
 rows: {test_id:string;status:string;duration_ms:number}[]=[];
 steps: {test_id:string;step_id:string;status:string;duration_ms:number}[]=[];
 onStepEnd(test:TestCase,_result:TestResult,step:TestStep){
  if(/^P270_STEP_[0-9]{2}_[A-Za-z0-9_]+$/.test(step.title))this.steps.push({test_id:this.safeId(test.title),step_id:step.title,status:step.error?'failed':'passed',duration_ms:step.duration});
 }
 runnerErrors=0;
 onError(){this.runnerErrors+=1;}
 private safeId(title:string){return /^(A05|B05|C05|P270|D04|D05|D06|D07|DX6|XX6)_[0-9]{2}_[A-Za-z0-9_]+$/.test(title)?title:'A05_unregistered_test';}
 onTestEnd(test:TestCase,result:TestResult){
  // Only sanitized diagnostics stay private; public evidence never includes them.
  const dir=resolve('.runtime');mkdirSync(dir,{recursive:true,mode:0o700});
  let secrets:string[]=[];
  try{const config=JSON.parse(readFileSync(resolve('../backend/.runtime/A05-fixture.json'),'utf8'));
   secrets=Object.values(JSON.parse(readFileSync(config.secret_path,'utf8')).passwords);
  }catch{}
  if(result.status!=='passed'){
   const text=redact(result.errors.map(e=>e.message??'').join('\\n'),secrets)
    .replace(/[A-Za-z0-9_-]{43}(?![A-Za-z0-9_-])/g,'[REDACTED]');
   writeFileSync(resolve(dir,this.safeId(test.title)+'-private.txt'),text,{mode:0o600});
  }
  this.rows.push({test_id:this.safeId(test.title),status:result.status,duration_ms:result.duration});
 }
 onEnd(result:FullResult){
  const dir=resolve('.runtime');mkdirSync(dir,{recursive:true,mode:0o700});
  writeFileSync(resolve(dir,'A05-browser-results.json'),JSON.stringify({status:result.status,duration_ms:result.duration,runner_errors:this.runnerErrors,tests:this.rows,steps:this.steps},null,2)+'\n',{mode:0o600});
  process.stdout.write(JSON.stringify({status:result.status,passed:this.rows.filter(x=>x.status==='passed').length,
   failed:this.rows.filter(x=>x.status!=='passed').length})+'\n');
 }
 printsToStdio(){return true;}
}
