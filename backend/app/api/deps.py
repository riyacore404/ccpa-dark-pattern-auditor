"""Shared request dependencies: settings, database, auth, queue, progress."""

import secrets
from collections.abc import Callable

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.core.config import Settings, get_settings
from app.db.repository import AuditRepository
from app.services.progress import RedisProgressSource
from app.services.tinyfish import TinyFishClient, TinyFishConfigurationError

_bearer = HTTPBearer(auto_error=False)


def get_app_settings() -> Settings:
    return get_settings()


def get_repository(settings: Settings = Depends(get_app_settings)) -> AuditRepository:
    return AuditRepository(settings)


def token_matches(settings: Settings, supplied: str | None) -> bool:
    expected = settings.api_access_token
    if expected is None or not supplied:
        return False
    return secrets.compare_digest(
        supplied.encode("utf-8"), expected.get_secret_value().encode("utf-8")
    )


def require_token(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
    settings: Settings = Depends(get_app_settings),
) -> None:
    """Fail closed: with no API_ACCESS_TOKEN configured nothing is served."""
    if settings.api_access_token is None:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "API access is not configured. Set API_ACCESS_TOKEN in backend/.env.",
        )
    if credentials is None or not token_matches(settings, credentials.credentials):
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED,
            "Missing or invalid access token.",
            headers={"WWW-Authenticate": "Bearer"},
        )


def get_enqueuer() -> Callable[[str], None]:
    def enqueue(session_id: str) -> None:
        from app.workers.tasks import run_audit

        run_audit.delay(session_id)

    return enqueue


def get_run_canceller(
    settings: Settings = Depends(get_app_settings),
) -> Callable[[str], bool] | None:
    try:
        return TinyFishClient(settings).cancel_run
    except TinyFishConfigurationError:
        return None


def get_progress_source(settings: Settings = Depends(get_app_settings)) -> RedisProgressSource:
    return RedisProgressSource(settings.redis_url)
