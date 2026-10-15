import { api,ApiError,isAbort } from './api';
import type { Scope,Tenant,User } from './types';
interface State {phase:'boot'|'login'|'ready'|'error'|'logout_pending';user:User|null;tenants:Tenant[];tenantId:string|null;generation:number;notice:string|null;failure:string|null}
export class SessionStore {
 private state:State={phase:'boot',user:null,tenants:[],tenantId:null,generation:0,notice:null,failure:null};
 private listeners=new Set<()=>void>();private controller=new AbortController();private channel:BroadcastChannel|null=null;
 getSnapshot=()=>this.state;
 subscribe=(listener:()=>void)=>{this.listeners.add(listener);return()=>{this.listeners.delete(listener);};};
 private set(next:Partial<State>){this.state={...this.state,...next};this.listeners.forEach(f=>f());}
 private advance(){this.controller.abort();this.controller=new AbortController();this.set({generation:this.state.generation+1});}
 scope():Scope{return {generation:this.state.generation,tenantId:this.state.tenantId,userId:this.state.user?.user_id??null,signal:this.controller.signal};}
 current(scope:Scope){return !scope.signal.aborted&&scope.generation===this.state.generation&&scope.tenantId===this.state.tenantId&&scope.userId===(this.state.user?.user_id??null);}
 switchTenant(id:string){if(this.state.phase!=='ready'||!this.state.tenants.some(t=>t.tenant_id===id))return;this.advance();this.set({tenantId:id,notice:null});}
 signedOut(notice:string|null=null){this.advance();this.set({phase:'login',user:null,tenants:[],tenantId:null,notice,failure:null});}
 async restore(notice:string|null=null){
  if(this.state.phase==='logout_pending')return;
  const previousTenant=this.state.tenantId;
  this.advance();const generation=this.state.generation;const signal=this.controller.signal;
  this.set({phase:'boot',user:null,tenants:[],tenantId:null,failure:null});
  try{
   const user=await api.request<User>('/auth/me',{signal});
   const result=await api.request<{items:Tenant[]}>('/me/tenants',{signal});
   if(signal.aborted||generation!==this.state.generation)return;
   const selected=result.items.find(t=>t.tenant_id===previousTenant)?.tenant_id??(result.items.length===1?result.items[0].tenant_id:null);
   this.set({phase:'ready',user,tenants:result.items,tenantId:selected,notice,failure:null});
  }catch(error){
   if(isAbort(error)||signal.aborted||generation!==this.state.generation)return;
   if(error instanceof ApiError&&error.status===401)this.signedOut(notice);
   else this.set({phase:'error',failure:error instanceof ApiError?error.message:'연결을 확인할 수 없습니다.',user:null,tenants:[],tenantId:null});
  }
 }
 async logout(){
  const csrf=this.state.user?.csrf_token;
  if(!csrf)return;
  // Abort all content requests and hide their data before waiting for the server.
  this.advance();this.set({phase:'logout_pending',tenants:[],tenantId:null,notice:null,failure:null});
  try{
   const result=await api.request<{logout_confirmed:boolean}>('/auth/logout',{method:'POST',csrf});
   if(!result.logout_confirmed)throw new ApiError(503,'STORAGE_UNAVAILABLE');
   this.signedOut('로그아웃되었습니다.');this.channel?.postMessage({type:'signed-out'});
  }catch{this.set({failure:'로그아웃 확인이 필요합니다. 연결을 확인한 뒤 다시 시도해 주세요.'});}
 }
 connectTabs(){
  if(typeof BroadcastChannel==='undefined')return()=>{};
  const channel=new BroadcastChannel('ai-portal-session');this.channel=channel;
  channel.onmessage=(event)=>{if(event.data?.type==='signed-out')this.signedOut('다른 탭에서 로그아웃되었습니다.');};
  return()=>{channel.close();if(this.channel===channel)this.channel=null;};
 }
}
export const session=new SessionStore();
