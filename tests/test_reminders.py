import uuid
from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

from fastapi.testclient import TestClient

from app.db.models import Reminder
from app.db.session import get_sessionmaker
from app.main import create_app

client = TestClient(create_app())
MOSCOW = ZoneInfo("Europe/Moscow")


def test_create_stores_a_pending_reminder_without_firing_it() -> None:
    token = _token()
    moment = _at(days=1, hour=18)

    created = _post(token, {"text": "  купить билеты  ", "fire_at": _zulu(moment)}, None)

    assert created.status_code == 201
    body = created.json()
    assert created.headers["location"].endswith(f"/api/v1/reminders/{body['id']}")
    assert body["type"] == "reminder"
    assert body["text"] == "купить билеты"
    assert body["status"] == "pending"
    assert body["fired_at"] is None
    assert body["source_id"] is None
    assert body["fire_at"].endswith("+03:00")
    assert _parse(body["fire_at"]) == moment.astimezone(UTC)
    shown = client.get(f"/api/v1/reminders/{body['id']}", headers=_auth(token))
    assert shown.json() == body


def test_past_moment_is_rejected_and_a_recent_one_is_kept() -> None:
    token = _token()
    now = datetime.now(UTC).replace(microsecond=0)

    rejected = _post(token, {"text": "поздно", "fire_at": _zulu(now - timedelta(seconds=90))}, None)
    accepted = _post(token, {"text": "сейчас", "fire_at": _zulu(now - timedelta(seconds=30))}, None)

    assert rejected.status_code == 422
    assert rejected.json()["code"] == "in_the_past"
    assert rejected.json()["details"] == {"field": "fire_at"}
    assert accepted.status_code == 201
    assert client.get("/api/v1/reminders", headers=_auth(token)).json()["total"] == 1


def test_list_filters_by_status_and_local_day() -> None:
    token = _token()
    first = _at(days=2, hour=10)
    second = _at(days=3, hour=10)
    midnight = _at(days=3, hour=0)
    early = _create(token, "утро", first)
    later = _create(token, "следующий день", second)
    boundary = _create(token, "полночь", midnight)
    same = _create(token, "то же время", second)
    _fire(later["id"])

    day = first.astimezone(MOSCOW).date().isoformat()
    next_day = second.astimezone(MOSCOW).date().isoformat()
    listed = client.get("/api/v1/reminders", headers=_auth(token), params={"from": day, "to": day})
    both = client.get("/api/v1/reminders", headers=_auth(token), params={"from": day, "to": next_day})
    pending = client.get("/api/v1/reminders", headers=_auth(token), params={"status": "pending"})
    fired = client.get("/api/v1/reminders", headers=_auth(token), params={"status": "fired"})
    only_from = client.get("/api/v1/reminders", headers=_auth(token), params={"from": day})

    assert [item["text"] for item in listed.json()["items"]] == ["утро"]
    assert [item["id"] for item in both.json()["items"][:2]] == [early["id"], boundary["id"]]
    assert [item["id"] for item in both.json()["items"][2:]] == sorted([later["id"], same["id"]])
    assert early["id"] in [item["id"] for item in pending.json()["items"]]
    assert [item["id"] for item in fired.json()["items"]] == [later["id"]]
    assert only_from.status_code == 422
    assert only_from.json()["details"]["errors"][0]["field"] == "to"


def test_patch_changes_only_sent_fields_and_rejects_a_past_moment() -> None:
    token = _token()
    created = _create(token, "билеты", _at(days=4, hour=18))
    moved = _at(days=4, hour=20)
    stale = datetime.now(UTC).replace(microsecond=0) - timedelta(seconds=90)

    renamed = client.patch(
        f"/api/v1/reminders/{created['id']}",
        headers=_auth(token),
        json={"text": "  паспорт  "},
    )
    rejected = client.patch(
        f"/api/v1/reminders/{created['id']}",
        headers=_auth(token),
        json={"text": "не сохранять", "fire_at": _zulu(stale)},
    )
    shifted = client.patch(
        f"/api/v1/reminders/{created['id']}",
        headers=_auth(token),
        json={"fire_at": _zulu(moved)},
    )

    assert renamed.status_code == 200
    assert renamed.json()["text"] == "паспорт"
    assert renamed.json()["fire_at"] == created["fire_at"]
    assert rejected.status_code == 422
    assert rejected.json()["details"] == {"field": "fire_at"}
    shown = client.get(f"/api/v1/reminders/{created['id']}", headers=_auth(token))
    assert shown.json()["text"] == "паспорт"
    assert shifted.json()["text"] == "паспорт"
    assert _parse(shifted.json()["fire_at"]) == moved.astimezone(UTC)
    assert shifted.json()["status"] == "pending"


