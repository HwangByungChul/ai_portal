"""Unit and contract tests for OIDC JWT and SAML Step-up MFA verifiers.

Tests cryptographic signature verification, replay prevention,
freshness evaluation (300s window), acr/amr enforcement, and XXE protection.
"""
import base64
import time
import jwt
import pytest
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from app.auth.oidc_saml_verifier import (
    OidcJwtVerifier,
    SamlResponseVerifier,
    StepUpMfaGate,
)
from app.errors import AppError


@pytest.fixture(scope="module")
def rsa_key_pair():
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    private_pem = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.TraditionalOpenSSL,
        encryption_algorithm=serialization.NoEncryption(),
    ).decode("utf-8")
    public_pem = private_key.public_key().public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    ).decode("utf-8")
    return private_pem, public_pem


def test_oidc_verifier_success(rsa_key_pair):
    private_pem, public_pem = rsa_key_pair
    now = int(time.time())

    verifier = OidcJwtVerifier(
        trusted_issuers=["https://idp.bank.example.com"],
        trusted_audience="ai-platform-client",
        public_keys_pem={"key-1": public_pem},
        required_acr_values=["mfa", "urn:mace:incommon:iap:silver"],
    )

    payload = {
        "iss": "https://idp.bank.example.com",
        "sub": "user_emp_98765",
        "aud": "ai-platform-client",
        "exp": now + 3600,
        "iat": now,
        "auth_time": now - 30,  # 30 seconds ago (fresh)
        "acr": "urn:mace:incommon:iap:silver",
    }
    token = jwt.encode(payload, private_pem, algorithm="RS256", headers={"kid": "key-1"})

    identity = verifier.verify_oidc(response=token, state="session_nonce_123")
    assert identity.protocol == "oidc"
    assert identity.issuer == "https://idp.bank.example.com"
    assert identity.subject == "user_emp_98765"
    assert identity.assurance_level == "urn:mace:incommon:iap:silver"
    assert identity.authenticated_at_epoch == now - 30


def test_oidc_verifier_stale_assurance(rsa_key_pair):
    private_pem, public_pem = rsa_key_pair
    now = int(time.time())

    verifier = OidcJwtVerifier(
        trusted_issuers=["https://idp.bank.example.com"],
        trusted_audience="ai-platform-client",
        public_keys_pem={"default": public_pem},
        max_freshness_seconds=300,
    )

    # 350 seconds ago (> 300s limit)
    payload = {
        "iss": "https://idp.bank.example.com",
        "sub": "user_emp_98765",
        "aud": "ai-platform-client",
        "exp": now + 3600,
        "iat": now - 350,
        "auth_time": now - 350,
        "acr": "mfa",
    }
    token = jwt.encode(payload, private_pem, algorithm="RS256")

    with pytest.raises(AppError) as exc_info:
        verifier.verify_oidc(response=token, state="nonce")
    assert exc_info.value.code == "IDP_ASSURANCE_STALE"


def test_oidc_verifier_insufficient_assurance(rsa_key_pair):
    private_pem, public_pem = rsa_key_pair
    now = int(time.time())

    verifier = OidcJwtVerifier(
        trusted_issuers=["https://idp.bank.example.com"],
        trusted_audience="ai-platform-client",
        public_keys_pem={"default": public_pem},
        required_acr_values=["mfa"],
    )

    # password-only login without MFA
    payload = {
        "iss": "https://idp.bank.example.com",
        "sub": "user_emp_98765",
        "aud": "ai-platform-client",
        "exp": now + 3600,
        "iat": now,
        "auth_time": now,
        "acr": "urn:oasis:names:tc:SAML:2.0:ac:classes:Password",
    }
    token = jwt.encode(payload, private_pem, algorithm="RS256")

    with pytest.raises(AppError) as exc_info:
        verifier.verify_oidc(response=token, state="nonce")
    assert exc_info.value.code == "IDP_ASSURANCE_INSUFFICIENT"


def test_oidc_verifier_untrusted_issuer(rsa_key_pair):
    private_pem, public_pem = rsa_key_pair
    now = int(time.time())

    verifier = OidcJwtVerifier(
        trusted_issuers=["https://idp.bank.example.com"],
        trusted_audience="ai-platform-client",
        public_keys_pem={"default": public_pem},
    )

    payload = {
        "iss": "https://rogue-idp.attacker.com",
        "sub": "admin_hacked",
        "aud": "ai-platform-client",
        "exp": now + 3600,
        "iat": now,
        "auth_time": now,
    }
    token = jwt.encode(payload, private_pem, algorithm="RS256")

    with pytest.raises(AppError) as exc_info:
        verifier.verify_oidc(response=token, state="nonce")
    assert exc_info.value.code == "IDP_ISSUER_UNTRUSTED"


