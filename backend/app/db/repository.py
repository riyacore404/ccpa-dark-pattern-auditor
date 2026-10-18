"""Postgres access for audit sessions, steps and findings.

Plain SQL through psycopg. Each method runs in its own transaction, so a
crash never leaves a half-written step. The connection comes from a factory so
tests and the owner probe can substitute their own.

Findings are always stored as PENDING_REVIEW. Nothing here changes a review
status; only a human reviewer does that, in a later phase.
"""

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any
from uuid import UUID

import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from app.core.config import Settings, get_settings
from app.schemas.compliance import ValidatedFinding
from app.schemas.taxonomy import TAXONOMY_VERSION
from app.services.evidence import StoredEvidence

ALLOWED_FINAL_STATUSES = frozenset({"COMPLETED", "FAILED", "CANCELLED"})
ANALYSIS_STATUSES = frozenset({"COMPLETED", "FAILED", "SKIPPED"})
PLATFORM_CATEGORIES = frozenset(
    {"E_COMMERCE", "QUICK_COMMERCE", "TRAVEL", "SUBSCRIPTION", "OTHER"}
)
TRIGGER_SOURCES = frozenset({"DASHBOARD", "API", "SCHEDULED"})
_ERROR_MESSAGE_MAX_CHARS = 1000


class DatabaseConfigurationError(RuntimeError):
    """DATABASE_URL is missing."""


class SessionNotFoundError(LookupError):
    """No audit session has that id."""


@dataclass(frozen=True)
class SessionRecord:
    id: UUID
    platform_id: UUID
    status: str
    trigger_source: str
    requested_url: str
    agent_run_id: str | None


@dataclass(frozen=True)
class PlatformRecord:
    id: UUID
    domain: str
    is_active: bool


def _as_uuid(value: UUID | str) -> UUID:
    return value if isinstance(value, UUID) else UUID(str(value))


def _default_connect(settings: Settings | None) -> Callable[[], Any]:
    settings = settings or get_settings()
    if settings.database_url is None:
        raise DatabaseConfigurationError("DATABASE_URL is not set in backend/.env.")
    dsn = settings.database_url.get_secret_value()

    def connect():
        # prepare_threshold=None keeps this working behind transaction-mode
        # connection poolers, which do not support prepared statements.
        return psycopg.connect(
            dsn, row_factory=dict_row, prepare_threshold=None, connect_timeout=10
        )

    return connect


