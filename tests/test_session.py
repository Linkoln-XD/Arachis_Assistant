import uuid
from datetime import UTC, datetime, timedelta

import jwt
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.auth.security import hash_refresh_token
from app.config import get_settings
from app.db.models import RefreshToken
from app.db.session import get_sessionmaker
from app.main import create_app

client = TestClient(create_app())


@pytest.fixture(autouse=True)
def reset_login_limit() -> None:
    client.app.state.login_rate_limiter.reset()


def test_login_opens_profile() -> None:
    registered = _register()
    email = registered["user"]["email"]

    login = client.post(
        "/api/v1/auth/login",
        json={"email": f"  {email.upper()}  ", "password": "password1"},
    )

    assert login.status_code == 200
    body = login.json()
    assert body["user"]["id"] == registered["user"]["id"]
    assert body["token_type"] == "Bearer"
    profile = client.get("/api/v1/auth/me", headers=_auth(body["access_token"]))
    assert profile.status_code == 200
    assert profile.json()["email"] == email


def test_login_uses_the_same_error_for_unknown_user_and_wrong_password() -> None:
    registered = _register()
    wrong_password = client.post(
        "/api/v1/auth/login",
        json={"email": registered["user"]["email"], "password": "wrong-password"},
    )
    unknown_user = client.post(
        "/api/v1/auth/login",
        json={"email": _email(), "password": "password1"},
    )

    assert wrong_password.status_code == 401
    assert unknown_user.status_code == 401
    assert wrong_password.json() == unknown_user.json()
    assert wrong_password.json()["code"] == "invalid_credentials"


def test_refresh_replaces_token_and_rejects_reuse() -> None:
    registered = _register()
    rotated = client.post("/api/v1/auth/refresh", json={"refresh_token": registered["refresh_token"]})
    reused = client.post("/api/v1/auth/refresh", json={"refresh_token": registered["refresh_token"]})
    fresh = client.post("/api/v1/auth/refresh", json={"refresh_token": rotated.json()["refresh_token"]})

    assert rotated.status_code == 200
    assert reused.status_code == 401
    assert reused.json()["code"] == "invalid_refresh"
    assert fresh.status_code == 200
    assert fresh.json()["refresh_token"] != rotated.json()["refresh_token"]


def test_expired_refresh_token_is_rejected() -> None:
    registered = _register()
    session = get_sessionmaker()()
    try:
        stored = session.scalar(
            select(RefreshToken).where(RefreshToken.token_hash == hash_refresh_token(registered["refresh_token"]))
        )
        assert stored is not None
        stored.expires_at = datetime.now(UTC) - timedelta(minutes=1)
        session.commit()
    finally:
        session.close()

    response = client.post("/api/v1/auth/refresh", json={"refresh_token": registered["refresh_token"]})

    assert response.status_code == 401
    assert response.json()["code"] == "invalid_refresh"


def test_logout_can_be_repeated_and_keeps_access_token() -> None:
    registered = _register()
    token = registered["refresh_token"]

    first = client.post("/api/v1/auth/logout", json={"refresh_token": token})
    second = client.post("/api/v1/auth/logout", json={"refresh_token": token})
    unknown = client.post("/api/v1/auth/logout", json={"refresh_token": "never-issued"})
    refresh = client.post("/api/v1/auth/refresh", json={"refresh_token": token})
    profile = client.get("/api/v1/auth/me", headers=_auth(registered["access_token"]))

    assert first.status_code == 204
    assert first.content == b""
    assert second.status_code == 204
    assert unknown.status_code == 204
    assert refresh.status_code == 401
    assert profile.status_code == 200


def test_expired_access_token_is_distinct_from_a_bad_one() -> None:
    registered = _register()
    now = datetime.now(UTC)
    expired = jwt.encode(
        {
            "sub": registered["user"]["id"],
            "iat": int((now - timedelta(minutes=20)).timestamp()),
            "exp": int((now - timedelta(minutes=5)).timestamp()),
            "type": "access",
        },
        get_settings().jwt_secret,
        algorithm="HS256",
    )

    missing = client.get("/api/v1/auth/me")
    malformed = client.get("/api/v1/auth/me", headers={"Authorization": "Bearer not-a-token"})
    stale = client.get("/api/v1/auth/me", headers=_auth(expired))

    assert missing.status_code == 401
    assert missing.json()["code"] == "unauthorized"
    assert malformed.status_code == 401
    assert malformed.json()["code"] == "unauthorized"
    assert stale.status_code == 401
    assert stale.json()["code"] == "token_expired"


def test_timezone_change_keeps_the_same_instant() -> None:
    registered = _register()
    before = datetime.fromisoformat(registered["user"]["created_at"])

    response = client.patch(
        "/api/v1/auth/me",
        headers=_auth(registered["access_token"]),
        json={"timezone": "Asia/Yekaterinburg"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["timezone"] == "Asia/Yekaterinburg"
    assert body["created_at"].endswith("+05:00")
    assert datetime.fromisoformat(body["created_at"]) == before


def test_login_is_limited_per_address() -> None:
    for _ in range(10):
        response = client.post(
            "/api/v1/auth/login",
            json={"email": "nobody@example.com", "password": "password1"},
        )
        assert response.status_code == 401

    blocked = client.post(
        "/api/v1/auth/login",
        json={"email": "nobody@example.com", "password": "password1"},
    )

    assert blocked.status_code == 429
    assert blocked.json()["code"] == "too_many_requests"


def _register() -> dict[str, object]:
    response = client.post(
        "/api/v1/auth/register",
        json={"email": _email(), "password": "password1"},
    )
    assert response.status_code == 201
    body = response.json()
    assert isinstance(body, dict)
    return body


def _email() -> str:
    return f"user-{uuid.uuid4().hex}@example.com"


def _auth(token: object) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}
