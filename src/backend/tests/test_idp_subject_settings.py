"""Environment decoding and strict programmatic subject key version contracts."""

import os
import traceback

import pytest
from pydantic import ValidationError

from app.config import Settings


@pytest.fixture(autouse=True)
def isolated_environment(monkeypatch):
    for name in os.environ:
        if name.startswith("AI_"):
            monkeypatch.delenv(name)


@pytest.mark.parametrize("version", ["1", "32767"])
def test_single_hmac_key_version_accepts_environment_integer(monkeypatch, version):
    monkeypatch.setenv("AI_IDP_SUBJECT_HMAC_KEY", "synthetic-settings-key-" + "x" * 32)
    monkeypatch.setenv("AI_IDP_SUBJECT_HMAC_KEY_VERSION", version)
    monkeypatch.setenv("AI_IDP_SUBJECT_HMAC_KEY_VERSIONS", "[1, 32767]")

    settings = Settings()

    assert type(settings.idp_subject_hmac_key_version) is int
    assert settings.idp_subject_hmac_key_version == int(version)
    assert settings.idp_subject_hmac_key_versions == (1, 32767)


@pytest.mark.parametrize("version", [
    "", "0", "32768", "-1", "1.0", "true", "+1", " 1 ", "one", "١",
])
def test_single_hmac_key_version_rejects_invalid_environment(monkeypatch, version):
    monkeypatch.setenv("AI_IDP_SUBJECT_HMAC_KEY_VERSION", version)

    with pytest.raises(ValidationError):
        Settings()


@pytest.mark.parametrize("version", [True, False, 1.0, "1", 0, 32768])
def test_single_hmac_key_version_keeps_strict_programmatic_validation(version):
    with pytest.raises(ValidationError):
        Settings(idp_subject_hmac_key_version=version)


def test_programmatic_integer_overrides_environment(monkeypatch):
    monkeypatch.setenv("AI_IDP_SUBJECT_HMAC_KEY_VERSION", "2")

    assert Settings(idp_subject_hmac_key_version=1).idp_subject_hmac_key_version == 1


@pytest.mark.parametrize("versions", [(True,), ("1",), (1.0,), (0,), (32768,), (1, 1)])
def test_hmac_key_version_tuple_validation_is_preserved(versions):
    with pytest.raises(ValidationError):
        Settings(idp_subject_hmac_key_version=1, idp_subject_hmac_key_versions=versions)


@pytest.mark.parametrize("source", ["environment", "programmatic"])
@pytest.mark.parametrize("invalid", ["missing-version", "short-key", "active-key-missing", "invalid-origin"])
def test_validation_error_rendering_hides_raw_subject_key(monkeypatch, source, invalid):
    secret = "synthetic-settings-sensitive-" + "x" * 32
    values = {"idp_subject_hmac_key": secret, "idp_subject_hmac_key_version": 1}
    if invalid == "missing-version":
        del values["idp_subject_hmac_key_version"]
    elif invalid == "short-key":
        secret = "synthetic-short-key"
        values["idp_subject_hmac_key"] = secret
    elif invalid == "active-key-missing":
        values["idp_subject_hmac_key_versions"] = (2,)
    else:
        values["origin"] = "https://example.invalid"

    if source == "environment":
        for name, value in values.items():
            monkeypatch.setenv("AI_" + name.upper(), "[2]" if isinstance(value, tuple) else str(value))
        values = {}

    with pytest.raises(ValidationError) as caught:
        Settings(**values)

    for rendered in (str(caught.value), repr(caught.value), "".join(traceback.format_exception(caught.value))):
        assert secret not in rendered
        assert "input_value=" not in rendered
