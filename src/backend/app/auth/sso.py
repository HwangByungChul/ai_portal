"""OIDC / Microsoft Entra ID SSO Integration & State Verification Module."""
import secrets
import time
from typing import Any
from urllib.parse import urlencode
from app.errors import AppError

SUPPORTED_PROVIDERS = {
    "entra-id": {
        "name": "Microsoft Entra ID",
        "auth_endpoint": "https://login.microsoftonline.com/common/oauth2/v2.0/authorize",
        "client_id": "mock-entra-client-id",
        "scopes": ["openid", "profile", "email"],
    },
    "mock-idp": {
        "name": "Mock Corporate IdP",
        "auth_endpoint": "http://127.0.0.1:8000/api/v1/auth/sso/mock-auth",
        "client_id": "mock-corp-client",
        "scopes": ["openid", "profile"],
    },
}

class SsoStateStore:
    def __init__(self, ttl_seconds: int = 600):
        self.ttl_seconds = ttl_seconds
        self._states: dict[str, dict[str, Any]] = {}

    def issue(self, provider: str, redirect_uri: str) -> str:
        state = secrets.token_urlsafe(32)
        now = time.time()
        # Clean expired
        self._states = {k: v for k, v in self._states.items() if v["expires_at"] > now}
        self._states[state] = {
            "provider": provider,
            "redirect_uri": redirect_uri,
            "expires_at": now + self.ttl_seconds,
            "used": False,
        }
        return state

    def consume(self, state: str, provider: str) -> dict[str, Any]:
        now = time.time()
        record = self._states.get(state)
        if not record:
            raise AppError("SSO_INVALID_STATE", 400)
        if record["expires_at"] < now:
            self._states.pop(state, None)
            raise AppError("SSO_STATE_EXPIRED", 400)
        if record["used"]:
            self._states.pop(state, None)
            raise AppError("SSO_STATE_REPLAYED", 400)
        if record["provider"] != provider:
            raise AppError("SSO_PROVIDER_MISMATCH", 400)
        
        record["used"] = True
        self._states.pop(state, None)
        return record

GLOBAL_SSO_STORE = SsoStateStore()

class SsoService:
    def __init__(self, store: SsoStateStore | None = None):
        self.store = store or GLOBAL_SSO_STORE

    def get_auth_url(self, provider: str, redirect_uri: str) -> dict[str, str]:
        if provider not in SUPPORTED_PROVIDERS:
            raise AppError("SSO_PROVIDER_UNSUPPORTED", 400)
        
        cfg = SUPPORTED_PROVIDERS[provider]
        state = self.store.issue(provider, redirect_uri)
        params = {
            "client_id": cfg["client_id"],
            "response_type": "code",
            "redirect_uri": redirect_uri,
            "response_mode": "query",
            "scope": " ".join(cfg["scopes"]),
            "state": state,
        }
        auth_url = f"{cfg['auth_endpoint']}?{urlencode(params)}"
        return {
            "provider": provider,
            "auth_url": auth_url,
            "state": state,
        }

    def verify_callback(self, provider: str, code: str, state: str) -> dict[str, Any]:
        if not code or not state:
            raise AppError("SSO_INVALID_CALLBACK", 400)
        
        self.store.consume(state, provider)
        
        # Synthetic / Mock identity extraction based on code pattern
        # e.g., code format "mock-user:A-U1" or default test account
        login_id = "a-u1"
        if ":" in code:
            parts = code.split(":", 1)
            login_id = parts[1].lower()

        return {
            "provider": provider,
            "identity_kind": "synthetic",
            "login_id": login_id,
            "verified": False,
            "assurance_evidence_created": False,
        }

GLOBAL_SSO_SERVICE = SsoService()
