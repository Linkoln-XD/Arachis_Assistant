import uuid
from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

from fastapi.testclient import TestClient

from app.db.models import Meeting
from app.db.session import get_sessionmaker
from app.main import create_app

client = TestClient(create_app())
MOSCOW = ZoneInfo("Europe/Moscow")


def test_moving_only_the_start_keeps_the_duration() -> None:
    token = _token()
    start = _at(days=2, hour=13)
    created = _meeting(token, "план", start, start + timedelta(hours=2))
    moved = start + timedelta(hours=3)

    patched = _patch(token, created["id"], {"starts_at": _zulu(moved)})

    assert patched.status_code == 200
    body = patched.json()
    assert body["meeting"]["id"] == created["id"]
    assert body["overlaps"] == []
    assert _parse(body["meeting"]["starts_at"]) == moved.astimezone(UTC)
    assert _parse(body["meeting"]["ends_at"]) - _parse(body["meeting"]["starts_at"]) == timedelta(hours=2)
    assert client.get("/api/v1/meetings", headers=_auth(token)).json()["total"] == 1


def test_sending_both_bounds_replaces_the_interval() -> None:
    token = _token()
    start = _at(days=2, hour=15)
    created = _meeting(token, "план", start, start + timedelta(hours=2))
    new_start = start + timedelta(hours=1)
    new_end = new_start + timedelta(minutes=30)

    patched = _patch(token, created["id"], {"starts_at": _zulu(new_start), "ends_at": _zulu(new_end)})

    assert _parse(patched.json()["meeting"]["starts_at"]) == new_start.astimezone(UTC)
    assert _parse(patched.json()["meeting"]["ends_at"]) == new_end.astimezone(UTC)


def test_overlap_on_move_updates_the_same_meeting() -> None:
    token = _token()
    start = _at(days=3, hour=13)
    first = _meeting(token, "первая", start, start + timedelta(hours=1))
    second = _meeting(token, "вторая", start + timedelta(hours=3), start + timedelta(hours=4))
    moved = start + timedelta(minutes=30)

    blocked = _patch(token, second["id"], {"starts_at": _zulu(moved)})
    shown = client.get(f"/api/v1/meetings/{second['id']}", headers=_auth(token))
    agreed = _patch(token, second["id"], {"starts_at": _zulu(moved), "allow_overlap": True})

    assert blocked.status_code == 409
    assert blocked.json()["code"] == "overlap"
    assert [item["id"] for item in blocked.json()["details"]["conflicts"]] == [first["id"]]
    assert shown.json()["starts_at"] == second["starts_at"]
    assert shown.json()["updated_at"] == second["updated_at"]
    assert agreed.status_code == 200
    assert agreed.json()["meeting"]["id"] == second["id"]
    assert [item["id"] for item in agreed.json()["overlaps"]] == [first["id"]]
    assert client.get("/api/v1/meetings", headers=_auth(token)).json()["total"] == 2


def test_renaming_does_not_check_an_existing_overlap() -> None:
    token = _token()
    start = _at(days=4, hour=11)
    _meeting(token, "первая", start, start + timedelta(hours=1))
    second = _meeting(
        token,
        "вторая",
        start + timedelta(minutes=30),
        start + timedelta(minutes=90),
        allow_overlap=True,
    )

    renamed = _patch(token, second["id"], {"title": "  новое имя  "})

    assert renamed.status_code == 200
    assert renamed.json()["meeting"]["title"] == "новое имя"
    assert renamed.json()["meeting"]["starts_at"] == second["starts_at"]
    assert renamed.json()["meeting"]["ends_at"] == second["ends_at"]
    assert renamed.json()["overlaps"] == []