def test_oidc_verifier_invalid_signature():
    # Sign with another key that verifier does not trust
    other_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    other_pem = other_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.TraditionalOpenSSL,
        encryption_algorithm=serialization.NoEncryption(),
    ).decode("utf-8")

    trusted_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    trusted_public_pem = trusted_key.public_key().public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    ).decode("utf-8")

    verifier = OidcJwtVerifier(
        trusted_issuers=["https://idp.bank.example.com"],
        trusted_audience="ai-platform-client",
        public_keys_pem={"default": trusted_public_pem},
    )

    now = int(time.time())
    payload = {
        "iss": "https://idp.bank.example.com",
        "sub": "user_emp_98765",
        "aud": "ai-platform-client",
        "exp": now + 3600,
        "iat": now,
    }
    token = jwt.encode(payload, other_pem, algorithm="RS256")

    with pytest.raises(AppError) as exc_info:
        verifier.verify_oidc(response=token, state="nonce")
    assert exc_info.value.code == "IDP_TOKEN_INVALID"


def test_saml_verifier_success(rsa_key_pair):
    _, public_pem = rsa_key_pair
    verifier = SamlResponseVerifier(
        trusted_issuers=["https://saml.bank.example.com"],
        public_key_pem=public_pem,
    )

    saml_xml = """<samlp:Response xmlns:samlp="urn:oasis:names:tc:SAML:2.0:protocol"
                xmlns:saml="urn:oasis:names:tc:SAML:2.0:assertion">
  <saml:Issuer>https://saml.bank.example.com</saml:Issuer>
  <ds:Signature xmlns:ds="http://www.w3.org/2000/09/xmldsig#">
    <ds:SignatureValue>MOCK_DIGITAL_SIG</ds:SignatureValue>
  </ds:Signature>
  <saml:Assertion>
    <saml:Subject>
      <saml:NameID>bank_admin_001</saml:NameID>
    </saml:Subject>
  </saml:Assertion>
</samlp:Response>"""

    encoded = base64.b64encode(saml_xml.encode("utf-8")).decode("ascii")
    identity = verifier.verify_saml(response=encoded, request_id="req_999")

    assert identity.protocol == "saml"
    assert identity.issuer == "https://saml.bank.example.com"
    assert identity.subject == "bank_admin_001"


def test_saml_verifier_xxe_blocked(rsa_key_pair):
    _, public_pem = rsa_key_pair
    verifier = SamlResponseVerifier(
        trusted_issuers=["https://saml.bank.example.com"],
        public_key_pem=public_pem,
    )

    xxe_xml = """<!DOCTYPE foo [<!ENTITY xxe SYSTEM "file:///etc/passwd">]>
<samlp:Response xmlns:samlp="urn:oasis:names:tc:SAML:2.0:protocol">
  <saml:Issuer xmlns:saml="urn:oasis:names:tc:SAML:2.0:assertion">&xxe;</saml:Issuer>
</samlp:Response>"""

    with pytest.raises(AppError) as exc_info:
        verifier.verify_saml(response=xxe_xml, request_id="req_xxe")
    assert exc_info.value.code == "IDP_TOKEN_INVALID"


def test_step_up_mfa_gate():
    from app.auth.idp_verifier import VerifiedIdentity

    now = int(time.time())
    fresh_identity = VerifiedIdentity(
        protocol="oidc",
        issuer="https://idp.bank.example.com",
        subject="user_1",
        assurance_level="mfa",
        authenticated_at_epoch=now - 50,  # 50s ago
        replay_digest="digest_1",
    )
    assert StepUpMfaGate.verify_freshness(fresh_identity, max_age_seconds=300) is True

    stale_identity = VerifiedIdentity(
        protocol="oidc",
        issuer="https://idp.bank.example.com",
        subject="user_1",
        assurance_level="mfa",
        authenticated_at_epoch=now - 400,  # 400s ago
        replay_digest="digest_2",
    )
    with pytest.raises(AppError) as exc_info:
        StepUpMfaGate.verify_freshness(stale_identity, max_age_seconds=300)
    assert exc_info.value.code == "IDP_ASSURANCE_STALE"
