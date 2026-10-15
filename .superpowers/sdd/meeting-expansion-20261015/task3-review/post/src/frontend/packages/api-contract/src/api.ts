import {DOCX_MEDIA_TYPE,XLSX_MEDIA_TYPE} from './types';
export interface RequestOptions {method?:'GET'|'POST'|'PATCH'|'PUT'|'DELETE';body?:unknown;tenantId?:string;csrf?:string;signal?:AbortSignal}
const messages:Record<string,string>={WORKFLOW_INVALID:'승인 Workflow 구조·이름·연결을 확인해 주세요.',WORKFLOW_REFERENCE_INVALID:'binding은 선행 노드만 참조할 수 있습니다.',WORKFLOW_DISCONNECTED:'모든 노드가 입력과 최종 출력에 연결되어야 합니다.',WORKFLOW_DEPENDENCY_UNAVAILABLE:'현재 Agent·Tool 승인 또는 자료 권한을 확인해 주세요.',TOOL_APPROVAL_CONFLICT:'도구 승인 head가 변경되었습니다. 현재 상태를 새로 조회해 주세요.',WORKFLOW_APPROVAL_CONFLICT:'Workflow 승인 head가 변경되었습니다. 현재 상태를 새로 조회해 주세요.',BUILDER_PROFILE_REQUIRED:'구조화 프롬프트는 Agent Builder에서 수정해 주세요.',BUILDER_TEMPLATE_INVALID:'변수 이름·필수값·템플릿 형식과 길이를 확인해 주세요.',ASSET_LEGACY_READ_ONLY:'기존 운영 Agent는 Agent 관리에서 변경해 주세요.',ASSET_LIMIT_REACHED:'자산 또는 버전 등록 한도에 도달했습니다.',APPROVAL_REQUIRED:'운영 설정 변경은 배포 승인 요청을 통해 반영해 주세요.',DEPLOYMENT_QUEUE_FULL:'대기 요청 한도에 도달했습니다. 기존 요청을 처리한 뒤 제출해 주세요.',SUMMARY_LIMIT_EXCEEDED:'문서 요약 지원 한도를 초과했습니다. 더 짧은 문서를 선택해 주세요.',SUMMARY_NOT_READY:'완료된 요약만 내려받을 수 있습니다.',SUMMARY_OUTPUT_INVALID:'요약 결과를 검증할 수 없습니다. 새 요약을 요청해 주세요.',XLSX_INVALID:"XLSX 파일 형식 또는 셀 값을 확인해 주세요.",XLSX_UNSUPPORTED:"수식·숨김·병합·날짜/통화/백분율 서식 등은 현재 지원하지 않습니다.",XLSX_ENCRYPTED:"암호화되지 않은 XLSX를 등록해 주세요.",XLSX_ZIP_LIMIT:"XLSX 압축 구조 또는 해제 크기 한도를 초과했습니다.",XLSX_XML_LIMIT:"XLSX 문서 구조 복잡도 한도를 초과했습니다.",XLSX_TEXT_LIMIT:"XLSX 텍스트 또는 셀 수 한도를 초과했습니다.",XLSX_SHEET_LIMIT:"XLSX는 표시 가능한 시트 10개 이하로 등록해 주세요.",XLSX_EMPTY:"XLSX에 읽을 수 있는 셀 값이 없습니다.",XLSX_ACTIVE_CONTENT:"외부 참조·매크로·첨부 없는 XLSX를 등록해 주세요.",XLSX_RESOURCE_LIMIT:"XLSX 처리 한도를 초과했습니다. 파일을 줄여 주세요.",XLSX_PARSER_UNAVAILABLE:"XLSX 격리 처리 환경을 사용할 수 없습니다.",DOCX_INVALID:"DOCX 파일 형식 또는 내용을 확인해 주세요.",DOCX_UNSUPPORTED:"본문 문단과 중첩·병합 없는 표만 지원합니다. 이미지·머리말·변경 추적 등은 제거해 주세요.",DOCX_ENCRYPTED:"암호화되지 않은 DOCX를 등록해 주세요.",DOCX_ZIP_LIMIT:"DOCX 압축 파일의 항목 또는 해제 크기 한도를 초과했습니다.",DOCX_XML_LIMIT:"DOCX 문서 구조의 복잡도 한도를 초과했습니다.",DOCX_TEXT_LIMIT:"DOCX 추출 텍스트가 허용 범위를 넘었습니다.",DOCX_EMPTY:"DOCX 본문에 읽을 수 있는 텍스트가 없습니다.",DOCX_ACTIVE_CONTENT:"외부 참조·매크로·첨부·활성 콘텐츠가 없는 DOCX를 등록해 주세요.",DOCX_RESOURCE_LIMIT:"DOCX 처리 한도를 초과했습니다. 파일을 줄여 주세요.",DOCX_PARSER_UNAVAILABLE:"DOCX 격리 처리 환경을 사용할 수 없습니다.",PDF_INVALID:"PDF 파일 형식 또는 내용을 확인해 주세요.",PDF_ENCRYPTED:"암호화되지 않은 텍스트 PDF를 등록해 주세요.",PDF_PAGE_LIMIT:"PDF는 20페이지 이하로 등록해 주세요.",PDF_ACTIVE_CONTENT:"링크·첨부·자동 실행 등이 없는 PDF를 등록해 주세요.",PDF_OCR_UNSUPPORTED:"텍스트가 없는 페이지가 있습니다. 스캔 PDF는 현재 지원하지 않습니다.",PDF_STREAM_LIMIT:"PDF 내부 데이터 크기가 허용 범위를 넘었습니다.",PDF_TEXT_LIMIT:"추출된 텍스트가 허용 범위를 넘었습니다.",PDF_RESOURCE_LIMIT:"PDF 처리 한도를 초과했습니다. 파일을 줄여 주세요.",PDF_PARSER_UNAVAILABLE:"PDF 격리 처리 환경을 사용할 수 없습니다.",DOCUMENT_POLICY_BLOCKED:"개인정보 후보 또는 위험 지시문이 포함되어 있습니다. 내용을 확인한 뒤 다시 등록해 주세요.",DOCUMENT_POLICY_UNAVAILABLE:"문서 수집 검사를 수행할 수 없습니다. 잠시 후 다시 시도해 주세요.",FEEDBACK_CONFLICT:'평가가 변경되었습니다. 최신 평가를 확인한 뒤 다시 저장해 주세요.',FEEDBACK_NOT_READY:'현재 조회 가능한 완료 답변만 평가할 수 있습니다.',METADATA_CONFLICT:'다른 변경이 반영되었습니다. 최신 대화 목록에서 다시 시도해 주세요.',CONVERSATION_BUSY:'답변이 진행 중입니다. 취소하거나 완료된 뒤 삭제해 주세요.',CONVERSATION_DELETED:'삭제한 대화를 다시 사용할 수 없습니다. 새 대화를 시작해 주세요.',DOCUMENT_UNAVAILABLE:'문서를 찾을 수 없거나 현재 읽기 권한이 없습니다.',MANAGEMENT_DENIED:'현재 문서 관리 권한이 없습니다.',SOURCE_INVALID:'TXT/Markdown 또는 텍스트 PDF/DOCX/XLSX와 입력 범위를 확인해 주세요.',SOURCE_CONFLICT:'같은 접수의 파일 내용이 다릅니다. 접수 결과를 확인해 주세요.',ANSWER_EVIDENCE_INVALID:'답변 근거를 확인할 수 없습니다.',SEARCH_FAILED:'문서 검색을 처리하지 못했습니다.',LOGIN_FAILED:'로그인 정보를 확인해 주세요.',AUTH_REQUIRED:'로그인이 필요합니다.',
 REQUEST_FORBIDDEN:'현재 권한으로 수행할 수 없습니다.',TENANT_FORBIDDEN:'현재 사용할 수 없는 조직입니다.',
 CSRF_FAILED:'요청을 확인할 수 없습니다. 다시 로그인해 주세요.',REQUEST_INVALID:'입력 내용을 확인해 주세요.',
 RESOURCE_NOT_FOUND:'자료를 찾을 수 없거나 접근 권한이 변경되었습니다.',REVISION_CONFLICT:'다른 변경이 먼저 적용되었습니다. 최신 내용을 확인한 뒤 다시 변경해 주세요.',
 RATE_LIMITED:'잠시 후 다시 시도해 주세요.',STORAGE_UNAVAILABLE:'처리 결과를 확인할 수 없습니다. 다시 조회해 주세요.',
 AGENT_DISABLED:'현재 이 Agent의 운영이 중지되어 있습니다.',FEATURE_NOT_READY:'아직 준비 중인 기능입니다.',PROJECT_STOPPED:'플랫폼 운영이 중지되어 있습니다.',TENANT_STOPPED:'이 조직의 운영이 중지되어 있습니다.',QUOTA_EXCEEDED:'사용 한도에 도달했습니다.',BUDGET_NOT_READY:'조직의 사용 한도 설정이 필요합니다.',EXECUTION_NOT_READY:'실행 설정이 필요합니다.',EXECUTION_CAPACITY_EXCEEDED:'진행 중인 작업을 마친 뒤 다시 시도해 주세요.',BUDGET_LIMIT_CONFLICT:'배정 한도 또는 기존 사용·예약 금액을 확인해 주세요.',REVIEW_REQUIRED:'사용량 확인이 필요해 재개할 수 없습니다.',PAYLOAD_TOO_LARGE:'입력 크기를 줄여 주세요.',AGENT_MISMATCH:'다른 Agent를 사용하려면 새 대화를 시작해 주세요.',WORKFLOW_BLOCKED:'Workflow 승인 또는 이용 권한이 변경되었습니다.',WORKFLOW_QUEUE_LIMIT:'진행 중인 Workflow를 확인해 주세요.',WORKFLOW_BINDING_INVALID:'Workflow 노드 연결값을 확인해 주세요.',WORKFLOW_CHILD_FAILED:'연결된 Agent 또는 Tool 실행을 완료하지 못했습니다.',MEETING_CONTEXT_TOO_LARGE:'회의 메모·자료·날짜와 서버 구분 문구가 4000자 한도를 넘었습니다. 분량을 줄여 주세요.',TOKEN_LIMIT_EXCEEDED:'실행 입력의 토큰 한도를 넘었습니다. 분량을 줄여 주세요.',NETWORK:'연결을 확인할 수 없습니다. 다시 시도해 주세요.',SCOPE_CHANGED:'현재 조직의 내용을 다시 조회해 주세요.'};
