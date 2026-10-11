from datetime import date, datetime
from typing import Annotated, Literal, cast
from uuid import UUID
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, Header, Query, Request, Response
from pydantic import BaseModel, Field, field_validator
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.api.errors import APIError, validation_details
from app.calendar.reminders import (
    InvalidReminderQuery,
    ReminderInThePast,
    ReminderListQuery,
    ReminderNotFound,
    create_reminder,
    delete_reminder,
    get_reminder,
    list_reminders,
    update_reminder,
)
from app.db.models import Reminder, User
from app.db.session import get_session
from app.idempotency import PreparedResponse, raw_body, run_idempotent, valid_key

router = APIRouter(prefix="/reminders")


class CreateReminderRequest(BaseModel):
    text: str = Field(min_length=1, max_length=2000)
    fire_at: datetime

    @field_validator("text", mode="before")
    @classmethod
    def strip_text(cls, value: object) -> object:
        if isinstance(value, str):
            return value.strip()
        return value

    @field_validator("fire_at")
    @classmethod
    def aware_moment(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("invalid")
        return value


class UpdateReminderRequest(BaseModel):
    text: str | None = Field(default=None, min_length=1, max_length=2000)
    fire_at: datetime | None = None

    @field_validator("text", mode="before")
    @classmethod
    def strip_text(cls, value: object) -> object:
        if value is None:
            raise ValueError("required")
        if isinstance(value, str):
            return value.strip()
        return value

    @field_validator("fire_at", mode="before")
    @classmethod
    def reject_empty_moment(cls, value: object) -> object:
        if value is None:
            raise ValueError("required")
        return value

    @field_validator("fire_at")
    @classmethod
    def aware_moment(cls, value: datetime | None) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("invalid")
        return value


class ReminderResponse(BaseModel):
    id: str
    type: Literal["reminder"]
    text: str
    fire_at: datetime
    status: Literal["pending", "fired"]
    fired_at: datetime | None
    source_id: str | None
    created_at: datetime
    updated_at: datetime


class ReminderListResponse(BaseModel):
    items: list[ReminderResponse]
    limit: int
    offset: int
    total: int


@router.post("", status_code=201, response_model=ReminderResponse)
def create(
    body: CreateReminderRequest,
    request: Request,
    raw: Annotated[bytes, Depends(raw_body)],
    session: Session = Depends(get_session),
    user: User = Depends(get_current_user),
    idempotency_key: Annotated[str | None, Header()] = None,
) -> Response:
    key = valid_key(idempotency_key)

    def perform() -> PreparedResponse:
        try:
            reminder = create_reminder(session, user, text=body.text, fire_at=body.fire_at)
        except ReminderInThePast as error:
            return PreparedResponse(422, _past_body(error.field))
        payload = _reminder_response(reminder, user).model_dump(mode="json")
        return PreparedResponse(201, payload, {"Location": f"/api/v1/reminders/{reminder.id}"})

    return run_idempotent(
        session,
        user=user,
        method=request.method,
        path=request.url.path,
        key=key,
        request_body=raw,
        perform=perform,
    )


@router.get("", response_model=ReminderListResponse)
def index(
    session: Session = Depends(get_session),
    user: User = Depends(get_current_user),
    status: Literal["pending", "fired", "all"] = "all",
    date_from: Annotated[date | None, Query(alias="from")] = None,
    date_to: Annotated[date | None, Query(alias="to")] = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 100,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> ReminderListResponse:
    query = ReminderListQuery(status=status, date_from=date_from, date_to=date_to, limit=limit, offset=offset)
    try:
        page = list_reminders(session, user, query)
    except InvalidReminderQuery as error:
        raise APIError(422, "validation_error", "Некорректные данные", validation_details(error.errors)) from error
    return ReminderListResponse(
        items=[_reminder_response(reminder, user) for reminder in page.items],
        limit=page.limit,
        offset=page.offset,
        total=page.total,
    )


@router.get("/{reminder_id}", response_model=ReminderResponse)
def show(
    reminder_id: UUID,
    session: Session = Depends(get_session),
    user: User = Depends(get_current_user),
) -> ReminderResponse:
    try:
        reminder = get_reminder(session, user, reminder_id)
    except ReminderNotFound as error:
        raise APIError(404, "not_found", "Запись не найдена") from error
    return _reminder_response(reminder, user)


@router.patch("/{reminder_id}", response_model=ReminderResponse)
def update(
    reminder_id: UUID,
    body: UpdateReminderRequest,
    session: Session = Depends(get_session),
    user: User = Depends(get_current_user),
) -> ReminderResponse:
    try:
        reminder = update_reminder(
            session,
            user,
            reminder_id,
            text=body.text,
            fire_at=body.fire_at,
            update_text="text" in body.model_fields_set,
            update_fire_at="fire_at" in body.model_fields_set,
        )
    except ReminderNotFound as error:
        raise APIError(404, "not_found", "Запись не найдена") from error
    except ReminderInThePast as error:
        raise APIError(422, "in_the_past", "Указанное время уже прошло", {"field": error.field}) from error
    return _reminder_response(reminder, user)


@router.delete("/{reminder_id}", status_code=204)
def destroy(
    reminder_id: UUID,
    request: Request,
    raw: Annotated[bytes, Depends(raw_body)],
    session: Session = Depends(get_session),
    user: User = Depends(get_current_user),
    idempotency_key: Annotated[str | None, Header()] = None,
) -> Response:
    key = valid_key(idempotency_key)

    def perform() -> PreparedResponse:
        try:
            delete_reminder(session, user, reminder_id)
        except ReminderNotFound:
            return PreparedResponse(404, {"code": "not_found", "message": "Запись не найдена", "details": {}})
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


def _past_body(field: str) -> dict[str, object]:
    return {"code": "in_the_past", "message": "Указанное время уже прошло", "details": {"field": field}}


def _reminder_response(reminder: Reminder, user: User) -> ReminderResponse:
    zone = ZoneInfo(user.timezone)
    return ReminderResponse(
        id=str(reminder.id),
        type="reminder",
        text=reminder.text,
        fire_at=_in_zone(reminder.fire_at, zone),
        status=cast(Literal["pending", "fired"], reminder.status),
        fired_at=_in_zone(reminder.fired_at, zone),
        source_id=reminder.source_id,
        created_at=_in_zone(reminder.created_at, zone),
        updated_at=_in_zone(reminder.updated_at, zone),
    )


def _in_zone(value: datetime | None, zone: ZoneInfo) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=ZoneInfo("UTC"))
    return value.astimezone(zone)
