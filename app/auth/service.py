from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.auth.security import (
    create_access_token,
    hash_password,
    hash_refresh_token,
    new_refresh_token,
    refresh_expires_at,
)
from app.db.models import RefreshToken, User


class EmailTaken(Exception):
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


def _email_constraint(error: IntegrityError) -> bool:
    diagnostic = getattr(error.orig, "diag", None)
    return getattr(diagnostic, "constraint_name", None) == "uq_users_email"
