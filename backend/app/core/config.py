from functools import lru_cache

from pydantic import Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_env: str = "development"
    app_debug: bool = True
    database_url: str = "postgresql+asyncpg://cyberbook:cyberbook@postgres:5432/cyberbook"
    redis_url: str = "redis://redis:6379/0"
    jwt_secret: SecretStr = SecretStr("development-only-change-this-secret")
    jwt_access_token_expire_minutes: int = Field(default=20, ge=1, le=1440)
    jwt_refresh_token_expire_days: int = Field(default=14, ge=1, le=90)
    cors_origins: str = "http://localhost,http://localhost:6006"

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    @model_validator(mode="after")
    def require_production_secret(self) -> "Settings":
        if self.app_env == "production" and self.jwt_secret.get_secret_value() == "development-only-change-this-secret":
            raise ValueError("JWT_SECRET must be configured in production")
        return self

    @property
    def allowed_origins(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()