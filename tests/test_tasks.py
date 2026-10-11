import uuid
from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

from fastapi.testclient import TestClient

from app.db.models import Task
from app.db.session import get_sessionmaker
from app.main import create_app

client = TestClient(create_app())


def test_create_undated_task_and_read_it_back() -> None:
    token = _token()
    created = client.post(
        "/api/v1/tasks",
        headers=_auth(token),
        json={"description": "  купить билеты  "},
    )

    assert created.status_code == 201
    body = created.json()
    assert created.headers["location"].endswith(f"/api/v1/tasks/{body['id']}")
    assert body["type"] == "task"
    assert body["description"] == "купить билеты"
    assert body["due_on"] is None
    assert body["status"] == "active"
    assert body["completed_at"] is None
    assert body["source_id"] is None
    assert body["created_at"].endswith("+03:00")
    assert body["updated_at"] == body["created_at"]

    shown = client.get(f"/api/v1/tasks/{body['id']}", headers=_auth(token))
    assert shown.status_code == 200
    assert shown.json() == body

    listed = client.get("/api/v1/tasks", headers=_auth(token))
    assert listed.status_code == 200
    page = listed.json()
    assert page["limit"] == 100
    assert page["offset"] == 0
    assert page["total"] == 1
    assert page["items"] == [body]


def test_today_is_allowed_and_yesterday_is_rejected() -> None:
    token = _token(timezone="Pacific/Auckland")
    today = datetime.now(UTC).astimezone(ZoneInfo("Pacific/Auckland")).date()
    offset = datetime.now(UTC).astimezone(ZoneInfo("Pacific/Auckland")).isoformat()[-6:]

    rejected = client.post(
        "/api/v1/tasks",
        headers=_auth(token),
        json={"description": "вчера", "due_on": (today - timedelta(days=1)).isoformat()},
    )
    created = client.post(
        "/api/v1/tasks",
        headers=_auth(token),
        json={"description": "сегодня", "due_on": today.isoformat()},
    )

    assert rejected.status_code == 422
    assert rejected.json()["code"] == "in_the_past"
    assert rejected.json()["details"] == {"field": "due_on"}
    assert created.status_code == 201
    assert created.json()["due_on"] == today.isoformat()
    assert created.json()["created_at"].endswith(offset)
    listed = client.get("/api/v1/tasks", headers=_auth(token))
    assert listed.json()["total"] == 1


def test_list_keeps_undated_tasks_and_filters_a_period() -> None:
    token = _token()
    today = datetime.now(UTC).astimezone(ZoneInfo("Europe/Moscow")).date()
    tomorrow = today + timedelta(days=1)
    later = today + timedelta(days=3)
    _create(token, "без срока")
    _create(token, "сегодня", today.isoformat())
    _create(token, "завтра", tomorrow.isoformat())
    _create(token, "позже", later.isoformat())

    dated = client.get("/api/v1/tasks", headers=_auth(token), params={"due": "dated"})
    undated = client.get("/api/v1/tasks", headers=_auth(token), params={"due": "undated"})
    period = client.get(
        "/api/v1/tasks",
        headers=_auth(token),
        params={"from": today.isoformat(), "to": tomorrow.isoformat()},
    )

    assert [item["description"] for item in dated.json()["items"]] == ["сегодня", "завтра", "позже"]
    assert [item["description"] for item in undated.json()["items"]] == ["без срока"]
    assert [item["description"] for item in period.json()["items"]] == ["сегодня", "завтра"]
    assert period.json()["total"] == 2


def test_list_orders_active_before_completed_and_undated_last() -> None:
    token = _token()
    today = datetime.now(UTC).astimezone(ZoneInfo("Europe/Moscow")).date()
    soon = _create(token, "скоро", (today + timedelta(days=1)).isoformat())
    later = _create(token, "позже", (today + timedelta(days=2)).isoformat())
    first_open = _create(token, "без срока раньше")
    second_open = _create(token, "без срока позже")
    done = _create(token, "уже сделано", today.isoformat())
    moment = datetime(2026, 10, 11, 12, tzinfo=UTC)
    _stamp(first_open, moment)
    _stamp(second_open, moment + timedelta(seconds=1))
    _complete(done)

    listed = client.get("/api/v1/tasks", headers=_auth(token))

    assert [item["description"] for item in listed.json()["items"]] == [
        "скоро",
        "позже",
        "без срока раньше",
        "без срока позже",
        "уже сделано",
    ]


