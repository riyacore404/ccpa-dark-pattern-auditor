from datetime import datetime, timezone
from decimal import Decimal
from uuid import UUID, uuid4

import psycopg
import pytest
from fastapi.testclient import TestClient

from app.api.deps import get_app_settings, get_enqueuer, get_repository, get_run_canceller
from app.core.config import Settings
from app.db.repository import PlatformRecord
from app.main import create_app

TOKEN = "t" * 32
AUTH = {"Authorization": f"Bearer {TOKEN}"}
PUBLIC_URL = "https://93.184.216.34/shop"
NOW = datetime(2026, 10, 14, 12, 0, tzinfo=timezone.utc)


def make_settings(**kw):
    values = dict(api_access_token=TOKEN, cors_origins="http://localhost:3000")
    values.update(kw)
    return Settings(_env_file=None, **values)


class FakeRepo:
    def __init__(self):
        self.platform_active = True
        self.sessions = {}
        self.steps = {}
        self.findings = {}
        self.finished = []
        self.fail_with = None

    def _maybe_fail(self):
        if self.fail_with:
            raise self.fail_with

    def get_or_create_platform(self, domain, name=None, category="OTHER"):
        self._maybe_fail()
        return PlatformRecord(id=uuid4(), domain=domain, is_active=self.platform_active)

    def create_session(self, platform_id, url, trigger_source="API"):
        sid = uuid4()
        self.sessions[sid] = dict(
            id=sid, status="QUEUED", domain="93.184.216.34", requested_url=url,
            trigger_source=trigger_source, created_at=NOW, started_at=None, completed_at=None,
            error_code=None, error_message=None, agent_provider=None, agent_run_id=None,
            vision_model=None, taxonomy_version="CCPA-2023", step_count=0, finding_count=0,
        )
        return sid

    def finish_session(self, sid, status, code=None, message=None):
        row = self.sessions[sid]
        if row["status"] not in ("QUEUED", "RUNNING"):
            return False
        row.update(status=status, error_code=code, error_message=message, completed_at=NOW)
        self.finished.append((sid, status, code))
        return True

    def get_session_summary(self, sid):
        self._maybe_fail()
        return self.sessions.get(sid)

    def list_session_summaries(self, limit=25, offset=0):
        rows = list(self.sessions.values())
        return rows[offset : offset + limit]

    def list_steps(self, sid):
        return self.steps.get(sid, [])

    def list_findings(self, sid):
        return self.findings.get(sid, [])


class Harness:
    def __init__(self, **settings_kw):
        self.settings = make_settings(**settings_kw)
        self.repo = FakeRepo()
        self.enqueued = []
        self.cancelled_runs = []
        self.enqueue_error = None
        self.canceller_available = True
        self.app = create_app(self.settings)
        self.app.dependency_overrides[get_app_settings] = lambda: self.settings
        self.app.dependency_overrides[get_repository] = lambda: self.repo
        self.app.dependency_overrides[get_enqueuer] = lambda: self._enqueue
        self.app.dependency_overrides[get_run_canceller] = lambda: (
            self._cancel if self.canceller_available else None
        )
        self.client = TestClient(self.app, raise_server_exceptions=False)

    def _enqueue(self, session_id):
        if self.enqueue_error:
            raise self.enqueue_error
        self.enqueued.append(session_id)

    def _cancel(self, run_id):
        self.cancelled_runs.append(run_id)
        return True

    def add_session(self, status="QUEUED", **extra):
        sid = self.repo.create_session(uuid4(), PUBLIC_URL)
        self.repo.sessions[sid].update(status=status, **extra)
        return sid


@pytest.fixture
def h():
    return Harness()


# --- authentication ---------------------------------------------------------


def test_health_needs_no_token(h):
    assert h.client.get("/health").json() == {"status": "ok"}


@pytest.mark.parametrize(
    "method,path",
    [
        ("get", "/api/v1/audits"),
        ("post", "/api/v1/audits"),
        ("get", f"/api/v1/audits/{uuid4()}"),
        ("get", f"/api/v1/audits/{uuid4()}/steps"),
        ("get", f"/api/v1/audits/{uuid4()}/findings"),
        ("post", f"/api/v1/audits/{uuid4()}/cancel"),
    ],
)
def test_every_audit_route_requires_the_token(h, method, path):
    response = getattr(h.client, method)(path)
    assert response.status_code == 401
    assert response.headers["www-authenticate"] == "Bearer"
    wrong = getattr(h.client, method)(path, headers={"Authorization": "Bearer " + "x" * 32})
    assert wrong.status_code == 401


def test_token_in_the_url_is_ignored(h):
    assert h.client.get(f"/api/v1/audits?token={TOKEN}").status_code == 401


def test_wrong_scheme_is_refused(h):
    assert h.client.get("/api/v1/audits", headers={"Authorization": f"Basic {TOKEN}"}).status_code == 401


