from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.auth.security import (
    create_access_token,
    hash_password,
    hash_refresh_token,
    new_refresh_token,
    refresh_expires_at,
    verify_password,
)
from app.db.models import RefreshToken, User

_DUMMY_PASSWORD_HASH = hash_password("not-a-real-password")


class EmailTaken(Exception):
    pass


class InvalidCredentials(Exception):
    pass


class InvalidRefresh(Exception):
    pass


@dataclass(frozen=True)
class IssuedSession:
    user: User
    access_token: str
    refresh_token: str


def register_user(session: Session, *, email: str, password: str, timezone: str) -> IssuedSession:
    if session.scalar(select(User.id).where(User.email == email)) is not None:
        raise EmailTaken

    user = User(email=email, password_hash=hash_password(password), timezone=timezone)
    session.add(user)
    try:
        session.flush()
    except IntegrityError as error:
        session.rollback()
        if _email_constraint(error):
            raise EmailTaken from error
        raise

    return _issue_session(session, user)


def authenticate(session: Session, *, email: str, password: str) -> IssuedSession:
    user = session.scalar(select(User).where(User.email == email))
    if user is None:
        verify_password(password, _DUMMY_PASSWORD_HASH)
        raise InvalidCredentials
    if not verify_password(password, user.password_hash):
        raise InvalidCredentials
    return _issue_session(session, user)


def rotate_refresh_token(session: Session, raw_token: str) -> IssuedSession:
    stored = _find_refresh_token(session, raw_token)
    if stored is None or stored.expires_at <= datetime.now(UTC):
        if stored is not None:
            session.delete(stored)
            session.commit()
        raise InvalidRefresh
    user = session.get(User, stored.user_id)
    session.delete(stored)
    if user is None:
        session.commit()
        raise InvalidRefresh
    return _issue_session(session, user)


def revoke_refresh_token(session: Session, raw_token: str) -> None:
    stored = _find_refresh_token(session, raw_token)
    if stored is None:
        return
    session.delete(stored)
    session.commit()


def update_timezone(session: Session, user: User, timezone: str) -> User:
    user.timezone = timezone
    session.commit()
    return user


def _issue_session(session: Session, user: User) -> IssuedSession:
    raw_refresh = new_refresh_token()
    session.add(
        RefreshToken(
            user_id=user.id,
            token_hash=hash_refresh_token(raw_refresh),
            expires_at=refresh_expires_at(),
        )
    )
    session.commit()
    return IssuedSession(
        user=user,
        access_token=create_access_token(user.id),
        refresh_token=raw_refresh,
    )


def _find_refresh_token(session: Session, raw_token: str) -> RefreshToken | None:
    return session.scalar(select(RefreshToken).where(RefreshToken.token_hash == hash_refresh_token(raw_token)))


def _email_constraint(error: IntegrityError) -> bool:
    diagnostic = getattr(error.orig, "diag", None)
    return getattr(diagnostic, "constraint_name", None) == "uq_users_email"
