from datetime import date, datetime
from typing import Annotated, Literal, cast
from uuid import UUID
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, Query, Response
from pydantic import BaseModel, Field, field_validator
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.api.errors import APIError, validation_details
from app.calendar.tasks import (
    DueInThePast,
    InvalidTaskQuery,
    TaskListQuery,
    TaskNotFound,
    create_task,
    get_task,
    list_tasks,
)
from app.db.models import Task, User
from app.db.session import get_session

router = APIRouter(prefix="/tasks")


class CreateTaskRequest(BaseModel):
    description: str = Field(min_length=1, max_length=2000)
    due_on: date | None = None

    @field_validator("description", mode="before")
    @classmethod
    def strip_description(cls, value: object) -> object:
        if isinstance(value, str):
            return value.strip()
        return value


class TaskResponse(BaseModel):
    id: str
    type: Literal["task"]
    description: str
    due_on: date | None
    status: Literal["active", "completed"]
    completed_at: datetime | None
    source_id: str | None
    created_at: datetime
    updated_at: datetime


class TaskListResponse(BaseModel):
    items: list[TaskResponse]
    limit: int
    offset: int
    total: int


@router.post("", status_code=201, response_model=TaskResponse)
def create(
    body: CreateTaskRequest,
    response: Response,
    session: Session = Depends(get_session),
    user: User = Depends(get_current_user),
) -> TaskResponse:
    try:
        task = create_task(session, user, description=body.description, due_on=body.due_on)
    except DueInThePast as error:
        raise APIError(
            422,
            "in_the_past",
            "Указанное время уже прошло",
            {"field": error.field},
        ) from error
    response.headers["Location"] = f"/api/v1/tasks/{task.id}"
    return _task_response(task, user)


@router.get("", response_model=TaskListResponse)
def index(
    session: Session = Depends(get_session),
    user: User = Depends(get_current_user),
    status: Literal["active", "completed", "all"] = "all",
    due: Literal["any", "dated", "undated"] = "any",
    date_from: Annotated[date | None, Query(alias="from")] = None,
    date_to: Annotated[date | None, Query(alias="to")] = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 100,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> TaskListResponse:
    query = TaskListQuery(
        status=status,
        due=due,
        date_from=date_from,
        date_to=date_to,
        limit=limit,
        offset=offset,
    )
    try:
        page = list_tasks(session, user, query)
    except InvalidTaskQuery as error:
        raise APIError(422, "validation_error", "Некорректные данные", validation_details(error.errors)) from error
    return TaskListResponse(
        items=[_task_response(task, user) for task in page.items],
        limit=page.limit,
        offset=page.offset,
        total=page.total,
    )


@router.get("/{task_id}", response_model=TaskResponse)
def show(
    task_id: UUID,
    session: Session = Depends(get_session),
    user: User = Depends(get_current_user),
) -> TaskResponse:
    try:
        task = get_task(session, user, task_id)
    except TaskNotFound as error:
        raise APIError(404, "not_found", "Запись не найдена") from error
    return _task_response(task, user)


def _task_response(task: Task, user: User) -> TaskResponse:
    zone = ZoneInfo(user.timezone)
    return TaskResponse(
        id=str(task.id),
        type="task",
        description=task.description,
        due_on=task.due_on,
        status=cast(Literal["active", "completed"], task.status),
        completed_at=_in_zone(task.completed_at, zone),
        source_id=task.source_id,
        created_at=_in_zone(task.created_at, zone),
        updated_at=_in_zone(task.updated_at, zone),
    )


def _in_zone(value: datetime | None, zone: ZoneInfo) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=ZoneInfo("UTC"))
    return value.astimezone(zone)
