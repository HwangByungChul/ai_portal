import {readFileSync,readdirSync,statSync} from 'node:fs';
import {resolve} from 'node:path';
import assert from 'node:assert/strict';
const adminModules=['AdminHomePage','ApprovalsPage','AgentSettingsPage','AgentAccessEditor','AssetsPage','BuilderPreview','BuilderProfileEditor','BuilderTrial','BuilderEvidence','BuilderEvaluation','BuilderEvidenceShare','SharedEvidenceReview','AssetDeployments','AssetDeploymentRequest','AssetPublicationHistory','MembersPage','PlatformPage','FeedbackSummaryPage','DocumentSharingPanel'];
const reports={};
function texts(path){return readdirSync(path).flatMap(name=>{const p=resolve(path,name);return statSync(p).isDirectory()?texts(p):p.endsWith('.js')?[readFileSync(p,'utf8')]:[];});}
const sites=process.argv.slice(2);if(!sites.length)sites.push('user','admin');assert.ok(sites.every(site=>['user','admin'].includes(site)));
for(const site of sites){
 const root=resolve('dist',site),report=JSON.parse(readFileSync(resolve(root,'portal-build.json'),'utf8'));
 assert.equal(report.site,site);assert.ok(readFileSync(resolve(root,'index.html'),'utf8').includes(site==='user'?'/user/assets/':'/manage/assets/'));
 assert.ok(report.modules.includes('apps/'+site+'-web/src/App.tsx'));assert.ok(!report.modules.includes('src/App.tsx'));
 assert.ok(report.modules.includes('packages/api-contract/src/session.ts'));assert.ok(report.modules.includes('packages/ui/src/PortalShell.tsx'));
 if(site==='user'){
  for(const name of adminModules)assert.ok(!report.modules.some(id=>id.endsWith('/'+name+'.tsx')),name+' leaked to user bundle');
  const source=texts(root).join('\n');
  for(const token of ['/admin/agent-deployments','/admin/assets','/admin/builder/','/admin/budget','/admin/jobs/','버전 공유 관리','조직 제한 저장'])assert.ok(!source.includes(token),'management implementation leaked to user bundle');
 }else{for(const name of adminModules)assert.ok(report.modules.some(id=>id.endsWith('/'+name+'.tsx')),name+' missing from admin bundle');assert.ok(!report.modules.some(id=>id.endsWith('/ChatPage.tsx')||id.endsWith('/HomePage.tsx')));}
 reports[site]={modules:report.modules.length,boundary_verified:true};
}
console.log(JSON.stringify({status:'passed',sites:reports}));
