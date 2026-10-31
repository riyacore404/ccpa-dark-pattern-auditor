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
- If the model fails several steps in a row, analysis stops for the rest of
  the audit (those steps are marked SKIPPED) so an outage cannot stall it.
  Evidence is still captured for every step.
- The same finding seen on several steps of one audit (same category, same
  verified page-text quote) is stored once, from the earliest step.
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
from app.schemas.compliance import EvidenceKind
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
    findings_duplicates: int = 0


def _no_progress(event: dict[str, Any]) -> None:
    return None


def _dedup_key(finding: Any) -> tuple[str, str] | None:
    """Identity of a finding across steps: its category plus its first
    verified page-text quote. Findings with no such quote are never merged."""
    for item in finding.evidence:
        if item.kind == EvidenceKind.DOM_TEXT and item.verified:
            return str(finding.category), " ".join(item.observation.split()).casefold()
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
        resolved = settings or get_settings()
        self._max_steps = resolved.audit_max_steps
        self._max_analysis_failures = resolved.audit_max_analysis_failures
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

        steps_ok = capture_failures = analysis_failures = analysis_skipped = 0
        findings_saved = findings_rejected = findings_duplicates = 0
        consecutive_failures = 0
        analysis_stopped = False
        seen_findings: set[tuple[str, str]] = set()

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

            if analysis_stopped:
                self._repo.set_analysis_status(step_id, "SKIPPED")
                analysis_skipped += 1
                self._emit(sid, "analysis_skipped", step_number=number)
                continue

            try:
                report = self._analyzer.analyze_step(to_step_context(stored))
            except GeminiAnalysisError as exc:
                cause = exc.__cause__
                logger.warning(
                    "audit %s step %s analysis failed: %s (cause %s, code %s)",
                    sid,
                    number,
                    exc,
                    type(cause).__name__ if cause else "none",
                    getattr(cause, "code", None),
                )
                self._repo.set_analysis_status(step_id, "FAILED")
                analysis_failures += 1
                consecutive_failures += 1
                self._emit(sid, "analysis_failed", step_number=number)
                if consecutive_failures >= self._max_analysis_failures:
                    analysis_stopped = True
                    logger.warning(
                        "audit %s: %d analysis failures in a row; skipping analysis "
                        "for the remaining steps",
                        sid,
                        consecutive_failures,
                    )
                continue

            consecutive_failures = 0
            kept = []
            for item in report.accepted:
                key = _dedup_key(item)
                if key is not None and key in seen_findings:
                    findings_duplicates += 1
                    continue
                if key is not None:
                    seen_findings.add(key)
                kept.append(item)
            self._repo.save_analysis(sid, step_id, kept, report.dom_truncated)
            findings_saved += len(kept)
            findings_rejected += len(report.rejected)
            self._emit(
                sid,
                "step_analyzed",
                step_number=number,
                findings=len(kept),
                rejected=len(report.rejected),
            )

        status, code, message = self._final_status(
            watched, steps_ok, capture_failures, analysis_failures, analysis_skipped
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
            findings_duplicates=findings_duplicates,
        )

    @staticmethod
    def _final_status(
        watched: WatchedRun,
        steps_ok: int,
        capture_failures: int,
        analysis_failures: int,
        analysis_skipped: int = 0,
    ) -> tuple[str, str | None, str | None]:
        counts = (
            f"{steps_ok} step(s) captured, {capture_failures} capture failure(s), "
            f"{analysis_failures} analysis failure(s)."
        )
        if analysis_skipped:
            counts += f" {analysis_skipped} step(s) not analysed after repeated model failures."
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
        if capture_failures or analysis_failures or analysis_skipped:
            return "COMPLETED", "PARTIAL_RESULTS", f"Some steps are incomplete. {counts}"
        return "COMPLETED", None, None
