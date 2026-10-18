"""Run one queued audit end to end.

claim the session -> start the browser agent run -> supervise it -> for each
captured step: store evidence, record the step, analyze it, store findings ->
write the final session status.

Rules this module keeps:
- A session is claimed atomically (QUEUED -> RUNNING), so a redelivered job
  never starts a second paid run.
- Whatever evidence was captured is kept, even when the run is stopped early.
- One bad step does not discard the others; the gap is recorded and the
  session finishes COMPLETED with error_code PARTIAL_RESULTS.
- Findings are stored as PENDING_REVIEW only. This module never reviews.
- run() does not raise for audit problems. It records them on the session.
"""

import logging
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Protocol
from uuid import UUID

from app.core.config import Settings, get_settings
from app.core.security import TargetValidationError
from app.db.repository import AuditRepository
from app.services.evidence import EvidenceError, StoredEvidence, to_step_context
from app.services.gemini import GeminiAnalysisError
from app.services.tinyfish import TinyFishError, WatchedRun, evidence_steps

logger = logging.getLogger(__name__)

AGENT_PROVIDER = "tinyfish"
MAX_ERROR_DETAIL_CHARS = 300

ProgressSink = Callable[[dict[str, Any]], None]


class _TinyFish(Protocol):
    def start_run(self, url: str) -> str: ...
    def watch_run(self, run_id: str) -> WatchedRun: ...
    def cancel_run(self, run_id: str) -> bool: ...


class _Evidence(Protocol):
    def capture_step(self, **kwargs: Any) -> StoredEvidence: ...


class _Analyzer(Protocol):
    def analyze_step(self, step: Any) -> Any: ...


@dataclass(frozen=True)
class AuditOutcome:
    session_id: UUID
    status: str
    error_code: str | None = None
    steps_captured: int = 0
    findings_saved: int = 0
    findings_rejected: int = 0
    skipped: bool = False


def _no_progress(event: dict[str, Any]) -> None:
    return None


def _failure_for(exc: Exception) -> tuple[str, str]:
    """(error_code, message). Messages come only from our own error types,
    which are written not to contain secrets. Anything else is reported by
    class name alone."""
    if isinstance(exc, TargetValidationError):
        return "TARGET_REJECTED", str(exc)
    if isinstance(exc, TinyFishError):
        return "AGENT_ERROR", str(exc)[:MAX_ERROR_DETAIL_CHARS]
    return "INTERNAL_ERROR", f"unexpected {type(exc).__name__}"