def test_nothing_is_served_when_no_token_is_configured():
    harness = Harness(api_access_token=None)
    response = harness.client.get("/api/v1/audits", headers=AUTH)
    assert response.status_code == 503
    assert "API_ACCESS_TOKEN" in response.json()["detail"]
    assert TOKEN not in response.text


def test_valid_token_is_accepted(h):
    assert h.client.get("/api/v1/audits", headers=AUTH).status_code == 200


# --- creating audits --------------------------------------------------------


def test_create_audit_queues_exactly_one_job(h):
    response = h.client.post("/api/v1/audits", headers=AUTH, json={"url": PUBLIC_URL})
    assert response.status_code == 202
    body = response.json()
    assert body["status"] == "QUEUED"
    assert h.enqueued == [body["session_id"]]
    assert UUID(body["session_id"]) in h.repo.sessions


def test_trigger_source_is_recorded(h):
    h.client.post("/api/v1/audits", headers=AUTH, json={"url": PUBLIC_URL, "trigger_source": "DASHBOARD"})
    assert next(iter(h.repo.sessions.values()))["trigger_source"] == "DASHBOARD"


@pytest.mark.parametrize(
    "url",
    [
        "http://localhost/",
        "http://127.0.0.1/",
        "http://169.254.169.254/latest/meta-data",
        "http://10.0.0.5/",
        "https://user:pw@93.184.216.34/",
        "https://93.184.216.34:8443/",
        "ftp://93.184.216.34/",
        "javascript:alert(1)",
    ],
)
def test_unsafe_targets_are_rejected_before_anything_is_stored_or_queued(h, url):
    response = h.client.post("/api/v1/audits", headers=AUTH, json={"url": url})
    assert response.status_code == 422
    assert h.enqueued == [] and h.repo.sessions == {}


def test_extra_fields_and_scheduled_source_are_refused(h):
    assert h.client.post("/api/v1/audits", headers=AUTH, json={"url": PUBLIC_URL, "extra": 1}).status_code == 422
    assert h.client.post("/api/v1/audits", headers=AUTH, json={"url": PUBLIC_URL, "trigger_source": "SCHEDULED"}).status_code == 422
    assert h.client.post("/api/v1/audits", headers=AUTH, json={}).status_code == 422
    assert h.client.post("/api/v1/audits", headers=AUTH, json={"url": "x" * 3000}).status_code == 422


def test_inactive_platform_is_a_conflict(h):
    h.repo.platform_active = False
    response = h.client.post("/api/v1/audits", headers=AUTH, json={"url": PUBLIC_URL})
    assert response.status_code == 409 and h.enqueued == []


def test_queue_failure_marks_the_session_failed_and_returns_503(h):
    h.enqueue_error = ConnectionError("redis password=hunter2 down")
    response = h.client.post("/api/v1/audits", headers=AUTH, json={"url": PUBLIC_URL})
    assert response.status_code == 503
    assert "hunter2" not in response.text
    (sid, status, code), = h.repo.finished
    assert (status, code) == ("FAILED", "QUEUE_UNAVAILABLE")


# --- reading audits ---------------------------------------------------------


def test_list_returns_summaries_and_validates_paging(h):
    h.add_session()
    h.add_session("COMPLETED")
    assert len(h.client.get("/api/v1/audits", headers=AUTH).json()) == 2
    assert len(h.client.get("/api/v1/audits?limit=1", headers=AUTH).json()) == 1
    assert h.client.get("/api/v1/audits?limit=0", headers=AUTH).status_code == 422
    assert h.client.get("/api/v1/audits?limit=101", headers=AUTH).status_code == 422
    assert h.client.get("/api/v1/audits?offset=-1", headers=AUTH).status_code == 422


def test_get_audit_and_not_found_cases(h):
    sid = h.add_session("RUNNING", agent_run_id="run-1", step_count=2)
    body = h.client.get(f"/api/v1/audits/{sid}", headers=AUTH).json()
    assert body["status"] == "RUNNING" and body["agent_run_id"] == "run-1" and body["step_count"] == 2
    assert h.client.get(f"/api/v1/audits/{uuid4()}", headers=AUTH).status_code == 404
    assert h.client.get("/api/v1/audits/not-a-uuid", headers=AUTH).status_code == 422
    assert h.client.get(f"/api/v1/audits/{uuid4()}/steps", headers=AUTH).status_code == 404
    assert h.client.get(f"/api/v1/audits/{uuid4()}/findings", headers=AUTH).status_code == 404


def step_row(n=1, with_paths=True):
    return dict(
        step_number=n, status="COMPLETED", analysis_status="COMPLETED", action_description="Look",
        page_title="T", page_url=PUBLIC_URL, page_url_source="canonical", captured_at=NOW,
        screenshot_sha256="a" * 64, dom_sha256="b" * 64, dom_truncated=False,
        screenshot_object_path="audit-sessions/secret/step-0001/screenshot.jpg" if with_paths else None,
        dom_object_path="audit-sessions/secret/step-0001/dom.html" if with_paths else None,
    )


