"""TinyFish Agent API client.

Request and response shapes follow the TinyFish documentation and were
confirmed against a real account with the owner-run probe: run-async with
capture_config, GET /v1/runs/{id}, and the API-key step artifact endpoints.

Notes:
- The step "screenshot"/"html" links inside a run object are browser-session
  links and reject API keys. Artifacts are fetched from
  /v1/runs/{id}/steps/{stepId}/screenshot and /html instead.
- agent_config.max_steps is beta-gated by TinyFish, so the step limit is
  enforced here by cancelling the run.
- The API key is sent only to the configured https base URL, and redirects
  are never followed.
"""

import json
import re
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

import httpx
from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

from app.core.config import Settings, get_settings
from app.core.security import (
    ActionVerdict,
    Resolver,
    check_agent_action,
    system_resolver,
    validate_target_url,
)

_ID_PATTERN = re.compile(r"^[A-Za-z0-9_-]{1,128}$")

TERMINAL_STATUSES = frozenset({"COMPLETED", "FAILED", "CANCELLED"})
DEADLINE_GRACE_SECONDS = 60.0
MAX_SCREENSHOT_BYTES = 10_000_000
MAX_HTML_BYTES = 5_000_000
_ERROR_SNIPPET_CHARS = 300

_JPEG_MAGIC = b"\xff\xd8\xff"
_PNG_MAGIC = b"\x89PNG\r\n\x1a\n"


class TinyFishError(RuntimeError):
    """A TinyFish request failed or returned something unusable."""


class TinyFishConfigurationError(TinyFishError):
    """Required TinyFish settings are missing or unsafe."""


AUDIT_GOAL_TEMPLATE = (
    "You are auditing this website for a consumer-protection review. Browse "
    "it the way an ordinary shopper would to reach the product pages, the "
    "cart and the checkout summary, and look at what a user is shown: "
    "prices, fees, timers, stock messages, pre-selected options, pop-ups, "
    "subscription terms and cancellation paths.\n"
    "Adding an item to the cart is allowed.\n"
    "Hard rules:\n"
    "- Never complete a purchase, booking, subscription or payment. Stop at "
    "the last page before any payment step.\n"
    "- Never enter card, bank, UPI or wallet details, and never request or "
    "enter an OTP or verification code.\n"
    "- Never log in, create an account, or use any credentials. If a login "
    "is required, stop.\n"
    "- Never solve or bypass a CAPTCHA or any other access control. If you "
    "are blocked, stop.\n"
    "- Do not submit any form except a search box or a delivery pincode "
    "check.\n"
    "- Take at most {max_steps} actions.\n"
    "When you have viewed the main product, cart and checkout summary pages, "
    "or you are blocked, stop and return JSON with the keys pages_visited "
    "(a list) and stopped_because (a string)."
)


def build_audit_goal(max_steps: int) -> str:
    return AUDIT_GOAL_TEMPLATE.format(max_steps=max_steps)


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------


class RunStep(BaseModel):
    model_config = ConfigDict(extra="ignore")

    id: str
    timestamp: str | None = None
    status: str | None = None
    action: str | None = None
    screenshot: str | None = None
    html: str | None = None
    duration: str | None = None

    @property
    def has_evidence(self) -> bool:
        """Only steps with both a screenshot and HTML can be analyzed."""
        return bool(self.screenshot) and bool(self.html)


class RunDetail(BaseModel):
    model_config = ConfigDict(extra="ignore")

    run_id: str
    status: str
    num_of_steps: int | None = None
    result: Any = None
    error: Any = None
    steps: list[RunStep] = Field(default_factory=list)

    @field_validator("steps", mode="before")
    @classmethod
    def _null_steps_to_empty(cls, value):
        return [] if value is None else value


def evidence_steps(detail: RunDetail) -> list[RunStep]:
    return [step for step in detail.steps if step.has_evidence]


@dataclass(frozen=True)
class WatchedRun:
    run_id: str
    detail: RunDetail
    aborted_reason: str | None = None
    blocked_action: str | None = None

    @property
    def completed_normally(self) -> bool:
        return self.aborted_reason is None and self.detail.status == "COMPLETED"


# ---------------------------------------------------------------------------
# Client
# ---------------------------------------------------------------------------


