import logging
from datetime import datetime, timezone
from uuid import UUID

import pytest

from app.core.config import Settings
from app.core.security import TargetValidationError
from app.db.repository import SessionRecord
from app.schemas.compliance import (
    EvidenceKind,
    GroundingLevel,
    GroundingReport,
    ModelFinding,
    RejectedFinding,
    ValidatedFinding,
    VerifiedEvidence,
)
from app.schemas.taxonomy import DarkPatternCategory
from app.services.audit_runner import AuditRunner
from app.services.evidence import EvidenceStorageError, StoredEvidence
from app.services.gemini import GeminiAnalysisError
from app.services.tinyfish import RunDetail, RunStep, TinyFishError, WatchedRun

SID = UUID("11111111-1111-1111-1111-111111111111")
URL = "https://shop.example.com/product"
RUN = "run-abc-123"


def settings(**kw):
    return Settings(_env_file=None, **kw)


def run_step(i, *, evidence=True, action="Look at the page"):
    return RunStep(
        id=f"evt_{i}",
        timestamp="2026-10-11T15:47:53Z",
        status="RUNNING",
        action=action,
        screenshot="s" if evidence else None,
        html="h" if evidence else None,
    )


def watched(steps, status="COMPLETED", aborted=None, blocked=None, error=None):
    detail = RunDetail(run_id=RUN, status=status, steps=steps, error=error)
    return WatchedRun(run_id=RUN, detail=detail, aborted_reason=aborted, blocked_action=blocked)


def finding(step_number=1, category=DarkPatternCategory.FALSE_URGENCY):
    return ValidatedFinding(
        step_number=step_number,
        category=category,
        confidence_score=0.9,
        explanation="e",
        observed_behavior="o",
        legal_reference="ref",
        evidence=[VerifiedEvidence(kind=EvidenceKind.DOM_TEXT, observation="q", verified=True)],
        grounding=GroundingLevel.DOM_VERIFIED,
        model_provider="gemini",
        model_version="m",
    )


class FakeRepo:
    FINAL = {"COMPLETED", "FAILED", "CANCELLED"}

    def __init__(self, status="QUEUED", cancel_after_run_id=False, cancel_after_capture=False):
        self.status = status
        self.calls = []
        self.claimed = status == "QUEUED"
        self.finished = None
        self.saved = []
        self.failed_steps = []
        self.analysis = {}
        self.cancel_after_run_id = cancel_after_run_id
        self.cancel_after_capture = cancel_after_capture

    def get_session(self, session_id):
        return SessionRecord(
            id=SID, platform_id=SID, status=self.status, trigger_source="API",
            requested_url=URL, agent_run_id=None,
        )

    def claim_session(self, sid, *, agent_provider, vision_model):
        self.calls.append(("claim", agent_provider, vision_model))
        if self.claimed:
            self.status = "RUNNING"
        return self.claimed

    def set_agent_run_id(self, sid, run_id):
        self.calls.append(("run_id", run_id))
        if self.cancel_after_run_id:
            self.status = "CANCELLED"

    def insert_step(self, sid, evidence):
        self.calls.append(("step", evidence.step_number))
        if self.cancel_after_capture:
            self.status = "CANCELLED"
        return f"step-{evidence.step_number}"

    def insert_failed_step(self, sid, number, action, url):
        self.failed_steps.append((number, action, url))
        return f"failed-{number}"

    def set_analysis_status(self, step_id, status):
        self.analysis[step_id] = status

    def save_analysis(self, sid, step_id, findings, dom_truncated):
        self.saved.append((step_id, list(findings), dom_truncated))
        self.analysis[step_id] = "COMPLETED"
        return len(findings)

    def finish_session(self, sid, status, code=None, message=None):
        if self.status in self.FINAL:
            return False
        self.status = status
        self.finished = (status, code, message)
        return True


class FakeTinyFish:
    def __init__(self, result=None, start_error=None, watch_error=None):
        self.result = result
        self.start_error = start_error
        self.watch_error = watch_error
        self.started = []
        self.cancelled = []

    def start_run(self, url):
        self.started.append(url)
        if self.start_error:
            raise self.start_error
        return RUN

    def watch_run(self, run_id):
        if self.watch_error:
            raise self.watch_error
        return self.result

    def cancel_run(self, run_id):
        self.cancelled.append(run_id)
        return True


