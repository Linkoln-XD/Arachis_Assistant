import uuid
from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

from fastapi.testclient import TestClient
from sqlalchemy import select

from app.db.models import IdempotencyKey, Task
from app.db.session import get_sessionmaker
from app.main import create_app

client = TestClient(create_app())


def test_patch_changes_only_sent_fields_and_can_clear_the_due_date() -> None:
    token = _token()
    today = _today()
    created = _create(token, "отчёт", today.isoformat())

    renamed = client.patch(
        f"/api/v1/tasks/{created['id']}",
        headers=_auth(token),
        json={"description": "  черновик  "},
    )
    cleared = client.patch(
        f"/api/v1/tasks/{created['id']}",
        headers=_auth(token),
        json={"due_on": None},
    )

    assert renamed.status_code == 200
    assert renamed.json()["description"] == "черновик"
    assert renamed.json()["due_on"] == today.isoformat()
    assert renamed.json()["updated_at"] != created["updated_at"]
    assert cleared.json()["description"] == "черновик"
    assert cleared.json()["due_on"] is None


def test_patch_rejects_a_past_due_date_and_leaves_the_task_unchanged() -> None:
    token = _token()
    today = _today()
    created = _create(token, "отчёт", today.isoformat())
    yesterday = (today - timedelta(days=1)).isoformat()

    rejected = client.patch(
        f"/api/v1/tasks/{created['id']}",
        headers=_auth(token),
        json={"description": "новое", "due_on": yesterday},
    )
    shown = client.get(f"/api/v1/tasks/{created['id']}", headers=_auth(token))

    assert rejected.status_code == 422
    assert rejected.json()["code"] == "in_the_past"
    assert rejected.json()["details"] == {"field": "due_on"}
    assert shown.json()["description"] == "отчёт"
    assert shown.json()["due_on"] == today.isoformat()
    assert shown.json()["updated_at"] == created["updated_at"]


def test_patch_does_not_change_status() -> None:
    token = _token()
    created = _create(token, "отчёт")
    completed = client.post(f"/api/v1/tasks/{created['id']}/complete", headers=_auth(token))
    patched = client.patch(
        f"/api/v1/tasks/{created['id']}",
        headers=_auth(token),
        json={"description": "уточнение", "status": "active"},
    )

    assert patched.status_code == 200
    assert patched.json()["status"] == "completed"
    assert patched.json()["completed_at"] == completed.json()["task"]["completed_at"]


def test_complete_and_reopen_are_safe_to_repeat() -> None:
    token = _token()
    today = _today()
    created = _create(token, "отчёт", today.isoformat())
    _set_due(created["id"], today - timedelta(days=2))

    completed = client.post(f"/api/v1/tasks/{created['id']}/complete", headers=_auth(token))
    repeated = client.post(f"/api/v1/tasks/{created['id']}/complete", headers=_auth(token))
    reopened = client.post(f"/api/v1/tasks/{created['id']}/reopen", headers=_auth(token))
    reopened_again = client.post(f"/api/v1/tasks/{created['id']}/reopen", headers=_auth(token))

    assert completed.status_code == 200
    assert completed.json()["status_changed"] is True
    assert completed.json()["task"]["status"] == "completed"
    assert completed.json()["task"]["completed_at"] is not None
    assert repeated.json()["status_changed"] is False
    assert repeated.json()["task"]["completed_at"] == completed.json()["task"]["completed_at"]
    assert repeated.json()["task"]["updated_at"] == completed.json()["task"]["updated_at"]
    assert reopened.json()["status_changed"] is True
    assert reopened.json()["task"]["status"] == "active"
    assert reopened.json()["task"]["completed_at"] is None
    assert reopened.json()["task"]["due_on"] == (today - timedelta(days=2)).isoformat()
    assert reopened_again.json()["status_changed"] is False


def test_delete_without_a_key_is_gone_on_the_second_try() -> None:
    token = _token()
    stranger = _token()
    created = _create(token, "отчёт")

    hidden = client.delete(f"/api/v1/tasks/{created['id']}", headers=_auth(stranger))
    removed = client.delete(f"/api/v1/tasks/{created['id']}", headers=_auth(token))
    missing = client.delete(f"/api/v1/tasks/{created['id']}", headers=_auth(token))

    assert hidden.status_code == 404
    assert hidden.json()["code"] == "not_found"
    assert removed.status_code == 204
    assert removed.content == b""
    assert missing.status_code == 404
    shown = client.get(f"/api/v1/tasks/{created['id']}", headers=_auth(token))
    assert shown.status_code == 404


