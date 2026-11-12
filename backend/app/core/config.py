from functools import lru_cache

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_name: str = "Bill Snap API"
    environment: str = "development"
    database_url: str | None = None
    supabase_url: str | None = None
    supabase_anon_key: SecretStr | None = None
    supabase_service_role_key: SecretStr | None = None
    supabase_jwt_secret: SecretStr | None = None
    supabase_storage_bucket: str | None = None
    cors_origins: str = "http://localhost:3000,http://localhost:5173"
    max_upload_bytes: int = Field(default=10 * 1024 * 1024, ge=1024, le=50 * 1024 * 1024)
    upload_rate_limit_per_minute: int = Field(default=10, ge=1, le=120)

    @property
    def cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]

    @property
    def storage_is_configured(self) -> bool:
        return bool(self.supabase_url and self.supabase_storage_bucket and self.supabase_service_role_key)


@lru_cache
def get_settings() -> Settings:
    return Settings()
