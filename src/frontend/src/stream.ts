import {ApiError} from './api';
export interface StreamEvent {event:string;tenant_id:string;run_id:string;execution_epoch:number|null;sequence:number;data:Record<string,unknown>}
const bytes=(text:string)=>new TextEncoder().encode(text).byteLength;
export async function subscribe(runId:string,tenantId:string,signal:AbortSignal,onEvent:(event:StreamEvent)=>void):Promise<void>{
 const response=await fetch('/api/v1/runs/'+encodeURIComponent(runId)+'/events',{headers:{'X-Tenant-ID':tenantId,Accept:'text/event-stream'},credentials:'same-origin',cache:'no-store',signal});
 if(!response.ok){let code='STORAGE_UNAVAILABLE';try{code=(await response.json()).error?.code??code;}catch{}throw new ApiError(response.status,code);}
 if(!response.headers.get('Content-Type')?.startsWith('text/event-stream')||!response.body)throw new ApiError(503,'STORAGE_UNAVAILABLE');
 const reader=response.body.getReader();const decoder=new TextDecoder('utf-8',{fatal:true});let buffer='',sequence=0,epoch:number|null=null;
 try{
  while(!signal.aborted){
   const chunk=await reader.read();if(chunk.done)break;
   buffer=(buffer+decoder.decode(chunk.value,{stream:true})).replace(/\r\n/g,'\n');
   let boundary:number;
   while((boundary=buffer.indexOf('\n\n'))>=0){
    const frame=buffer.slice(0,boundary);buffer=buffer.slice(boundary+2);
    if(bytes(frame)>65536)throw new ApiError(503,'SCOPE_CHANGED');
    let event='',data='';for(const line of frame.split('\n')){
     if(line.startsWith('event:'))event=line.slice(6).trim();
     if(line.startsWith('data:'))data+=(data?'\n':'')+line.slice(5).trimStart();
    }
    if(!data)continue;
    const value=JSON.parse(data) as StreamEvent;
    if(value.run_id!==runId||value.tenant_id!==tenantId||!Number.isSafeInteger(value.sequence)||value.sequence!==sequence+1)throw new ApiError(503,'SCOPE_CHANGED');
    if(!['snapshot','draft_delta','status','terminal','delivery_error'].includes(event))throw new ApiError(503,'SCOPE_CHANGED');
    if(value.execution_epoch!==null&&(!Number.isSafeInteger(value.execution_epoch)||value.execution_epoch<0))throw new ApiError(503,'SCOPE_CHANGED');
    if(epoch!==null&&value.execution_epoch!==null&&epoch!==value.execution_epoch)throw new ApiError(503,'SCOPE_CHANGED');
    if(value.execution_epoch!==null)epoch=value.execution_epoch;
    if(!value.data||typeof value.data!=='object')throw new ApiError(503,'STORAGE_UNAVAILABLE');
    if(event==='draft_delta'&&(value.data.replace!==true||typeof value.data.text!=='string'||bytes(value.data.text)>65536||(!Number.isSafeInteger(value.data.draft_sequence)||(value.data.draft_sequence as number)<1)))throw new ApiError(503,'STORAGE_UNAVAILABLE');
    sequence=value.sequence;onEvent({...value,event});
   }
   if(bytes(buffer)>65536)throw new ApiError(503,'SCOPE_CHANGED');
  }
  // A truncated frame or clean EOF is never a completion proof; caller queries stored run state.
 }finally{try{await reader.cancel();}catch{}reader.releaseLock();}
}
