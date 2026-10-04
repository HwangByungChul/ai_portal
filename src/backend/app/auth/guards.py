import hmac
from app.errors import AppError


def check_transport(request, settings):
    if settings.profile == 'local':
        if request.url.hostname != '127.0.0.1' or not request.client or request.client.host != '127.0.0.1':
            raise AppError('REQUEST_FORBIDDEN', 403)
    elif request.url.scheme != 'https':
        raise AppError('REQUEST_FORBIDDEN', 403)


def check_write(request, settings, *, json_body=False):
    check_transport(request, settings)
    if (request.headers.getlist('origin') != [settings.origin]
            or request.headers.getlist('x-requested-with') != ['ai-portal']):
        raise AppError('REQUEST_FORBIDDEN', 403)
    if json_body:
        types = request.headers.getlist('content-type')
        if len(types) != 1 or types[0].split(';')[0].strip().lower() != 'application/json':
            raise AppError('REQUEST_INVALID', 400)


def cookie_token(request, settings):
    configured = settings.session_cookie_name
    other = '__Host-ai_session' if configured == 'ai_session_dev' else 'ai_session_dev'
    values = []
    for header in request.headers.getlist('cookie'):
        for part in header.split(';'):
            key, separator, value = part.strip().partition('=')
            if key == other:
                raise AppError('AUTH_REQUIRED', 401)
            if key == configured and separator:
                values.append(value)
    if len(values) > 1:
        raise AppError('AUTH_REQUIRED', 401)
    return values[0] if values else None


def check_csrf(request, secret):
    values = request.headers.getlist('x-csrf-token')
    if (len(values) != 1 or len(values[0]) > 128
            or not hmac.compare_digest(values[0].encode('utf-8'), secret.encode('ascii'))):
        raise AppError('CSRF_FAILED', 403)