def test_steps_never_expose_storage_paths(h):
    sid = h.add_session("COMPLETED")
    h.repo.steps[sid] = [step_row(1), step_row(2, with_paths=False)]
    response = h.client.get(f"/api/v1/audits/{sid}/steps", headers=AUTH)
    rows = response.json()
    assert [r["has_evidence"] for r in rows] == [True, False]
    assert "audit-sessions" not in response.text and "object_path" not in response.text


def test_findings_are_returned_as_pending_review_with_float_confidence(h):
    sid = h.add_session("COMPLETED")
    h.repo.findings[sid] = [dict(
        id=uuid4(), step_number=1, category="FALSE_URGENCY", confidence_score=Decimal("0.950"),
        grounding="DOM_VERIFIED", explanation="e", observed_behavior="o", suggested_fix=None,
        offending_element_selector=None, legal_reference="ref", review_status="PENDING_REVIEW",
        evidence=[{"kind": "DOM_TEXT", "observation": "q", "verified": True}],
        model_provider="gemini", model_version="m", created_at=NOW,
    )]
    (finding,) = h.client.get(f"/api/v1/audits/{sid}/findings", headers=AUTH).json()
    assert finding["confidence_score"] == 0.95 and finding["review_status"] == "PENDING_REVIEW"
    assert finding["evidence"][0]["verified"] is True


# --- cancelling -------------------------------------------------------------


def test_cancel_a_queued_audit(h):
    sid = h.add_session("QUEUED")
    response = h.client.post(f"/api/v1/audits/{sid}/cancel", headers=AUTH)
    assert response.status_code == 200
    assert response.json()["status"] == "CANCELLED" and response.json()["error_code"] == "CANCELLED_BY_USER"
    assert h.cancelled_runs == []


def test_cancel_a_running_audit_also_cancels_the_agent_run(h):
    sid = h.add_session("RUNNING", agent_run_id="run-9")
    assert h.client.post(f"/api/v1/audits/{sid}/cancel", headers=AUTH).status_code == 200
    assert h.cancelled_runs == ["run-9"]


def test_cancel_still_works_without_an_agent_client(h):
    h.canceller_available = False
    sid = h.add_session("RUNNING", agent_run_id="run-9")
    assert h.client.post(f"/api/v1/audits/{sid}/cancel", headers=AUTH).json()["status"] == "CANCELLED"
    assert h.cancelled_runs == []


@pytest.mark.parametrize("final", ["COMPLETED", "FAILED", "CANCELLED"])
def test_finished_audits_cannot_be_cancelled(h, final):
    sid = h.add_session(final)
    assert h.client.post(f"/api/v1/audits/{sid}/cancel", headers=AUTH).status_code == 409
    assert h.repo.sessions[sid]["status"] == final


def test_cancel_unknown_audit_is_404(h):
    assert h.client.post(f"/api/v1/audits/{uuid4()}/cancel", headers=AUTH).status_code == 404


# --- cross-cutting ----------------------------------------------------------


def test_database_outage_is_a_clean_503(h):
    h.repo.fail_with = psycopg.OperationalError("connection to server at db.secret-host failed")
    response = h.client.get(f"/api/v1/audits/{uuid4()}", headers=AUTH)
    assert response.status_code == 503
    assert "secret-host" not in response.text


def test_other_database_errors_are_a_clean_500_without_details(h):
    h.repo.fail_with = psycopg.errors.UndefinedTable('relation "public.audit_sessions" does not exist')
    response = h.client.get(f"/api/v1/audits/{uuid4()}", headers=AUTH)
    assert response.status_code == 500
    assert response.json() == {"detail": "A database error occurred."}
    assert "audit_sessions" not in response.text


def test_cors_allows_only_listed_origins_and_no_credentials(h):
    ok = h.client.options(
        "/api/v1/audits",
        headers={"Origin": "http://localhost:3000", "Access-Control-Request-Method": "POST",
                 "Access-Control-Request-Headers": "authorization,content-type"},
    )
    assert ok.headers["access-control-allow-origin"] == "http://localhost:3000"
    assert "access-control-allow-credentials" not in ok.headers
    bad = h.client.options(
        "/api/v1/audits",
        headers={"Origin": "https://evil.example", "Access-Control-Request-Method": "POST"},
    )
    assert "access-control-allow-origin" not in bad.headers


def test_responses_are_not_cacheable(h):
    response = h.client.get("/health")
    assert response.headers["cache-control"] == "no-store"
    assert response.headers["x-content-type-options"] == "nosniff"


def test_docs_exist_only_in_development():
    assert Harness(app_env="development").client.get("/docs").status_code == 200
    prod = Harness(app_env="production")
    assert prod.client.get("/docs").status_code == 404
    assert prod.client.get("/openapi.json").status_code == 404
