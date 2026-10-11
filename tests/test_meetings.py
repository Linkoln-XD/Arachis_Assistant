import uuid
from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

from fastapi.testclient import TestClient

from app.db.models import Meeting
from app.db.session import get_sessionmaker
from app.main import create_app

client = TestClient(create_app())
MOSCOW = ZoneInfo("Europe/Moscow")


def test_create_defaults_to_one_hour_and_shows_the_user_timezone() -> None:
    token = _token()
    start = _future(hours=3)

    created = _post(token, {"title": "  встреча с дизайнером  ", "starts_at": _zulu(start)}, None)

    assert created.status_code == 201
    body = created.json()
    meeting = body["meeting"]
    assert created.headers["location"].endswith(f"/api/v1/meetings/{meeting['id']}")
    assert body["overlaps"] == []
    assert meeting["type"] == "meeting"
    assert meeting["title"] == "встреча с дизайнером"
    assert meeting["source_id"] is None
    assert meeting["starts_at"].endswith("+03:00")
    assert meeting["created_at"].endswith("+03:00")
    assert _parse(meeting["starts_at"]) == start
    assert _parse(meeting["ends_at"]) - _parse(meeting["starts_at"]) == timedelta(hours=1)

    shown = client.get(f"/api/v1/meetings/{meeting['id']}", headers=_auth(token))
    assert shown.status_code == 200
    assert shown.json() == meeting


def test_rejects_past_start_and_a_bad_duration() -> None:
    token = _token()
    recent = datetime.now(UTC).replace(microsecond=0) - timedelta(seconds=30)
    stale = datetime.now(UTC).replace(microsecond=0) - timedelta(seconds=90)
    future = _future(hours=4)

    allowed = _post(token, {"title": "только что", "starts_at": _zulu(recent)}, None)
    rejected = _post(token, {"title": "вчера", "starts_at": _zulu(stale)}, None)
    too_long = _post(
        token,
        {"title": "сутки", "starts_at": _zulu(future), "ends_at": _zulu(future + timedelta(hours=24, seconds=1))},
        None,
    )
    exact = _post(
        token,
        {"title": "ровно сутки", "starts_at": _zulu(future + timedelta(hours=2)), "ends_at": _zulu(future + timedelta(hours=26))},
        None,
    )
    backwards = _post(
        token,
        {"title": "наоборот", "starts_at": _zulu(future), "ends_at": _zulu(future)},
        None,
    )

    assert allowed.status_code == 201
    assert rejected.status_code == 422
    assert rejected.json()["code"] == "in_the_past"
    assert rejected.json()["details"] == {"field": "starts_at"}
    assert too_long.status_code == 422
    assert too_long.json()["details"]["errors"][0]["code"] == "duration_too_long"
    assert exact.status_code == 201
    assert backwards.json()["details"]["errors"][0] == {
        "field": "ends_at",
        "code": "invalid_interval",
        "message": "Конец должен быть позже начала",
    }
    listed = client.get("/api/v1/meetings", headers=_auth(token))
    assert listed.json()["total"] == 2


def test_overlap_needs_consent_and_touching_edges_do_not_count() -> None:
    token = _token()
    start = _at(days=2, hour=13)
    first = _post(token, {"title": "первая", "starts_at": _zulu(start), "ends_at": _zulu(start + timedelta(hours=1))}, "step-1")
    touching = _post(
        token,
        {
            "title": "следом",
            "starts_at": _zulu(start + timedelta(hours=1)),
            "ends_at": _zulu(start + timedelta(hours=2)),
        },
        None,
    )
    inside = start + timedelta(minutes=15)
    blocked = _post(
        token,
        {"title": "поверх", "starts_at": _zulu(inside), "ends_at": _zulu(inside + timedelta(minutes=30))},
        "step-2",
    )
    same_key = _post(
        token,
        {
            "title": "поверх",
            "starts_at": _zulu(inside),
            "ends_at": _zulu(inside + timedelta(minutes=30)),
            "allow_overlap": True,
        },
        "step-2",
    )
    agreed = _post(
        token,
        {
            "title": "поверх",
            "starts_at": _zulu(inside),
            "ends_at": _zulu(inside + timedelta(minutes=30)),
            "allow_overlap": True,
        },
        "step-3",
    )

    assert first.status_code == 201
    assert touching.status_code == 201
    assert touching.json()["overlaps"] == []
    assert blocked.status_code == 409
    assert blocked.json()["code"] == "overlap"
    assert [item["id"] for item in blocked.json()["details"]["conflicts"]] == [first.json()["meeting"]["id"]]
    assert same_key.status_code == 409
    assert same_key.json()["code"] == "idempotency_conflict"
    assert agreed.status_code == 201
    assert [item["id"] for item in agreed.json()["overlaps"]] == [first.json()["meeting"]["id"]]
    listed = client.get("/api/v1/meetings", headers=_auth(token))
    assert listed.json()["total"] == 3