class FakeEvidence:
    def __init__(self, fail_on=(), error=None):
        self.fail_on = set(fail_on)
        self.error = error or EvidenceStorageError("upload failed")
        self.captures = []

    def capture_step(self, *, run_id, step, session_id, step_number, requested_url):
        self.captures.append((step.id, step_number, session_id))
        if step_number in self.fail_on:
            raise self.error
        return StoredEvidence(
            step_number=step_number, tinyfish_step_id=step.id, action_description=step.action,
            page_title="T", page_url=requested_url, page_url_source="requested_url",
            screenshot_object_path=f"audit-sessions/{session_id}/step-{step_number:04d}/screenshot.jpg",
            dom_object_path=f"audit-sessions/{session_id}/step-{step_number:04d}/dom.html",
            screenshot_sha256="a" * 64, dom_sha256="b" * 64,
            captured_at=datetime(2026, 10, 11, tzinfo=timezone.utc),
            screenshot_mime_type="image/jpeg", dom_text="page text", screenshot=b"\xff\xd8\xff",
        )


class FakeAnalyzer:
    def __init__(self, reports=None, fail_on=(), unexpected_on=()):
        self.reports = reports or {}
        self.fail_on = set(fail_on)
        self.unexpected_on = set(unexpected_on)
        self.seen = []

    def analyze_step(self, ctx):
        self.seen.append(ctx.step_number)
        if ctx.step_number in self.fail_on:
            raise GeminiAnalysisError("Gemini request failed")
        if ctx.step_number in self.unexpected_on:
            raise RuntimeError("secret-key-abc leaked in message")
        return self.reports.get(ctx.step_number, GroundingReport())


def build(result=None, *, repo=None, tinyfish=None, evidence=None, analyzer=None, progress=None, **kw):
    repo = repo or FakeRepo()
    tinyfish = tinyfish or FakeTinyFish(result)
    evidence = evidence or FakeEvidence()
    analyzer = analyzer or FakeAnalyzer()
    events = []
    runner = AuditRunner(
        repository=repo, tinyfish=tinyfish, evidence=evidence, analyzer=analyzer,
        vision_model="test-model", settings=settings(**kw),
        progress=progress or events.append,
    )
    return runner, repo, tinyfish, evidence, analyzer, events


# --- happy path -----------------------------------------------------------


def test_successful_audit_stores_steps_and_pending_findings():
    reports = {1: GroundingReport(accepted=[finding(1)], rejected=[]), 2: GroundingReport()}
    runner, repo, tf, ev, an, events = build(
        watched([run_step(1), run_step(2)]), analyzer=FakeAnalyzer(reports)
    )
    outcome = runner.run(SID)
    assert outcome.status == "COMPLETED" and outcome.error_code is None
    assert (outcome.steps_captured, outcome.findings_saved) == (2, 1)
    assert repo.finished == ("COMPLETED", None, None)
    assert repo.calls[0] == ("claim", "tinyfish", "test-model")
    assert ("run_id", RUN) in repo.calls
    assert tf.started == [URL] and tf.cancelled == []
    assert repo.saved[0][1][0].review_status == "PENDING_REVIEW"
    assert [e["event"] for e in events][0] == "session_started"
    assert events[-1] == {"event": "session_finished", "session_id": str(SID), "status": "COMPLETED", "error_code": None}


def test_rejected_findings_are_counted_not_stored():
    rejected = RejectedFinding(
        finding=ModelFinding(
            category=DarkPatternCategory.NAGGING, confidence_score=0.5, explanation="x",
            observed_behavior="y", evidence=[],
        ),
        reason="quote not found",
    )
    runner, repo, *_ = build(
        watched([run_step(1)]),
        analyzer=FakeAnalyzer({1: GroundingReport(accepted=[finding(1)], rejected=[rejected])}),
    )
    outcome = runner.run(SID)
    assert (outcome.findings_saved, outcome.findings_rejected) == (1, 1)
    assert len(repo.saved[0][1]) == 1


def test_dom_truncation_flag_is_passed_through():
    runner, repo, *_ = build(
        watched([run_step(1)]),
        analyzer=FakeAnalyzer({1: GroundingReport(dom_truncated=True)}),
    )
    runner.run(SID)
    assert repo.saved[0][2] is True


def test_only_steps_with_evidence_are_numbered_and_captured():
    steps = [run_step(1), run_step(2, evidence=False), run_step(3)]
    runner, repo, tf, ev, an, events = build(watched(steps))
    runner.run(SID)
    assert [(c[0], c[1]) for c in ev.captures] == [("evt_1", 1), ("evt_3", 2)]


