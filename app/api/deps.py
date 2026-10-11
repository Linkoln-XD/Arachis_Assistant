from typing import Annotated

from fastapi import Depends, Header
from sqlalchemy.orm import Session

from app.api.errors import APIError
from app.auth.security import TokenExpired, TokenInvalid, decode_access_token
from app.db.models import User
from app.db.session import get_session


def get_current_user(
    session: Session = Depends(get_session),
    authorization: Annotated[str | None, Header()] = None,
) -> User:
    token = _bearer_token(authorization)
    try:
        user_id = decode_access_token(token)
    except TokenExpired as error:
        raise APIError(401, "token_expired", "Срок входа истёк") from error
    except TokenInvalid as error:
        raise APIError(401, "unauthorized", "Нужна авторизация") from error

    user = session.get(User, user_id)
    if user is None:
        raise APIError(401, "unauthorized", "Нужна авторизация")
    return user


def _bearer_token(authorization: str | None) -> str:
    if authorization is None:
        raise APIError(401, "unauthorized", "Нужна авторизация")
    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or token == "":
        raise APIError(401, "unauthorized", "Нужна авторизация")
    return token
