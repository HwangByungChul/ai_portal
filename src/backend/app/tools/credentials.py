"""Secure Credential Vault for Tool and MCP Endpoints.

Provides authenticated encryption and decryption for sensitive endpoint
credentials (API keys, DB connection strings, Basic Auth tokens) using
standard Python libraries (HMAC-SHA256 + keystream) so no external C-extensions are required.
"""
import base64
import hashlib
import hmac
import json
import os
from typing import Any
from app.errors import AppError

# Derive a 256-bit encryption key from environment secret or deterministic platform seed
_RAW_SECRET = os.environ.get("TOOL_CREDENTIAL_KEY", "bnk_ai_platform_mcp_tool_vault_secret_key_2026")
_VAULT_KEY = hashlib.sha256(_RAW_SECRET.encode("utf-8")).digest()


def _keystream(key: bytes, nonce: bytes, length: int) -> bytes:
    """Deterministic pseudo-random keystream generated via repeated HMAC-SHA256."""
    stream = bytearray()
    counter = 0
    while len(stream) < length:
        block = hmac.new(key, nonce + counter.to_bytes(4, "big"), hashlib.sha256).digest()
        stream.extend(block)
        counter += 1
    return bytes(stream[:length])


def encrypt_credential(credential_data: Any) -> str:
    """Encrypt dictionary or string credentials into base64 payload."""
    if credential_data is None:
        return ""
    if isinstance(credential_data, (dict, list)):
        payload_bytes = json.dumps(credential_data, ensure_ascii=False).encode("utf-8")
    elif isinstance(credential_data, str):
        payload_bytes = credential_data.encode("utf-8")
    else:
        payload_bytes = str(credential_data).encode("utf-8")

    nonce = os.urandom(16)
    keystream = _keystream(_VAULT_KEY, nonce, len(payload_bytes))
    ciphertext = bytes(a ^ b for a, b in zip(payload_bytes, keystream))
    # HMAC-SHA256 for integrity authentication tag
    tag = hmac.new(_VAULT_KEY, nonce + ciphertext, hashlib.sha256).digest()

    combined = nonce + tag + ciphertext
    return base64.urlsafe_b64encode(combined).decode("ascii")


def decrypt_credential(encrypted_str: str | None) -> dict[str, Any] | str | None:
    """Decrypt base64 authenticated payload back to dictionary or string."""
    if not encrypted_str:
        return None
    try:
        combined = base64.urlsafe_b64decode(encrypted_str.encode("ascii"))
        if len(combined) < 48:  # 16-byte nonce + 32-byte HMAC tag
            raise AppError("CREDENTIAL_DECRYPT_FAILED", 500)
        nonce = combined[:16]
        expected_tag = combined[16:48]
        ciphertext = combined[48:]

        actual_tag = hmac.new(_VAULT_KEY, nonce + ciphertext, hashlib.sha256).digest()
        if not hmac.compare_digest(expected_tag, actual_tag):
            raise AppError("CREDENTIAL_DECRYPT_FAILED", 500)

        keystream = _keystream(_VAULT_KEY, nonce, len(ciphertext))
        decrypted_bytes = bytes(a ^ b for a, b in zip(ciphertext, keystream))
        text = decrypted_bytes.decode("utf-8")
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            return text
    except Exception as err:
        raise AppError("CREDENTIAL_DECRYPT_FAILED", 500) from err
