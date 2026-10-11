from functools import lru_cache

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


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

    @field_validator("gemini_api_key", "gemini_model", mode="before")
    @classmethod
    def _blank_to_none(cls, value):
        # .env.example ships these as empty strings; treat them as unset.
        if isinstance(value, str) and not value.strip():
            return None
        return value


@lru_cache
def get_settings() -> Settings:
    return Settings()
