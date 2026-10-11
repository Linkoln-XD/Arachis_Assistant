import uuid
from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

from fastapi.testclient import TestClient

from app.db.models import Reminder
from app.db.session import get_sessionmaker
from app.main import create_app

client = TestClient(create_app())
MOSCOW = ZoneInfo("Europe/Moscow")


def test_calendar_orders_meetings_reminders_and_dated_tasks() -> None:
    token = _token()
    stranger = _token()
    day = _at(days=3, hour=0)
    previous = day - timedelta(days=1)
    _task(token, "без срока", None)
    task = _task(token, "отчёт", day.date().isoformat())
    client.post(f"/api/v1/tasks/{task['id']}/complete", headers=_auth(token))
    reminder = _reminder(token, "билеты", day)
    _fire(reminder["id"])
    midnight = _meeting(token, "полночь", day, day + timedelta(hours=1))
    later = _meeting(token, "утром", day.replace(hour=9), day.replace(hour=10))
    _meeting(token, "до полуночи", previous.replace(hour=22), previous.replace(hour=23))
    overnight = _meeting(
        token,
        "через полночь",
        previous.replace(hour=23),
        day + timedelta(minutes=30),
        allow_overlap=True,
    )
    _meeting(stranger, "чужая", day.replace(hour=11), day.replace(hour=12))

    listed = client.get(
        "/api/v1/calendar",
        headers=_auth(token),
        params={"from": day.date().isoformat(), "to": day.date().isoformat()},
    )
    only_tasks = client.get(
        "/api/v1/calendar",
        headers=_auth(token),
        params={"from": day.date().isoformat(), "to": day.date().isoformat(), "types": "task"},
    )

    assert listed.status_code == 200
    body = listed.json()
    assert body["from"] == day.date().isoformat()
    assert body["to"] == day.date().isoformat()
    assert body["timezone"] == "Europe/Moscow"
    assert [item["id"] for item in body["items"]] == [
        overnight["id"],
        midnight["id"],
        reminder["id"],
        task["id"],
        later["id"],
    ]
    assert [item["type"] for item in body["items"]] == ["meeting", "meeting", "reminder", "task", "meeting"]
    assert body["items"][3]["status"] == "completed"
    assert body["items"][2]["status"] == "fired"
    assert [item["id"] for item in only_tasks.json()["items"]] == [task["id"]]


def test_same_moment_uses_id_inside_one_kind() -> None:
    token = _token()
    moment = _at(days=4, hour=15)
    first = _reminder(token, "первая", moment)
    second = _reminder(token, "вторая", moment)

    listed = client.get(
        "/api/v1/calendar",
        headers=_auth(token),
        params={"from": moment.date().isoformat(), "to": moment.date().isoformat(), "types": "reminder"},
    )

    assert [item["id"] for item in listed.json()["items"]] == sorted([first["id"], second["id"]])


def test_empty_period_is_successful_and_bounds_are_checked() -> None:
    token = _token(timezone="Asia/Yekaterinburg")

    empty = client.get("/api/v1/calendar", headers=_auth(token), params={"from": "2026-02-01", "to": "2026-02-01"})
    widest = client.get("/api/v1/calendar", headers=_auth(token), params={"from": "2026-01-01", "to": "2027-01-01"})
    too_wide = client.get("/api/v1/calendar", headers=_auth(token), params={"from": "2026-01-01", "to": "2027-01-02"})
    reversed_bounds = client.get(
        "/api/v1/calendar",
        headers=_auth(token),
        params={"from": "2026-10-12", "to": "2026-10-11", "types": "note"},
    )
    missing = client.get("/api/v1/calendar", headers=_auth(token), params={"types": "task, nope"})
    anonymous = client.get("/api/v1/calendar", params={"from": "2026-10-11", "to": "2026-10-11"})

    assert empty.status_code == 200
    assert empty.json() == {
        "from": "2026-02-01",
        "to": "2026-02-01",
        "timezone": "Asia/Yekaterinburg",
        "items": [],
    }
    assert widest.status_code == 200
    assert too_wide.status_code == 422
    assert too_wide.json()["details"]["errors"] == [
        {"field": "from", "code": "invalid_range", "message": "Некорректный диапазон"}
    ]
    assert reversed_bounds.json()["details"]["errors"] == [
        {"field": "from", "code": "invalid_range", "message": "Некорректный диапазон"},
        {"field": "types", "code": "invalid_type", "message": "Некорректный тип"},
    ]
    assert missing.json()["details"]["errors"] == [
        {"field": "from", "code": "required", "message": "Нужно заполнить поле"},
        {"field": "to", "code": "required", "message": "Нужно заполнить поле"},
        {"field": "types", "code": "invalid_type", "message": "Некорректный тип"},
    ]
    assert anonymous.status_code == 401


def _at(*, days: int, hour: int) -> datetime:
    moment = datetime.now(UTC).astimezone(MOSCOW) + timedelta(days=days)
    return moment.replace(hour=hour, minute=0, second=0, microsecond=0)


def _zulu(value: datetime) -> str:
    return value.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def _token(timezone: str = "Europe/Moscow") -> str:
    response = client.post(
        "/api/v1/auth/register",
        json={
            "email": f"calendar-{uuid.uuid4().hex}@example.com",
            "password": "password1",
            "timezone": timezone,
        },
    )
    assert response.status_code == 201
    return str(response.json()["access_token"])


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _task(token: str, description: str, due_on: str | None) -> dict[str, object]:
    payload: dict[str, str] = {"description": description}
    if due_on is not None:
        payload["due_on"] = due_on
    response = client.post("/api/v1/tasks", headers=_auth(token), json=payload)
    assert response.status_code == 201
    body = response.json()
    assert isinstance(body, dict)
    return body


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
    response = client.post(
        "/api/v1/meetings",
        headers=_auth(token),
        json=payload,
    )
    assert response.status_code == 201
    meeting = response.json()["meeting"]
    assert isinstance(meeting, dict)
    return meeting


def _reminder(token: str, text: str, moment: datetime) -> dict[str, object]:
    response = client.post(
        "/api/v1/reminders",
        headers=_auth(token),
        json={"text": text, "fire_at": _zulu(moment)},
    )
    assert response.status_code == 201
    body = response.json()
    assert isinstance(body, dict)
    return body


def _fire(reminder_id: object) -> None:
    session = get_sessionmaker()()
    try:
        reminder = session.get(Reminder, uuid.UUID(str(reminder_id)))
        assert reminder is not None
        reminder.status = "fired"
        reminder.fired_at = datetime.now(UTC)
        session.commit()
    finally:
        session.close()