def test_moving_a_fired_reminder_forward_makes_it_pending_again() -> None:
    token = _token()
    created = _create(token, "старое", _at(days=5, hour=9))
    fired_at = datetime.now(UTC).replace(microsecond=0)
    _fire(created["id"], fired_at)
    future = _at(days=5, hour=12)

    renamed = client.patch(
        f"/api/v1/reminders/{created['id']}",
        headers=_auth(token),
        json={"text": "уточнение"},
    )
    reopened = client.patch(
        f"/api/v1/reminders/{created['id']}",
        headers=_auth(token),
        json={"fire_at": _zulu(future)},
    )

    assert renamed.json()["status"] == "fired"
    assert _parse(renamed.json()["fired_at"]) == fired_at
    assert renamed.json()["text"] == "уточнение"
    assert reopened.json()["status"] == "pending"
    assert reopened.json()["fired_at"] is None
    assert reopened.json()["text"] == "уточнение"
    assert _parse(reopened.json()["fire_at"]) == future.astimezone(UTC)


def test_delete_and_idempotent_create_stay_with_the_owner() -> None:
    token = _token()
    stranger = _token()
    moment = _at(days=6, hour=15)
    payload = {"text": "позвонить", "fire_at": _zulu(moment)}
    first = _post(token, payload, "once")
    second = _post(token, payload, "once")
    hidden = client.get(f"/api/v1/reminders/{first.json()['id']}", headers=_auth(stranger))
    assert second.json() == first.json()
    assert client.get("/api/v1/reminders", headers=_auth(token)).json()["total"] == 1
    assert hidden.status_code == 404

    removed = client.delete(
        f"/api/v1/reminders/{first.json()['id']}",
        headers={**_auth(token), "Idempotency-Key": "drop"},
    )
    repeated = client.delete(
        f"/api/v1/reminders/{first.json()['id']}",
        headers={**_auth(token), "Idempotency-Key": "drop"},
    )
    missing = client.delete(f"/api/v1/reminders/{first.json()['id']}", headers=_auth(token))
    anonymous = client.post("/api/v1/reminders", json=payload)

    assert removed.status_code == 204
    assert removed.content == b""
    assert repeated.status_code == 204
    assert missing.status_code == 404
    assert anonymous.status_code == 401
    assert client.get("/api/v1/reminders", headers=_auth(token)).json()["total"] == 0


def _at(*, days: int, hour: int) -> datetime:
    moment = datetime.now(UTC).astimezone(MOSCOW) + timedelta(days=days)
    return moment.replace(hour=hour, minute=0, second=0, microsecond=0)


def _zulu(value: datetime) -> str:
    return value.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def _parse(value: str) -> datetime:
    return datetime.fromisoformat(value).astimezone(UTC).replace(microsecond=0)


def _token() -> str:
    response = client.post(
        "/api/v1/auth/register",
        json={"email": f"remind-{uuid.uuid4().hex}@example.com", "password": "password1"},
    )
    assert response.status_code == 201
    return str(response.json()["access_token"])


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _post(token: str, payload: dict[str, str], key: str | None):
    headers = _auth(token)
    if key is not None:
        headers["Idempotency-Key"] = key
    return client.post("/api/v1/reminders", headers=headers, json=payload)


def _create(token: str, text: str, moment: datetime) -> dict[str, object]:
    response = _post(token, {"text": text, "fire_at": _zulu(moment)}, None)
    assert response.status_code == 201
    body = response.json()
    assert isinstance(body, dict)
    return body


def _fire(reminder_id: object, fired_at: datetime | None = None) -> None:
    session = get_sessionmaker()()
    try:
        reminder = session.get(Reminder, uuid.UUID(str(reminder_id)))
        assert reminder is not None
        reminder.status = "fired"
        reminder.fired_at = fired_at or datetime.now(UTC)
        session.commit()
    finally:
        session.close()
