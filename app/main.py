from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api import API_PREFIX
from app.api.auth import router as auth_router
from app.api.errors import register_exception_handlers
from app.api.health import router as health_router
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
    app.state.login_rate_limiter = LoginRateLimiter()
    register_exception_handlers(app)
    app.include_router(health_router, prefix=API_PREFIX)
    app.include_router(auth_router, prefix=API_PREFIX)
    return app


app = create_app()