def test_page_limit_and_offset() -> None:
    token = _token()
    _create(token, "первая")
    _create(token, "вторая")
    _create(token, "третья")

    page = client.get("/api/v1/tasks", headers=_auth(token), params={"limit": 2, "offset": 1})

    assert page.status_code == 200
    body = page.json()
    assert body["total"] == 3
    assert body["limit"] == 2
    assert body["offset"] == 1
    assert [item["description"] for item in body["items"]] == ["вторая", "третья"]


def test_status_filter() -> None:
    token = _token()
    _create(token, "в работе")
    done = _create(token, "закрыта")
    _complete(done)

    active = client.get("/api/v1/tasks", headers=_auth(token), params={"status": "active"})
    completed = client.get("/api/v1/tasks", headers=_auth(token), params={"status": "completed"})

    assert [item["description"] for item in active.json()["items"]] == ["в работе"]
    assert [item["description"] for item in completed.json()["items"]] == ["закрыта"]


def test_other_user_does_not_see_the_task() -> None:
    owner = _token()
    stranger = _token()
    task_id = _create(owner, "личное")

    hidden = client.get(f"/api/v1/tasks/{task_id}", headers=_auth(stranger))
    missing = client.get(f"/api/v1/tasks/{uuid.uuid4()}", headers=_auth(owner))
    own_list = client.get("/api/v1/tasks", headers=_auth(stranger))

    assert hidden.status_code == 404
    assert hidden.json()["code"] == "not_found"
    assert missing.status_code == 404
    assert own_list.json()["items"] == []


def test_task_list_rejects_an_incomplete_or_contradictory_range() -> None:
    token = _token()
    today = datetime.now(UTC).astimezone(ZoneInfo("Europe/Moscow")).date().isoformat()

    only_from = client.get("/api/v1/tasks", headers=_auth(token), params={"from": today})
    only_to = client.get("/api/v1/tasks", headers=_auth(token), params={"to": today})
    undated = client.get(
        "/api/v1/tasks",
        headers=_auth(token),
        params={"due": "undated", "from": today},
    )
    bad_status = client.get("/api/v1/tasks", headers=_auth(token), params={"status": "nope"})

    assert only_from.status_code == 422
    assert only_from.json()["details"]["errors"] == [
        {"field": "to", "code": "required", "message": "Нужно заполнить поле"}
    ]
    assert only_to.json()["details"]["errors"][0]["field"] == "from"
    assert undated.json()["details"]["errors"] == [
        {"field": "to", "code": "required", "message": "Нужно заполнить поле"},
        {"field": "due", "code": "invalid_range", "message": "Некорректный диапазон"},
    ]
    assert bad_status.json()["details"]["errors"][0]["code"] == "invalid_status"


def test_description_is_required_and_limited() -> None:
    token = _token()

    empty = client.post("/api/v1/tasks", headers=_auth(token), json={"description": "   "})
    too_long = client.post("/api/v1/tasks", headers=_auth(token), json={"description": "а" * 2001})
    anonymous = client.post("/api/v1/tasks", json={"description": "без входа"})

    assert empty.status_code == 422
    assert empty.json()["details"]["errors"][0]["code"] == "too_short"
    assert too_long.json()["details"]["errors"][0]["code"] == "too_long"
    assert anonymous.status_code == 401
    assert anonymous.json()["code"] == "unauthorized"


def _token(timezone: str = "Europe/Moscow") -> str:
    response = client.post(
        "/api/v1/auth/register",
        json={"email": f"task-{uuid.uuid4().hex}@example.com", "password": "password1", "timezone": timezone},
    )
    assert response.status_code == 201
    return str(response.json()["access_token"])


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _create(token: str, description: str, due_on: str | None = None) -> str:
    payload: dict[str, str] = {"description": description}
    if due_on is not None:
        payload["due_on"] = due_on
    response = client.post("/api/v1/tasks", headers=_auth(token), json=payload)
    assert response.status_code == 201
    return str(response.json()["id"])


def _complete(task_id: str) -> None:
    session = get_sessionmaker()()
    try:
        task = session.get(Task, uuid.UUID(task_id))
        assert task is not None
        task.status = "completed"
        task.completed_at = datetime.now(UTC)
        session.commit()
    finally:
        session.close()


def _stamp(task_id: str, moment: datetime) -> None:
    session = get_sessionmaker()()
    try:
        task = session.get(Task, uuid.UUID(task_id))
        assert task is not None
        task.created_at = moment
        task.updated_at = moment
        session.commit()
    finally:
        session.close()