def test_another_users_meeting_is_not_a_conflict() -> None:
    owner = _token()
    other = _token()
    start = _at(days=3, hour=10)
    payload = {"title": "созвон", "starts_at": _zulu(start), "ends_at": _zulu(start + timedelta(hours=1))}

    _post(owner, payload, None)
    created = _post(other, payload, None)
    hidden = client.get(f"/api/v1/meetings/{created.json()['meeting']['id']}", headers=_auth(owner))

    assert created.status_code == 201
    assert created.json()["overlaps"] == []
    assert hidden.status_code == 404
    assert client.get("/api/v1/meetings", headers=_auth(owner)).json()["total"] == 1


def test_list_uses_an_inclusive_local_day_and_keeps_order() -> None:
    token = _token()
    first_day = _at(days=4, hour=10)
    second_day = _at(days=5, hour=9)
    overnight = _at(days=4, hour=23, minute=30)
    same_start_later = _at(days=5, hour=9)
    _post(token, {"title": "утро", "starts_at": _zulu(first_day), "ends_at": _zulu(first_day + timedelta(hours=1))}, None)
    second = _post(
        token,
        {"title": "следующий день", "starts_at": _zulu(second_day), "ends_at": _zulu(second_day + timedelta(hours=1))},
        None,
    )
    _post(
        token,
        {
            "title": "через полночь",
            "starts_at": _zulu(overnight),
            "ends_at": _zulu(overnight + timedelta(hours=1)),
        },
        None,
    )
    tied = _post(
        token,
        {
            "title": "то же время",
            "starts_at": _zulu(same_start_later),
            "ends_at": _zulu(same_start_later + timedelta(hours=1)),
            "allow_overlap": True,
        },
        None,
    )

    day = client.get(
        "/api/v1/meetings",
        headers=_auth(token),
        params={"from": first_day.astimezone(MOSCOW).date().isoformat(), "to": first_day.astimezone(MOSCOW).date().isoformat()},
    )
    both = client.get(
        "/api/v1/meetings",
        headers=_auth(token),
        params={
            "from": first_day.astimezone(MOSCOW).date().isoformat(),
            "to": second_day.astimezone(MOSCOW).date().isoformat(),
        },
    )
    next_day = client.get(
        "/api/v1/meetings",
        headers=_auth(token),
        params={"from": second_day.astimezone(MOSCOW).date().isoformat(), "to": second_day.astimezone(MOSCOW).date().isoformat()},
    )

    assert [item["title"] for item in day.json()["items"]] == ["утро", "через полночь"]
    assert [item["title"] for item in both.json()["items"][:2]] == ["утро", "через полночь"]
    assert [item["id"] for item in both.json()["items"][2:]] == sorted(
        [second.json()["meeting"]["id"], tied.json()["meeting"]["id"]]
    )
    next_titles = [item["title"] for item in next_day.json()["items"]]
    assert "через полночь" in next_titles
    assert "утро" not in next_titles
    tied_ids = [item["id"] for item in next_day.json()["items"] if item["title"] in {"следующий день", "то же время"}]
    assert tied_ids == sorted([second.json()["meeting"]["id"], tied.json()["meeting"]["id"]])