export class ApiError extends Error {
 constructor(public status:number,public code:string,public requestId:string|null=null){super(messages[code]??messages.STORAGE_UNAVAILABLE);}
}
export class ApiClient {
 async request<T>(path:string,options:RequestOptions={}):Promise<T>{
  const method=options.method??'GET';const headers:Record<string,string>={};
  if(options.tenantId)headers['X-Tenant-ID']=options.tenantId;
  if(method!=='GET'){
   headers['X-Requested-With']='ai-portal';if(options.csrf)headers['X-CSRF-Token']=options.csrf;
   if(options.body!==undefined&&!(options.body instanceof FormData))headers['Content-Type']='application/json';
  }
  let response:Response;
  try{response=await fetch('/api/v1'+path,{method,headers,body:options.body===undefined?undefined:options.body instanceof FormData?options.body:JSON.stringify(options.body),
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
export async function sourceBlob(runId:string,ordinal:number,options:RequestOptions,mediaType:'text/plain'|'application/pdf'|typeof DOCX_MEDIA_TYPE|typeof XLSX_MEDIA_TYPE='text/plain'):Promise<Blob>{
 if(!/^[0-9a-f-]{36}$/.test(runId)||!Number.isInteger(ordinal)||ordinal<0||ordinal>19)throw new ApiError(422,'REQUEST_INVALID');
 let reply:Response;
 try{reply=await fetch('/api/v1/runs/'+runId+'/evidence/'+ordinal+'/source',{headers:{'X-Tenant-ID':options.tenantId??''},credentials:'same-origin',cache:'no-store',signal:options.signal});}
 catch(error){if(isAbort(error))throw error;throw new ApiError(0,'NETWORK');}
 if(!reply.ok){let code='STORAGE_UNAVAILABLE';try{code=(await reply.json()).error?.code??code;}catch{}throw new ApiError(reply.status,code);}
 if(reply.headers.get('Content-Type')?.split(';')[0].trim().toLowerCase()!==mediaType)throw new ApiError(503,'STORAGE_UNAVAILABLE');
 return reply.blob();
}
export const api=new ApiClient();
export function isAbort(error:unknown){return error instanceof DOMException&&error.name==='AbortError';}

export async function summaryBlob(runId:string,options:RequestOptions,mediaType:import('./types').SummaryMediaType,ordinal?:number):Promise<Blob>{
 if(!/^[0-9a-f-]{36}$/.test(runId)||ordinal!==undefined&&(!Number.isInteger(ordinal)||ordinal<0||ordinal>4))throw new ApiError(422,'REQUEST_INVALID');
 const path='/api/v1/document-summaries/'+runId+(ordinal===undefined?'/export?format=md':'/evidence/'+ordinal+'/source');
 let reply:Response;
 try{reply=await fetch(path,{headers:{'X-Tenant-ID':options.tenantId??''},credentials:'same-origin',cache:'no-store',signal:options.signal});}catch(error){if(isAbort(error))throw error;throw new ApiError(0,'NETWORK');}
 if(!reply.ok){let code='STORAGE_UNAVAILABLE';try{code=(await reply.json()).error?.code??code;}catch{}throw new ApiError(reply.status,code);}
 if(reply.headers.get('Content-Type')?.split(';')[0].trim().toLowerCase()!==mediaType||reply.headers.get('X-Content-Type-Options')!=='nosniff'||!reply.headers.get('Cache-Control')?.includes('no-store'))throw new ApiError(503,'STORAGE_UNAVAILABLE');
 const blob=await reply.blob();if(options.signal?.aborted)throw new DOMException('Aborted','AbortError');return blob;
}
export const summaryAPI={
 create:(body:import('./types').SummarySubmission,options:RequestOptions)=>api.request<import('./types').SummaryAdmission>('/document-summaries',{...options,method:'POST',body}),
 read:(id:string,options:RequestOptions)=>api.request<import('./types').SummaryRun>('/document-summaries/'+id,options),
 regenerate:(id:string,body:{client_send_id:string;expected_revision:number},options:RequestOptions)=>api.request<import('./types').SummaryAdmission>('/document-summaries/'+id+'/regenerate',{...options,method:'POST',body}),
 cancel:(id:string,revision:number,options:RequestOptions)=>api.request<RunCancel>('/document-summaries/'+id+'/cancel',{...options,method:'POST',body:{expected_revision:revision}})
};
type RunCancel=Pick<import('./types').Run,'run_id'|'state'|'revision'|'is_terminal'>;
