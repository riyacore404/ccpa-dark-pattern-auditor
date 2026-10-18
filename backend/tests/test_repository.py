"""Database tests. They run only when TEST_DATABASE_URL points at a throwaway
PostgreSQL database whose name contains "test". The fixture applies the real
migrations 001 and 002 and removes everything it created afterwards.

    TEST_DATABASE_URL=postgresql://user@localhost:5432/ccpa_test pytest -q
"""

import os
import pathlib
from datetime import datetime, timezone
from uuid import uuid4

import pytest

psycopg = pytest.importorskip("psycopg")
from psycopg.rows import dict_row  # noqa: E402

from app.core.config import Settings  # noqa: E402
from app.db.repository import (  # noqa: E402
    AuditRepository,
    DatabaseConfigurationError,
    SessionNotFoundError,
)
from app.schemas.compliance import (  # noqa: E402
    EvidenceKind,
    GroundingLevel,
    GroundingReport,
    ValidatedFinding,
    VerifiedEvidence,
)
from app.schemas.taxonomy import DarkPatternCategory  # noqa: E402
from app.services.audit_intake import request_audit  # noqa: E402
from app.services.audit_runner import AuditRunner  # noqa: E402
from app.services.evidence import StoredEvidence  # noqa: E402
from tests.test_audit_runner import (  # noqa: E402
    FakeAnalyzer,
    FakeEvidence,
    FakeTinyFish,
    run_step,
    watched,
)

URL_ENV = os.environ.get("TEST_DATABASE_URL")
MIGRATIONS = pathlib.Path(__file__).resolve().parents[2] / "database" / "migrations"

pytestmark = pytest.mark.skipif(
    not URL_ENV, reason="set TEST_DATABASE_URL to a throwaway database named *test*"
)

DROP_ALL = """
DROP TABLE IF EXISTS public.dark_pattern_violations, public.audit_steps,
    public.audit_sessions, public.platforms CASCADE;
DROP FUNCTION IF EXISTS public.set_updated_at() CASCADE;
DROP TYPE IF EXISTS public.audit_status, public.audit_step_status,
    public.ccpa_dark_pattern_category, public.finding_review_status,
    public.audit_trigger_source CASCADE;
"""


def _connect():
    return psycopg.connect(URL_ENV, row_factory=dict_row, prepare_threshold=None)


@pytest.fixture(scope="module")
def repo():
    with psycopg.connect(URL_ENV, autocommit=True) as admin:
        name = admin.execute("SELECT current_database()").fetchone()[0]
        assert "test" in name, "refusing to run against a database not named *test*"
        admin.execute(DROP_ALL)
        for script in ("001_initial_schema.sql", "002_audit_run_provenance.sql"):
            admin.execute((MIGRATIONS / script).read_text())
    yield AuditRepository(connect=_connect)
    with psycopg.connect(URL_ENV, autocommit=True) as admin:
        admin.execute(DROP_ALL)


def new_session(repo, url="https://shop.example.com/p"):
    platform = repo.get_or_create_platform(f"{uuid4().hex[:8]}.example.com")
    return repo.create_session(platform.id, url, "API")


def stored(step_number=1, **kw):
    values = dict(
        step_number=step_number, tinyfish_step_id="evt_1", action_description="Look",
        page_title="Title", page_url="https://shop.example.com/p", page_url_source="canonical",
        screenshot_object_path=f"audit-sessions/x/step-{step_number:04d}/screenshot.jpg",
        dom_object_path=f"audit-sessions/x/step-{step_number:04d}/dom.html",
        screenshot_sha256="a" * 64, dom_sha256="b" * 64,
        captured_at=datetime(2026, 10, 11, 12, 0, tzinfo=timezone.utc),
        screenshot_mime_type="image/jpeg", dom_text="text", screenshot=b"\xff\xd8\xff",
    )
    values.update(kw)
    return StoredEvidence(**values)


def finding(**kw):
    values = dict(
        step_number=1, category=DarkPatternCategory.CONFIRM_SHAMING, confidence_score=0.95,
        explanation="why", observed_behavior="what", suggested_fix="fix",
        offending_element_selector="a.decline", legal_reference="ref",
        evidence=[
            VerifiedEvidence(kind=EvidenceKind.DOM_TEXT, observation="No thanks", verified=True),
            VerifiedEvidence(kind=EvidenceKind.VISUAL, observation="grey text", verified=False),
        ],
        grounding=GroundingLevel.DOM_VERIFIED, model_provider="gemini", model_version="m-1",
    )
    values.update(kw)
    return ValidatedFinding(**values)


def test_missing_database_url_is_a_clear_error():
    with pytest.raises(DatabaseConfigurationError):
        AuditRepository(Settings(_env_file=None))


def test_platform_is_created_once_and_reused(repo):
    a = repo.get_or_create_platform("reuse.example.com")
    b = repo.get_or_create_platform("reuse.example.com", name="Other name")
    assert a.id == b.id and a.is_active and a.domain == "reuse.example.com"


