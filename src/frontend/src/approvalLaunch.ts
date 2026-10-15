import type {ApprovalKind} from './types';
export type ApprovalLaunch={kind:ApprovalKind;requestId:string};
export function readApprovalLaunch(search:string):ApprovalLaunch|undefined {
 const query=new URLSearchParams(search),kind=query.get('kind'),id=query.get('request_id');
 if(query.getAll('kind').length!==1||query.getAll('request_id').length!==1)return;
 if(!['settings','dynamic','tool','workflow'].includes(kind??'')||!id||!/^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i.test(id))return;
 return {kind:kind as ApprovalKind,requestId:id};
}
