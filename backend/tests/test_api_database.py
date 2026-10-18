"""The HTTP API against a real database. Runs only with TEST_DATABASE_URL
(see test_repository.py)."""

import os
from uuid import UUID

import pytest

psycopg = pytest.importorskip("psycopg")
from fastapi.testclient import TestClient  # noqa: E402
from psycopg.rows import dict_row  # noqa: E402

from app.api.deps import get_app_settings, get_enqueuer, get_repository, get_run_canceller  # noqa: E402
from app.core.config import Settings  # noqa: E402
from app.db.repository import AuditRepository  # noqa: E402
from app.main import create_app  # noqa: E402
from app.schemas.compliance import GroundingReport  # noqa: E402
from app.services.audit_runner import AuditRunner  # noqa: E402
from tests.test_audit_runner import FakeAnalyzer, FakeEvidence, FakeTinyFish, finding, run_step, watched  # noqa: E402
from tests.test_repository import DROP_ALL, MIGRATIONS  # noqa: E402

URL_ENV = os.environ.get("TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(
    not URL_ENV, reason="set TEST_DATABASE_URL to a throwaway database named *test*"
)

TOKEN = "d" * 32
AUTH = {"Authorization": f"Bearer {TOKEN}"}


def _connect():
    return psycopg.connect(URL_ENV, row_factory=dict_row, prepare_threshold=None)


@pytest.fixture(scope="module")
def world():
    with psycopg.connect(URL_ENV, autocommit=True) as admin:
        assert "test" in admin.execute("SELECT current_database()").fetchone()[0]
        admin.execute(DROP_ALL)
        for script in ("001_initial_schema.sql", "002_audit_run_provenance.sql"):
            admin.execute((MIGRATIONS / script).read_text())
    repo = AuditRepository(connect=_connect)
    settings = Settings(_env_file=None, api_access_token=TOKEN)
    queued, cancelled_runs = [], []
    app = create_app(settings)
    app.dependency_overrides[get_app_settings] = lambda: settings
    app.dependency_overrides[get_repository] = lambda: repo
    app.dependency_overrides[get_enqueuer] = lambda: queued.append
    app.dependency_overrides[get_run_canceller] = lambda: cancelled_runs.append
    yield TestClient(app), repo, queued, cancelled_runs
    with psycopg.connect(URL_ENV, autocommit=True) as admin:
        admin.execute(DROP_ALL)


def test_create_read_and_review_an_audit_end_to_end(world):
    client, repo, queued, _ = world
    created = client.post("/api/v1/audits", headers=AUTH, json={"url": "https://93.184.216.34/shop"})
    assert created.status_code == 202
    sid = created.json()["session_id"]
    assert queued == [sid]

    detail = client.get(f"/api/v1/audits/{sid}", headers=AUTH).json()
    assert detail["status"] == "QUEUED" and detail["domain"] == "93.184.216.34"

    reports = {1: GroundingReport(accepted=[finding(step_number=1)]), 2: GroundingReport()}
    runner = AuditRunner(
        repository=repo,
        tinyfish=FakeTinyFish(watched([run_step(1), run_step(2)])),
        evidence=FakeEvidence(),
        analyzer=FakeAnalyzer(reports),
        vision_model="m-1",
        settings=Settings(_env_file=None),
    )
    assert runner.run(UUID(sid)).status == "COMPLETED"

    detail = client.get(f"/api/v1/audits/{sid}", headers=AUTH).json()
    assert detail["status"] == "COMPLETED" and detail["step_count"] == 2 and detail["finding_count"] == 1
    assert detail["agent_run_id"] == "run-abc-123" and detail["vision_model"] == "m-1"

    steps = client.get(f"/api/v1/audits/{sid}/steps", headers=AUTH)
    assert [s["step_number"] for s in steps.json()] == [1, 2]
    assert all(s["has_evidence"] for s in steps.json())
    assert "audit-sessions" not in steps.text

    (found,) = client.get(f"/api/v1/audits/{sid}/findings", headers=AUTH).json()
    assert found["review_status"] == "PENDING_REVIEW" and found["confidence_score"] == 0.9
    assert found["evidence"] == [{"kind": "DOM_TEXT", "observation": "q", "verified": True}]
    assert found["step_number"] == 1 and found["category"] == "FALSE_URGENCY"

    listed = client.get("/api/v1/audits?limit=5", headers=AUTH).json()
    assert sid in [row["id"] for row in listed]


def test_cancelling_a_queued_audit_stops_the_worker_from_running_it(world):
    client, repo, _, cancelled_runs = world
    sid = client.post("/api/v1/audits", headers=AUTH, json={"url": "https://93.184.216.34/other"}).json()["session_id"]
    response = client.post(f"/api/v1/audits/{sid}/cancel", headers=AUTH)
    assert response.json()["status"] == "CANCELLED" and response.json()["error_code"] == "CANCELLED_BY_USER"
    runner = AuditRunner(
        repository=repo, tinyfish=FakeTinyFish(watched([run_step(1)])), evidence=FakeEvidence(),
        analyzer=FakeAnalyzer(), vision_model="m", settings=Settings(_env_file=None),
    )
    assert runner.run(UUID(sid)).skipped is True
    assert client.post(f"/api/v1/audits/{sid}/cancel", headers=AUTH).status_code == 409
    assert cancelled_runs == []


def test_a_failed_queue_publish_leaves_a_failed_session_in_the_database(world):
    client, repo, _, _ = world
    app = client.app
    original = app.dependency_overrides[get_enqueuer]

    def broken():
        def enqueue(session_id):
            raise ConnectionError("down")
        return enqueue

    app.dependency_overrides[get_enqueuer] = broken
    try:
        response = client.post("/api/v1/audits", headers=AUTH, json={"url": "https://93.184.216.34/queue"})
    finally:
        app.dependency_overrides[get_enqueuer] = original
    assert response.status_code == 503
    newest = repo.list_session_summaries(limit=1)[0]
    assert newest["status"] == "FAILED" and newest["error_code"] == "QUEUE_UNAVAILABLE"
