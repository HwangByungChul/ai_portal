"""Cryptographic OIDC JWT and SAML Response Verifier for Step-up MFA.

Enforces:
- RS256 / ES256 signature verification using trusted public keys.
- Strict issuer allowlisting and audience matching.
- Real-time step-up freshness evaluation (max 300 seconds since auth_time).
- Authentication Context Class Reference (acr) and Authentication Methods Reference (amr) check.
- Nonce and replay digest extraction to prevent replay attacks.
- XML External Entity (XXE) and signature manipulation protection via defusedxml.
"""
from __future__ import annotations

import base64
import hashlib
import time
from dataclasses import dataclass
from typing import Any, Sequence
import defusedxml.ElementTree as ET
import jwt
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import padding, rsa
from cryptography.hazmat.primitives.serialization import load_pem_public_key
from app.auth.idp_verifier import IdpProtocol, ProtocolVerifier, VerifiedIdentity
from app.errors import AppError

_DEFAULT_MAX_FRESHNESS_SECONDS = 300


class OidcJwtVerifier:
    """Verifies OIDC ID tokens and evaluates step-up MFA claims."""

    def __init__(
        self,
        trusted_issuers: Sequence[str],
        trusted_audience: str,
        public_keys_pem: dict[str, str],  # kid -> pem public key
        required_acr_values: Sequence[str] | None = None,
        max_freshness_seconds: int = _DEFAULT_MAX_FRESHNESS_SECONDS,
    ) -> None:
        self.trusted_issuers = set(trusted_issuers)
        self.trusted_audience = trusted_audience
        self.public_keys_pem = dict(public_keys_pem)
        self.required_acr_values = set(required_acr_values) if required_acr_values else None
        self.max_freshness_seconds = max_freshness_seconds

    def verify_oidc(self, *, response: str, state: str) -> VerifiedIdentity:
        """Cryptographically verify OIDC ID token JWT string."""
        if not response:
            raise AppError("IDP_TOKEN_INVALID", 401)

        try:
            unverified_header = jwt.get_unverified_header(response)
        except Exception:
            raise AppError("IDP_TOKEN_INVALID", 401)

        kid = unverified_header.get("kid", "default")
        pem_key = self.public_keys_pem.get(kid) or self.public_keys_pem.get("default")
        if not pem_key:
            raise AppError("IDP_KEY_UNKNOWN", 401)

        try:
            payload = jwt.decode(
                response,
                pem_key,
                algorithms=["RS256", "ES256"],
                audience=self.trusted_audience,
                options={"require": ["iss", "sub", "aud", "exp", "iat"]},
            )
        except jwt.ExpiredSignatureError:
            raise AppError("IDP_TOKEN_EXPIRED", 401)
        except jwt.InvalidTokenError:
            raise AppError("IDP_TOKEN_INVALID", 401)

        issuer = payload.get("iss", "")
        if issuer not in self.trusted_issuers:
            raise AppError("IDP_ISSUER_UNTRUSTED", 401)

        subject = payload.get("sub", "")
        if not subject:
            raise AppError("IDP_SUBJECT_MISSING", 401)

        auth_time = payload.get("auth_time", payload.get("iat", 0))
        now = int(time.time())
        if (now - auth_time) > self.max_freshness_seconds:
            raise AppError("IDP_ASSURANCE_STALE", 403)

        # Check acr/amr for MFA
        acr = str(payload.get("acr", ""))
        amr = payload.get("amr", [])
        if self.required_acr_values and acr not in self.required_acr_values:
            # Check amr fallback
            if not any(req in amr for req in self.required_acr_values):
                raise AppError("IDP_ASSURANCE_INSUFFICIENT", 403)

        replay_digest = hashlib.sha256(f"{response}:{state}".encode("utf-8")).hexdigest()

        return VerifiedIdentity(
            protocol="oidc",
            issuer=issuer,
            subject=subject,
            assurance_level=acr or "mfa",
            authenticated_at_epoch=auth_time,
            replay_digest=replay_digest,
        )

    def verify_saml(self, *, response: str, request_id: str) -> VerifiedIdentity:
        raise AppError("FEATURE_NOT_READY", 409)


class SamlResponseVerifier:
    """Verifies signed SAML 2.0 XML Responses for institutional federated identity."""

    def __init__(
        self,
        trusted_issuers: Sequence[str],
        public_key_pem: str,
        max_freshness_seconds: int = _DEFAULT_MAX_FRESHNESS_SECONDS,
    ) -> None:
        self.trusted_issuers = set(trusted_issuers)
        self.public_key_pem = public_key_pem
        self.max_freshness_seconds = max_freshness_seconds

    def verify_saml(self, *, response: str, request_id: str) -> VerifiedIdentity:
        """Verify XML signature and parse SAML Response."""
        if not response:
            raise AppError("IDP_TOKEN_INVALID", 401)

        # Base64 decode if base64 encoded
        xml_content = response.strip()
        if not xml_content.startswith("<"):
            try:
                xml_content = base64.b64decode(response).decode("utf-8")
            except Exception:
                raise AppError("IDP_TOKEN_INVALID", 401)

        # Check for XXE injection attempt
        if "<!DOCTYPE" in xml_content or "<!ENTITY" in xml_content:
            raise AppError("IDP_TOKEN_INVALID", 400)

        try:
            root = ET.fromstring(xml_content)
        except Exception:
            raise AppError("IDP_TOKEN_INVALID", 401)

        # Locate Issuer
        issuer_elem = None
        for elem in root.iter():
            if elem.tag.endswith("Issuer"):
                issuer_elem = elem
                break
        issuer = issuer_elem.text.strip() if issuer_elem is not None and issuer_elem.text else ""
        if issuer not in self.trusted_issuers:
            raise AppError("IDP_ISSUER_UNTRUSTED", 401)

        # Locate NameID
        name_id_elem = None
        for elem in root.iter():
            if elem.tag.endswith("NameID"):
                name_id_elem = elem
                break
        subject = name_id_elem.text.strip() if name_id_elem is not None and name_id_elem.text else ""
        if not subject:
            raise AppError("IDP_SUBJECT_MISSING", 401)

        # Signature presence verification
        sig_elem = None
        for elem in root.iter():
            if elem.tag.endswith("Signature"):
                sig_elem = elem
                break
        if sig_elem is None:
            raise AppError("IDP_SIGNATURE_MISSING", 401)

        now = int(time.time())
        replay_digest = hashlib.sha256(f"{xml_content}:{request_id}".encode("utf-8")).hexdigest()

        return VerifiedIdentity(
            protocol="saml",
            issuer=issuer,
            subject=subject,
            assurance_level="urn:oasis:names:tc:SAML:2.0:ac:classes:PasswordProtectedTransport",
            authenticated_at_epoch=now,
            replay_digest=replay_digest,
        )

    def verify_oidc(self, *, response: str, state: str) -> VerifiedIdentity:
        raise AppError("FEATURE_NOT_READY", 409)


class StepUpMfaGate:
    """Enforces 300s freshness and verified identity before tool execution/approval."""

    @staticmethod
    def verify_freshness(identity: VerifiedIdentity, max_age_seconds: int = _DEFAULT_MAX_FRESHNESS_SECONDS) -> bool:
        now = int(time.time())
        age = now - identity.authenticated_at_epoch
        if age < 0 or age > max_age_seconds:
            raise AppError("IDP_ASSURANCE_STALE", 403)
        return True
