from functools import lru_cache

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

DEFAULT_TINYFISH_BASE_URL = "https://agent.tinyfish.ai"
DEFAULT_EVIDENCE_BUCKET = "private-audit-evidence"


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

    gemini_api_key: SecretStr | None = None
    gemini_model: str | None = None
    audit_max_dom_bytes: int = Field(default=250000, gt=0)

    tinyfish_api_key: SecretStr | None = None
    tinyfish_api_base_url: str = DEFAULT_TINYFISH_BASE_URL

    supabase_url: str | None = None
    supabase_service_role_key: SecretStr | None = None
    supabase_storage_bucket: str = DEFAULT_EVIDENCE_BUCKET

    audit_max_steps: int = Field(default=20, ge=1, le=100)
    audit_timeout_seconds: int = Field(default=180, ge=30, le=900)
    audit_require_target_validation: bool = True
    audit_allow_purchases: bool = False

    @field_validator(
        "gemini_api_key",
        "gemini_model",
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


@lru_cache
def get_settings() -> Settings:
    return Settings()
