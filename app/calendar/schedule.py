from datetime import UTC, date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import Meeting, Reminder, Task, User

_MAX_DAYS = 366
_KINDS = ("task", "meeting", "reminder")
_RANK = {"meeting": 0, "reminder": 1, "task": 2}


class InvalidCalendarQuery(Exception):
    def __init__(self, errors: list[tuple[str, str]]) -> None:
        self.errors = errors


def list_calendar(
    session: Session,
    user: User,
    *,
    date_from: date | None,
    date_to: date | None,
    types: str | None,
) -> list[Task | Meeting | Reminder]:
    errors = _query_errors(date_from, date_to, types)
    if errors:
        raise InvalidCalendarQuery(errors)
    assert date_from is not None and date_to is not None

    selected = _selected_types(types)
    records: list[Task | Meeting | Reminder] = []
    if "task" in selected:
        records.extend(_tasks(session, user, date_from, date_to))
    if "meeting" in selected:
        records.extend(_meetings(session, user, date_from, date_to))
    if "reminder" in selected:
        records.extend(_reminders(session, user, date_from, date_to))
    return sorted(records, key=lambda record: _sort_key(user, record))


def _query_errors(date_from: date | None, date_to: date | None, types: str | None) -> list[tuple[str, str]]:
    errors: list[tuple[str, str]] = []
    if date_from is None:
        errors.append(("from", "required"))
    if date_to is None:
        errors.append(("to", "required"))
    if date_from is not None and date_to is not None and (
        date_from > date_to or (date_to - date_from).days + 1 > _MAX_DAYS
    ):
        errors.append(("from", "invalid_range"))
    if types is not None and _selected_types(types) is None:
        errors.append(("types", "invalid_type"))
    return errors


def _selected_types(types: str | None) -> set[str] | None:
    if types is None:
        return set(_KINDS)
    names = [part.strip() for part in types.split(",") if part.strip()]
    if not names or any(name not in _KINDS for name in names):
        return None
    return set(names)


def _tasks(session: Session, user: User, date_from: date, date_to: date) -> list[Task]:
    rows = session.scalars(
        select(Task).where(
            Task.user_id == user.id,
            Task.due_on.is_not(None),
            Task.due_on >= date_from,
            Task.due_on <= date_to,
        )
    ).all()
    return list(rows)


def _meetings(session: Session, user: User, date_from: date, date_to: date) -> list[Meeting]:
    window_start, window_end = _window(user, date_from, date_to)
    rows = session.scalars(
        select(Meeting).where(
            Meeting.user_id == user.id,
            Meeting.starts_at < window_end,
            Meeting.ends_at > window_start,
        )
    ).all()
    return list(rows)


def _reminders(session: Session, user: User, date_from: date, date_to: date) -> list[Reminder]:
    window_start, window_end = _window(user, date_from, date_to)
    rows = session.scalars(
        select(Reminder).where(
            Reminder.user_id == user.id,
            Reminder.fire_at >= window_start,
            Reminder.fire_at < window_end,
        )
    ).all()
    return list(rows)


def _window(user: User, date_from: date, date_to: date) -> tuple[datetime, datetime]:
    zone = ZoneInfo(user.timezone)
    start = datetime.combine(date_from, time.min, tzinfo=zone)
    end = datetime.combine(date_to + timedelta(days=1), time.min, tzinfo=zone)
    return start, end


def _sort_key(user: User, record: Task | Meeting | Reminder) -> tuple[datetime, int, object]:
    if isinstance(record, Meeting):
        return (_aware(record.starts_at), _RANK["meeting"], record.id)
    if isinstance(record, Reminder):
        return (_aware(record.fire_at), _RANK["reminder"], record.id)
    zone = ZoneInfo(user.timezone)
    assert record.due_on is not None
    return (datetime.combine(record.due_on, time.min, tzinfo=zone), _RANK["task"], record.id)


def _aware(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value