def test_a_bad_move_leaves_the_meeting_in_place() -> None:
    token = _token()
    start = _at(days=5, hour=12)
    created = _meeting(token, "план", start, start + timedelta(hours=1))
    stale = datetime.now(UTC).replace(microsecond=0) - timedelta(seconds=90)

    past_start = _patch(token, created["id"], {"starts_at": _zulu(stale)})
    too_long = _patch(token, created["id"], {"ends_at": _zulu(start + timedelta(hours=24, seconds=1))})
    same_instant = _patch(token, created["id"], {"ends_at": _zulu(start)})
    shown = client.get(f"/api/v1/meetings/{created['id']}", headers=_auth(token))

    assert past_start.status_code == 422
    assert past_start.json()["details"] == {"field": "starts_at"}
    assert too_long.json()["details"]["errors"][0]["code"] == "duration_too_long"
    assert same_instant.json()["details"]["errors"][0]["code"] == "invalid_interval"
    assert shown.json()["starts_at"] == created["starts_at"]
    assert shown.json()["ends_at"] == created["ends_at"]
    assert shown.json()["updated_at"] == created["updated_at"]


def test_a_new_end_in_the_past_is_rejected_and_a_recent_one_is_kept() -> None:
    token = _token()
    start = _at(days=5, hour=16)
    created = _meeting(token, "уже была", start, start + timedelta(hours=1))
    now = datetime.now(UTC).replace(microsecond=0)
    _place(created["id"], now - timedelta(hours=3), now - timedelta(hours=2))

    rejected = _patch(token, created["id"], {"ends_at": _zulu(now - timedelta(seconds=90))})
    accepted = _patch(token, created["id"], {"ends_at": _zulu(now - timedelta(seconds=30))})

    assert rejected.status_code == 422
    assert rejected.json()["code"] == "in_the_past"
    assert rejected.json()["details"] == {"field": "ends_at"}
    assert _parse(accepted.json()["meeting"]["ends_at"]) == now - timedelta(seconds=30)
    assert _parse(accepted.json()["meeting"]["starts_at"]) == now - timedelta(hours=3)


def test_delete_repeats_with_the_same_key_and_hides_another_users_meeting() -> None:
    token = _token()
    stranger = _token()
    created = _meeting(token, "удалить", _at(days=6, hour=10), _at(days=6, hour=11))

    hidden = client.delete(f"/api/v1/meetings/{created['id']}", headers=_auth(stranger))
    removed = client.delete(
        f"/api/v1/meetings/{created['id']}",
        headers={**_auth(token), "Idempotency-Key": "drop"},
    )
    repeated = client.delete(
        f"/api/v1/meetings/{created['id']}",
        headers={**_auth(token), "Idempotency-Key": "drop"},
    )
    missing = client.delete(f"/api/v1/meetings/{created['id']}", headers=_auth(token))

    assert hidden.status_code == 404
    assert removed.status_code == 204
    assert removed.content == b""
    assert repeated.status_code == 204
    assert repeated.content == b""
    assert missing.status_code == 404
    assert client.get("/api/v1/meetings", headers=_auth(token)).json()["total"] == 0


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
        json={"email": f"move-{uuid.uuid4().hex}@example.com", "password": "password1"},
    )
    assert response.status_code == 201
    return str(response.json()["access_token"])


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _meeting(
    token: str,
    title: str,
    start: datetime,
    end: datetime,
    allow_overlap: bool = False,
) -> dict[str, object]:
    payload: dict[str, object] = {"title": title, "starts_at": _zulu(start), "ends_at": _zulu(end)}
    if allow_overlap:
        payload["allow_overlap"] = True
    response = client.post("/api/v1/meetings", headers=_auth(token), json=payload)
    assert response.status_code == 201
    meeting = response.json()["meeting"]
    assert isinstance(meeting, dict)
    return meeting


def _patch(token: str, meeting_id: object, payload: dict[str, object]):
    return client.patch(f"/api/v1/meetings/{meeting_id}", headers=_auth(token), json=payload)


def _place(meeting_id: object, start: datetime, end: datetime) -> None:
    session = get_sessionmaker()()
    try:
        meeting = session.get(Meeting, uuid.UUID(str(meeting_id)))
        assert meeting is not None
        meeting.starts_at = start
        meeting.ends_at = end
        session.commit()
    finally:
        session.close()
