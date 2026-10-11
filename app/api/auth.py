from datetime import datetime
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from fastapi import APIRouter, Depends, Request, Response
from pydantic import BaseModel, EmailStr, Field, field_validator
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.api.errors import APIError
from app.auth.rate_limit import LoginRateLimiter
from app.auth.service import (
    EmailTaken,
    InvalidCredentials,
    InvalidRefresh,
    IssuedSession,
    authenticate,
    register_user,
    revoke_refresh_token,
    rotate_refresh_token,
    update_timezone,
)
from app.config import get_settings
from app.db.models import User
from app.db.session import get_session

router = APIRouter(prefix="/auth")


def _normalize_email(value: object) -> object:
    if isinstance(value, str):
        return value.strip().lower()
    return value


def _known_timezone(value: str) -> str:
    try:
        ZoneInfo(value)
    except ZoneInfoNotFoundError as error:
        raise ValueError("invalid_timezone") from error
    return value


class RegisterRequest(BaseModel):
    email: EmailStr = Field(max_length=254)
    password: str = Field(min_length=8, max_length=128)
    timezone: str = "Europe/Moscow"

    @field_validator("email", mode="before")
    @classmethod
    def normalize_email(cls, value: object) -> object:
        return _normalize_email(value)

    @field_validator("timezone")
    @classmethod
    def known_timezone(cls, value: str) -> str:
        return _known_timezone(value)


class LoginRequest(BaseModel):
    email: EmailStr = Field(max_length=254)
    password: str = Field(min_length=1, max_length=128)

    @field_validator("email", mode="before")
    @classmethod
    def normalize_email(cls, value: object) -> object:
        return _normalize_email(value)


class RefreshRequest(BaseModel):
    refresh_token: str = Field(min_length=1)


class TimezoneRequest(BaseModel):
    timezone: str

    @field_validator("timezone")
    @classmethod
    def known_timezone(cls, value: str) -> str:
        return _known_timezone(value)


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

    return _session_response(issued)


@router.post("/login", response_model=SessionResponse)
def login(body: LoginRequest, request: Request, session: Session = Depends(get_session)) -> SessionResponse:
    limiter: LoginRateLimiter = request.app.state.login_rate_limiter
    address = request.client.host if request.client is not None else "unknown"
    if not limiter.allow(address):
        raise APIError(429, "too_many_requests", "Слишком много попыток входа")
    try:
        issued = authenticate(session, email=body.email, password=body.password)
    except InvalidCredentials as error:
        raise APIError(401, "invalid_credentials", "Неверная почта или пароль") from error
    return _session_response(issued)


@router.post("/refresh", response_model=SessionResponse)
def refresh(body: RefreshRequest, session: Session = Depends(get_session)) -> SessionResponse:
    try:
        issued = rotate_refresh_token(session, body.refresh_token)
    except InvalidRefresh as error:
        raise APIError(401, "invalid_refresh", "Нужно войти снова") from error
    return _session_response(issued)


@router.post("/logout", status_code=204)
def logout(body: RefreshRequest, session: Session = Depends(get_session)) -> Response:
    revoke_refresh_token(session, body.refresh_token)
    return Response(status_code=204)


@router.get("/me", response_model=UserResponse)
def me(user: User = Depends(get_current_user)) -> UserResponse:
    return _user_response(user)


@router.patch("/me", response_model=UserResponse)
def patch_me(
    body: TimezoneRequest,
    session: Session = Depends(get_session),
    user: User = Depends(get_current_user),
) -> UserResponse:
    updated = update_timezone(session, user, body.timezone)
    return _user_response(updated)


def _session_response(issued: IssuedSession) -> SessionResponse:
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