def test_same_idempotency_key_replays_create_and_rejects_a_different_body() -> None:
    token = _token()
    key = str(uuid.uuid4())
    payload = {"description": "отчёт", "due_on": _today().isoformat()}

    first = _post(token, payload, key)
    second = _post(token, payload, key)
    conflict = _post(token, {"description": "другое"}, key)
    listed = client.get("/api/v1/tasks", headers=_auth(token))

    assert first.status_code == 201
    assert second.status_code == 201
    assert second.json() == first.json()
    assert second.headers["location"] == first.headers["location"]
    assert conflict.status_code == 409
    assert conflict.json()["code"] == "idempotency_conflict"
    assert listed.json()["total"] == 1


def test_create_without_a_key_makes_a_new_task_each_time() -> None:
    token = _token()
    first = _post(token, {"description": "первая"}, None)
    second = _post(token, {"description": "первая"}, None)

    assert first.json()["id"] != second.json()["id"]


def test_expired_idempotency_key_can_be_used_again() -> None:
    token = _token()
    key = f"again-{uuid.uuid4().hex}"
    first = _post(token, {"description": "первая"}, key)
    _expire(key)

    second = _post(token, {"description": "вторая"}, key)
    listed = client.get("/api/v1/tasks", headers=_auth(token))

    assert first.status_code == 201
    assert second.status_code == 201
    assert second.json()["id"] != first.json()["id"]
    assert listed.json()["total"] == 2


def test_delete_with_the_same_key_stays_successful() -> None:
    token = _token()
    created = _create(token, "отчёт")
    key = "delete-once"
    headers = {**_auth(token), "Idempotency-Key": key}

    first = client.delete(f"/api/v1/tasks/{created['id']}", headers=headers)
    second = client.delete(f"/api/v1/tasks/{created['id']}", headers=headers)
    missing = client.delete(f"/api/v1/tasks/{created['id']}", headers=_auth(token))

    assert first.status_code == 204
    assert first.content == b""
    assert second.status_code == 204
    assert second.content == b""
    assert missing.status_code == 404


def test_idempotency_key_has_a_length_limit() -> None:
    token = _token()
    response = _post(token, {"description": "отчёт"}, "k" * 129)
    listed = client.get("/api/v1/tasks", headers=_auth(token))

    assert response.status_code == 422
    assert response.json()["details"]["errors"] == [
        {"field": "Idempotency-Key", "code": "too_long", "message": "Слишком длинное значение"}
    ]
    assert listed.json()["total"] == 0


def test_the_same_key_belongs_to_one_user_and_one_path() -> None:
    owner = _token()
    other = _token()
    key = "shared"
    owner_task = _post(owner, {"description": "моё"}, key)
    other_task = _post(other, {"description": "чужое"}, key)
    removed = client.delete(
        f"/api/v1/tasks/{owner_task.json()['id']}",
        headers={**_auth(owner), "Idempotency-Key": key},
    )

    assert owner_task.json()["id"] != other_task.json()["id"]
    assert removed.status_code == 204
    assert client.get("/api/v1/tasks", headers=_auth(other)).json()["total"] == 1


def _today():
    return datetime.now(UTC).astimezone(ZoneInfo("Europe/Moscow")).date()


def _token() -> str:
    response = client.post(
        "/api/v1/auth/register",
        json={"email": f"change-{uuid.uuid4().hex}@example.com", "password": "password1"},
    )
    assert response.status_code == 201
    return str(response.json()["access_token"])


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _create(token: str, description: str, due_on: str | None = None) -> dict[str, object]:
    payload: dict[str, str] = {"description": description}
    if due_on is not None:
        payload["due_on"] = due_on
    response = _post(token, payload, None)
    assert response.status_code == 201
    body = response.json()
    assert isinstance(body, dict)
    return body


def _post(token: str, payload: dict[str, str], key: str | None):
    headers = _auth(token)
    if key is not None:
        headers["Idempotency-Key"] = key
    return client.post("/api/v1/tasks", headers=headers, json=payload)


def _set_due(task_id: str, due) -> None:
    session = get_sessionmaker()()
    try:
        task = session.get(Task, uuid.UUID(task_id))
        assert task is not None
        task.due_on = due
        session.commit()
    finally:
        session.close()


def _expire(key: str) -> None:
    session = get_sessionmaker()()
    try:
        stored = session.scalar(select(IdempotencyKey).where(IdempotencyKey.key == key))
        assert stored is not None
        stored.expires_at = datetime.now(UTC) - timedelta(seconds=1)
        session.commit()
    finally:
        session.close()
