interface RequestOptions {method?:'GET'|'POST'|'PATCH'|'PUT';body?:unknown;tenantId?:string;csrf?:string;signal?:AbortSignal}
const messages:Record<string,string>={LOGIN_FAILED:'로그인 정보를 확인해 주세요.',AUTH_REQUIRED:'로그인이 필요합니다.',
 REQUEST_FORBIDDEN:'현재 권한으로 수행할 수 없습니다.',TENANT_FORBIDDEN:'현재 사용할 수 없는 조직입니다.',
 CSRF_FAILED:'요청을 확인할 수 없습니다. 다시 로그인해 주세요.',REQUEST_INVALID:'입력 내용을 확인해 주세요.',
 RESOURCE_NOT_FOUND:'자료를 찾을 수 없거나 접근 권한이 변경되었습니다.',REVISION_CONFLICT:'다른 변경이 먼저 적용되었습니다. 최신 내용을 확인한 뒤 다시 변경해 주세요.',
 RATE_LIMITED:'잠시 후 다시 시도해 주세요.',STORAGE_UNAVAILABLE:'처리 결과를 확인할 수 없습니다. 다시 조회해 주세요.',
 NETWORK:'연결을 확인할 수 없습니다. 다시 시도해 주세요.',SCOPE_CHANGED:'현재 조직의 내용을 다시 조회해 주세요.'};
export class ApiError extends Error {
 constructor(public status:number,public code:string,public requestId:string|null=null){super(messages[code]??messages.STORAGE_UNAVAILABLE);}
}
export class ApiClient {
 async request<T>(path:string,options:RequestOptions={}):Promise<T>{
  const method=options.method??'GET';const headers:Record<string,string>={};
  if(options.tenantId)headers['X-Tenant-ID']=options.tenantId;
  if(method!=='GET'){
   headers['X-Requested-With']='ai-portal';if(options.csrf)headers['X-CSRF-Token']=options.csrf;
   if(options.body!==undefined)headers['Content-Type']='application/json';
  }
  let response:Response;
  try{response=await fetch('/api/v1'+path,{method,headers,body:options.body===undefined?undefined:JSON.stringify(options.body),
    credentials:'same-origin',cache:'no-store',signal:options.signal});}
  catch(error){if(error instanceof DOMException&&error.name==='AbortError')throw error;throw new ApiError(0,'NETWORK');}
  let value:{data?:T;error?:{code:string};meta?:{tenant_id:string|null;request_id:string}};
  try{value=await response.json();}catch{throw new ApiError(response.status,'STORAGE_UNAVAILABLE');}
  const id=value.meta?.request_id;const safeId=id&&/^[0-9a-f-]{36}$/.test(id)?id:null;
  if(!response.ok)throw new ApiError(response.status,value.error?.code??'STORAGE_UNAVAILABLE',safeId);
  if(options.tenantId&&value.meta?.tenant_id!==options.tenantId)throw new ApiError(503,'SCOPE_CHANGED',safeId);
  if(value.data===undefined)throw new ApiError(503,'STORAGE_UNAVAILABLE',safeId);
  return value.data;
 }
}
export const api=new ApiClient();
export function isAbort(error:unknown){return error instanceof DOMException&&error.name==='AbortError';}