def test_meeting_that_ends_at_the_window_edge_stays_inside() -> None:
    token = _token()
    start = _at(days=6, hour=23)
    ends = _at(days=7, hour=0)
    _post(token, {"title": "до полуночи", "starts_at": _zulu(start), "ends_at": _zulu(ends)}, None)
    _post(token, {"title": "после полуночи", "starts_at": _zulu(ends), "ends_at": _zulu(ends + timedelta(hours=1))}, None)
    day = start.astimezone(MOSCOW).date().isoformat()
    next_day = ends.astimezone(MOSCOW).date().isoformat()

    first = client.get("/api/v1/meetings", headers=_auth(token), params={"from": day, "to": day})
    second = client.get("/api/v1/meetings", headers=_auth(token), params={"from": next_day, "to": next_day})

    assert [item["title"] for item in first.json()["items"]] == ["до полуночи"]
    assert [item["title"] for item in second.json()["items"]] == ["после полуночи"]


def test_same_key_replays_the_created_meeting() -> None:
    token = _token()
    start = _at(days=8, hour=15)
    payload = {"title": "планёрка", "starts_at": _zulu(start)}
    first = _post(token, payload, "once")
    second = _post(token, payload, "once")
    _remove(first.json()["meeting"]["id"])
    replay = _post(token, payload, "once")

    assert second.json() == first.json()
    assert replay.status_code == 201
    assert replay.json()["meeting"]["id"] == first.json()["meeting"]["id"]
    assert client.get("/api/v1/meetings", headers=_auth(token)).json()["total"] == 0


def test_list_requires_both_bounds_and_pages() -> None:
    token = _token()
    for hour in (9, 10, 11):
        start = _at(days=9, hour=hour)
        _post(token, {"title": str(hour), "starts_at": _zulu(start), "ends_at": _zulu(start + timedelta(hours=1))}, None)
    day = _at(days=9, hour=9).astimezone(MOSCOW).date().isoformat()

    only_from = client.get("/api/v1/meetings", headers=_auth(token), params={"from": day})
    page = client.get("/api/v1/meetings", headers=_auth(token), params={"limit": 2, "offset": 1})
    anonymous = client.post("/api/v1/meetings", json={"title": "нет", "starts_at": _zulu(_future(hours=1))})

    assert only_from.status_code == 422
    assert only_from.json()["details"]["errors"][0] == {
        "field": "to",
        "code": "required",
        "message": "Нужно заполнить поле",
    }
    assert page.json()["total"] == 3
    assert [item["title"] for item in page.json()["items"]] == ["10", "11"]
    assert anonymous.status_code == 401


def _future(*, hours: int) -> datetime:
    return datetime.now(UTC).replace(microsecond=0) + timedelta(hours=hours)


def _at(*, days: int, hour: int, minute: int = 0) -> datetime:
    moment = datetime.now(UTC).astimezone(MOSCOW) + timedelta(days=days)
    return moment.replace(hour=hour, minute=minute, second=0, microsecond=0)


def _zulu(value: datetime) -> str:
    return value.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def _parse(value: str) -> datetime:
    return datetime.fromisoformat(value).astimezone(UTC)


def _token() -> str:
    response = client.post(
        "/api/v1/auth/register",
        json={"email": f"meeting-{uuid.uuid4().hex}@example.com", "password": "password1"},
    )
    assert response.status_code == 201
    return str(response.json()["access_token"])


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _post(token: str, payload: dict[str, object], key: str | None):
    headers = _auth(token)
    if key is not None:
        headers["Idempotency-Key"] = key
    return client.post("/api/v1/meetings", headers=headers, json=payload)


def _remove(meeting_id: str) -> None:
    session = get_sessionmaker()()
    try:
        meeting = session.get(Meeting, uuid.UUID(meeting_id))
        assert meeting is not None
        session.delete(meeting)
        session.commit()
    finally:
        session.close()