class AuditRunner:
    def __init__(
        self,
        *,
        repository: AuditRepository,
        tinyfish: _TinyFish,
        evidence: _Evidence,
        analyzer: _Analyzer,
        vision_model: str | None,
        settings: Settings | None = None,
        progress: ProgressSink = _no_progress,
    ) -> None:
        self._repo = repository
        self._tinyfish = tinyfish
        self._evidence = evidence
        self._analyzer = analyzer
        self._vision_model = vision_model
        self._max_steps = (settings or get_settings()).audit_max_steps
        self._progress = progress

    def _emit(self, session_id: UUID, event: str, **data: Any) -> None:
        # A broken progress channel must never break or hide an audit.
        try:
            self._progress({"event": event, "session_id": str(session_id), **data})
        except Exception:
            logger.warning("progress sink failed for session %s", session_id)

    def run(self, session_id: UUID | str) -> AuditOutcome:
        session = self._repo.get_session(session_id)
        sid = session.id

        claimed = self._repo.claim_session(
            sid, agent_provider=AGENT_PROVIDER, vision_model=self._vision_model
        )
        if not claimed:
            return AuditOutcome(session_id=sid, status=session.status, skipped=True)

        self._emit(sid, "session_started")
        holder: dict[str, str] = {}
        try:
            return self._execute(session, holder)
        except Exception as exc:
            run_id = holder.get("run_id")
            if run_id:
                self._tinyfish.cancel_run(run_id)
            code, message = _failure_for(exc)
            logger.error("audit %s failed: %s (%s)", sid, code, type(exc).__name__)
            status, code = self._finish(sid, "FAILED", code, message)
            self._emit(sid, "session_finished", status=status, error_code=code)
            return AuditOutcome(session_id=sid, status=status, error_code=code)

    def _finish(
        self, sid: UUID, status: str, code: str | None, message: str | None
    ) -> tuple[str, str | None]:
        """Write the final status. If the session was already finished (for
        example cancelled by the user), keep that status and report it."""
        if self._repo.finish_session(sid, status, code, message):
            return status, code
        return self._repo.get_session(sid).status, None

    def _execute(self, session, holder: dict[str, str]) -> AuditOutcome:
        sid = session.id
        run_id = self._tinyfish.start_run(session.requested_url)
        holder["run_id"] = run_id
        self._repo.set_agent_run_id(sid, run_id)

        # The audit may have been cancelled while the run was starting.
        current = self._repo.get_session(sid).status
        if current != "RUNNING":
            self._tinyfish.cancel_run(run_id)
            self._emit(sid, "session_finished", status=current, error_code=None)
            return AuditOutcome(session_id=sid, status=current)

        self._emit(sid, "agent_run_started")

        watched = self._tinyfish.watch_run(run_id)
        captured_steps = evidence_steps(watched.detail)[: self._max_steps]

        steps_ok = capture_failures = analysis_failures = 0
        findings_saved = findings_rejected = 0

        for number, run_step in enumerate(captured_steps, start=1):
            try:
                stored = self._evidence.capture_step(
                    run_id=run_id,
                    step=run_step,
                    session_id=str(sid),
                    step_number=number,
                    requested_url=session.requested_url,
                )
            except (EvidenceError, TinyFishError) as exc:
                logger.warning("audit %s step %s capture failed: %s", sid, number, type(exc).__name__)
                self._repo.insert_failed_step(
                    sid, number, run_step.action, session.requested_url
                )
                capture_failures += 1
                self._emit(sid, "step_failed", step_number=number)
                continue

            step_id = self._repo.insert_step(sid, stored)
            steps_ok += 1
            self._emit(sid, "step_captured", step_number=number)

            try:
                report = self._analyzer.analyze_step(to_step_context(stored))
            except GeminiAnalysisError:
                self._repo.set_analysis_status(step_id, "FAILED")
                analysis_failures += 1
                self._emit(sid, "analysis_failed", step_number=number)
                continue

            self._repo.save_analysis(sid, step_id, report.accepted, report.dom_truncated)
            findings_saved += len(report.accepted)
            findings_rejected += len(report.rejected)
            self._emit(
                sid,
                "step_analyzed",
                step_number=number,
                findings=len(report.accepted),
                rejected=len(report.rejected),
            )

        status, code, message = self._final_status(
            watched, steps_ok, capture_failures, analysis_failures
        )
        status, code = self._finish(sid, status, code, message)
        self._emit(sid, "session_finished", status=status, error_code=code)
        return AuditOutcome(
            session_id=sid,
            status=status,
            error_code=code,
            steps_captured=steps_ok,
            findings_saved=findings_saved,
            findings_rejected=findings_rejected,
        )

    @staticmethod
    def _final_status(
        watched: WatchedRun, steps_ok: int, capture_failures: int, analysis_failures: int
    ) -> tuple[str, str | None, str | None]:
        counts = (
            f"{steps_ok} step(s) captured, {capture_failures} capture failure(s), "
            f"{analysis_failures} analysis failure(s)."
        )
        reason = watched.aborted_reason
        if reason:
            if reason.startswith("guard:"):
                rule = reason.split(":", 1)[1]
                return (
                    "FAILED",
                    "AGENT_ACTION_BLOCKED",
                    f"Stopped for human review: an agent step matched safety rule "
                    f"'{rule}'. {counts}",
                )
            if reason == "step_limit":
                return "FAILED", "STEP_LIMIT_EXCEEDED", f"Stopped at the step limit. {counts}"
            if reason == "timeout":
                return "FAILED", "TIMEOUT", f"Stopped at the time limit. {counts}"
            return "FAILED", "AGENT_STOPPED", f"Stopped early ({reason}). {counts}"

        if watched.detail.status != "COMPLETED":
            detail = str(watched.detail.error or "")[:MAX_ERROR_DETAIL_CHARS]
            return (
                "FAILED",
                "AGENT_RUN_FAILED",
                f"Agent run ended as {watched.detail.status}. {detail} {counts}".strip(),
            )
        if steps_ok == 0:
            return "FAILED", "NO_EVIDENCE_CAPTURED", f"No usable evidence. {counts}"
        if capture_failures or analysis_failures:
            return "COMPLETED", "PARTIAL_RESULTS", f"Some steps are incomplete. {counts}"
        return "COMPLETED", None, None
