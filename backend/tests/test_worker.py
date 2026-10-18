import pytest
from celery import Celery
from google.genai import types

import app.workers.tasks as tasks
from app.api.deps import get_enqueuer
from app.core.config import Settings
from app.services.audit_runner import AuditOutcome
from app.services.evidence import EvidenceConfigurationError
from app.services.gemini import GeminiConfigurationError
from app.services.tinyfish import TinyFishConfigurationError
from app.workers.celery_app import create_celery_app
from app.workers.run_worker import worker_argv

SID = "11111111-1111-1111-1111-111111111111"


def settings(**kw):
    return Settings(_env_file=None, **kw)


class FakeRepo:
    def __init__(self):
        self.finished = []

    def finish_session(self, sid, status, code=None, message=None):
        self.finished.append((str(sid), status, code, message))
        return True


class FakeRunner:
    def __init__(self, outcome):
        self.outcome = outcome
        self.ran = []

    def run(self, sid):
        self.ran.append(sid)
        return self.outcome


def test_celery_app_is_configured_for_safe_single_runs():
    app = create_celery_app(settings(redis_url="redis://r:6379/3"))
    assert isinstance(app, Celery)
    conf = app.conf
    assert conf.broker_url == "redis://r:6379/3" and conf.result_backend == "redis://r:6379/3"
    assert conf.task_serializer == "json" and list(conf.accept_content) == ["json"]
    assert conf.task_acks_late is False and conf.task_reject_on_worker_lost is False
    assert conf.worker_prefetch_multiplier == 1 and conf.task_ignore_result is True
    assert conf.task_default_queue == "audits"
    assert conf.broker_connection_timeout == 3


def test_separate_broker_and_backend_urls_win_over_redis_url():
    app = create_celery_app(settings(celery_broker_url="redis://b/1", celery_result_backend="redis://c/2"))
    assert (app.conf.broker_url, app.conf.result_backend) == ("redis://b/1", "redis://c/2")


def test_task_is_registered_under_a_stable_name_and_never_retries():
    assert tasks.run_audit.name == "audits.run"
    assert tasks.run_audit.max_retries == 0


def test_worker_concurrency_follows_the_setting():
    argv = worker_argv(settings(audit_max_concurrent_runs=3))
    assert "--concurrency=3" in argv and "--pool=threads" in argv and "--queues=audits" in argv


def test_successful_job_returns_the_outcome_summary():
    runner = FakeRunner(AuditOutcome(
        session_id=SID, status="COMPLETED", steps_captured=3, findings_saved=2, findings_rejected=1,
    ))
    result = tasks.execute_audit(SID, settings(), FakeRepo(), lambda s, r: runner)
    assert result == {
        "session_id": SID, "status": "COMPLETED", "error_code": None, "steps_captured": 3,
        "findings_saved": 2, "findings_rejected": 1, "skipped": False,
    }
    assert [str(x) for x in runner.ran] == [SID]


@pytest.mark.parametrize(
    "error",
    [
        TinyFishConfigurationError("TINYFISH_API_KEY is not set."),
        EvidenceConfigurationError("SUPABASE_URL must use https"),
        GeminiConfigurationError("GEMINI_MODEL is not set."),
    ],
)
def test_missing_configuration_fails_the_session_instead_of_leaving_it_queued(error):
    repo = FakeRepo()

    def broken_factory(s, r):
        raise error

    result = tasks.execute_audit(SID, settings(), repo, broken_factory)
    assert result["status"] == "FAILED" and result["error_code"] == "WORKER_MISCONFIGURED"
    assert repo.finished == [(SID, "FAILED", "WORKER_MISCONFIGURED", str(error))]


def test_unexpected_factory_errors_are_not_swallowed():
    def factory(s, r):
        raise RuntimeError("bug")

    with pytest.raises(RuntimeError):
        tasks.execute_audit(SID, settings(), FakeRepo(), factory)


def test_invalid_session_id_is_refused():
    with pytest.raises(ValueError):
        tasks.execute_audit("not-a-uuid", settings(), FakeRepo(), lambda s, r: None)


def test_celery_task_runs_execute_audit(monkeypatch):
    calls = []
    monkeypatch.setattr(tasks, "execute_audit", lambda sid: calls.append(sid) or {"ok": True})
    assert tasks.run_audit.apply(args=[SID]).get() == {"ok": True}
    assert calls == [SID]


def test_api_enqueuer_sends_the_session_id_to_the_task(monkeypatch):
    sent = []

    class FakeTask:
        def delay(self, sid):
            sent.append(sid)

    monkeypatch.setattr(tasks, "run_audit", FakeTask())
    get_enqueuer()(SID)
    assert sent == [SID]


def test_build_runner_requires_each_credential():
    with pytest.raises(TinyFishConfigurationError):
        tasks.build_runner(settings(), FakeRepo())
    with pytest.raises(EvidenceConfigurationError):
        tasks.build_runner(settings(tinyfish_api_key="tf"), FakeRepo())
    base = dict(tinyfish_api_key="tf", supabase_url="https://x.supabase.co", supabase_service_role_key="k")
    with pytest.raises(GeminiConfigurationError):
        tasks.build_runner(settings(**base), FakeRepo())
    with pytest.raises(GeminiConfigurationError):
        tasks.build_runner(settings(gemini_api_key="g", **base), FakeRepo())


def test_build_runner_gives_gemini_a_request_timeout(monkeypatch):
    seen = {}

    class SpyClient:
        def __init__(self, **kwargs):
            seen.update(kwargs)

    monkeypatch.setattr(tasks.genai, "Client", SpyClient)
    runner = tasks.build_runner(
        settings(
            tinyfish_api_key="tf", supabase_url="https://x.supabase.co",
            supabase_service_role_key="k", gemini_api_key="g", gemini_model="m",
        ),
        FakeRepo(),
    )
    assert isinstance(seen["http_options"], types.HttpOptions)
    assert seen["http_options"].timeout == tasks.GEMINI_TIMEOUT_MS
    assert seen["api_key"] == "g"
    assert runner._vision_model == "m"