def test_steps_beyond_the_step_limit_are_not_captured():
    steps = [run_step(i) for i in range(1, 8)]
    runner, repo, tf, ev, *_ = build(watched(steps), audit_max_steps=3)
    outcome = runner.run(SID)
    assert len(ev.captures) == 3 and outcome.steps_captured == 3


def test_session_id_in_object_paths_is_the_session_uuid():
    runner, repo, tf, ev, *_ = build(watched([run_step(1)]))
    runner.run(SID)
    assert ev.captures[0][2] == str(SID)


# --- claiming -------------------------------------------------------------


def test_already_claimed_session_is_skipped_without_any_agent_call():
    repo = FakeRepo(status="RUNNING")
    runner, repo, tf, ev, an, events = build(watched([run_step(1)]), repo=repo)
    outcome = runner.run(SID)
    assert outcome.skipped and outcome.status == "RUNNING"
    assert tf.started == [] and ev.captures == [] and an.seen == []
    assert repo.finished is None and events == []


# --- failures of the whole run ---------------------------------------------


def test_rejected_target_marks_the_session_failed():
    tf = FakeTinyFish(start_error=TargetValidationError("IP address is not a public address"))
    runner, repo, tf, *_ = build(tinyfish=tf)
    outcome = runner.run(SID)
    assert outcome.status == "FAILED" and outcome.error_code == "TARGET_REJECTED"
    assert repo.finished[2] == "IP address is not a public address"
    assert tf.cancelled == []


def test_agent_start_error_is_recorded_as_agent_error():
    tf = FakeTinyFish(start_error=TinyFishError("TinyFish did not start the run: HTTP 500"))
    runner, repo, *_ = build(tinyfish=tf)
    outcome = runner.run(SID)
    assert outcome.error_code == "AGENT_ERROR"
    assert "HTTP 500" in repo.finished[2]


def test_error_while_watching_cancels_the_run():
    tf = FakeTinyFish(watch_error=TinyFishError("poll failed"))
    runner, repo, tf, *_ = build(tinyfish=tf)
    outcome = runner.run(SID)
    assert outcome.error_code == "AGENT_ERROR"
    assert tf.cancelled == [RUN]


def test_unexpected_error_reports_only_the_class_name_and_cancels_the_run():
    an = FakeAnalyzer(unexpected_on={1})
    runner, repo, tf, ev, an, events = build(watched([run_step(1)]), analyzer=an)
    outcome = runner.run(SID)
    assert outcome.status == "FAILED" and outcome.error_code == "INTERNAL_ERROR"
    assert repo.finished[2] == "unexpected RuntimeError"
    assert "secret" not in repr(repo.finished) and "secret" not in repr(events)
    assert tf.cancelled == [RUN]


def test_agent_reporting_failure_is_recorded():
    runner, repo, *_ = build(watched([run_step(1)], status="FAILED", error="site blocked us"))
    outcome = runner.run(SID)
    assert outcome.status == "FAILED" and outcome.error_code == "AGENT_RUN_FAILED"
    assert "site blocked us" in repo.finished[2]
    assert outcome.steps_captured == 1  # evidence gathered so far is kept


def test_completed_run_with_no_usable_evidence_fails():
    runner, repo, *_ = build(watched([run_step(1, evidence=False)]))
    outcome = runner.run(SID)
    assert outcome.status == "FAILED" and outcome.error_code == "NO_EVIDENCE_CAPTURED"


# --- safety stops keep evidence ---------------------------------------------


@pytest.mark.parametrize(
    "reason,code",
    [("guard:payment_details", "AGENT_ACTION_BLOCKED"), ("step_limit", "STEP_LIMIT_EXCEEDED"), ("timeout", "TIMEOUT")],
)
def test_safety_stops_fail_the_session_but_keep_the_evidence(reason, code):
    runner, repo, tf, ev, an, events = build(
        watched([run_step(1), run_step(2)], status="CANCELLED", aborted=reason, blocked="Enter card number")
    )
    outcome = runner.run(SID)
    assert outcome.status == "FAILED" and outcome.error_code == code
    assert outcome.steps_captured == 2
    if reason.startswith("guard:"):
        assert "payment_details" in repo.finished[2]
        assert "card number" not in repo.finished[2].lower()


# --- partial results --------------------------------------------------------


def test_one_capture_failure_keeps_other_steps_and_records_the_gap():
    ev = FakeEvidence(fail_on={2})
    runner, repo, tf, ev, an, events = build(
        watched([run_step(1), run_step(2, action="Click add"), run_step(3)]), evidence=ev
    )
    outcome = runner.run(SID)
    assert outcome.status == "COMPLETED" and outcome.error_code == "PARTIAL_RESULTS"
    assert outcome.steps_captured == 2
    assert repo.failed_steps == [(2, "Click add", URL)]
    assert an.seen == [1, 3]
    assert any(e["event"] == "step_failed" and e["step_number"] == 2 for e in events)


