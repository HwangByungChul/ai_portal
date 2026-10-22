"""Fail-closed IdP verification boundary and keyed subject pseudonymization.

This module deliberately does not parse tokens or assertions. A protocol-specific
backend must be supplied only after its cryptographic implementation, issuer
metadata, claim policy, and replay handling have been reviewed and configured.
"""
from __future__ import annotations

import hashlib
import hmac
from dataclasses import dataclass
from types import MappingProxyType
from typing import Literal, Mapping, Protocol

from pydantic import SecretStr

from app.errors import AppError

IdpProtocol = Literal["oidc", "saml"]


@dataclass(frozen=True)
class VerifiedIdentity:
    """Minimal identity returned only by a trusted, fully configured verifier."""

    protocol: IdpProtocol
    issuer: str
    subject: str
    assurance_level: str
    authenticated_at_epoch: int
    replay_digest: str


class ProtocolVerifier(Protocol):
    def verify_oidc(self, *, response: str, state: str) -> VerifiedIdentity: ...

    def verify_saml(self, *, response: str, request_id: str) -> VerifiedIdentity: ...


@dataclass(frozen=True)
class SubjectDigest:
    digest: str
    key_version: int


class SubjectKeyProvider(Protocol):
    """Secret-manager adapter contract; providers return secrets only to the server."""

    def get_subject_key(self, key_version: int) -> SecretStr | None: ...


class SubjectDigestKeyring:
    """Versioned HMAC keys for rotation while retaining lookup of old digests."""

    _DOMAIN = b"ai-platform:idp-subject:v1\x00"

    def __init__(self, keys: Mapping[int, SecretStr | str], *, active_version: int):
        if isinstance(active_version, bool) or not isinstance(active_version, int) or not 1 <= active_version <= 32767:
            raise ValueError("IDP_SUBJECT_KEY_VERSION_INVALID")
        normalized: dict[int, bytes] = {}
        for version, secret in keys.items():
            if isinstance(version, bool) or not isinstance(version, int) or not 1 <= version <= 32767:
                raise ValueError("IDP_SUBJECT_KEY_VERSION_INVALID")
            value = secret.get_secret_value() if isinstance(secret, SecretStr) else secret
            if not isinstance(value, str) or len(value.encode("utf-8")) < 32:
                raise ValueError("IDP_SUBJECT_KEY_TOO_SHORT")
            normalized[version] = value.encode("utf-8")
        if active_version not in normalized:
            raise ValueError("IDP_SUBJECT_ACTIVE_KEY_MISSING")
        self._keys = MappingProxyType(normalized)
        self.active_version = active_version

    @classmethod
    def from_provider(
        cls, provider: SubjectKeyProvider, *, key_versions: tuple[int, ...], active_version: int
    ) -> "SubjectDigestKeyring":
        if (not key_versions or any(isinstance(v, bool) or not isinstance(v, int) or not 1 <= v <= 32767 for v in key_versions)
                or len(set(key_versions)) != len(key_versions) or active_version not in key_versions):
            raise ValueError("IDP_SUBJECT_KEY_VERSION_INVALID")
        loaded: dict[int, SecretStr] = {}
        for version in key_versions:
            try:
                key = provider.get_subject_key(version)
            except Exception:
                raise ValueError("IDP_SUBJECT_KEY_UNAVAILABLE") from None
            if key is None:
                raise ValueError("IDP_SUBJECT_KEY_MISSING")
            loaded[version] = key
        return cls(loaded, active_version=active_version)

    def digest(
        self, protocol: IdpProtocol, issuer: str, subject: str, *, key_version: int | None = None
    ) -> SubjectDigest:
        version = self.active_version if key_version is None else key_version
        if isinstance(version, bool) or not isinstance(version, int):
            raise ValueError("IDP_SUBJECT_KEY_VERSION_INVALID")
        key = self._keys.get(version)
        if key is None:
            raise ValueError("IDP_SUBJECT_KEY_VERSION_UNKNOWN")
        if protocol not in ("oidc", "saml"):
            raise ValueError("IDP_PROTOCOL_INVALID")
        if not issuer or not subject or "\x00" in issuer or "\x00" in subject:
            raise ValueError("IDP_SUBJECT_INPUT_INVALID")
        # Length-prefix each UTF-8 value to avoid ambiguous concatenation.
        fields = (protocol.encode("ascii"), issuer.encode("utf-8"), subject.encode("utf-8"))
        message = self._DOMAIN + b"".join(len(item).to_bytes(4, "big") + item for item in fields)
        value = hmac.new(key, message, hashlib.sha256).hexdigest()
        return SubjectDigest(digest=value, key_version=version)


class SubjectDigestService:
    """Create a stable, keyed digest without retaining or returning the raw subject."""

    def __init__(self, key: SecretStr | str, key_version: int):
        self.keyring = SubjectDigestKeyring({key_version: key}, active_version=key_version)
        self.key_version = key_version

    def digest(self, protocol: IdpProtocol, issuer: str, subject: str) -> SubjectDigest:
        return self.keyring.digest(protocol, issuer, subject)


class IdpVerifier:
    """Dispatch to an explicitly wired verifier; absent configuration always denies."""

    def __init__(self, backend: ProtocolVerifier | None = None):
        self._backend = backend

    @property
    def active(self) -> bool:
        return self._backend is not None

    def verify_oidc(self, *, response: str, state: str) -> VerifiedIdentity:
        if self._backend is None:
            raise AppError("IDP_VERIFIER_NOT_CONFIGURED", 503)
        return self._backend.verify_oidc(response=response, state=state)

    def verify_saml(self, *, response: str, request_id: str) -> VerifiedIdentity:
        if self._backend is None:
            raise AppError("IDP_VERIFIER_NOT_CONFIGURED", 503)
        return self._backend.verify_saml(response=response, request_id=request_id)
