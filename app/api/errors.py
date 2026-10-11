from collections.abc import Mapping
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

_FIELD_CODES = {
    "missing": "required",
    "string_too_short": "too_short",
    "string_too_long": "too_long",
    "too_short": "too_short",
    "too_long": "too_long",
}

_MESSAGES = {
    "required": "Нужно заполнить поле",
    "too_short": "Слишком короткое значение",
    "too_long": "Слишком длинное значение",
    "invalid": "Некорректное значение",
    "invalid_timezone": "Неизвестный часовой пояс",
    "invalid_status": "Некорректный статус",
    "invalid_range": "Некорректный диапазон",
}


class APIError(Exception):
    def __init__(self, status_code: int, code: str, message: str, details: Mapping[str, Any] | None = None) -> None:
        self.status_code = status_code
        self.code = code
        self.message = message
        self.details = dict(details or {})


def register_exception_handlers(app: FastAPI) -> None:
    app.add_exception_handler(APIError, _api_error)
    app.add_exception_handler(RequestValidationError, _validation_error)


def _api_error(_request: Request, exc: Exception) -> JSONResponse:
    error = exc if isinstance(exc, APIError) else APIError(500, "error", "Ошибка")
    return JSONResponse(
        status_code=error.status_code,
        content={"code": error.code, "message": error.message, "details": error.details},
    )


def _validation_error(_request: Request, exc: Exception) -> JSONResponse:
    validation_error = exc if isinstance(exc, RequestValidationError) else RequestValidationError([])
    errors = [_field_error(item) for item in validation_error.errors()]
    return JSONResponse(
        status_code=422,
        content={
            "code": "validation_error",
            "message": "Некорректные данные",
            "details": {"errors": errors},
        },
    )


def _field_error(item: Mapping[str, Any]) -> dict[str, str]:
    code = _error_code(item)
    return {
        "field": _field_name(item.get("loc", ())),
        "code": code,
        "message": _MESSAGES[code],
    }


def validation_details(errors: list[tuple[str, str]]) -> dict[str, list[dict[str, str]]]:
    return {
        "errors": [
            {"field": field, "code": code, "message": _MESSAGES[code]}
            for field, code in errors
        ]
    }


def _error_code(item: Mapping[str, Any]) -> str:
    message = str(item.get("msg", ""))
    if "invalid_timezone" in message:
        return "invalid_timezone"
    field = _field_name(item.get("loc", ()))
    error_type = str(item.get("type", ""))
    if field == "status" and error_type == "literal_error":
        return "invalid_status"
    return _FIELD_CODES.get(error_type, "invalid")


def _field_name(location: object) -> str:
    if not isinstance(location, tuple):
        return ""
    parts = [str(part) for part in location if part not in {"body", "query", "path"}]
    return ".".join(parts)
