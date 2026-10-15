import {defineConfig,type Plugin} from 'vite';
import react from '@vitejs/plugin-react';
import {loadEnvironment} from './scripts/environment.mjs';
import {resolve,relative} from 'node:path';
import {mkdirSync,renameSync,writeFileSync,readFileSync,statSync} from 'node:fs';
function sitePlugin(site:'user'|'admin'|null):Plugin{
 const prefix=site==='user'?'/user/':'/manage/';
 return {name:'portal-sites',
 configureServer(server){server.middlewares.use((req,_res,next)=>{const path=req.url?.split('?')[0]??'';
  // Tests may serve the exact independent production artifacts through the owned same-origin fixture.
  if(process.env.PORTAL_TEST_BUILT==='1'&&(path==='/user'||path.startsWith('/user/')||path==='/manage'||path.startsWith('/manage/'))){
   const app=path==='/user'||path.startsWith('/user/')?'user':'admin',base=app==='user'?'/user/':'/manage/';
   const root=resolve('dist/'+app),html=req.headers.accept?.includes('text/html'),file=resolve(root,html?'index.html':path.slice(base.length));
   if(!file.startsWith(root+'/')){_res.statusCode=404;_res.end();return;}
   try{if(!statSync(file).isFile())throw new Error('missing');_res.setHeader('Content-Type',file.endsWith('.js')?'text/javascript':file.endsWith('.css')?'text/css':file.endsWith('.json')?'application/json':'text/html');_res.setHeader('Cache-Control','no-store');_res.end(readFileSync(file));}catch{_res.statusCode=404;_res.end();}return;
  }
  // Rewrite only browser HTML navigations, never API/assets/Vite modules.
  if(req.method==='GET'&&req.headers.accept?.includes('text/html')){
   if(path==='/'||path==='/home'){_res.statusCode=302;_res.setHeader('Location','/user/home');_res.end();return;}
   if(path==='/user'||path.startsWith('/user/'))req.url=(site?prefix:'/')+'apps/user-web/index.html';
   else if(path==='/manage'||path.startsWith('/manage/'))req.url=(site?prefix:'/')+'apps/admin-web/index.html';
  }next();});},
 generateBundle(_options,bundle){if(!site)return;const modules=[...new Set(Object.values(bundle).flatMap(item=>item.type==='chunk'?Object.entries(item.modules).filter(([,value])=>value.renderedLength>0).map(([id])=>id):[]))].filter(id=>id.startsWith(resolve('.'))&&!id.includes('/node_modules/')).map(id=>relative(resolve('.'),id)).sort();
  this.emitFile({type:'asset',fileName:'portal-build.json',source:JSON.stringify({site,base:prefix,modules},null,2)+'\n'});},
 closeBundle(){if(!site)return;const out=resolve('dist/'+site);mkdirSync(out,{recursive:true});renameSync(resolve(out,'apps/'+site+'-web/index.html'),resolve(out,'index.html'));const path=resolve(out,'.vite/manifest.json');const manifest=JSON.parse(readFileSync(path,'utf8'));for(const entry of Object.values(manifest) as {isEntry?:boolean;file:string}[])if(entry.isEntry&&entry.file.endsWith('index.html'))entry.file='index.html';writeFileSync(path,JSON.stringify(manifest,null,2)+'\n');}
 };
}
export default defineConfig(({mode,command})=>{const environment=loadEnvironment();if(command==='serve'&&environment.environment!=='local')throw new Error('USE_DEPLOYMENT_RUNTIME_FOR_NONLOCAL');const site=mode==='user'||mode==='admin'?mode:null;
 return {plugins:[react(),sitePlugin(site)],base:site==='user'?'/user/':site==='admin'?'/manage/':'/',define:{'import.meta.env.PORTAL_SITE':JSON.stringify(site??'combined'),'import.meta.env.PORTAL_USER_URL':JSON.stringify(environment.user.origin!+environment.user.entry),'import.meta.env.PORTAL_ADMIN_URL':JSON.stringify(environment.admin.origin!+environment.admin.entry)},
 build:{outDir:site?'dist/'+site:'dist/combined',manifest:true,rollupOptions:site?{input:resolve('apps/'+site+'-web/index.html')}:undefined},
 server:{host:'127.0.0.1',port:site==='admin'?environment.admin.port:environment.user.port,strictPort:true,proxy:{'/api':{target:environment.api.origin!,changeOrigin:false}}}};
});
