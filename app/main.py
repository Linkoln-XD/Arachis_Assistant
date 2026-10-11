from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import API_PREFIX
from app.api.auth import router as auth_router
from app.api.calendar import router as calendar_router
from app.api.errors import register_exception_handlers
from app.api.health import router as health_router
from app.api.meetings import router as meetings_router
from app.api.reminders import router as reminders_router
from app.api.tasks import router as tasks_router
from app.auth.rate_limit import LoginRateLimiter
from app.config import get_settings
from app.db.session import ping_database


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    ping_database()
    yield


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(title=settings.app_name, lifespan=lifespan)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list(),
        allow_methods=["GET", "POST", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type", "Idempotency-Key"],
        expose_headers=["Location"],
        allow_credentials=False,
    )
    app.state.login_rate_limiter = LoginRateLimiter()
    register_exception_handlers(app)
    app.include_router(health_router, prefix=API_PREFIX)
    app.include_router(auth_router, prefix=API_PREFIX)
    app.include_router(tasks_router, prefix=API_PREFIX)
    app.include_router(meetings_router, prefix=API_PREFIX)
    app.include_router(reminders_router, prefix=API_PREFIX)
    app.include_router(calendar_router, prefix=API_PREFIX)
    return app


app = create_app()