def test_new_session_is_queued_with_defaults(repo):
    sid = new_session(repo)
    session = repo.get_session(sid)
    assert session.status == "QUEUED" and session.trigger_source == "API"
    assert session.agent_run_id is None


def test_unknown_session_raises(repo):
    with pytest.raises(SessionNotFoundError):
        repo.get_session(uuid4())


def test_claim_succeeds_once_and_records_provenance(repo):
    sid = new_session(repo)
    assert repo.claim_session(sid, agent_provider="tinyfish", vision_model="m-1") is True
    assert repo.claim_session(sid, agent_provider="tinyfish", vision_model="m-1") is False
    with _connect() as conn:
        row = conn.execute(
            "SELECT status, started_at, agent_provider, vision_model, taxonomy_version "
            "FROM audit_sessions WHERE id = %s", (sid,)
        ).fetchone()
    assert row["status"] == "RUNNING" and row["started_at"] is not None
    assert (row["agent_provider"], row["vision_model"]) == ("tinyfish", "m-1")
    assert row["taxonomy_version"] == "CCPA-2023"


def test_agent_run_id_is_stored(repo):
    sid = new_session(repo)
    repo.set_agent_run_id(sid, "run-xyz")
    assert repo.get_session(sid).agent_run_id == "run-xyz"


def test_finish_works_once_and_a_final_status_is_never_overwritten(repo):
    sid = new_session(repo)
    repo.claim_session(sid, agent_provider="tinyfish", vision_model=None)
    assert repo.finish_session(sid, "FAILED", "TIMEOUT", "x" * 5000) is True
    assert repo.finish_session(sid, "COMPLETED") is False
    with _connect() as conn:
        row = conn.execute(
            "SELECT status, error_code, error_message, completed_at FROM audit_sessions WHERE id=%s",
            (sid,),
        ).fetchone()
    assert row["status"] == "FAILED" and row["error_code"] == "TIMEOUT"
    assert len(row["error_message"]) == 1000 and row["completed_at"] is not None


def test_a_queued_session_can_be_failed_without_a_claim(repo):
    sid = new_session(repo)
    assert repo.finish_session(sid, "FAILED", "TARGET_REJECTED", "no") is True


def test_finish_rejects_non_final_statuses(repo):
    with pytest.raises(ValueError):
        repo.finish_session(new_session(repo), "RUNNING")


def test_step_is_stored_with_hashes_paths_and_provenance(repo):
    sid = new_session(repo)
    repo.insert_step(sid, stored())
    (row,) = repo.list_steps(sid)
    assert row["status"] == "COMPLETED" and row["analysis_status"] == "PENDING"
    assert row["page_url_source"] == "canonical" and row["dom_truncated"] is False
    assert row["screenshot_sha256"] == "a" * 64
    assert row["screenshot_object_path"].endswith("screenshot.jpg")
    assert "http" not in row["screenshot_object_path"]


def test_duplicate_step_number_is_refused(repo):
    sid = new_session(repo)
    repo.insert_step(sid, stored(1))
    with pytest.raises(psycopg.errors.UniqueViolation):
        repo.insert_step(sid, stored(1))


def test_failed_step_keeps_the_gap_visible(repo):
    sid = new_session(repo)
    repo.insert_failed_step(sid, 1, "Click", "https://shop.example.com/p")
    (row,) = repo.list_steps(sid)
    assert row["status"] == "FAILED" and row["analysis_status"] == "SKIPPED"
    assert row["screenshot_object_path"] is None


def test_findings_are_stored_pending_review_with_evidence_and_grounding(repo):
    sid = new_session(repo)
    step_id = repo.insert_step(sid, stored())
    assert repo.save_analysis(sid, step_id, [finding()], dom_truncated=True) == 1
    (row,) = repo.list_findings(sid)
    assert row["review_status"] == "PENDING_REVIEW" and row["reviewed_at"] is None
    assert row["category"] == "CONFIRM_SHAMING" and float(row["confidence_score"]) == 0.95
    assert row["grounding"] == "DOM_VERIFIED" and row["step_number"] == 1
    assert row["evidence"] == [
        {"kind": "DOM_TEXT", "observation": "No thanks", "verified": True},
        {"kind": "VISUAL", "observation": "grey text", "verified": False},
    ]
    (step,) = repo.list_steps(sid)
    assert step["analysis_status"] == "COMPLETED" and step["dom_truncated"] is True


def test_save_analysis_is_all_or_nothing(repo):
    sid = new_session(repo)
    step_id = repo.insert_step(sid, stored())
    with pytest.raises(psycopg.errors.CheckViolation):
        repo.save_analysis(sid, step_id, [finding(), finding(explanation="   ")], False)
    assert repo.list_findings(sid) == []
    assert repo.list_steps(sid)[0]["analysis_status"] == "PENDING"


def test_analysis_status_can_be_marked_failed(repo):
    sid = new_session(repo)
    step_id = repo.insert_step(sid, stored())
    repo.set_analysis_status(step_id, "FAILED")
    assert repo.list_steps(sid)[0]["analysis_status"] == "FAILED"
    with pytest.raises(ValueError):
        repo.set_analysis_status(step_id, "PENDING")


