import pytest
from pydantic import ValidationError
from app.config import Settings


def test_default_is_loopback_and_mock():
    settings = Settings(_env_file=None)
    assert settings.bind_host == '127.0.0.1'
    assert settings.origin == 'http://127.0.0.1:5173'
    assert settings.mode == 'mock'
    assert settings.web_dsn is None


@pytest.mark.parametrize('origin', [
    'http://example.com:5173', 'http://localhost:5173',
    'http://127.0.0.1:5173/', 'http://127.0.0.1:5173?x=1',
    'http://someone@127.0.0.1:5173',
])
def test_local_origin_is_exact(origin):
    with pytest.raises(ValidationError):
        Settings(origin=origin, _env_file=None)


def test_wildcard_binding_is_rejected():
    with pytest.raises(ValidationError):
        Settings(bind_host='0.0.0.0', _env_file=None)


def test_secrets_are_not_printed_in_settings():
    sentinel = 'synthetic-secret-for-repr-check'
    settings = Settings(web_dsn=sentinel, login_hmac_secret=sentinel, _env_file=None)
    leaked = sentinel in repr(settings)
    assert leaked is False
