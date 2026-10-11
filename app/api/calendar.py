from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.api.errors import APIError, validation_details
from app.api.meetings import MeetingResponse, _meeting_response
from app.api.reminders import ReminderResponse, _reminder_response
from app.api.tasks import TaskResponse, _task_response
from app.calendar.schedule import InvalidCalendarQuery, list_calendar
from app.db.models import Meeting, Reminder, Task, User
from app.db.session import get_session

router = APIRouter()


class CalendarResponse(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    date_from: date = Field(alias="from")
    date_to: date = Field(alias="to")
    timezone: str
    items: list[TaskResponse | MeetingResponse | ReminderResponse]


@router.get("/calendar", response_model=CalendarResponse)
def show(
    session: Session = Depends(get_session),
    user: User = Depends(get_current_user),
    date_from: Annotated[date | None, Query(alias="from")] = None,
    date_to: Annotated[date | None, Query(alias="to")] = None,
    types: str | None = None,
) -> CalendarResponse:
    try:
        records = list_calendar(session, user, date_from=date_from, date_to=date_to, types=types)
    except InvalidCalendarQuery as error:
        raise APIError(422, "validation_error", "Некорректные данные", validation_details(error.errors)) from error
    assert date_from is not None and date_to is not None
    return CalendarResponse(
        date_from=date_from,
        date_to=date_to,
        timezone=user.timezone,
        items=[_item(record, user) for record in records],
    )


def _item(record: Task | Meeting | Reminder, user: User) -> TaskResponse | MeetingResponse | ReminderResponse:
    if isinstance(record, Task):
        return _task_response(record, user)
    if isinstance(record, Meeting):
        return _meeting_response(record, user)
    return _reminder_response(record, user)
