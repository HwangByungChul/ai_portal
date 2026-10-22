"""Synthetic unit coverage only; no institution IdP verification is performed."""

import traceback

import pytest
from pydantic import SecretStr

from app.auth.idp_verifier import IdpVerifier, SubjectDigestKeyring, VerifiedIdentity
from app.errors import AppError


@pytest.mark.parametrize(
    "method,inputs",
    [
        ("verify_oidc", {"response": "synthetic-oidc", "state": "synthetic-state"}),
        ("verify_saml", {"response": "synthetic-saml", "request_id": "synthetic-request"}),
    ],
)
def test_unconfigured_verifier_denies_both_protocols(method, inputs):
    verifier = IdpVerifier()

    assert verifier.active is False
    with pytest.raises(AppError) as caught:
        getattr(verifier, method)(**inputs)

    assert caught.value.code == "IDP_VERIFIER_NOT_CONFIGURED"
    assert caught.value.status == 503


@pytest.mark.parametrize("protocol", ["oidc", "saml"])
def test_explicit_backend_receives_exact_inputs_and_returns_same_identity(protocol):
    identity = VerifiedIdentity(
        protocol=protocol,
        issuer="https://synthetic.invalid/issuer",
        subject="synthetic-subject",
        assurance_level="synthetic-only",
        authenticated_at_epoch=123,
        replay_digest="synthetic-replay-digest",
    )
    calls = []

    class SyntheticBackend:
        def verify_oidc(self, *, response, state):
            calls.append(("oidc", response, state))
            return identity

        def verify_saml(self, *, response, request_id):
            calls.append(("saml", response, request_id))
            return identity

    verifier = IdpVerifier(SyntheticBackend())
    response = "  opaque synthetic response \n"
    correlation = "  opaque synthetic correlation \n"
    assert verifier.active is True

    if protocol == "oidc":
        result = verifier.verify_oidc(response=response, state=correlation)
    else:
        result = verifier.verify_saml(response=response, request_id=correlation)

    assert result is identity
    assert calls == [(protocol, response, correlation)]


def test_rotation_defaults_to_active_key_and_reproduces_retained_digest():
    retained_key = SecretStr("synthetic-retained-key-" + "a" * 32)
    active_key = SecretStr("synthetic-active-key-" + "b" * 32)
    old_ring = SubjectDigestKeyring({1: retained_key}, active_version=1)
    rotated_ring = SubjectDigestKeyring(
        {1: retained_key, 2: active_key}, active_version=2
    )
    inputs = ("oidc", "https://synthetic.invalid/issuer", "synthetic-subject")

    old_digest = old_ring.digest(*inputs)
    active_digest = rotated_ring.digest(*inputs)
    retained_digest = rotated_ring.digest(*inputs, key_version=1)

    assert active_digest.key_version == 2
    assert active_digest == rotated_ring.digest(*inputs, key_version=2)
    assert retained_digest == old_digest
    assert retained_digest.key_version == 1
    assert active_digest.digest != retained_digest.digest
    assert len(active_digest.digest) == 64
    assert all(character in "0123456789abcdef" for character in active_digest.digest)


def test_digest_separates_protocol_issuer_and_subject_domains():
    ring = SubjectDigestKeyring({1: "synthetic-domain-key-" + "c" * 32}, active_version=1)
    inputs = [
        ("oidc", "issuer-a", "subject-a"),
        ("saml", "issuer-a", "subject-a"),
        ("oidc", "issuer-b", "subject-a"),
        ("oidc", "issuer-a", "subject-b"),
        # Equal concatenated issuer/subject bytes must remain distinct fields.
        ("oidc", "issuer-asubject-", "a"),
    ]

    digests = [ring.digest(*fields).digest for fields in inputs]

    assert len(set(digests)) == len(inputs)


def test_unknown_key_version_has_fixed_error_without_secret_material():
    secret = "synthetic-unknown-version-secret-" + "d" * 32
    ring = SubjectDigestKeyring({1: SecretStr(secret)}, active_version=1)

    with pytest.raises(ValueError) as caught:
        ring.digest("oidc", "synthetic-issuer", "synthetic-subject", key_version=2)

    assert str(caught.value) == "IDP_SUBJECT_KEY_VERSION_UNKNOWN"
    assert secret not in repr(caught.value)


def test_missing_active_key_has_fixed_error_without_secret_material():
    secret = "synthetic-missing-active-secret-" + "e" * 32

    with pytest.raises(ValueError) as caught:
        SubjectDigestKeyring({1: SecretStr(secret)}, active_version=2)

    assert str(caught.value) == "IDP_SUBJECT_ACTIVE_KEY_MISSING"
    assert secret not in repr(caught.value)


@pytest.mark.parametrize(
    "provider_fails,expected_error",
    [
        (False, "IDP_SUBJECT_KEY_MISSING"),
        (True, "IDP_SUBJECT_KEY_UNAVAILABLE"),
    ],
)
def test_provider_missing_key_and_exception_have_fixed_safe_errors(
    provider_fails, expected_error
):
    secret = "synthetic-provider-secret-" + "f" * 32
    calls = []

    class SyntheticKeyProvider:
        def get_subject_key(self, key_version):
            calls.append(key_version)
            if key_version == 1:
                return SecretStr(secret)
            if provider_fails:
                raise RuntimeError(secret)
            return None

    with pytest.raises(ValueError) as caught:
        SubjectDigestKeyring.from_provider(
            SyntheticKeyProvider(), key_versions=(1, 2), active_version=2
        )

    assert calls == [1, 2]
    assert str(caught.value) == expected_error
    assert secret not in repr(caught.value)
    assert secret not in "".join(traceback.format_exception(caught.value))
    if provider_fails:
        assert caught.value.__suppress_context__ is True
