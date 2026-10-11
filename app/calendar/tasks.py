from dataclasses import dataclass
from datetime import UTC, date, datetime
from uuid import UUID
from zoneinfo import ZoneInfo

from sqlalchemy import case, func, select
from sqlalchemy.orm import Session

from app.db.models import Task, User


class DueInThePast(Exception):
    def __init__(self, field: str) -> None:
        self.field = field


class TaskNotFound(Exception):
    pass


class InvalidTaskQuery(Exception):
    def __init__(self, errors: list[tuple[str, str]]) -> None:
        self.errors = errors


@dataclass(frozen=True)
class TaskListQuery:
    status: str = "all"
    due: str = "any"
    date_from: date | None = None
    date_to: date | None = None
    limit: int = 100
    offset: int = 0


@dataclass(frozen=True)
class TaskPage:
    items: list[Task]
    limit: int
    offset: int
    total: int


@dataclass(frozen=True)
class StatusChange:
    task: Task
    status_changed: bool


def create_task(session: Session, user: User, *, description: str, due_on: date | None) -> Task:
    if due_on is not None and due_on < _today(user):
        raise DueInThePast("due_on")

    now = datetime.now(UTC)
    task = Task(
        user_id=user.id,
        description=description,
        due_on=due_on,
        status="active",
        completed_at=None,
        source_id=None,
        created_at=now,
        updated_at=now,
    )
    session.add(task)
    session.flush()
    return task


def update_task(
    session: Session,
    user: User,
    task_id: UUID,
    *,
    description: str | None,
    due_on: date | None,
    update_description: bool,
    update_due_on: bool,
) -> Task:
    task = get_task(session, user, task_id)
    if update_due_on and due_on is not None and due_on < _today(user):
        raise DueInThePast("due_on")
    if update_description and description is not None:
        task.description = description
    if update_due_on:
        task.due_on = due_on
    if update_description or update_due_on:
        task.updated_at = datetime.now(UTC)
        session.commit()
    return task


def complete_task(session: Session, user: User, task_id: UUID) -> StatusChange:
    task = get_task(session, user, task_id)
    if task.status == "completed":
        return StatusChange(task, False)
    now = datetime.now(UTC)
    task.status = "completed"
    task.completed_at = now
    task.updated_at = now
    session.commit()
    return StatusChange(task, True)


def reopen_task(session: Session, user: User, task_id: UUID) -> StatusChange:
    task = get_task(session, user, task_id)
    if task.status == "active":
        return StatusChange(task, False)
    task.status = "active"
    task.completed_at = None
    task.updated_at = datetime.now(UTC)
    session.commit()
    return StatusChange(task, True)


def delete_task(session: Session, user: User, task_id: UUID) -> None:
    task = get_task(session, user, task_id)
    session.delete(task)
    session.flush()


def get_task(session: Session, user: User, task_id: UUID) -> Task:
    task = session.get(Task, task_id)
    if task is None or task.user_id != user.id:
        raise TaskNotFound
    return task


def list_tasks(session: Session, user: User, query: TaskListQuery) -> TaskPage:
    errors = _query_errors(query)
    if errors:
        raise InvalidTaskQuery(errors)

    filtered = select(Task).where(Task.user_id == user.id)
    if query.status != "all":
        filtered = filtered.where(Task.status == query.status)
    if query.due == "dated":
        filtered = filtered.where(Task.due_on.is_not(None))
    elif query.due == "undated":
        filtered = filtered.where(Task.due_on.is_(None))
    if query.date_from is not None and query.date_to is not None:
        filtered = filtered.where(Task.due_on >= query.date_from, Task.due_on <= query.date_to)

    total = session.scalar(select(func.count()).select_from(filtered.subquery())) or 0
    status_rank = case((Task.status == "active", 0), else_=1)
    rows = session.scalars(
        filtered.order_by(status_rank, Task.due_on.asc().nulls_last(), Task.created_at.asc())
        .limit(query.limit)
        .offset(query.offset)
    ).all()
    return TaskPage(items=list(rows), limit=query.limit, offset=query.offset, total=total)


def _today(user: User) -> date:
    return datetime.now(UTC).astimezone(ZoneInfo(user.timezone)).date()


def _query_errors(query: TaskListQuery) -> list[tuple[str, str]]:
    errors: list[tuple[str, str]] = []
    has_from = query.date_from is not None
    has_to = query.date_to is not None
    if has_from != has_to:
        errors.append(("to" if has_from else "from", "required"))
    if query.due == "undated" and (has_from or has_to):
        errors.append(("due", "invalid_range"))
    return errors
