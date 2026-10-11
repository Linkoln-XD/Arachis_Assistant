from fastapi import FastAPI

from app.api import API_PREFIX
from app.api.health import router as health_router
from app.config import get_settings


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(title=settings.app_name)
    app.include_router(health_router, prefix=API_PREFIX)
    return app


app = create_app()
