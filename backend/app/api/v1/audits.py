"""Audit routes. Every route here requires the access token."""

import asyncio
import logging
from collections.abc import Callable
from typing import Any
from uuid import UUID

import redis
from fastapi import APIRouter, Depends, HTTPException, Query, WebSocket, WebSocketDisconnect, status
from fastapi.concurrency import run_in_threadpool

from app.api.deps import (
    get_app_settings,
    get_enqueuer,
    get_progress_source,
    get_repository,
    get_run_canceller,
    require_token,
    token_matches,
)
from app.core.config import Settings
from app.core.security import TargetValidationError
from app.db.repository import AuditRepository
from app.schemas.api import (
    AuditCreate,
    AuditCreated,
    AuditFinding,
    AuditStep,
    AuditSummary,
    finding_from_row,
    step_from_row,
)
from app.services.audit_intake import AuditRequestError, request_audit

logger = logging.getLogger(__name__)

FINAL_STATUSES = frozenset({"COMPLETED", "FAILED", "CANCELLED"})
AUTH_TIMEOUT_SECONDS = 10.0
HEARTBEAT_SECONDS = 25.0
STREAM_GRACE_SECONDS = 900.0

router = APIRouter(prefix="/api/v1", dependencies=[Depends(require_token)])
ws_router = APIRouter(prefix="/api/v1")


def _summary_or_404(repo: AuditRepository, session_id: UUID) -> dict[str, Any]:
    row = repo.get_session_summary(session_id)
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Audit not found.")
    return row


@router.post("/audits", response_model=AuditCreated, status_code=status.HTTP_202_ACCEPTED)
def create_audit(
    body: AuditCreate,
    repo: AuditRepository = Depends(get_repository),
    enqueue: Callable[[str], None] = Depends(get_enqueuer),
) -> AuditCreated:
    try:
        request = request_audit(repo, body.url, body.trigger_source)
    except TargetValidationError as exc:
        raise HTTPException(422, str(exc)) from exc
    except AuditRequestError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc

    try:
        enqueue(str(request.session_id))
    except Exception as exc:
        logger.error("could not queue audit %s: %s", request.session_id, type(exc).__name__)
        repo.finish_session(
            request.session_id, "FAILED", "QUEUE_UNAVAILABLE", "The job queue is unavailable."
        )
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE, "The job queue is unavailable."
        ) from exc
    return AuditCreated(session_id=request.session_id)


@router.get("/audits", response_model=list[AuditSummary])
def list_audits(
    limit: int = Query(25, ge=1, le=100),
    offset: int = Query(0, ge=0),
    repo: AuditRepository = Depends(get_repository),
) -> list[AuditSummary]:
    return [AuditSummary(**row) for row in repo.list_session_summaries(limit, offset)]


@router.get("/audits/{session_id}", response_model=AuditSummary)
def get_audit(session_id: UUID, repo: AuditRepository = Depends(get_repository)) -> AuditSummary:
    return AuditSummary(**_summary_or_404(repo, session_id))


@router.get("/audits/{session_id}/steps", response_model=list[AuditStep])
def get_audit_steps(
    session_id: UUID, repo: AuditRepository = Depends(get_repository)
) -> list[AuditStep]:
    _summary_or_404(repo, session_id)
    return [step_from_row(row) for row in repo.list_steps(session_id)]


@router.get("/audits/{session_id}/findings", response_model=list[AuditFinding])
def get_audit_findings(
    session_id: UUID, repo: AuditRepository = Depends(get_repository)
) -> list[AuditFinding]:
    _summary_or_404(repo, session_id)
    return [finding_from_row(row) for row in repo.list_findings(session_id)]


@router.post("/audits/{session_id}/cancel", response_model=AuditSummary)
def cancel_audit(
    session_id: UUID,
    repo: AuditRepository = Depends(get_repository),
    cancel_run: Callable[[str], bool] | None = Depends(get_run_canceller),
) -> AuditSummary:
    row = _summary_or_404(repo, session_id)
    if row["status"] not in ("QUEUED", "RUNNING"):
        raise HTTPException(status.HTTP_409_CONFLICT, "This audit has already finished.")
    if not repo.finish_session(session_id, "CANCELLED", "CANCELLED_BY_USER", "Cancelled by the user."):
        raise HTTPException(status.HTTP_409_CONFLICT, "This audit has already finished.")
    if row["agent_run_id"] and cancel_run is not None:
        cancel_run(row["agent_run_id"])
    return AuditSummary(**_summary_or_404(repo, session_id))


# ---------------------------------------------------------------------------
# WebSocket progress stream
# ---------------------------------------------------------------------------


def _snapshot(summary: dict[str, Any]) -> dict[str, Any]:
    return {
        "event": "snapshot",
        "session_id": str(summary["id"]),
        "status": summary["status"],
        "step_count": summary["step_count"],
        "finding_count": summary["finding_count"],
        "error_code": summary["error_code"],
    }


async def _reject(websocket: WebSocket) -> None:
    await websocket.close(code=status.WS_1008_POLICY_VIOLATION)


@ws_router.websocket("/ws/audits/{session_id}")
async def audit_progress(
    websocket: WebSocket,
    session_id: UUID,
    settings: Settings = Depends(get_app_settings),
    repo: AuditRepository = Depends(get_repository),
    source=Depends(get_progress_source),
) -> None:
    """Send {"type": "auth", "token": "..."} as the first message. The token
    is never accepted in the URL, where it would end up in logs."""
    origin = websocket.headers.get("origin")
    if origin is not None and origin not in settings.cors_origin_list:
        await _reject(websocket)
        return

    await websocket.accept()
    try:
        first = await asyncio.wait_for(websocket.receive_json(), AUTH_TIMEOUT_SECONDS)
    except (asyncio.TimeoutError, WebSocketDisconnect, ValueError, TypeError, KeyError):
        await _reject(websocket)
        return
    supplied = first.get("token") if isinstance(first, dict) and first.get("type") == "auth" else None
    if not isinstance(supplied, str) or not token_matches(settings, supplied):
        await _reject(websocket)
        return

    loop = asyncio.get_running_loop()
    deadline = loop.time() + settings.audit_timeout_seconds + STREAM_GRACE_SECONDS
    try:
        async with source.subscribe(session_id) as reader:
            # Subscribe first, then read the database, so no event is missed.
            summary = await run_in_threadpool(repo.get_session_summary, session_id)
            if summary is None:
                await websocket.send_json({"event": "error", "message": "Audit not found."})
                await _reject(websocket)
                return
            await websocket.send_json(_snapshot(summary))
            if summary["status"] in FINAL_STATUSES:
                await websocket.close(code=status.WS_1000_NORMAL_CLOSURE)
                return

            while True:
                remaining = deadline - loop.time()
                if remaining <= 0:
                    await websocket.close(code=status.WS_1000_NORMAL_CLOSURE)
                    return
                event = await reader.next(min(HEARTBEAT_SECONDS, remaining))
                if event is None:
                    await websocket.send_json({"event": "ping"})
                    continue
                await websocket.send_json(event)
                if event.get("event") == "session_finished":
                    await websocket.close(code=status.WS_1000_NORMAL_CLOSURE)
                    return
    except (WebSocketDisconnect, RuntimeError):
        return
    except (redis.RedisError, OSError):
        logger.error("progress channel unavailable for audit %s", session_id)
        try:
            await websocket.send_json({"event": "error", "message": "Progress channel unavailable."})
            await websocket.close(code=status.WS_1011_INTERNAL_ERROR)
        except (WebSocketDisconnect, RuntimeError):
            pass
