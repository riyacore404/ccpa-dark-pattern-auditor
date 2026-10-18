from functools import lru_cache

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

DEFAULT_TINYFISH_BASE_URL = "https://agent.tinyfish.ai"
DEFAULT_EVIDENCE_BUCKET = "private-audit-evidence"
DEFAULT_CORS_ORIGINS = "http://localhost:3000"
DEFAULT_REDIS_URL = "redis://localhost:6379/0"
MIN_API_TOKEN_CHARS = 24


class Settings(BaseSettings):
    """Backend settings, read from environment variables and backend/.env.

    Only the values needed so far are declared. Unknown variables in the
    environment file are ignored, so the full .env.example can be used as is.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    app_name: str = "CCPA Dark Pattern Auto-Auditor"
    app_env: str = "development"
    cors_origins: str = DEFAULT_CORS_ORIGINS
    api_access_token: SecretStr | None = None

    redis_url: str = DEFAULT_REDIS_URL
    celery_broker_url: str | None = None
    celery_result_backend: str | None = None

    gemini_api_key: SecretStr | None = None
    gemini_model: str | None = None
    audit_max_dom_bytes: int = Field(default=250000, gt=0)

    database_url: SecretStr | None = None

    tinyfish_api_key: SecretStr | None = None
    tinyfish_api_base_url: str = DEFAULT_TINYFISH_BASE_URL

    supabase_url: str | None = None
    supabase_service_role_key: SecretStr | None = None
    supabase_storage_bucket: str = DEFAULT_EVIDENCE_BUCKET

    audit_max_concurrent_runs: int = Field(default=2, ge=1, le=10)
    audit_max_steps: int = Field(default=20, ge=1, le=100)
    audit_timeout_seconds: int = Field(default=180, ge=30, le=900)
    audit_require_target_validation: bool = True
    audit_allow_purchases: bool = False

    @field_validator(
        "gemini_api_key",
        "gemini_model",
        "database_url",
        "api_access_token",
        "celery_broker_url",
        "celery_result_backend",
        "tinyfish_api_key",
        "supabase_url",
        "supabase_service_role_key",
        mode="before",
    )
    @classmethod
    def _blank_to_none(cls, value):
        # .env.example ships these as empty strings; treat them as unset.
        if isinstance(value, str) and not value.strip():
            return None
        return value

    @field_validator("tinyfish_api_base_url", mode="before")
    @classmethod
    def _blank_tinyfish_url_to_default(cls, value):
        if value is None or (isinstance(value, str) and not value.strip()):
            return DEFAULT_TINYFISH_BASE_URL
        return value

    @field_validator("supabase_storage_bucket", mode="before")
    @classmethod
    def _blank_bucket_to_default(cls, value):
        if value is None or (isinstance(value, str) and not value.strip()):
            return DEFAULT_EVIDENCE_BUCKET
        return value

    @field_validator("cors_origins", "redis_url", mode="before")
    @classmethod
    def _blank_to_default(cls, value, info):
        if value is None or (isinstance(value, str) and not value.strip()):
            return DEFAULT_CORS_ORIGINS if info.field_name == "cors_origins" else DEFAULT_REDIS_URL
        return value

    @field_validator("cors_origins")
    @classmethod
    def _cors_origins_are_explicit(cls, value):
        for origin in (part.strip() for part in value.split(",") if part.strip()):
            if "*" in origin:
                raise ValueError("CORS_ORIGINS must list explicit origins, not wildcards.")
            if not origin.startswith(("http://", "https://")):
                raise ValueError("CORS_ORIGINS entries must start with http:// or https://")
        return value

    @field_validator("redis_url", "celery_broker_url", "celery_result_backend")
    @classmethod
    def _redis_urls_use_redis_scheme(cls, value):
        if value is not None and not value.startswith(("redis://", "rediss://")):
            raise ValueError("Redis URLs must start with redis:// or rediss://")
        return value

    @field_validator("api_access_token")
    @classmethod
    def _api_token_is_long_enough(cls, value):
        if value is not None and len(value.get_secret_value()) < MIN_API_TOKEN_CHARS:
            raise ValueError(
                f"API_ACCESS_TOKEN must be at least {MIN_API_TOKEN_CHARS} characters."
            )
        return value

    @field_validator("audit_allow_purchases")
    @classmethod
    def _purchases_never_allowed(cls, value):
        if value:
            raise ValueError(
                "AUDIT_ALLOW_PURCHASES must stay false: this auditor never "
                "completes purchases, payments or OTP steps."
            )
        return value

    @field_validator("audit_require_target_validation")
    @classmethod
    def _target_validation_cannot_be_disabled(cls, value):
        if not value:
            raise ValueError(
                "AUDIT_REQUIRE_TARGET_VALIDATION must stay true in this version."
            )
        return value

    @property
    def cors_origin_list(self) -> list[str]:
        return [part.strip() for part in self.cors_origins.split(",") if part.strip()]

    @property
    def broker_url(self) -> str:
        return self.celery_broker_url or self.redis_url

    @property
    def result_backend_url(self) -> str:
        return self.celery_result_backend or self.redis_url

    @property
    def docs_enabled(self) -> bool:
        return self.app_env.strip().lower() == "development"


@lru_cache
def get_settings() -> Settings:
    return Settings()
