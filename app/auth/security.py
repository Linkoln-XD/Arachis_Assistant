import hashlib
import secrets
import uuid
from datetime import UTC, datetime, timedelta

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import VerificationError
from jwt import InvalidTokenError

from app.config import get_settings

_password_hasher = PasswordHasher()


class TokenExpired(Exception):
    pass


class TokenInvalid(Exception):
    pass


def hash_password(password: str) -> str:
    return _password_hasher.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return _password_hasher.verify(password_hash, password)
    except VerificationError:
        return False


def hash_refresh_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def create_access_token(user_id: uuid.UUID) -> str:
    settings = get_settings()
    now = datetime.now(UTC)
    payload = {
        "sub": str(user_id),
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(seconds=settings.access_token_ttl_seconds)).timestamp()),
        "type": "access",
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm="HS256")


def decode_access_token(token: str) -> uuid.UUID:
    settings = get_settings()
    try:
        payload = jwt.decode(token, settings.jwt_secret, algorithms=["HS256"])
    except jwt.ExpiredSignatureError as error:
        raise TokenExpired from error
    except InvalidTokenError as error:
        raise TokenInvalid from error
    if payload.get("type") != "access":
        raise TokenInvalid
    subject = payload.get("sub")
    try:
        return uuid.UUID(str(subject))
    except (TypeError, ValueError) as error:
        raise TokenInvalid from error


def new_refresh_token() -> str:
    return secrets.token_urlsafe(32)


def refresh_expires_at() -> datetime:
    settings = get_settings()
    return datetime.now(UTC) + timedelta(seconds=settings.refresh_token_ttl_seconds)
