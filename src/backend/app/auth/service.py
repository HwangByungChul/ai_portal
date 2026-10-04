import asyncio
import hashlib
from app.auth.crypto import new_secret, normalize_login, token_digest, verify_password, window_digest
from app.auth.repository import AuthRepository
from app.errors import AppError
from app.types import AuthContext, LoginResult


class AuthService:
    def __init__(self, pool, settings):
        self.pool, self.settings = pool, settings
        self.repository = AuthRepository()

    async def login(self, login_id, password, old_token, client_ip):
        secret = self.settings.login_hmac_secret.get_secret_value()
        ip_digest = window_digest(secret, 'login_ip', 'ip', client_ip)
        # Commit the IP attempt even if later password checking fails or is cancelled.
        async with self.pool.connection() as conn:
            async with conn.transaction():
                ip = await self.repository.window(conn, 'login_ip', 'ip', ip_digest, 30, True)
        if not ip['allowed']:
            raise AppError('RATE_LIMITED', 429, ip['retry_after'])
        try:
            normalized = normalize_login(login_id)
            valid_format = True
        except ValueError:
            normalized = 'invalid:' + hashlib.sha256(login_id.strip().lower().encode('utf-8', errors='surrogatepass')).hexdigest()
            valid_format = False
        digest = window_digest(secret, 'login_input', 'login', normalized)
        credential = None
        async with self.pool.connection() as conn:
            async with conn.transaction():
                window = await self.repository.window(conn, 'login_input', 'login', digest, 5, False)
                if window['allowed']:
                    credential = await self.repository.credential(conn, normalized) if valid_format else None
                    valid = await asyncio.to_thread(verify_password,
                        credential['password_hash'] if credential else None, password)
                    if valid and credential['active']:
                        await self.repository.reset_input(conn, digest)
                    else:
                        credential = None
                        await self.repository.window(conn, 'login_input', 'login', digest, 5, True)
        # Errors occur after commit so failure counters are not rolled back.
        if not window['allowed']:
            raise AppError('RATE_LIMITED', 429, window['retry_after'])
        if credential is None:
            raise AppError('LOGIN_FAILED', 401)
        token, csrf = new_secret(), new_secret()
        try:
            old_digest = token_digest(old_token) if old_token else None
        except ValueError:
            old_digest = None
        async with self.pool.connection() as conn:
            async with conn.transaction():
                issued = await self.repository.create(conn, credential['user_id'], credential['auth_revision'],
                                                      token_digest(token), csrf, old_digest)
        if not issued:
            raise AppError('LOGIN_FAILED', 401)
        return LoginResult(token, csrf, credential['user_id'], credential['display_name'], issued['expires_at'])

    async def validate(self, token):
        try:
            digest = token_digest(token or '')
        except ValueError:
            raise AppError('AUTH_REQUIRED', 401) from None
        async with self.pool.connection() as conn:
            session = await self.repository.validate(conn, digest)
        if not session:
            raise AppError('AUTH_REQUIRED', 401)
        return session

    async def logout(self, token):
        try:
            digest = token_digest(token or '')
        except ValueError:
            return True
        async with self.pool.connection() as conn:
            async with conn.transaction():
                confirmed = await self.repository.revoke(conn, digest)
        return confirmed

    async def resolve_tenant(self, token, tenant):
        session = await self.validate(token)
        async with self.pool.connection() as conn:
            member = await self.repository.membership(conn, session.session_id, tenant)
        if not member:
            raise AppError('TENANT_FORBIDDEN', 403)
        return AuthContext(session.session_id, session.user_id, tenant, member['effective_role'], session.csrf_secret)

    async def session_data(self, session):
        async with self.pool.connection() as conn:
            current = await self.repository.capabilities(conn, session.session_id,
                                                        self.settings.budget_period, self.settings.mode)
        if not current:
            raise AppError('AUTH_REQUIRED', 401)
        data = {'user_id': str(session.user_id), 'display_name': session.display_name,
                'session_expires_at': session.expires_at.isoformat(), 'csrf_token': session.csrf_secret,
                'capabilities': {'can_view_platform_usage': current['can_view_platform_usage'],
                                 'can_change_platform_availability': current['can_change_platform_availability']}}
        if current['can_change_platform_availability']:
            data['platform_availability'] = {'enabled': current['availability_enabled'],
                                            'revision': current['availability_revision']}
        return data