def test_deleting_a_session_removes_its_steps_and_findings(repo):
    sid = new_session(repo)
    step_id = repo.insert_step(sid, stored())
    repo.save_analysis(sid, step_id, [finding()], False)
    with _connect() as conn:
        conn.execute("DELETE FROM audit_sessions WHERE id = %s", (sid,))
    assert repo.list_steps(sid) == [] and repo.list_findings(sid) == []


def test_intake_creates_a_queued_session_through_the_real_repository(repo):
    result = request_audit(
        repo, "https://www.real-intake.example.com/x", "DASHBOARD", resolver=lambda h, p: ["93.184.216.34"]
    )
    assert result.domain == "real-intake.example.com"
    assert repo.get_session(result.session_id).status == "QUEUED"


def test_full_audit_against_the_real_database(repo):
    sid = new_session(repo)
    reports = {1: GroundingReport(accepted=[finding(step_number=1)], dom_truncated=False), 2: GroundingReport()}
    runner = AuditRunner(
        repository=repo,
        tinyfish=FakeTinyFish(watched([run_step(1), run_step(2)])),
        evidence=FakeEvidence(),
        analyzer=FakeAnalyzer(reports),
        vision_model="m-1",
        settings=Settings(_env_file=None),
    )
    outcome = runner.run(sid)
    assert outcome.status == "COMPLETED"
    session = repo.get_session(sid)
    assert session.status == "COMPLETED" and session.agent_run_id == "run-abc-123"
    assert [s["step_number"] for s in repo.list_steps(sid)] == [1, 2]
    assert [f["review_status"] for f in repo.list_findings(sid)] == ["PENDING_REVIEW"]
    assert runner.run(sid).skipped is True  # redelivery does nothing


def test_partial_audit_against_the_real_database(repo):
    sid = new_session(repo)
    runner = AuditRunner(
        repository=repo,
        tinyfish=FakeTinyFish(watched([run_step(1), run_step(2)])),
        evidence=FakeEvidence(fail_on={1}),
        analyzer=FakeAnalyzer(fail_on={2}),
        vision_model="m-1",
        settings=Settings(_env_file=None),
    )
    outcome = runner.run(sid)
    assert (outcome.status, outcome.error_code) == ("COMPLETED", "PARTIAL_RESULTS")
    statuses = [(s["status"], s["analysis_status"]) for s in repo.list_steps(sid)]
    assert statuses == [("FAILED", "SKIPPED"), ("COMPLETED", "FAILED")]


def test_session_summary_counts_steps_and_findings_and_joins_the_platform(repo):
    sid = new_session(repo)
    step_id = repo.insert_step(sid, stored(1))
    repo.insert_failed_step(sid, 2, "Click", "https://shop.example.com/p")
    repo.save_analysis(sid, step_id, [finding(), finding(category=DarkPatternCategory.NAGGING)], False)
    row = repo.get_session_summary(sid)
    assert row["step_count"] == 2 and row["finding_count"] == 2
    assert row["domain"].endswith(".example.com") and row["status"] == "QUEUED"
    assert row["taxonomy_version"] == "CCPA-2023" and row["agent_run_id"] is None


def test_unknown_session_summary_is_none(repo):
    assert repo.get_session_summary(uuid4()) is None


def test_session_list_is_newest_first_and_paged(repo):
    first, second, third = new_session(repo), new_session(repo), new_session(repo)
    ids = [r["id"] for r in repo.list_session_summaries(limit=100)]
    assert ids.index(third) < ids.index(second) < ids.index(first)
    assert len(repo.list_session_summaries(limit=2)) == 2
    page_one = [r["id"] for r in repo.list_session_summaries(limit=2, offset=0)]
    page_two = [r["id"] for r in repo.list_session_summaries(limit=2, offset=2)]
    assert not set(page_one) & set(page_two)


@pytest.mark.parametrize("limit,offset", [(0, 0), (101, 0), (10, -1)])
def test_session_list_rejects_bad_paging(repo, limit, offset):
    with pytest.raises(ValueError):
        repo.list_session_summaries(limit, offset)


def test_cancelled_session_is_not_overwritten_by_a_running_audit(repo):
    sid = new_session(repo)
    repo.claim_session(sid, agent_provider="tinyfish", vision_model="m-1")
    assert repo.finish_session(sid, "CANCELLED", "CANCELLED_BY_USER", "Cancelled by the user.")
    runner = AuditRunner(
        repository=repo,
        tinyfish=FakeTinyFish(watched([run_step(1)])),
        evidence=FakeEvidence(),
        analyzer=FakeAnalyzer(),
        vision_model="m-1",
        settings=Settings(_env_file=None),
    )
    # Simulate the worker arriving after the cancel: the claim is refused.
    assert runner.run(sid).skipped is True
    assert repo.get_session(sid).status == "CANCELLED"
