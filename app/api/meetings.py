from datetime import date, datetime
from typing import Annotated, Literal
from uuid import UUID
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, Header, Query, Request, Response
from pydantic import BaseModel, Field, field_validator
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.api.errors import APIError, validation_details
from app.calendar.meetings import (
    CreatedMeeting,
    InvalidMeetingInterval,
    InvalidMeetingQuery,
    MeetingInThePast,
    MeetingListQuery,
    MeetingNotFound,
    MeetingOverlap,
    create_meeting,
    delete_meeting,
    get_meeting,
    list_meetings,
    update_meeting,
)
from app.db.models import Meeting, User
from app.db.session import get_session
from app.idempotency import PreparedResponse, raw_body, run_idempotent, valid_key

router = APIRouter(prefix="/meetings")


class CreateMeetingRequest(BaseModel):
    title: str = Field(min_length=1, max_length=2000)
    starts_at: datetime
    ends_at: datetime | None = None
    allow_overlap: bool = False

    @field_validator("title", mode="before")
    @classmethod
    def strip_title(cls, value: object) -> object:
        if isinstance(value, str):
            return value.strip()
        return value

    @field_validator("starts_at", "ends_at")
    @classmethod
    def aware_moment(cls, value: datetime | None) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("invalid")
        return value


class MeetingResponse(BaseModel):
    id: str
    type: Literal["meeting"]
    title: str
    starts_at: datetime
    ends_at: datetime
    source_id: str | None
    created_at: datetime
    updated_at: datetime


class MeetingCreatedResponse(BaseModel):
    meeting: MeetingResponse
    overlaps: list[MeetingResponse]


class UpdateMeetingRequest(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=2000)
    starts_at: datetime | None = None
    ends_at: datetime | None = None
    allow_overlap: bool = False

    @field_validator("title", mode="before")
    @classmethod
    def strip_title(cls, value: object) -> object:
        if value is None:
            raise ValueError("required")
        if isinstance(value, str):
            return value.strip()
        return value

    @field_validator("starts_at", "ends_at", mode="before")
    @classmethod
    def reject_empty_moment(cls, value: object) -> object:
        if value is None:
            raise ValueError("required")
        return value

    @field_validator("starts_at", "ends_at")
    @classmethod
    def aware_moment(cls, value: datetime | None) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("invalid")
        return value


class MeetingListResponse(BaseModel):
    items: list[MeetingResponse]
    limit: int
    offset: int
    total: int


@router.post("", status_code=201, response_model=MeetingCreatedResponse)
def create(
    body: CreateMeetingRequest,
    request: Request,
    raw: Annotated[bytes, Depends(raw_body)],
    session: Session = Depends(get_session),
    user: User = Depends(get_current_user),
    idempotency_key: Annotated[str | None, Header()] = None,
) -> Response:
    key = valid_key(idempotency_key)

    def perform() -> PreparedResponse:
        try:
            created = create_meeting(
                session,
                user,
                title=body.title,
                starts_at=body.starts_at,
                ends_at=body.ends_at,
                allow_overlap=body.allow_overlap,
            )
        except MeetingInThePast as error:
            return PreparedResponse(422, _past_body(error.field))
        except InvalidMeetingInterval as error:
            return PreparedResponse(422, _validation_body(error.errors))
        except MeetingOverlap as error:
            return PreparedResponse(409, _overlap_body(error.conflicts, user))
        return PreparedResponse(201, _created_body(created, user), {"Location": f"/api/v1/meetings/{created.meeting.id}"})

    return run_idempotent(
        session,
        user=user,
        method=request.method,
        path=request.url.path,
        key=key,
        request_body=raw,
        perform=perform,
    )


