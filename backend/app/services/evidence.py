"""Evidence capture: download a step's screenshot and HTML from TinyFish,
hash the exact bytes, store them in a PRIVATE bucket, and derive the visible
page text that the Gemini analyzer will be shown.

Only object paths and SHA-256 hashes are returned for the database. No public
URL is ever created or stored.
"""

import hashlib
import re
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime, timezone
from html.parser import HTMLParser
from typing import Protocol
from urllib.parse import quote, urlsplit

import httpx

from app.core.config import Settings, get_settings
from app.schemas.compliance import StepContext
from app.services.tinyfish import RunStep, TinyFishClient

_OBJECT_PATH = re.compile(r"^[A-Za-z0-9][A-Za-z0-9/_.-]*$")
_SAFE_ID = re.compile(r"^[A-Za-z0-9-]{1,64}$")
_ERROR_SNIPPET_CHARS = 200


class EvidenceError(RuntimeError):
    """Evidence could not be captured."""


class EvidenceStorageError(EvidenceError):
    """The private evidence store rejected or failed a request."""


class EvidenceConfigurationError(EvidenceError):
    """Required storage settings are missing or unsafe."""


# ---------------------------------------------------------------------------
# HTML to visible text
# ---------------------------------------------------------------------------

_SKIPPED_TAGS = frozenset({"script", "style", "noscript", "template", "svg", "title"})
_VOID_TAGS = frozenset(
    {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta",
     "param", "source", "track", "wbr"}
)
_BLOCK_TAGS = frozenset(
    {"address", "article", "aside", "blockquote", "body", "br", "button", "dd",
     "details", "div", "dl", "dt", "fieldset", "figcaption", "figure", "footer",
     "form", "h1", "h2", "h3", "h4", "h5", "h6", "header", "hr", "label", "li",
     "main", "nav", "ol", "option", "p", "section", "summary", "table", "td",
     "th", "tr", "ul"}
)
_TEXT_ATTRIBUTES = ("alt", "aria-label", "title", "placeholder")
_BUTTON_INPUT_TYPES = frozenset({"submit", "button", "reset"})
_HIDDEN_STYLE = re.compile(r"display\s*:\s*none|visibility\s*:\s*hidden", re.IGNORECASE)


class _TextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self.title_parts: list[str] = []
        self.canonical: str | None = None
        self._stack: list[tuple[str, bool]] = []
        self._hidden_depth = 0

    def _in_title(self) -> bool:
        return any(tag == "title" for tag, _ in self._stack)

    def handle_starttag(self, tag, attrs):
        attributes = {name: (value or "") for name, value in attrs}
        if tag == "link" and "canonical" in attributes.get("rel", "").lower().split():
            self.canonical = self.canonical or attributes.get("href") or None

        hidden = (
            tag in _SKIPPED_TAGS
            or "hidden" in attributes
            or bool(_HIDDEN_STYLE.search(attributes.get("style", "")))
        )
        visible = hidden is False and self._hidden_depth == 0

        if visible:
            if tag in _BLOCK_TAGS:
                self.parts.append("\n")
            for name in _TEXT_ATTRIBUTES:
                if attributes.get(name, "").strip():
                    self.parts.append("\n" + attributes[name])
            if tag == "input" and attributes.get("type", "").lower() in _BUTTON_INPUT_TYPES:
                if attributes.get("value", "").strip():
                    self.parts.append("\n" + attributes["value"])

        if tag not in _VOID_TAGS:
            self._stack.append((tag, hidden))
            if hidden:
                self._hidden_depth += 1

    def handle_endtag(self, tag):
        if tag in _VOID_TAGS:
            return
        for index in range(len(self._stack) - 1, -1, -1):
            if self._stack[index][0] == tag:
                for _, was_hidden in self._stack[index:]:
                    if was_hidden:
                        self._hidden_depth -= 1
                del self._stack[index:]
                break
        if self._hidden_depth == 0 and tag in _BLOCK_TAGS:
            self.parts.append("\n")

    def handle_data(self, data):
        if self._in_title():
            self.title_parts.append(data)
        elif self._hidden_depth == 0:
            self.parts.append(data)


def _parse_html(html: bytes | str) -> _TextExtractor:
    text = html.decode("utf-8", errors="replace") if isinstance(html, bytes) else html
    parser = _TextExtractor()
    parser.feed(text)
    parser.close()
    return parser


def html_to_text(html: bytes | str) -> str:
    """Visible page text: scripts, styles and hidden elements removed;
    button labels, alt text, placeholders and aria labels included."""
    parser = _parse_html(html)
    lines = []
    for line in "".join(parser.parts).splitlines():
        cleaned = " ".join(line.split())
        if cleaned:
            lines.append(cleaned)
    return "\n".join(lines)


def extract_page_metadata(html: bytes | str, requested_url: str) -> tuple[str | None, str, str]:
    """Returns (title, page_url, page_url_source).

    TinyFish steps carry no page URL. The best available is the page's own
    canonical link, used only when it stays on the requested site. Otherwise
    the requested URL is used and the source says so.
    """
    parser = _parse_html(html)
    title = " ".join("".join(parser.title_parts).split()) or None

    def site(url: str) -> str:
        host = (urlsplit(url).hostname or "").lower()
        return host[4:] if host.startswith("www.") else host

    canonical = parser.canonical
    if canonical:
        parts = urlsplit(canonical)
        if parts.scheme in ("http", "https") and site(canonical) == site(requested_url):
            return title, canonical, "canonical"
    return title, requested_url, "requested_url"


# ---------------------------------------------------------------------------
# Storage
# ---------------------------------------------------------------------------


class EvidenceStore(Protocol):
    def put(self, object_path: str, data: bytes, content_type: str) -> None: ...


