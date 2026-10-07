from datetime import datetime, timezone
from fastapi.responses import JSONResponse

MESSAGES = {
    'XLSX_INVALID': 'XLSX 파일 형식 또는 셀 값을 확인해 주세요.',
    'XLSX_UNSUPPORTED': '수식·숨김·병합·날짜/통화/백분율 서식 등은 현재 지원하지 않습니다.',
    'XLSX_ENCRYPTED': '암호화되지 않은 XLSX를 등록해 주세요.',
    'XLSX_ZIP_LIMIT': 'XLSX 압축 구조 또는 해제 크기 한도를 초과했습니다.',
    'XLSX_XML_LIMIT': 'XLSX 문서 구조 복잡도 한도를 초과했습니다.',
    'XLSX_TEXT_LIMIT': 'XLSX 텍스트 또는 셀 수 한도를 초과했습니다.',
    'XLSX_SHEET_LIMIT': 'XLSX는 표시 가능한 시트 10개 이하로 등록해 주세요.',
    'XLSX_EMPTY': 'XLSX에 읽을 수 있는 셀 값이 없습니다.',
    'XLSX_ACTIVE_CONTENT': '외부 참조·매크로·첨부 없는 XLSX를 등록해 주세요.',
    'XLSX_RESOURCE_LIMIT': 'XLSX 처리 한도를 초과했습니다. 파일을 줄여 주세요.',
    'XLSX_PARSER_UNAVAILABLE': 'XLSX 격리 처리 환경을 사용할 수 없습니다.',

    "DOCX_INVALID": "DOCX 파일 형식 또는 내용을 확인해 주세요.",
    "DOCX_UNSUPPORTED": "본문 문단과 중첩·병합 없는 표만 지원합니다. 이미지·머리말·변경 추적 등은 제거해 주세요.",
    "DOCX_ENCRYPTED": "암호화되지 않은 DOCX를 등록해 주세요.",
    "DOCX_ZIP_LIMIT": "DOCX 압축 파일의 항목 또는 해제 크기 한도를 초과했습니다.",
    "DOCX_XML_LIMIT": "DOCX 문서 구조의 복잡도 한도를 초과했습니다.",
    "DOCX_TEXT_LIMIT": "DOCX 추출 텍스트가 허용 범위를 넘었습니다.",
    "DOCX_EMPTY": "DOCX 본문에 읽을 수 있는 텍스트가 없습니다.",
    "DOCX_ACTIVE_CONTENT": "외부 참조·매크로·첨부·활성 콘텐츠가 없는 DOCX를 등록해 주세요.",
    "DOCX_RESOURCE_LIMIT": "DOCX 처리 한도를 초과했습니다. 파일을 줄여 주세요.",
    "DOCX_PARSER_UNAVAILABLE": "DOCX 격리 처리 환경을 사용할 수 없습니다.",

    "PDF_INVALID": "PDF 파일 형식 또는 내용을 확인해 주세요.",
    "PDF_ENCRYPTED": "암호화되지 않은 텍스트 PDF를 등록해 주세요.",
    "PDF_PAGE_LIMIT": "PDF는 20페이지 이하로 등록해 주세요.",
    "PDF_ACTIVE_CONTENT": "링크·첨부·자동 실행 등이 없는 PDF를 등록해 주세요.",
    "PDF_OCR_UNSUPPORTED": "텍스트가 없는 페이지가 있습니다. 스캔 PDF는 현재 지원하지 않습니다.",
    "PDF_STREAM_LIMIT": "PDF 내부 데이터 크기가 허용 범위를 넘었습니다.",
    "PDF_TEXT_LIMIT": "추출된 텍스트가 허용 범위를 넘었습니다.",
    "PDF_RESOURCE_LIMIT": "PDF 처리 한도를 초과했습니다. 파일을 줄여 주세요.",
    "PDF_PARSER_UNAVAILABLE": "PDF 격리 처리 환경을 사용할 수 없습니다.",

    "DOCUMENT_POLICY_BLOCKED": "개인정보 후보 또는 위험 지시문이 포함되어 있습니다. 내용을 확인한 뒤 다시 등록해 주세요.",
    "DOCUMENT_POLICY_UNAVAILABLE": "문서 수집 검사를 수행할 수 없습니다. 잠시 후 다시 시도해 주세요.",
    "FEEDBACK_CONFLICT":"평가가 변경되었습니다. 최신 평가를 확인한 뒤 다시 저장해 주세요.",
    "FEEDBACK_NOT_READY":"현재 조회 가능한 완료 답변만 평가할 수 있습니다.",
    "METADATA_CONFLICT":"다른 변경이 반영되었습니다. 최신 대화 목록에서 다시 시도해 주세요.",
    "CONVERSATION_BUSY":"답변이 진행 중입니다. 취소하거나 완료된 뒤 삭제해 주세요.",
    "CONVERSATION_DELETED":"삭제한 대화를 다시 사용할 수 없습니다. 새 대화를 시작해 주세요.",
    'SOURCE_INVALID': '지원하는 문서 형식과 크기를 확인해 주세요.',
    'SOURCE_CONFLICT': '같은 등록 번호의 파일을 확인해 주세요.',
    'DOCUMENT_UNAVAILABLE': '문서를 조회할 수 없습니다.',
    'MANAGEMENT_DENIED': '관리 권한을 확인해 주세요.',
    'EXECUTION_FENCED': '작업 권한이 변경되었습니다.',
    'AGENT_DISABLED': 'Agent가 중지되어 있습니다.',
    'INDEX_NEEDS_REVIEW': '처리 결과를 확인한 뒤 다시 진행해 주세요.',
    'PROJECT_STOPPED': 'AI 실행이 중지되어 있습니다. 준비 상태를 확인해 주세요.',
    'STREAM_LIMIT_REACHED': '열려 있는 응답 창을 확인한 뒤 다시 시도해 주세요.',
    'STREAM_ACCESS_UNAVAILABLE': '응답을 조회할 권한과 연결 상태를 확인해 주세요.',
    'SEND_ID_CONFLICT': '같은 전송 번호의 입력을 확인해 주세요.',
    'CONVERSATION_AGENT_MISMATCH': '대화에 연결된 Agent를 확인해 주세요.',
    'AGENT_STOPPED': '선택한 Agent가 중지되어 있습니다.',
    'FEATURE_NOT_READY': '아직 준비되지 않은 기능입니다.',
    'PLATFORM_STOPPED': 'AI 서비스가 중지되어 있습니다.',
    'QUOTA_EXCEEDED': '사용 한도를 확인해 주세요.',
    'EXECUTION_CAPACITY_EXCEEDED': '진행 중인 질문을 확인한 뒤 다시 시도해 주세요.',
    'TOKEN_LIMIT_EXCEEDED': '질문과 지시문의 길이를 줄여 주세요.',
    'SERVICE_UNAVAILABLE': '서비스 준비 상태를 확인해 주세요.',
    'PAYLOAD_TOO_LARGE': '요청 크기를 줄여 주세요.',
    'BUDGET_LIMIT_CONFLICT': '현재 배정과 사용량을 확인해 주세요.',
    'REVIEW_REQUIRED': '미확인 사용량을 확인한 뒤 다시 시도해 주세요.',
    'RESOURCE_NOT_FOUND': '대상을 찾을 수 없습니다.',
    'REVISION_CONFLICT': '변경된 내용을 다시 조회해 주세요.',
    'LOGIN_FAILED': '로그인 정보를 확인해 주세요.',
    'AUTH_REQUIRED': '로그인이 필요합니다.',
    'REQUEST_FORBIDDEN': '허용되지 않은 요청입니다.',
    'CSRF_FAILED': '요청 확인에 실패했습니다.',
    'REQUEST_INVALID': '입력 형식을 확인해 주세요.',
    'RATE_LIMITED': '잠시 후 다시 시도해 주세요.',
    'STORAGE_UNAVAILABLE': '저장소 연결을 확인한 뒤 다시 시도해 주세요.',
    'TENANT_FORBIDDEN': '사용 가능한 조직이 아닙니다.',
}


class AppError(Exception):
    def __init__(self, code, status, retry_after=None):
        super().__init__(code)
        self.code, self.status, self.retry_after = code, status, retry_after


def response(request, data=None, error=None, field_paths=None, *, status_code=200):
    headers = {'Cache-Control': 'no-store', 'X-Request-ID': request.state.request_id}
    meta = {'request_id': request.state.request_id, 'tenant_id': getattr(request.state,'tenant_id',None),
            'server_time': datetime.now(timezone.utc).isoformat()}
    if error:
        if error.status == 401:
            headers['WWW-Authenticate'] = 'Session realm="ai-portal"'
        if error.retry_after:
            headers['Retry-After'] = str(error.retry_after)
        return JSONResponse({'error': {'code': error.code, 'message': MESSAGES[error.code],
            'field_paths': field_paths or [], 'retryable': error.status in (429,503)}, 'meta': meta},
            status_code=error.status, headers=headers)
    return JSONResponse({'data': data, 'meta': meta}, headers=headers,status_code=status_code)
