import {readFileSync} from 'node:fs';
import {fileURLToPath} from 'node:url';
export const environments=['local','dev','tb','prd'];
function require(condition){if(!condition)throw new Error('PORTAL_CONFIGURATION_INVALID');}
export function validateEnvironment(data,expected,ready=true){
 require(data&&typeof data==='object'&&!Array.isArray(data)&&Object.keys(data).sort().join(',')===['version','environment','configured','bind_host','session_mode','user','admin','api'].sort().join(','));
 require(data.version===1&&data.environment===expected&&environments.includes(expected)&&typeof data.configured==='boolean'&&data.bind_host==='127.0.0.1');
 require(data.session_mode===(expected==='local'?'shared-host-development':'site-sessions-required'));
 const ports=[];
 for(const [key,entry] of [['user','/user/home'],['admin','/manage/admin'],['api','/api/v1']]){
  const item=data[key];require(item&&Object.keys(item).sort().join(',')==='entry,origin,port'&&item.entry===entry&&Number.isInteger(item.port)&&item.port>=1&&item.port<=65535);ports.push(item.port);
  if(item.origin===null){require(!data.configured&&expected!=='local');continue;}
  require(typeof item.origin==='string');let url;try{url=new URL(item.origin);}catch{throw new Error('PORTAL_CONFIGURATION_INVALID');}
  require(url.protocol===(expected==='local'?'http:':'https:')&&url.hostname&&!url.username&&!url.password&&!url.search&&!url.hash&&url.pathname==='/'&&url.origin===item.origin&&Number(url.port||(url.protocol==='https:'?443:80))===item.port);
  if(expected==='local')require(url.hostname==='127.0.0.1');
 }
 require(new Set(ports).size===3&&(expected!=='local'||data.configured));
 if(ready&&!data.configured)throw new Error('PORTAL_ENVIRONMENT_NOT_CONFIGURED');return data;
}
export function loadEnvironment(environment=process.env.AI_ENVIRONMENT??'local',ready=true){
 if(!environments.includes(environment))throw new Error('PORTAL_ENVIRONMENT_UNKNOWN');let data;
 try{data=JSON.parse(readFileSync(fileURLToPath(new URL('../../../config/environments/'+environment+'.json',import.meta.url)),'utf8'));}catch{throw new Error('PORTAL_CONFIGURATION_INVALID');}
 return validateEnvironment(data,environment,ready);
}