@router.get("", response_model=MeetingListResponse)
def index(
    session: Session = Depends(get_session),
    user: User = Depends(get_current_user),
    date_from: Annotated[date | None, Query(alias="from")] = None,
    date_to: Annotated[date | None, Query(alias="to")] = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 100,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> MeetingListResponse:
    query = MeetingListQuery(date_from=date_from, date_to=date_to, limit=limit, offset=offset)
    try:
        page = list_meetings(session, user, query)
    except InvalidMeetingQuery as error:
        raise APIError(422, "validation_error", "Некорректные данные", validation_details(error.errors)) from error
    return MeetingListResponse(
        items=[_meeting_response(meeting, user) for meeting in page.items],
        limit=page.limit,
        offset=page.offset,
        total=page.total,
    )


@router.get("/{meeting_id}", response_model=MeetingResponse)
def show(
    meeting_id: UUID,
    session: Session = Depends(get_session),
    user: User = Depends(get_current_user),
) -> MeetingResponse:
    try:
        meeting = get_meeting(session, user, meeting_id)
    except MeetingNotFound as error:
        raise APIError(404, "not_found", "Запись не найдена") from error
    return _meeting_response(meeting, user)


@router.patch("/{meeting_id}", response_model=MeetingCreatedResponse)
def update(
    meeting_id: UUID,
    body: UpdateMeetingRequest,
    session: Session = Depends(get_session),
    user: User = Depends(get_current_user),
) -> MeetingCreatedResponse:
    try:
        updated = update_meeting(
            session,
            user,
            meeting_id,
            title=body.title,
            starts_at=body.starts_at,
            ends_at=body.ends_at,
            update_title="title" in body.model_fields_set,
            update_start="starts_at" in body.model_fields_set,
            update_end="ends_at" in body.model_fields_set,
            allow_overlap=body.allow_overlap,
        )
    except MeetingNotFound as error:
        raise APIError(404, "not_found", "Запись не найдена") from error
    except MeetingInThePast as error:
        raise APIError(422, "in_the_past", "Указанное время уже прошло", {"field": error.field}) from error
    except InvalidMeetingInterval as error:
        raise APIError(422, "validation_error", "Некорректные данные", validation_details(error.errors)) from error
    except MeetingOverlap as error:
        raise APIError(409, "overlap", "На это время уже есть встреча", _conflict_details(error.conflicts, user)) from error
    return MeetingCreatedResponse(
        meeting=_meeting_response(updated.meeting, user),
        overlaps=[_meeting_response(meeting, user) for meeting in updated.overlaps],
    )


@router.delete("/{meeting_id}", status_code=204)
def destroy(
    meeting_id: UUID,
    request: Request,
    raw: Annotated[bytes, Depends(raw_body)],
    session: Session = Depends(get_session),
    user: User = Depends(get_current_user),
    idempotency_key: Annotated[str | None, Header()] = None,
) -> Response:
    key = valid_key(idempotency_key)

    def perform() -> PreparedResponse:
        try:
            delete_meeting(session, user, meeting_id)
        except MeetingNotFound:
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


def _created_body(created: CreatedMeeting, user: User) -> dict[str, object]:
    return {
        "meeting": _meeting_response(created.meeting, user).model_dump(mode="json"),
        "overlaps": [_meeting_response(meeting, user).model_dump(mode="json") for meeting in created.overlaps],
    }


def _overlap_body(conflicts: list[Meeting], user: User) -> dict[str, object]:
    return {
        "code": "overlap",
        "message": "На это время уже есть встреча",
        "details": _conflict_details(conflicts, user),
    }


def _conflict_details(conflicts: list[Meeting], user: User) -> dict[str, object]:
    return {"conflicts": [_meeting_response(meeting, user).model_dump(mode="json") for meeting in conflicts]}


def _past_body(field: str) -> dict[str, object]:
    return {
        "code": "in_the_past",
        "message": "Указанное время уже прошло",
        "details": {"field": field},
    }


def _validation_body(errors: list[tuple[str, str]]) -> dict[str, object]:
    return {"code": "validation_error", "message": "Некорректные данные", "details": validation_details(errors)}


def _meeting_response(meeting: Meeting, user: User) -> MeetingResponse:
    zone = ZoneInfo(user.timezone)
    return MeetingResponse(
        id=str(meeting.id),
        type="meeting",
        title=meeting.title,
        starts_at=_in_zone(meeting.starts_at, zone),
        ends_at=_in_zone(meeting.ends_at, zone),
        source_id=meeting.source_id,
        created_at=_in_zone(meeting.created_at, zone),
        updated_at=_in_zone(meeting.updated_at, zone),
    )


def _in_zone(value: datetime, zone: ZoneInfo) -> datetime:
    if value.tzinfo is None:
        value = value.replace(tzinfo=ZoneInfo("UTC"))
    return value.astimezone(zone)
