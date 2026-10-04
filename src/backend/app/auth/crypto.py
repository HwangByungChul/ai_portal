import hashlib
import hmac
import re
import secrets
from argon2 import PasswordHasher, Type
from argon2.exceptions import InvalidHashError, VerificationError

HASHER = PasswordHasher(memory_cost=19456, time_cost=2, parallelism=1, type=Type.ID)
DUMMY_HASH = HASHER.hash(secrets.token_urlsafe(24))
TOKEN_PATTERN = re.compile(r'[A-Za-z0-9_-]{43}')


def normalize_login(value: str) -> str:
    result = value.strip().lower()
    if re.fullmatch(r'[a-z0-9._-]{3,64}', result) is None:
        raise ValueError('LOGIN_FORMAT_INVALID')
    return result


def token_digest(value: str) -> bytes:
    if TOKEN_PATTERN.fullmatch(value) is None:
        raise ValueError('SESSION_FORMAT_INVALID')
    return hashlib.sha256(value.encode('ascii')).digest()


def verify_password(encoded_hash: str | None, password: str) -> bool:
    try:
        encoded_length = len(password.encode('utf-8'))
    except UnicodeError:
        return False
    if len(password) > 128 or encoded_length > 512:
        return False
    try:
        valid = HASHER.verify(encoded_hash or DUMMY_HASH, password)
        return bool(encoded_hash) and valid
    except (InvalidHashError, VerificationError):
        return False


def new_secret() -> str:
    return secrets.token_urlsafe(32)


def window_digest(secret: str, purpose: str, kind: str, key: str) -> bytes:
    parts = [part.encode('utf-8') for part in (purpose, kind, key)]
    framed = b''.join(len(part).to_bytes(4, 'big') + part for part in parts)
    return hmac.new(secret.encode('ascii'), framed, hashlib.sha256).digest()
