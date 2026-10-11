from fastapi.testclient import TestClient

from app.config import get_settings
from app.main import create_app

client = TestClient(create_app())


def test_browser_from_the_configured_origin_can_call_the_api() -> None:
    origin = get_settings().cors_origin_list()[0]
    preflight = client.options(
        "/api/v1/tasks",
        headers={
            "Origin": origin,
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "authorization,content-type,idempotency-key",
        },
    )
    health = client.get("/api/v1/health", headers={"Origin": origin})

    assert preflight.status_code == 200
    assert preflight.headers["access-control-allow-origin"] == origin
    allowed = preflight.headers["access-control-allow-headers"].lower()
    assert "authorization" in allowed
    assert "content-type" in allowed
    assert "idempotency-key" in allowed
    assert health.status_code == 200
    assert health.headers["access-control-allow-origin"] == origin
    assert "location" in health.headers["access-control-expose-headers"].lower()
    assert health.json() == {"status": "ok"}


def test_unknown_origin_is_not_allowed() -> None:
    response = client.get("/api/v1/health", headers={"Origin": "http://evil.example"})

    assert response.status_code == 200
    assert "access-control-allow-origin" not in response.headers
