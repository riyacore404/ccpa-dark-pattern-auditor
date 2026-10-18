"""The audit job. All real work happens in AuditRunner; this file only
builds it from settings and records configuration problems on the session
so a misconfigured worker never leaves an audit stuck in QUEUED."""

import logging
from collections.abc import Callable
from typing import Any
from uuid import UUID

from google import genai
from google.genai import types

from app.core.config import Settings, get_settings
from app.db.repository import AuditRepository, DatabaseConfigurationError
from app.services.audit_runner import AuditRunner
from app.services.evidence import (
    EvidenceConfigurationError,
    EvidenceService,
    SupabaseEvidenceStore,
)
from app.services.gemini import GeminiAnalyzer, GeminiConfigurationError
from app.services.progress import RedisProgressPublisher
from app.services.tinyfish import TinyFishClient, TinyFishConfigurationError
from app.workers.celery_app import celery_app

logger = logging.getLogger(__name__)

GEMINI_TIMEOUT_MS = 120_000

CONFIGURATION_ERRORS = (
    TinyFishConfigurationError,
    EvidenceConfigurationError,
    GeminiConfigurationError,
    DatabaseConfigurationError,
)


def build_runner(settings: Settings, repository: AuditRepository) -> AuditRunner:
    tinyfish = TinyFishClient(settings)
    store = SupabaseEvidenceStore(settings)
    if settings.gemini_api_key is None:
        raise GeminiConfigurationError("GEMINI_API_KEY is not set. Set it in backend/.env.")
    client = genai.Client(
        api_key=settings.gemini_api_key.get_secret_value(),
        http_options=types.HttpOptions(timeout=GEMINI_TIMEOUT_MS),
    )
    return AuditRunner(
        repository=repository,
        tinyfish=tinyfish,
        evidence=EvidenceService(tinyfish, store),
        analyzer=GeminiAnalyzer(settings, client=client),
        vision_model=settings.gemini_model,
        settings=settings,
        progress=RedisProgressPublisher(settings.redis_url),
    )


def execute_audit(
    session_id: str,
    settings: Settings | None = None,
    repository: AuditRepository | None = None,
    runner_factory: Callable[[Settings, AuditRepository], AuditRunner] = build_runner,
) -> dict[str, Any]:
    settings = settings or get_settings()
    sid = UUID(str(session_id))
    repository = repository or AuditRepository(settings)

    try:
        runner = runner_factory(settings, repository)
    except CONFIGURATION_ERRORS as exc:
        logger.error("audit %s not started: %s", sid, type(exc).__name__)
        repository.finish_session(sid, "FAILED", "WORKER_MISCONFIGURED", str(exc))
        return {"session_id": str(sid), "status": "FAILED", "error_code": "WORKER_MISCONFIGURED"}

    outcome = runner.run(sid)
    return {
        "session_id": str(outcome.session_id),
        "status": outcome.status,
        "error_code": outcome.error_code,
        "steps_captured": outcome.steps_captured,
        "findings_saved": outcome.findings_saved,
        "findings_rejected": outcome.findings_rejected,
        "skipped": outcome.skipped,
    }


@celery_app.task(name="audits.run", max_retries=0)
def run_audit(session_id: str) -> dict[str, Any]:
    return execute_audit(session_id)


