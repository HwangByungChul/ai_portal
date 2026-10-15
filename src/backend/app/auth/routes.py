from fastapi import APIRouter, Request
from pydantic import BaseModel, ConfigDict, Field, SecretStr
from app.auth.guards import check_csrf, check_transport, check_write, cookie_token
from app.errors import AppError, response

router = APIRouter(prefix='/api/v1/auth')


class LoginRequest(BaseModel):
    model_config = ConfigDict(extra='forbid')
    login_id: str = Field(min_length=1, max_length=64)
    password: SecretStr = Field(min_length=1, max_length=128)


@router.post('/login')
async def login(request: Request, body: LoginRequest):
    settings, service = request.app.state.settings, request.app.state.auth
    check_write(request, settings, json_body=True)
    token = cookie_token(request, settings)
    result = await service.login(body.login_id, body.password.get_secret_value(), token, request.client.host)
    data = {'user_id': str(result.user_id), 'display_name': result.display_name,
            'session_expires_at': result.expires_at.isoformat(), 'csrf_token': result.csrf_token}
    reply = response(request, data)
    reply.set_cookie(settings.session_cookie_name, result.session_token,
                     httponly=True, secure=settings.profile=='https', samesite='lax', path='/')
    return reply


@router.get('/me')
async def me(request: Request):
    settings, service = request.app.state.settings, request.app.state.auth
    check_transport(request, settings)
    session = await service.validate(cookie_token(request, settings))
    return response(request, await service.session_data(session))


@router.post('/logout')
async def logout(request: Request):
    settings, service = request.app.state.settings, request.app.state.auth
    check_write(request, settings)
    try:
        token = cookie_token(request, settings)
    except AppError as error:
        if error.status != 401: raise
        token = None
    try:
        session = await service.validate(token)
    except AppError as error:
        if error.status != 401: raise
    else:
        check_csrf(request, session.csrf_secret)
    confirmed = await service.logout(token)
    reply = response(request, {'logout_confirmed': confirmed})
    reply.delete_cookie(settings.session_cookie_name, path='/', secure=settings.profile=='https', httponly=True, samesite='lax')
    return reply


@router.get('/sso/start')
async def sso_start(request: Request, provider: str = 'entra-id', redirect_uri: str = 'http://127.0.0.1:5173/auth/callback'):
    from app.auth.sso import GLOBAL_SSO_SERVICE
    return response(request, GLOBAL_SSO_SERVICE.get_auth_url(provider, redirect_uri))


@router.get('/sso/callback')
async def sso_callback(request: Request, provider: str, code: str, state: str):
    from app.auth.sso import GLOBAL_SSO_SERVICE
    verified = GLOBAL_SSO_SERVICE.verify_callback(provider, code, state)
    return response(request, verified)

