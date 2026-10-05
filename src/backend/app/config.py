from datetime import date
from typing import Literal
from urllib.parse import urlsplit

from pydantic import Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="AI_", extra="forbid", env_file=None)

    profile: Literal["local", "https"] = "local"
    origin: str = "http://127.0.0.1:5173"
    mode: Literal["mock", "real"] = "mock"
    budget_period: date = date(2026, 10, 1)
    execution_enabled: bool = False
    openai_api_key: SecretStr | None = Field(default=None, repr=False)
    db_port: int = Field(default=55432, ge=1, le=65535)
    bind_host: Literal["127.0.0.1"] = "127.0.0.1"
    web_dsn: SecretStr | None = Field(default=None, repr=False)
    meter_dsn: SecretStr | None = Field(default=None, repr=False)
    login_hmac_secret: SecretStr | None = Field(default=None, repr=False)

    @model_validator(mode="after")
    def validate_origin(self) -> "Settings":
        parsed = urlsplit(self.origin)
        if self.profile == "local":
            if self.origin != "http://127.0.0.1:5173":
                raise ValueError("local origin must match the configured loopback portal")
        elif (parsed.scheme != "https" or not parsed.hostname or parsed.username
              or parsed.password or parsed.path or parsed.query or parsed.fragment):
            raise ValueError("HTTPS origin must contain only a scheme, host and optional port")
        return self

    @property
    def session_cookie_name(self) -> str:
        return 'ai_session_dev' if self.profile == 'local' else '__Host-ai_session'

    def require_auth_configuration(self) -> None:
        secret = self.login_hmac_secret.get_secret_value() if self.login_hmac_secret else ''
        if self.web_dsn is None or len(secret) < 32 or not secret.isascii():
            raise ValueError('AUTH_CONFIGURATION_REQUIRED')

    def require_execution_configuration(self) -> None:
        if self.meter_dsn is None:
            raise ValueError('METER_CONFIGURATION_REQUIRED')
        if self.mode=='real' and (self.openai_api_key is None or not self.openai_api_key.get_secret_value().strip()):
            raise ValueError('PROVIDER_CONFIGURATION_REQUIRED')
