import os
from datetime import date
from pathlib import Path
from typing import Literal
from urllib.parse import urlsplit

from pydantic import Field, SecretStr, StrictInt, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="AI_", extra="forbid", env_file=None, hide_input_in_errors=True
    )

    profile: Literal["local", "https"] = "local"
    environment: Literal['local','dev','tb','prd'] = 'local'
    portal_origins: tuple[str, ...] = ()
    origin: str = "http://127.0.0.1:5173"
    mode: Literal["mock", "real"] = "mock"
    budget_period: date = date(2026, 10, 1)
    execution_enabled: bool = False
    index_enabled: bool = False
    index_dsn: SecretStr | None = Field(default=None, repr=False)
    source_root: Path = Field(default_factory=lambda: Path(__file__).resolve().parents[1]/".runtime"/"source-store", repr=False)
    openai_api_key: SecretStr | None = Field(default=None, repr=False)
    db_port: int = Field(default=55432, ge=1, le=65535)
    bind_host: Literal["127.0.0.1"] = "127.0.0.1"
    web_dsn: SecretStr | None = Field(default=None, repr=False)
    meter_dsn: SecretStr | None = Field(default=None, repr=False)
    login_hmac_secret: SecretStr | None = Field(default=None, repr=False)
    # Reserved for server-side IdP subject pseudonymization. No secret is checked in.
    idp_subject_hmac_key: SecretStr | None = Field(default=None, repr=False)
    idp_subject_hmac_key_version: StrictInt | None = Field(default=None, ge=1, le=32767)
    idp_subject_hmac_key_versions: tuple[StrictInt, ...] = ()

    @classmethod
    def settings_customise_sources(cls, settings_cls, init_settings, env_settings,
                                   dotenv_settings, file_secret_settings):
        def subject_version_environment():
            values = env_settings()
            field_name = "idp_subject_hmac_key_version"
            raw, key, _ = env_settings.get_field_value(settings_cls.model_fields[field_name], field_name)
            if raw is not None:
                # Decode only environment integers; direct values retain StrictInt validation.
                values[key] = int(raw) if raw.isascii() and raw.isdecimal() else raw
            return values

        return init_settings, subject_version_environment, dotenv_settings, file_secret_settings

    @model_validator(mode="after")
    def validate_idp_subject_key(self) -> "Settings":
        key = self.idp_subject_hmac_key.get_secret_value() if self.idp_subject_hmac_key else None
        version = self.idp_subject_hmac_key_version
        versions = self.idp_subject_hmac_key_versions
        if len(set(versions)) != len(versions) or any(not 1 <= item <= 32767 for item in versions):
            raise ValueError("IDP_SUBJECT_KEY_VERSION_INVALID")
        if key is not None and version is None:
            raise ValueError("IDP_SUBJECT_KEY_AND_VERSION_REQUIRED_TOGETHER")
        if version is not None and versions and version not in versions:
            raise ValueError("IDP_SUBJECT_ACTIVE_KEY_MISSING")
        if versions and version is None:
            raise ValueError("IDP_SUBJECT_ACTIVE_KEY_MISSING")
        if key is not None and len(key.encode("utf-8")) < 32:
            raise ValueError("IDP_SUBJECT_KEY_TOO_SHORT")
        return self

    @model_validator(mode="after")
    def validate_origin(self) -> "Settings":
        parsed = urlsplit(self.origin)
        if self.profile == "local":
            if self.portal_origins:
                for origin in self.portal_origins:
                    value=urlsplit(origin)
                    if value.scheme!='http' or value.hostname!='127.0.0.1' or value.username or value.password or value.path or value.query or value.fragment or not value.port:
                        raise ValueError('local origins must be configured loopback origins')
                if self.origin not in self.portal_origins or len(set(self.portal_origins))!=len(self.portal_origins):
                    raise ValueError('invalid configured local origins')
            elif self.origin != "http://127.0.0.1:5173":
                raise ValueError("local origin must match the configured loopback portal")
        elif (parsed.scheme != "https" or not parsed.hostname or parsed.username
              or parsed.password or parsed.path or parsed.query or parsed.fragment):
            raise ValueError("HTTPS origin must contain only a scheme, host and optional port")
        if self.profile=='https' and self.portal_origins:
            if self.origin not in self.portal_origins or len(set(self.portal_origins))!=len(self.portal_origins):raise ValueError('invalid configured HTTPS origins')
            for origin in self.portal_origins:
                value=urlsplit(origin)
                if value.scheme!='https' or not value.hostname or value.username or value.password or value.path or value.query or value.fragment:raise ValueError('invalid configured HTTPS origin')
        return self

    @classmethod
    def from_environment(cls):
        from app.environment import load_environment,ConfigurationError
        environment=os.environ.get('AI_ENVIRONMENT','local')
        config=load_environment(environment)
        # Commercial auth/DB profile must be implemented before a fixture-based app can run there.
        if environment!='local':raise ConfigurationError('COMMERCIAL_RUNTIME_PROFILE_NOT_READY')
        return cls(environment=environment,profile='local',origin=config['user']['origin'],portal_origins=(config['user']['origin'],config['admin']['origin']))

    @property
    def trusted_origins(self):return self.portal_origins or (self.origin,)

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

    def require_index_configuration(self):
        if self.index_dsn is None or self.meter_dsn is None:raise ValueError('INDEX_CONFIGURATION_REQUIRED')
        if self.mode=='real' and (self.openai_api_key is None or not self.openai_api_key.get_secret_value().strip()):raise ValueError('PROVIDER_CONFIGURATION_REQUIRED')
