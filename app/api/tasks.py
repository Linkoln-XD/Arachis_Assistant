from collections.abc import Callable
from datetime import date, datetime
from typing import Annotated, Literal, cast
from uuid import UUID
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, Header, Query, Request, Response
from pydantic import BaseModel, Field, field_validator
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.api.errors import APIError, validation_details
from app.calendar.tasks import (
    DueInThePast,
    InvalidTaskQuery,
    StatusChange,
    TaskListQuery,
    TaskNotFound,
    complete_task,
    create_task,
    delete_task,
    get_task,
    list_tasks,
    reopen_task,
    update_task,
)
from app.db.models import Task, User
from app.db.session import get_session
from app.idempotency import PreparedResponse, raw_body, run_idempotent, valid_key

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


class UpdateTaskRequest(BaseModel):
    description: str | None = Field(default=None, min_length=1, max_length=2000)
    due_on: date | None = None

    @field_validator("description", mode="before")
    @classmethod
    def strip_description(cls, value: object) -> object:
        if value is None:
            raise ValueError("required")
        if isinstance(value, str):
            return value.strip()
        return value


class TaskListResponse(BaseModel):
    items: list[TaskResponse]
    limit: int
    offset: int
    total: int


class TaskStatusResponse(BaseModel):
    task: TaskResponse
    status_changed: bool


@router.post("", status_code=201, response_model=TaskResponse)
def create(
    body: CreateTaskRequest,
    request: Request,
    raw: Annotated[bytes, Depends(raw_body)],
    session: Session = Depends(get_session),
    user: User = Depends(get_current_user),
    idempotency_key: Annotated[str | None, Header()] = None,
) -> Response:
    key = valid_key(idempotency_key)

    def perform() -> PreparedResponse:
        try:
            task = create_task(session, user, description=body.description, due_on=body.due_on)
        except DueInThePast as error:
            return PreparedResponse(
                422,
                {"code": "in_the_past", "message": "Указанное время уже прошло", "details": {"field": error.field}},
            )
        payload = _task_response(task, user).model_dump(mode="json")
        return PreparedResponse(201, payload, {"Location": f"/api/v1/tasks/{task.id}"})

    return run_idempotent(
        session,
        user=user,
        method=request.method,
        path=request.url.path,
        key=key,
        request_body=raw,
        perform=perform,
    )


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


@router.patch("/{task_id}", response_model=TaskResponse)
def update(
    task_id: UUID,
    body: UpdateTaskRequest,
    session: Session = Depends(get_session),
    user: User = Depends(get_current_user),
) -> TaskResponse:
    try:
        task = update_task(
            session,
            user,
            task_id,
            description=body.description,
            due_on=body.due_on,
            update_description="description" in body.model_fields_set,
            update_due_on="due_on" in body.model_fields_set,
        )
    except TaskNotFound as error:
        raise APIError(404, "not_found", "Запись не найдена") from error
    except DueInThePast as error:
        raise APIError(
            422,
            "in_the_past",
            "Указанное время уже прошло",
            {"field": error.field},
        ) from error
    return _task_response(task, user)


@router.post("/{task_id}/complete", response_model=TaskStatusResponse)
def complete(
    task_id: UUID,
    session: Session = Depends(get_session),
    user: User = Depends(get_current_user),
) -> TaskStatusResponse:
    return _status_response(session, user, task_id, complete_task)


@router.post("/{task_id}/reopen", response_model=TaskStatusResponse)
def reopen(
    task_id: UUID,
    session: Session = Depends(get_session),
    user: User = Depends(get_current_user),
) -> TaskStatusResponse:
    return _status_response(session, user, task_id, reopen_task)


@router.delete("/{task_id}", status_code=204)
def destroy(
    task_id: UUID,
    request: Request,
    raw: Annotated[bytes, Depends(raw_body)],
    session: Session = Depends(get_session),
    user: User = Depends(get_current_user),
    idempotency_key: Annotated[str | None, Header()] = None,
) -> Response:
    key = valid_key(idempotency_key)

    def perform() -> PreparedResponse:
        try:
            delete_task(session, user, task_id)
        except TaskNotFound:
            return PreparedResponse(
                404,
                {"code": "not_found", "message": "Запись не найдена", "details": {}},
            )
        return PreparedResponse(204)

    return run_idempotent(
        session,
        user=user,
        method=request.method,
        path=request.url.path,
        key=key,
        request_body=raw,
        perform=perform,
    )


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


def _status_response(
    session: Session,
    user: User,
    task_id: UUID,
    operation: Callable[[Session, User, UUID], StatusChange],
) -> TaskStatusResponse:
    try:
        result = operation(session, user, task_id)
    except TaskNotFound as error:
        raise APIError(404, "not_found", "Запись не найдена") from error
    return TaskStatusResponse(task=_task_response(result.task, user), status_changed=result.status_changed)


def _in_zone(value: datetime | None, zone: ZoneInfo) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=ZoneInfo("UTC"))
    return value.astimezone(zone)
