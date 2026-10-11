from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api import API_PREFIX
from app.api.health import router as health_router
from app.config import get_settings
from app.db.session import ping_database


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    ping_database()
    yield


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(title=settings.app_name, lifespan=lifespan)
    app.include_router(health_router, prefix=API_PREFIX)
    return app


app = create_app()