def _require_id(value: str, label: str) -> str:
    if not isinstance(value, str) or not _ID_PATTERN.match(value):
        raise TinyFishError(f"invalid {label}")
    return value


def _error_text(status: int, body: bytes) -> str:
    detail = ""
    try:
        parsed = json.loads(body.decode("utf-8", errors="replace"))
        error = parsed.get("error") if isinstance(parsed, dict) else None
        if isinstance(error, dict):
            detail = f"{error.get('code', '')}: {error.get('message', '')}".strip(": ")
        elif error:
            detail = str(error)
    except Exception:
        detail = body[:_ERROR_SNIPPET_CHARS].decode("utf-8", errors="replace")
    return f"HTTP {status}" + (f" - {detail[:_ERROR_SNIPPET_CHARS]}" if detail else "")


class TinyFishClient:
    def __init__(
        self,
        settings: Settings | None = None,
        http: httpx.Client | None = None,
        resolver: Resolver = system_resolver,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        settings = settings or get_settings()
        if settings.tinyfish_api_key is None:
            raise TinyFishConfigurationError(
                "TINYFISH_API_KEY is not set. Set it in backend/.env."
            )
        base = settings.tinyfish_api_base_url.rstrip("/")
        if not base.startswith("https://"):
            raise TinyFishConfigurationError(
                "TINYFISH_API_BASE_URL must use https so the API key is never sent in clear text."
            )
        self._key = settings.tinyfish_api_key.get_secret_value()
        self._base = base
        self._max_steps = settings.audit_max_steps
        self._timeout_seconds = settings.audit_timeout_seconds
        self._resolver = resolver
        self._sleep = sleep
        self._http = http or httpx.Client(
            timeout=httpx.Timeout(30.0, connect=10.0), follow_redirects=False
        )

    # -- low level ---------------------------------------------------------

    def _headers(self, accept: str = "application/json") -> dict[str, str]:
        return {"X-API-Key": self._key, "Accept": accept}

    def _send(
        self,
        method: str,
        path: str,
        *,
        json_body: dict | None = None,
        params: dict | None = None,
        retries: int = 0,
    ) -> httpx.Response:
        last_problem = "request failed"
        for attempt in range(retries + 1):
            try:
                response = self._http.request(
                    method,
                    self._base + path,
                    headers=self._headers(),
                    json=json_body,
                    params=params,
                    follow_redirects=False,
                )
            except httpx.HTTPError as exc:
                last_problem = type(exc).__name__
            else:
                if response.status_code == 429 or response.status_code >= 500:
                    last_problem = _error_text(response.status_code, response.content)
                else:
                    return response
            if attempt < retries:
                self._sleep(1.0 * (attempt + 1))
        raise TinyFishError(f"TinyFish request failed: {last_problem}")

    def _download(self, path: str, *, max_bytes: int, accept: str, retries: int = 2) -> tuple[bytes, str]:
        last_problem = "download failed"
        for attempt in range(retries + 1):
            try:
                with self._http.stream(
                    "GET",
                    self._base + path,
                    headers=self._headers(accept),
                    follow_redirects=False,
                ) as response:
                    if response.status_code != 200:
                        body = response.read()
                        problem = _error_text(response.status_code, body)
                        if response.status_code == 429 or response.status_code >= 500:
                            last_problem = problem
                            raise _Retry()
                        raise TinyFishError(f"TinyFish download failed: {problem}")
                    declared = response.headers.get("content-length")
                    if declared and declared.isdigit() and int(declared) > max_bytes:
                        raise TinyFishError("TinyFish download exceeds the size limit")
                    chunks: list[bytes] = []
                    total = 0
                    for chunk in response.iter_bytes():
                        total += len(chunk)
                        if total > max_bytes:
                            raise TinyFishError("TinyFish download exceeds the size limit")
                        chunks.append(chunk)
                    return b"".join(chunks), response.headers.get("content-type", "")
            except _Retry:
                pass
            except httpx.HTTPError as exc:
                last_problem = type(exc).__name__
            if attempt < retries:
                self._sleep(1.0 * (attempt + 1))
        raise TinyFishError(f"TinyFish download failed: {last_problem}")

    # -- runs --------------------------------------------------------------

    def start_run(self, url: str) -> str:
        """Validate the target, start an async run, and return its run id."""
        safe_url = validate_target_url(url, resolver=self._resolver)
        payload = {
            "url": safe_url,
            "goal": build_audit_goal(self._max_steps),
            "capture_config": {"screenshots": True, "html": True},
            "agent_config": {"max_duration_seconds": self._timeout_seconds},
        }
        response = self._send("POST", "/v1/automation/run-async", json_body=payload)
        try:
            body = response.json()
        except ValueError:
            body = None
        if response.status_code != 200 or not isinstance(body, dict) or not body.get("run_id"):
            raise TinyFishError(
                "TinyFish did not start the run: "
                + _error_text(response.status_code, response.content)
            )
        return _require_id(str(body["run_id"]), "run id")

    def get_run(self, run_id: str) -> RunDetail:
        _require_id(run_id, "run id")
        response = self._send(
            "GET",
            f"/v1/runs/{run_id}",
            params={"screenshots": "url", "html": "url"},
            retries=2,
        )
        if response.status_code != 200:
            raise TinyFishError(
                "TinyFish could not return the run: "
                + _error_text(response.status_code, response.content)
            )
        try:
            return RunDetail.model_validate(response.json())
        except (ValueError, ValidationError) as exc:
            raise TinyFishError("TinyFish returned an unreadable run") from exc

    def cancel_run(self, run_id: str) -> bool:
        """Best effort. Returns True when TinyFish accepted the cancel."""
        _require_id(run_id, "run id")
        try:
            response = self._send("POST", f"/v1/runs/{run_id}/cancel")
        except TinyFishError:
            return False
        return response.status_code == 200

    # -- artifacts ---------------------------------------------------------

    def download_screenshot(self, run_id: str, step_id: str) -> tuple[bytes, str]:
        """Returns (image bytes, mime type). Accepts JPEG or PNG only."""
        _require_id(run_id, "run id")
        _require_id(step_id, "step id")
        data, _ = self._download(
            f"/v1/runs/{run_id}/steps/{step_id}/screenshot",
            max_bytes=MAX_SCREENSHOT_BYTES,
            accept="image/*",
        )
        if data.startswith(_JPEG_MAGIC):
            return data, "image/jpeg"
        if data.startswith(_PNG_MAGIC):
            return data, "image/png"
        raise TinyFishError("screenshot is not a JPEG or PNG image")

    def download_html(self, run_id: str, step_id: str) -> bytes:
        _require_id(run_id, "run id")
        _require_id(step_id, "step id")
        data, _ = self._download(
            f"/v1/runs/{run_id}/steps/{step_id}/html",
            max_bytes=MAX_HTML_BYTES,
            accept="text/html",
        )
        return data

    # -- supervision -------------------------------------------------------

    def watch_run(
        self,
        run_id: str,
        *,
        guard: Callable[[str | None], ActionVerdict] = check_agent_action,
        poll_seconds: float = 5.0,
        clock: Callable[[], float] = time.monotonic,
    ) -> WatchedRun:
        """Poll a run until it ends, cancelling it if the guard blocks a step,
        the step limit is exceeded, or the deadline passes."""
        started = clock()
        deadline = self._timeout_seconds + DEADLINE_GRACE_SECONDS
        screened: set[str] = set()

        while True:
            try:
                detail = self.get_run(run_id)
            except TinyFishError:
                self.cancel_run(run_id)
                raise

            for step in detail.steps:
                if step.id in screened:
                    continue
                screened.add(step.id)
                verdict = guard(step.action)
                if not verdict.allowed:
                    return self._abort(run_id, detail, f"guard:{verdict.rule}", step.action)

            if len(detail.steps) > self._max_steps:
                return self._abort(run_id, detail, "step_limit")

            if detail.status in TERMINAL_STATUSES:
                return WatchedRun(run_id=run_id, detail=detail)

            if clock() - started > deadline:
                return self._abort(run_id, detail, "timeout")

            self._sleep(poll_seconds)

    def _abort(
        self,
        run_id: str,
        detail: RunDetail,
        reason: str,
        blocked_action: str | None = None,
    ) -> WatchedRun:
        self.cancel_run(run_id)
        try:
            detail = self.get_run(run_id)
        except TinyFishError:
            pass  # keep the last state we saw
        return WatchedRun(
            run_id=run_id,
            detail=detail,
            aborted_reason=reason,
            blocked_action=blocked_action,
        )


class _Retry(Exception):
    """Internal signal: retry the download."""
