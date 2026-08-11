"""Security primitives: password hashing, JWT, refresh tokens, CSRF, field encryption."""

import base64
import hashlib
import secrets
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import jwt
from cryptography.fernet import Fernet
from pwdlib import PasswordHash
from pwdlib.hashers.argon2 import Argon2Hasher

from app.core.config import get_settings

# Tests run hundreds of hash/verify calls; production cost parameters would
# turn the suite into a sleep marathon. The fast hasher keeps the exact same
# code path (pwdlib/argon2id) with dev/test-only low cost — production always
# uses the expensive parameters.
if get_settings().APP_ENV in ("dev", "test"):
    _password_hasher = PasswordHash(
        [Argon2Hasher(time_cost=1, memory_cost=1024, parallelism=1)]
    )
else:
    _password_hasher = PasswordHash([Argon2Hasher()])

GENESIS_HASH = "0" * 64


def hash_password(password: str) -> str:
    return _password_hasher.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    return _password_hasher.verify(password, password_hash)


# ---------------------------------------------------------------- JWT access


def create_access_token(
    *, subject: str, token_type: str, role: str | None = None, name: str | None = None
) -> str:
    settings = get_settings()
    minutes = (
        settings.ACCESS_TOKEN_MINUTES_PATIENT
        if token_type == "patient"
        else settings.ACCESS_TOKEN_MINUTES_STAFF
    )
    now = datetime.now(UTC)
    claims: dict[str, Any] = {
        "sub": subject,
        "typ": token_type,
        "iat": now,
        "exp": now + timedelta(minutes=minutes),
        "jti": uuid.uuid4().hex,
    }
    if role:
        claims["role"] = role
    if name:
        claims["name"] = name
    return jwt.encode(claims, settings.SECRET_KEY, algorithm=settings.TOKEN_ALG)


def decode_access_token(token: str) -> dict[str, Any]:
    settings = get_settings()
    return jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.TOKEN_ALG])


# ------------------------------------------------------------- refresh tokens


def generate_refresh_token() -> tuple[str, str, str]:
    """Returns (raw_token, sha256_hash, family_id). The raw token is given to
    the client once; only the hash is stored."""
    raw = secrets.token_urlsafe(32)
    return raw, sha256_hex(raw), uuid.uuid4().hex


def sha256_hex(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def refresh_expiry(token_type: str) -> datetime:
    settings = get_settings()
    days = (
        settings.REFRESH_TOKEN_DAYS_PATIENT
        if token_type == "patient"
        else settings.REFRESH_TOKEN_DAYS_STAFF
    )
    return datetime.now(UTC) + timedelta(days=days)


# ----------------------------------------------------------------------- CSRF


def generate_csrf_token() -> str:
    return secrets.token_urlsafe(32)


# ----------------------------------------------------------- field encryption


def _fernet() -> Fernet:
    key = get_settings().FIELD_ENCRYPTION_KEY
    if not key:
        raise RuntimeError("FIELD_ENCRYPTION_KEY is not configured")
    return Fernet(key.encode("utf-8"))


def encrypt_field(value: str) -> bytes:
    return _fernet().encrypt(value.encode("utf-8"))


def decrypt_field(ciphertext: bytes) -> str:
    return _fernet().decrypt(ciphertext).decode("utf-8")


def new_field_key() -> str:
    return base64.urlsafe_b64encode(Fernet.generate_key()).decode("utf-8")
