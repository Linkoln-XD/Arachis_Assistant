from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from uuid import UUID
from zoneinfo import ZoneInfo

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.models import Meeting, User

_SKEW = timedelta(seconds=60)
_MAX_DURATION = timedelta(hours=24)


class MeetingInThePast(Exception):
    def __init__(self, field: str) -> None:
        self.field = field


class MeetingNotFound(Exception):
    pass


class InvalidMeetingInterval(Exception):
    def __init__(self, errors: list[tuple[str, str]]) -> None:
        self.errors = errors


class MeetingOverlap(Exception):
    def __init__(self, conflicts: list[Meeting]) -> None:
        self.conflicts = conflicts


class InvalidMeetingQuery(Exception):
    def __init__(self, errors: list[tuple[str, str]]) -> None:
        self.errors = errors


@dataclass(frozen=True)
class MeetingListQuery:
    date_from: date | None = None
    date_to: date | None = None
    limit: int = 100
    offset: int = 0


@dataclass(frozen=True)
class MeetingPage:
    items: list[Meeting]
    limit: int
    offset: int
    total: int


@dataclass(frozen=True)
class CreatedMeeting:
    meeting: Meeting
    overlaps: list[Meeting]


def create_meeting(
    session: Session,
    user: User,
    *,
    title: str,
    starts_at: datetime,
    ends_at: datetime | None,
    allow_overlap: bool,
) -> CreatedMeeting:
    starts_at = _as_utc(starts_at)
    resolved_end = _as_utc(ends_at) if ends_at is not None else starts_at + timedelta(hours=1)
    errors = _interval_errors(starts_at, resolved_end)
    if errors:
        raise InvalidMeetingInterval(errors)
    if starts_at < datetime.now(UTC) - _SKEW:
        raise MeetingInThePast("starts_at")

    overlaps = _overlaps(session, user.id, starts_at, resolved_end)
    if overlaps and not allow_overlap:
        raise MeetingOverlap(overlaps)

    now = datetime.now(UTC)
    meeting = Meeting(
        user_id=user.id,
        title=title,
        starts_at=starts_at,
        ends_at=resolved_end,
        source_id=None,
        created_at=now,
        updated_at=now,
    )
    session.add(meeting)
    session.flush()
    return CreatedMeeting(meeting=meeting, overlaps=overlaps)


def update_meeting(
    session: Session,
    user: User,
    meeting_id: UUID,
    *,
    title: str | None,
    starts_at: datetime | None,
    ends_at: datetime | None,
    update_title: bool,
    update_start: bool,
    update_end: bool,
    allow_overlap: bool,
) -> CreatedMeeting:
    meeting = get_meeting(session, user, meeting_id)
    current_start = _as_utc(meeting.starts_at)
    current_end = _as_utc(meeting.ends_at)
    new_start = _as_utc(starts_at) if update_start and starts_at is not None else current_start
    if update_end and ends_at is not None:
        new_end = _as_utc(ends_at)
    elif update_start:
        new_end = new_start + (current_end - current_start)
    else:
        new_end = current_end

    interval_changed = new_start != current_start or new_end != current_end
    overlaps: list[Meeting] = []
    if interval_changed:
        errors = _interval_errors(new_start, new_end)
        if errors:
            raise InvalidMeetingInterval(errors)
        _reject_past(new_start, new_end, current_start, current_end)
        overlaps = _overlaps(session, user.id, new_start, new_end, exclude_id=meeting.id)
        if overlaps and not allow_overlap:
            raise MeetingOverlap(overlaps)

    changed = False
    if update_title and title is not None:
        meeting.title = title
        changed = True
    if interval_changed:
        meeting.starts_at = new_start
        meeting.ends_at = new_end
        changed = True
    if changed:
        meeting.updated_at = datetime.now(UTC)
        session.commit()
    return CreatedMeeting(meeting=meeting, overlaps=overlaps)


def delete_meeting(session: Session, user: User, meeting_id: UUID) -> None:
    meeting = get_meeting(session, user, meeting_id)
    session.delete(meeting)
    session.flush()


def get_meeting(session: Session, user: User, meeting_id: UUID) -> Meeting:
    meeting = session.get(Meeting, meeting_id)
    if meeting is None or meeting.user_id != user.id:
        raise MeetingNotFound
    return meeting


def list_meetings(session: Session, user: User, query: MeetingListQuery) -> MeetingPage:
    errors = _query_errors(query)
    if errors:
        raise InvalidMeetingQuery(errors)

    filtered = select(Meeting).where(Meeting.user_id == user.id)
    if query.date_from is not None and query.date_to is not None:
        window_start, window_end = _window(user, query.date_from, query.date_to)
        filtered = filtered.where(Meeting.starts_at < window_end, Meeting.ends_at > window_start)

    total = session.scalar(select(func.count()).select_from(filtered.subquery())) or 0
    rows = session.scalars(
        filtered.order_by(Meeting.starts_at.asc(), Meeting.id.asc()).limit(query.limit).offset(query.offset)
    ).all()
    return MeetingPage(items=list(rows), limit=query.limit, offset=query.offset, total=total)


def _interval_errors(starts_at: datetime, ends_at: datetime) -> list[tuple[str, str]]:
    if ends_at <= starts_at:
        return [("ends_at", "invalid_interval")]
    if ends_at - starts_at > _MAX_DURATION:
        return [("ends_at", "duration_too_long")]
    return []


def _reject_past(
    new_start: datetime,
    new_end: datetime,
    current_start: datetime,
    current_end: datetime,
) -> None:
    deadline = datetime.now(UTC) - _SKEW
    if new_start != current_start and new_start < deadline:
        raise MeetingInThePast("starts_at")
    if new_end != current_end and new_end < deadline:
        raise MeetingInThePast("ends_at")


def _overlaps(
    session: Session,
    user_id: UUID,
    starts_at: datetime,
    ends_at: datetime,
    exclude_id: UUID | None = None,
) -> list[Meeting]:
    filtered = select(Meeting).where(
        Meeting.user_id == user_id,
        Meeting.starts_at < ends_at,
        Meeting.ends_at > starts_at,
    )
    if exclude_id is not None:
        filtered = filtered.where(Meeting.id != exclude_id)
    rows = session.scalars(filtered.order_by(Meeting.starts_at.asc(), Meeting.id.asc())).all()
    return list(rows)


def _window(user: User, date_from: date, date_to: date) -> tuple[datetime, datetime]:
    zone = ZoneInfo(user.timezone)
    start = datetime.combine(date_from, time.min, tzinfo=zone)
    end = datetime.combine(date_to + timedelta(days=1), time.min, tzinfo=zone)
    return start, end


def _query_errors(query: MeetingListQuery) -> list[tuple[str, str]]:
    has_from = query.date_from is not None
    has_to = query.date_to is not None
    if has_from != has_to:
        return [("to" if has_from else "from", "required")]
    return []


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)