def _check_object_path(object_path: str) -> str:
    if not _OBJECT_PATH.match(object_path) or ".." in object_path or "//" in object_path:
        raise EvidenceStorageError("invalid evidence object path")
    return object_path


class SupabaseEvidenceStore:
    """Uploads to a PRIVATE Supabase Storage bucket with the backend secret key.

    Per Supabase's API key guidance, a secret key (sb_secret_...) goes in the
    apikey header only. A legacy service_role JWT additionally goes in
    Authorization, because it is a JWT.
    """

    def __init__(self, settings: Settings | None = None, http: httpx.Client | None = None) -> None:
        settings = settings or get_settings()
        if not settings.supabase_url or settings.supabase_service_role_key is None:
            raise EvidenceConfigurationError(
                "SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY must be set in backend/.env."
            )
        base = settings.supabase_url.rstrip("/")
        if not base.startswith("https://"):
            raise EvidenceConfigurationError("SUPABASE_URL must use https")
        self._base = base
        self._bucket = settings.supabase_storage_bucket
        self._key = settings.supabase_service_role_key.get_secret_value()
        self._http = http or httpx.Client(
            timeout=httpx.Timeout(60.0, connect=10.0), follow_redirects=False
        )

    def _headers(self) -> dict[str, str]:
        headers = {"apikey": self._key}
        if self._key.startswith("eyJ") and self._key.count(".") == 2:
            headers["Authorization"] = f"Bearer {self._key}"
        return headers

    def put(self, object_path: str, data: bytes, content_type: str) -> None:
        _check_object_path(object_path)
        url = f"{self._base}/storage/v1/object/{self._bucket}/{quote(object_path, safe='/')}"
        headers = {**self._headers(), "Content-Type": content_type, "x-upsert": "false"}
        try:
            response = self._http.post(url, content=data, headers=headers, follow_redirects=False)
        except httpx.HTTPError as exc:
            raise EvidenceStorageError(f"evidence upload failed: {type(exc).__name__}") from exc
        if response.status_code not in (200, 201):
            snippet = response.text[:_ERROR_SNIPPET_CHARS].replace(self._key, "<redacted>")
            raise EvidenceStorageError(
                f"evidence upload failed: HTTP {response.status_code} {snippet}".strip()
            )


# ---------------------------------------------------------------------------
# Capture
# ---------------------------------------------------------------------------


def sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def evidence_object_path(session_id: str, step_number: int, kind: str, extension: str) -> str:
    """e.g. audit-sessions/<session>/step-0003/screenshot.jpg"""
    if not _SAFE_ID.match(str(session_id)):
        raise EvidenceStorageError("invalid session id")
    if step_number < 1:
        raise EvidenceStorageError("step number must be positive")
    if kind not in ("screenshot", "dom"):
        raise EvidenceStorageError("invalid evidence kind")
    return f"audit-sessions/{session_id}/step-{step_number:04d}/{kind}.{extension}"


@dataclass(frozen=True)
class StoredEvidence:
    step_number: int
    tinyfish_step_id: str
    action_description: str | None
    page_title: str | None
    page_url: str
    page_url_source: str
    screenshot_object_path: str
    dom_object_path: str
    screenshot_sha256: str
    dom_sha256: str
    captured_at: datetime
    screenshot_mime_type: str
    dom_text: str = field(repr=False)
    screenshot: bytes = field(repr=False)


def _parse_timestamp(value: str | None, fallback: datetime) -> datetime:
    if value:
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
            return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
        except ValueError:
            pass
    return fallback


class EvidenceService:
    def __init__(
        self,
        tinyfish: TinyFishClient,
        store: EvidenceStore,
        clock: Callable[[], datetime] = lambda: datetime.now(timezone.utc),
    ) -> None:
        self._tinyfish = tinyfish
        self._store = store
        self._clock = clock

    def capture_step(
        self,
        *,
        run_id: str,
        step: RunStep,
        session_id: str,
        step_number: int,
        requested_url: str,
    ) -> StoredEvidence:
        if not step.has_evidence:
            raise EvidenceError("step has no screenshot and HTML to capture")

        screenshot, mime_type = self._tinyfish.download_screenshot(run_id, step.id)
        html = self._tinyfish.download_html(run_id, step.id)

        extension = "png" if mime_type == "image/png" else "jpg"
        screenshot_path = evidence_object_path(session_id, step_number, "screenshot", extension)
        dom_path = evidence_object_path(session_id, step_number, "dom", "html")

        self._store.put(screenshot_path, screenshot, mime_type)
        self._store.put(dom_path, html, "text/html; charset=utf-8")

        title, page_url, source = extract_page_metadata(html, requested_url)
        return StoredEvidence(
            step_number=step_number,
            tinyfish_step_id=step.id,
            action_description=step.action,
            page_title=title,
            page_url=page_url,
            page_url_source=source,
            screenshot_object_path=screenshot_path,
            dom_object_path=dom_path,
            screenshot_sha256=sha256_hex(screenshot),
            dom_sha256=sha256_hex(html),
            captured_at=_parse_timestamp(step.timestamp, self._clock()),
            screenshot_mime_type=mime_type,
            dom_text=html_to_text(html),
            screenshot=screenshot,
        )


def to_step_context(evidence: StoredEvidence) -> StepContext:
    """Hand a captured step to the Gemini analyzer."""
    return StepContext(
        step_number=evidence.step_number,
        page_url=evidence.page_url,
        page_title=evidence.page_title,
        action_description=evidence.action_description,
        screenshot=evidence.screenshot,
        screenshot_mime_type=evidence.screenshot_mime_type,
        dom_text=evidence.dom_text,
    )
