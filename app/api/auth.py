from datetime import datetime
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from fastapi import APIRouter, Depends
from pydantic import BaseModel, EmailStr, Field, field_validator
from sqlalchemy.orm import Session

from app.api.errors import APIError
from app.auth.service import EmailTaken, register_user
from app.config import get_settings
from app.db.models import User
from app.db.session import get_session

router = APIRouter(prefix="/auth")


class RegisterRequest(BaseModel):
    email: EmailStr = Field(max_length=254)
    password: str = Field(min_length=8, max_length=128)
    timezone: str = "Europe/Moscow"

    @field_validator("email", mode="before")
    @classmethod
    def normalize_email(cls, value: object) -> object:
        if isinstance(value, str):
            return value.strip().lower()
        return value

    @field_validator("timezone")
    @classmethod
    def known_timezone(cls, value: str) -> str:
        try:
            ZoneInfo(value)
        except ZoneInfoNotFoundError as error:
            raise ValueError("invalid_timezone") from error
        return value


class UserResponse(BaseModel):
    id: str
    email: str
    timezone: str
    created_at: datetime


class SessionResponse(BaseModel):
    access_token: str
    token_type: str
    expires_in: int
    refresh_token: str
    refresh_expires_in: int
    user: UserResponse


@router.post("/register", status_code=201, response_model=SessionResponse)
def register(body: RegisterRequest, session: Session = Depends(get_session)) -> SessionResponse:
    try:
        issued = register_user(
            session,
            email=body.email,
            password=body.password,
            timezone=body.timezone,
        )
    except EmailTaken as error:
        raise APIError(409, "email_taken", "Почта уже зарегистрирована.") from error

    settings = get_settings()
    return SessionResponse(
        access_token=issued.access_token,
        token_type="Bearer",
        expires_in=settings.access_token_ttl_seconds,
        refresh_token=issued.refresh_token,
        refresh_expires_in=settings.refresh_token_ttl_seconds,
        user=_user_response(issued.user),
    )


def _user_response(user: User) -> UserResponse:
    created_at = user.created_at
    if created_at.tzinfo is None:
        created_at = created_at.replace(tzinfo=ZoneInfo("UTC"))
    return UserResponse(
        id=str(user.id),
        email=user.email,
        timezone=user.timezone,
        created_at=created_at.astimezone(ZoneInfo(user.timezone)),
    )
