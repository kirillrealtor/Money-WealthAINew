"""Token + hashing primitives shared across auth."""
from __future__ import annotations

import base64
import hashlib
import secrets

import bcrypt

from app.config import settings


def random_token(nbytes: int = 32) -> str:
    """Opaque, URL-safe random token (refresh tokens, email verify links)."""
    return secrets.token_urlsafe(nbytes)


def sha256(value: str) -> str:
    """SHA-256 hex; used to store hashes of refresh/verification tokens."""
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def stable_bucket(value: str, mod: int = 1_000_000) -> int:
    """Deterministic bucket for a value, stable across processes/instances.

    Python's builtin hash() is randomized per-process (PYTHONHASHSEED), so it
    must NOT be used for cross-instance keys (e.g. rate-limit keys). SHA-256 is.
    """
    digest = hashlib.sha256(value.encode("utf-8")).digest()
    return int.from_bytes(digest[:8], "big") % mod


def _prehash(plain: str) -> bytes:
    """Map an arbitrary-length password into a fixed 44-byte token before bcrypt.

    bcrypt silently truncates input at 72 bytes; pre-hashing with SHA-256 then
    base64 (44 bytes, no NUL bytes) removes that footgun so long passphrases are
    fully honored. This is the widely used 'bcrypt(base64(sha256(pw)))' pattern.
    """
    return base64.b64encode(hashlib.sha256(plain.encode("utf-8")).digest())


def hash_password(plain: str) -> str:
    return bcrypt.hashpw(_prehash(plain), bcrypt.gensalt(rounds=settings.bcrypt_rounds)).decode("utf-8")


def verify_password(plain: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(_prehash(plain), hashed.encode("utf-8"))
    except (ValueError, TypeError):
        return False


# A valid bcrypt hash used to spend ~equal CPU when the account doesn't exist,
# closing the login user-enumeration timing oracle. Computed once at import.
DUMMY_PASSWORD_HASH: str = hash_password(secrets.token_urlsafe(16))
