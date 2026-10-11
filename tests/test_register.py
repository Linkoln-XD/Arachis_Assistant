import uuid

import jwt
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.auth.security import hash_refresh_token, verify_password
from app.config import get_settings
from app.db.models import RefreshToken, User
from app.db.session import get_sessionmaker
from app.main import create_app

client = TestClient(create_app())


def test_register_creates_user_and_session() -> None:
    email = _email()
    response = client.post(
        "/api/v1/auth/register",
        json={"email": f"  {email.upper()}  ", "password": "  secret1"},
    )

    assert response.status_code == 201
    body = response.json()
    assert body["token_type"] == "Bearer"
    assert body["expires_in"] == 900
    assert body["refresh_expires_in"] == 2_592_000
    assert body["user"]["email"] == email
    assert body["user"]["timezone"] == "Europe/Moscow"
    assert body["user"]["created_at"].endswith("+03:00")
    assert "password" not in body["user"]

    payload = jwt.decode(body["access_token"], get_settings().jwt_secret, algorithms=["HS256"])
    assert payload["sub"] == body["user"]["id"]
    assert payload["type"] == "access"
    assert "iat" in payload
    assert "exp" in payload

    session = get_sessionmaker()()
    try:
        user = session.scalar(select(User).where(User.email == email))
        assert user is not None
        assert verify_password("  secret1", user.password_hash)
        assert not verify_password("secret1", user.password_hash)
        stored = session.scalar(
            select(RefreshToken).where(RefreshToken.token_hash == hash_refresh_token(body["refresh_token"]))
        )
        assert stored is not None
        assert stored.token_hash != body["refresh_token"]
    finally:
        session.close()


def test_register_keeps_requested_timezone() -> None:
    response = client.post(
        "/api/v1/auth/register",
        json={"email": _email(), "password": "password1", "timezone": "Asia/Yekaterinburg"},
    )

    assert response.status_code == 201
    user = response.json()["user"]
    assert user["timezone"] == "Asia/Yekaterinburg"
    assert user["created_at"].endswith("+05:00")


def test_register_rejects_duplicate_email() -> None:
    email = _email()
    first = client.post("/api/v1/auth/register", json={"email": email, "password": "password1"})
    second = client.post("/api/v1/auth/register", json={"email": email.upper(), "password": "password2"})

    assert first.status_code == 201
    assert second.status_code == 409
    assert second.json() == {
        "code": "email_taken",
        "message": "Почта уже зарегистрирована.",
        "details": {},
    }


def test_register_reports_all_invalid_fields() -> None:
    response = client.post(
        "/api/v1/auth/register",
        json={"password": "short", "timezone": "Mars/Base"},
    )

    assert response.status_code == 422
    body = response.json()
    assert body["code"] == "validation_error"
    errors = {(item["field"], item["code"]) for item in body["details"]["errors"]}
    assert ("email", "required") in errors
    assert ("password", "too_short") in errors
    assert ("timezone", "invalid_timezone") in errors


def _email() -> str:
    return f"user-{uuid.uuid4().hex}@example.com"
