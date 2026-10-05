from datetime import datetime, timezone
from fastapi.responses import JSONResponse

MESSAGES = {
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


def response(request, data=None, error=None, field_paths=None):
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
    return JSONResponse({'data': data, 'meta': meta}, headers=headers)