class AuditRepository:
    def __init__(
        self,
        settings: Settings | None = None,
        connect: Callable[[], Any] | None = None,
    ) -> None:
        self._connect = connect or _default_connect(settings)

    # -- platforms ---------------------------------------------------------

    def get_or_create_platform(
        self, domain: str, name: str | None = None, category: str = "OTHER"
    ) -> PlatformRecord:
        if category not in PLATFORM_CATEGORIES:
            raise ValueError("unknown platform category")
        with self._connect() as conn, conn.cursor() as cur:
            cur.execute(
                "INSERT INTO public.platforms (domain, name, category) "
                "VALUES (%s, %s, %s) ON CONFLICT (domain) DO NOTHING "
                "RETURNING id, domain, is_active",
                (domain, name or domain, category),
            )
            row = cur.fetchone()
            if row is None:
                cur.execute(
                    "SELECT id, domain, is_active FROM public.platforms WHERE domain = %s",
                    (domain,),
                )
                row = cur.fetchone()
        return PlatformRecord(id=row["id"], domain=row["domain"], is_active=row["is_active"])

    # -- sessions ----------------------------------------------------------

    def create_session(
        self, platform_id: UUID | str, requested_url: str, trigger_source: str = "API"
    ) -> UUID:
        if trigger_source not in TRIGGER_SOURCES:
            raise ValueError("unknown trigger source")
        with self._connect() as conn, conn.cursor() as cur:
            cur.execute(
                "INSERT INTO public.audit_sessions "
                "(platform_id, requested_url, trigger_source) "
                "VALUES (%s, %s, %s) RETURNING id",
                (_as_uuid(platform_id), requested_url, trigger_source),
            )
            return cur.fetchone()["id"]

    def get_session(self, session_id: UUID | str) -> SessionRecord:
        with self._connect() as conn, conn.cursor() as cur:
            cur.execute(
                "SELECT id, platform_id, status, trigger_source, requested_url, agent_run_id "
                "FROM public.audit_sessions WHERE id = %s",
                (_as_uuid(session_id),),
            )
            row = cur.fetchone()
        if row is None:
            raise SessionNotFoundError("audit session not found")
        return SessionRecord(**row)

    def claim_session(
        self,
        session_id: UUID | str,
        *,
        agent_provider: str,
        vision_model: str | None,
    ) -> bool:
        """QUEUED -> RUNNING, atomically. Returns False when another worker
        already claimed it, so a redelivered job cannot start a second run."""
        with self._connect() as conn, conn.cursor() as cur:
            cur.execute(
                "UPDATE public.audit_sessions SET status = 'RUNNING', "
                "started_at = NOW(), agent_provider = %s, vision_model = %s, "
                "taxonomy_version = %s "
                "WHERE id = %s AND status = 'QUEUED' RETURNING id",
                (agent_provider, vision_model, TAXONOMY_VERSION, _as_uuid(session_id)),
            )
            return cur.fetchone() is not None

    def set_agent_run_id(self, session_id: UUID | str, run_id: str) -> None:
        with self._connect() as conn, conn.cursor() as cur:
            cur.execute(
                "UPDATE public.audit_sessions SET agent_run_id = %s WHERE id = %s",
                (run_id, _as_uuid(session_id)),
            )

    def finish_session(
        self,
        session_id: UUID | str,
        status: str,
        error_code: str | None = None,
        error_message: str | None = None,
    ) -> bool:
        """Move an unfinished session to a final status. Returns False when
        it was already finished, so a final status is never overwritten."""
        if status not in ALLOWED_FINAL_STATUSES:
            raise ValueError("not a final status")
        message = error_message[:_ERROR_MESSAGE_MAX_CHARS] if error_message else None
        with self._connect() as conn, conn.cursor() as cur:
            cur.execute(
                "UPDATE public.audit_sessions SET status = %s, "
                "started_at = COALESCE(started_at, NOW()), completed_at = NOW(), "
                "error_code = %s, error_message = %s "
                "WHERE id = %s AND status IN ('QUEUED', 'RUNNING') RETURNING id",
                (status, error_code, message, _as_uuid(session_id)),
            )
            return cur.fetchone() is not None

    # -- steps -------------------------------------------------------------

    def insert_step(self, session_id: UUID | str, evidence: StoredEvidence) -> UUID:
        with self._connect() as conn, conn.cursor() as cur:
            cur.execute(
                "INSERT INTO public.audit_steps "
                "(session_id, step_number, status, action_description, page_title, "
                "page_url, page_url_source, screenshot_object_path, dom_object_path, "
                "screenshot_sha256, dom_sha256, captured_at) "
                "VALUES (%s, %s, 'COMPLETED', %s, %s, %s, %s, %s, %s, %s, %s, %s) "
                "RETURNING id",
                (
                    _as_uuid(session_id),
                    evidence.step_number,
                    evidence.action_description,
                    evidence.page_title,
                    evidence.page_url,
                    evidence.page_url_source,
                    evidence.screenshot_object_path,
                    evidence.dom_object_path,
                    evidence.screenshot_sha256,
                    evidence.dom_sha256,
                    evidence.captured_at,
                ),
            )
            return cur.fetchone()["id"]

    def insert_failed_step(
        self,
        session_id: UUID | str,
        step_number: int,
        action_description: str | None,
        page_url: str,
    ) -> UUID:
        """A step whose evidence could not be captured. Kept so the gap is
        visible to the reviewer instead of silently missing."""
        with self._connect() as conn, conn.cursor() as cur:
            cur.execute(
                "INSERT INTO public.audit_steps "
                "(session_id, step_number, status, action_description, page_url, "
                "page_url_source, analysis_status) "
                "VALUES (%s, %s, 'FAILED', %s, %s, 'requested_url', 'SKIPPED') "
                "RETURNING id",
                (_as_uuid(session_id), step_number, action_description, page_url),
            )
            return cur.fetchone()["id"]

    def set_analysis_status(self, step_id: UUID | str, status: str) -> None:
        if status not in ANALYSIS_STATUSES:
            raise ValueError("unknown analysis status")
        with self._connect() as conn, conn.cursor() as cur:
            cur.execute(
                "UPDATE public.audit_steps SET analysis_status = %s WHERE id = %s",
                (status, _as_uuid(step_id)),
            )

    def save_analysis(
        self,
        session_id: UUID | str,
        step_id: UUID | str,
        findings: list[ValidatedFinding],
        dom_truncated: bool,
    ) -> int:
        """Store a step's findings and mark its analysis complete, in one
        transaction. Every finding is stored as PENDING_REVIEW."""
        with self._connect() as conn, conn.cursor() as cur:
            for finding in findings:
                cur.execute(
                    "INSERT INTO public.dark_pattern_violations "
                    "(session_id, step_id, category, confidence_score, explanation, "
                    "observed_behavior, suggested_fix, offending_element_selector, "
                    "legal_reference, review_status, model_provider, model_version, "
                    "evidence, grounding) "
                    "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, 'PENDING_REVIEW', "
                    "%s, %s, %s, %s)",
                    (
                        _as_uuid(session_id),
                        _as_uuid(step_id),
                        finding.category.value,
                        finding.confidence_score,
                        finding.explanation,
                        finding.observed_behavior,
                        finding.suggested_fix,
                        finding.offending_element_selector,
                        finding.legal_reference,
                        finding.model_provider,
                        finding.model_version,
                        Jsonb([item.model_dump(mode="json") for item in finding.evidence]),
                        finding.grounding.value,
                    ),
                )
            cur.execute(
                "UPDATE public.audit_steps SET analysis_status = 'COMPLETED', "
                "dom_truncated = %s WHERE id = %s",
                (dom_truncated, _as_uuid(step_id)),
            )
        return len(findings)

    # -- reads -------------------------------------------------------------

    _SESSION_SUMMARY_SQL = (
        "SELECT s.id, s.status, s.trigger_source, s.requested_url, p.domain, "
        "s.created_at, s.started_at, s.completed_at, s.error_code, s.error_message, "
        "s.agent_provider, s.vision_model, s.taxonomy_version, s.agent_run_id, "
        "(SELECT count(*) FROM public.audit_steps st WHERE st.session_id = s.id) "
        "AS step_count, "
        "(SELECT count(*) FROM public.dark_pattern_violations v "
        "WHERE v.session_id = s.id) AS finding_count "
        "FROM public.audit_sessions s JOIN public.platforms p ON p.id = s.platform_id "
    )

    def get_session_summary(self, session_id: UUID | str) -> dict[str, Any] | None:
        with self._connect() as conn, conn.cursor() as cur:
            cur.execute(self._SESSION_SUMMARY_SQL + "WHERE s.id = %s", (_as_uuid(session_id),))
            return cur.fetchone()

    def list_session_summaries(self, limit: int = 25, offset: int = 0) -> list[dict[str, Any]]:
        if not 1 <= limit <= 100 or offset < 0:
            raise ValueError("limit must be 1-100 and offset must not be negative")
        with self._connect() as conn, conn.cursor() as cur:
            cur.execute(
                self._SESSION_SUMMARY_SQL + "ORDER BY s.created_at DESC, s.id LIMIT %s OFFSET %s",
                (limit, offset),
            )
            return list(cur.fetchall())

    def list_steps(self, session_id: UUID | str) -> list[dict[str, Any]]:
        with self._connect() as conn, conn.cursor() as cur:
            cur.execute(
                "SELECT * FROM public.audit_steps WHERE session_id = %s "
                "ORDER BY step_number",
                (_as_uuid(session_id),),
            )
            return list(cur.fetchall())

    def list_findings(self, session_id: UUID | str) -> list[dict[str, Any]]:
        with self._connect() as conn, conn.cursor() as cur:
            cur.execute(
                "SELECT v.*, s.step_number FROM public.dark_pattern_violations v "
                "JOIN public.audit_steps s ON s.id = v.step_id "
                "WHERE v.session_id = %s ORDER BY s.step_number, v.created_at",
                (_as_uuid(session_id),),
            )
            return list(cur.fetchall())
