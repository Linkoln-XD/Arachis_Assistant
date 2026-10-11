import hashlib
import json
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

from fastapi import Request
from fastapi.responses import JSONResponse, Response
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.errors import APIError, validation_details
from app.db.models import IdempotencyKey, User

_TTL = timedelta(hours=24)


@dataclass(frozen=True)
class PreparedResponse:
    status_code: int
    body: dict[str, Any] | None = None
    headers: dict[str, str] | None = None

    def as_response(self) -> Response:
        headers = self.headers or {}
        if self.body is None:
            return Response(status_code=self.status_code, headers=headers)
        return JSONResponse(status_code=self.status_code, content=self.body, headers=headers)


async def raw_body(request: Request) -> bytes:
    return await request.body()


def valid_key(value: str | None) -> str | None:
    if value is None:
        return None
    if value == "":
        raise APIError(
            422,
            "validation_error",
            "Некорректные данные",
            validation_details([("Idempotency-Key", "too_short")]),
        )
    if len(value) > 128:
        raise APIError(
            422,
            "validation_error",
            "Некорректные данные",
            validation_details([("Idempotency-Key", "too_long")]),
        )
    return value


def run_idempotent(
    session: Session,
    *,
    user: User,
    method: str,
    path: str,
    key: str | None,
    request_body: bytes,
    perform: Callable[[], PreparedResponse],
) -> Response:
    if key is None:
        prepared = perform()
        session.commit()
        return prepared.as_response()

    digest = hashlib.sha256(request_body).hexdigest()
    existing = _current(session, user, method, path, key)
    if existing is not None:
        if existing.request_hash != digest:
            raise APIError(409, "idempotency_conflict", "Этот ключ уже использован с другим запросом")
        return _stored_response(existing)

    prepared = perform()
    session.add(_record(user, method, path, key, digest, prepared))
    try:
        session.commit()
    except IntegrityError as error:
        session.rollback()
        if not _scope_constraint(error):
            raise
        stored = _find(session, user, method, path, key)
        if stored is None or stored.request_hash != digest or stored.expires_at <= datetime.now(UTC):
            raise APIError(409, "idempotency_conflict", "Этот ключ уже использован с другим запросом") from error
        return _stored_response(stored)
    return prepared.as_response()


def _current(session: Session, user: User, method: str, path: str, key: str) -> IdempotencyKey | None:
    existing = _find(session, user, method, path, key)
    if existing is None:
        return None
    if existing.expires_at <= datetime.now(UTC):
        session.delete(existing)
        session.flush()
        return None
    return existing


def _find(session: Session, user: User, method: str, path: str, key: str) -> IdempotencyKey | None:
    return session.scalar(
        select(IdempotencyKey).where(
            IdempotencyKey.user_id == user.id,
            IdempotencyKey.method == method,
            IdempotencyKey.path == path,
            IdempotencyKey.key == key,
        )
    )


def _record(
    user: User,
    method: str,
    path: str,
    key: str,
    digest: str,
    prepared: PreparedResponse,
) -> IdempotencyKey:
    now = datetime.now(UTC)
    body = None if prepared.body is None else json.dumps(prepared.body, ensure_ascii=False)
    return IdempotencyKey(
        user_id=user.id,
        method=method,
        path=path,
        key=key,
        request_hash=digest,
        status_code=prepared.status_code,
        response_body=body,
        response_headers=json.dumps(prepared.headers or {}),
        created_at=now,
        expires_at=now + _TTL,
    )


def _stored_response(row: IdempotencyKey) -> Response:
    body = None if row.response_body is None else json.loads(row.response_body)
    headers = json.loads(row.response_headers)
    if not isinstance(body, dict) and body is not None:
        body = None
    if not isinstance(headers, dict):
        headers = {}
    return PreparedResponse(row.status_code, body, {str(name): str(value) for name, value in headers.items()}).as_response()


def _scope_constraint(error: IntegrityError) -> bool:
    diagnostic = getattr(error.orig, "diag", None)
    return getattr(diagnostic, "constraint_name", None) == "uq_idempotency_keys_scope"
