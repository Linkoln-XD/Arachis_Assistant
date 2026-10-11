from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_name: str = "Arachis Assistant"
    database_url: str = "postgresql+psycopg://arachis:arachis@localhost:5432/arachis"
    jwt_secret: str = "local-development-jwt-secret-key"
    access_token_ttl_seconds: int = 900
    refresh_token_ttl_seconds: int = 2_592_000


@lru_cache
def get_settings() -> Settings:
    return Settings()