def test_analysis_failure_keeps_the_step_and_marks_it_failed():
    runner, repo, tf, ev, an, events = build(
        watched([run_step(1), run_step(2)]), analyzer=FakeAnalyzer(fail_on={1})
    )
    outcome = runner.run(SID)
    assert outcome.status == "COMPLETED" and outcome.error_code == "PARTIAL_RESULTS"
    assert repo.analysis["step-1"] == "FAILED" and repo.analysis["step-2"] == "COMPLETED"
    assert outcome.steps_captured == 2


def test_analysis_failure_logs_the_cause_class_and_code_but_never_message_text(caplog):
    class ApiError(Exception):
        code = 429

    class CausedAnalyzer(FakeAnalyzer):
        def analyze_step(self, ctx):
            error = GeminiAnalysisError("Gemini request failed")
            error.__cause__ = ApiError("key=SECRET-VALUE quota exceeded")
            raise error

    runner, *_ = build(watched([run_step(1)]), analyzer=CausedAnalyzer())
    with caplog.at_level("WARNING"):
        runner.run(SID)
    assert "cause ApiError, code 429" in caplog.text
    assert "SECRET-VALUE" not in caplog.text


def test_all_captures_failing_is_a_failed_audit():
    runner, repo, *_ = build(
        watched([run_step(1), run_step(2)]), evidence=FakeEvidence(fail_on={1, 2})
    )
    outcome = runner.run(SID)
    assert outcome.status == "FAILED" and outcome.error_code == "NO_EVIDENCE_CAPTURED"
    assert len(repo.failed_steps) == 2


def test_tinyfish_download_error_counts_as_a_capture_failure():
    ev = FakeEvidence(fail_on={1}, error=TinyFishError("download failed"))
    runner, repo, *_ = build(watched([run_step(1), run_step(2)]), evidence=ev)
    outcome = runner.run(SID)
    assert outcome.error_code == "PARTIAL_RESULTS" and outcome.steps_captured == 1


# --- progress channel -------------------------------------------------------


def test_broken_progress_sink_does_not_break_the_audit(caplog):
    def boom(event):
        raise ConnectionError("redis down")

    with caplog.at_level(logging.WARNING):
        runner, repo, *_ = build(watched([run_step(1)]), progress=boom)
        outcome = runner.run(SID)
    assert outcome.status == "COMPLETED"
    assert "progress sink failed" in caplog.text


def test_events_do_not_carry_page_content_or_urls():
    reports = {1: GroundingReport(accepted=[finding(1)])}
    runner, repo, tf, ev, an, events = build(watched([run_step(1)]), analyzer=FakeAnalyzer(reports))
    runner.run(SID)
    text = repr(events)
    assert "page text" not in text and URL not in text and "explanation" not in text


# --- cancellation ------------------------------------------------------------


def test_cancel_during_start_cancels_the_agent_run_and_captures_nothing():
    repo = FakeRepo(cancel_after_run_id=True)
    runner, repo, tf, ev, an, events = build(watched([run_step(1)]), repo=repo)
    outcome = runner.run(SID)
    assert outcome.status == "CANCELLED" and outcome.steps_captured == 0
    assert tf.cancelled == [RUN] and ev.captures == [] and an.seen == []
    assert repo.finished is None
    assert events[-1]["event"] == "session_finished" and events[-1]["status"] == "CANCELLED"


def test_cancel_during_the_run_keeps_the_evidence_and_the_cancelled_status():
    repo = FakeRepo(cancel_after_capture=True)
    runner, repo, tf, ev, an, events = build(
        watched([run_step(1), run_step(2)], status="CANCELLED"), repo=repo
    )
    outcome = runner.run(SID)
    assert outcome.status == "CANCELLED"
    assert outcome.steps_captured == 2
    assert repo.finished is None  # the cancelled status was never overwritten
    assert events[-1]["status"] == "CANCELLED"


def test_unexpected_error_after_a_cancel_does_not_overwrite_the_cancelled_status():
    repo = FakeRepo(cancel_after_capture=True)
    runner, repo, tf, ev, an, events = build(
        watched([run_step(1)]), repo=repo, analyzer=FakeAnalyzer(unexpected_on={1})
    )
    outcome = runner.run(SID)
    assert outcome.status == "CANCELLED" and repo.finished is None
