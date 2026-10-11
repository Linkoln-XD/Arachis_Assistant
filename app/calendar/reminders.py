from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from uuid import UUID
from zoneinfo import ZoneInfo

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.models import Reminder, User

_SKEW = timedelta(seconds=60)


class ReminderInThePast(Exception):
    def __init__(self, field: str) -> None:
        self.field = field


class ReminderNotFound(Exception):
    pass


class InvalidReminderQuery(Exception):
    def __init__(self, errors: list[tuple[str, str]]) -> None:
        self.errors = errors


@dataclass(frozen=True)
class ReminderListQuery:
    status: str = "all"
    date_from: date | None = None
    date_to: date | None = None
    limit: int = 100
    offset: int = 0


@dataclass(frozen=True)
class ReminderPage:
    items: list[Reminder]
    limit: int
    offset: int
    total: int


def create_reminder(session: Session, user: User, *, text: str, fire_at: datetime) -> Reminder:
    moment = _as_utc(fire_at)
    _reject_past(moment)
    now = datetime.now(UTC)
    reminder = Reminder(
        user_id=user.id,
        text=text,
        fire_at=moment,
        status="pending",
        fired_at=None,
        source_id=None,
        created_at=now,
        updated_at=now,
    )
    session.add(reminder)
    session.flush()
    return reminder


def update_reminder(
    session: Session,
    user: User,
    reminder_id: UUID,
    *,
    text: str | None,
    fire_at: datetime | None,
    update_text: bool,
    update_fire_at: bool,
) -> Reminder:
    reminder = get_reminder(session, user, reminder_id)
    moment = _as_utc(fire_at) if update_fire_at and fire_at is not None else None
    if moment is not None and moment != _as_utc(reminder.fire_at):
        _reject_past(moment)

    changed = False
    if moment is not None and moment != _as_utc(reminder.fire_at):
        reminder.fire_at = moment
        if reminder.status == "fired":
            reminder.status = "pending"
            reminder.fired_at = None
        changed = True
    if update_text and text is not None:
        reminder.text = text
        changed = True
    if changed:
        reminder.updated_at = datetime.now(UTC)
        session.commit()
    return reminder


def delete_reminder(session: Session, user: User, reminder_id: UUID) -> None:
    reminder = get_reminder(session, user, reminder_id)
    session.delete(reminder)
    session.flush()


def get_reminder(session: Session, user: User, reminder_id: UUID) -> Reminder:
    reminder = session.get(Reminder, reminder_id)
    if reminder is None or reminder.user_id != user.id:
        raise ReminderNotFound
    return reminder


def list_reminders(session: Session, user: User, query: ReminderListQuery) -> ReminderPage:
    errors = _query_errors(query)
    if errors:
        raise InvalidReminderQuery(errors)

    filtered = select(Reminder).where(Reminder.user_id == user.id)
    if query.status != "all":
        filtered = filtered.where(Reminder.status == query.status)
    if query.date_from is not None and query.date_to is not None:
        window_start, window_end = _window(user, query.date_from, query.date_to)
        filtered = filtered.where(Reminder.fire_at >= window_start, Reminder.fire_at < window_end)

    total = session.scalar(select(func.count()).select_from(filtered.subquery())) or 0
    rows = session.scalars(
        filtered.order_by(Reminder.fire_at.asc(), Reminder.id.asc()).limit(query.limit).offset(query.offset)
    ).all()
    return ReminderPage(items=list(rows), limit=query.limit, offset=query.offset, total=total)


def _reject_past(moment: datetime) -> None:
    if moment < datetime.now(UTC) - _SKEW:
        raise ReminderInThePast("fire_at")


def _window(user: User, date_from: date, date_to: date) -> tuple[datetime, datetime]:
    zone = ZoneInfo(user.timezone)
    start = datetime.combine(date_from, time.min, tzinfo=zone)
    end = datetime.combine(date_to + timedelta(days=1), time.min, tzinfo=zone)
    return start, end


def _query_errors(query: ReminderListQuery) -> list[tuple[str, str]]:
    has_from = query.date_from is not None
    has_to = query.date_to is not None
    if has_from != has_to:
        return [("to" if has_from else "from", "required")]
    return []


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)
