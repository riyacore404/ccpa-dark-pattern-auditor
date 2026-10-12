import json

import httpx
import pytest

from app.core.config import Settings
from app.core.security import ActionVerdict
from app.services.tinyfish import (
    AUDIT_GOAL_TEMPLATE,
    RunDetail,
    RunStep,
    TinyFishClient,
    TinyFishConfigurationError,
    TinyFishError,
    build_audit_goal,
    evidence_steps,
)

KEY = "tf-super-secret-key"
RUN_ID = "2f855570-ea60-47f1-b9cb-a8f113dc93b0"
JPEG = b"\xff\xd8\xff\xe0" + b"0" * 100
PNG = b"\x89PNG\r\n\x1a\n" + b"0" * 100


def settings(**overrides):
    values = dict(tinyfish_api_key=KEY)
    values.update(overrides)
    return Settings(_env_file=None, **values)


class Recorder:
    """A fake TinyFish API. Collects every request it receives."""

    def __init__(self, routes):
        self.routes = routes
        self.requests: list[httpx.Request] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        handler = self.routes(request) if callable(self.routes) else self.routes
        return handler if isinstance(handler, httpx.Response) else handler(request)


def make_client(routes, **settings_overrides):
    recorder = Recorder(routes)
    sleeps = []
    client = TinyFishClient(
        settings(**settings_overrides),
        http=httpx.Client(transport=httpx.MockTransport(recorder)),
        resolver=lambda host, port: ["93.184.216.34"],
        sleep=sleeps.append,
    )
    return client, recorder, sleeps


def run_json(status="RUNNING", steps=None, **extra):
    body = {"run_id": RUN_ID, "status": status, "num_of_steps": len(steps or []), "steps": steps or []}
    body.update(extra)
    return httpx.Response(200, json=body)


def step(step_id="evt_1", action="Visit the page", screenshot="s", html="h"):
    return {
        "id": step_id,
        "timestamp": "2026-10-11T15:47:53Z",
        "status": "RUNNING",
        "action": action,
        "screenshot": screenshot,
        "html": html,
        "duration": "1s",
        "unexpected_field": True,
    }


# --- configuration --------------------------------------------------------


def test_missing_api_key_raises():
    with pytest.raises(TinyFishConfigurationError):
        TinyFishClient(Settings(_env_file=None))


def test_non_https_base_url_is_refused():
    with pytest.raises(TinyFishConfigurationError):
        TinyFishClient(settings(tinyfish_api_base_url="http://agent.tinyfish.ai"))


def test_goal_states_the_hard_rules_and_step_limit():
    goal = build_audit_goal(12)
    assert "Never complete a purchase" in goal
    assert "OTP" in goal
    assert "Never log in" in goal
    assert "CAPTCHA" in goal
    assert "at most 12 actions" in goal
    assert "{" not in goal.replace("{max_steps}", "")  # no unfilled placeholders
    assert "{max_steps}" in AUDIT_GOAL_TEMPLATE


# --- starting a run -------------------------------------------------------


def test_start_run_sends_the_confirmed_payload():
    client, rec, _ = make_client(lambda r: httpx.Response(200, json={"run_id": RUN_ID, "error": None}),
                                 audit_max_steps=15, audit_timeout_seconds=240)
    assert client.start_run("https://example.com/shop#x") == RUN_ID

    request = rec.requests[0]
    assert request.method == "POST"
    assert str(request.url) == "https://agent.tinyfish.ai/v1/automation/run-async"
    assert request.headers["X-API-Key"] == KEY
    body = json.loads(request.content)
    assert body["url"] == "https://example.com/shop"
    assert body["capture_config"] == {"screenshots": True, "html": True}
    assert body["agent_config"] == {"max_duration_seconds": 240}
    assert "at most 15 actions" in body["goal"]
    assert set(body) == {"url", "goal", "capture_config", "agent_config"}


def test_start_run_never_requests_vault_or_profiles():
    client, rec, _ = make_client(lambda r: httpx.Response(200, json={"run_id": RUN_ID}))
    client.start_run("https://example.com/")
    body = json.loads(rec.requests[0].content)
    assert "use_vault" not in body and "use_profile" not in body
    assert "credential_item_ids" not in body and "profile_id" not in body


@pytest.mark.parametrize(
    "url", ["http://127.0.0.1/", "http://localhost/", "https://user:pw@example.com/", "file:///etc/passwd"]
)
def test_start_run_rejects_unsafe_targets_before_any_request(url):
    client, rec, _ = make_client(lambda r: httpx.Response(200, json={"run_id": RUN_ID}))
    with pytest.raises(Exception) as excinfo:
        client.start_run(url)
    assert "TargetValidationError" in type(excinfo.value).__name__
    assert rec.requests == []


def test_start_run_with_private_resolution_is_rejected():
    recorder = Recorder(lambda r: httpx.Response(200, json={"run_id": RUN_ID}))
    client = TinyFishClient(
        settings(),
        http=httpx.Client(transport=httpx.MockTransport(recorder)),
        resolver=lambda h, p: ["10.1.2.3"],
    )
    with pytest.raises(Exception):
        client.start_run("https://sneaky.example.com/")
    assert recorder.requests == []


def test_start_run_null_run_id_reports_the_error():
    body = {"run_id": None, "error": {"code": "FEATURE_NOT_AVAILABLE", "message": "not enabled"}}
    client, _, _ = make_client(lambda r: httpx.Response(200, json=body))
    with pytest.raises(TinyFishError) as excinfo:
        client.start_run("https://example.com/")
    assert "FEATURE_NOT_AVAILABLE" in str(excinfo.value)


def test_start_run_http_error_is_reported_without_the_key():
    client, _, _ = make_client(
        lambda r: httpx.Response(403, json={"error": {"code": "FORBIDDEN", "message": f"no credits for {KEY}"}})
    )
    with pytest.raises(TinyFishError) as excinfo:
        client.start_run("https://example.com/")
    assert "403" in str(excinfo.value)


def test_start_run_is_not_retried_on_server_error():
    client, rec, sleeps = make_client(lambda r: httpx.Response(500, json={"error": "boom"}))
    with pytest.raises(TinyFishError):
        client.start_run("https://example.com/")
    assert len(rec.requests) == 1  # a retried POST could start (and bill) a second run


def test_start_run_rejects_malformed_run_id():
    client, _, _ = make_client(lambda r: httpx.Response(200, json={"run_id": "../../x"}))
    with pytest.raises(TinyFishError):
        client.start_run("https://example.com/")


# --- reading a run --------------------------------------------------------


def test_get_run_parses_steps_and_ignores_unknown_fields():
    client, rec, _ = make_client(lambda r: run_json("COMPLETED", [step(), step("evt_2", html=None)], result={"a": 1}))
    detail = client.get_run(RUN_ID)
    assert detail.status == "COMPLETED" and detail.result == {"a": 1}
    assert [s.id for s in detail.steps] == ["evt_1", "evt_2"]
    request = rec.requests[0]
    assert request.url.path == f"/v1/runs/{RUN_ID}"
    assert dict(request.url.params) == {"screenshots": "url", "html": "url"}
    assert request.headers["X-API-Key"] == KEY


def test_null_steps_become_an_empty_list():
    client, _, _ = make_client(lambda r: httpx.Response(200, json={"run_id": RUN_ID, "status": "PENDING", "steps": None}))
    assert client.get_run(RUN_ID).steps == []


@pytest.mark.parametrize("bad", ["", "../etc", "a/b", "a b", "x" * 200, "a?b=c"])
def test_invalid_run_ids_are_rejected_before_any_request(bad):
    client, rec, _ = make_client(lambda r: run_json())
    with pytest.raises(TinyFishError):
        client.get_run(bad)
    assert rec.requests == []


def test_get_run_retries_server_errors_then_succeeds():
    responses = iter([httpx.Response(503), httpx.Response(429), run_json("COMPLETED")])
    client, rec, sleeps = make_client(lambda r: next(responses))
    assert client.get_run(RUN_ID).status == "COMPLETED"
    assert len(rec.requests) == 3 and len(sleeps) == 2


def test_get_run_gives_up_after_retries():
    client, rec, _ = make_client(lambda r: httpx.Response(502))
    with pytest.raises(TinyFishError):
        client.get_run(RUN_ID)
    assert len(rec.requests) == 3


def test_get_run_does_not_retry_auth_errors():
    client, rec, _ = make_client(lambda r: httpx.Response(401, json={"error": {"code": "INVALID_API_KEY", "message": "bad"}}))
    with pytest.raises(TinyFishError) as excinfo:
        client.get_run(RUN_ID)
    assert "INVALID_API_KEY" in str(excinfo.value)
    assert len(rec.requests) == 1


def test_get_run_unreadable_body_is_an_error():
    client, _, _ = make_client(lambda r: httpx.Response(200, text="not json"))
    with pytest.raises(TinyFishError):
        client.get_run(RUN_ID)


def test_network_failure_is_reported_without_details():
    def explode(request):
        raise httpx.ConnectError(f"cannot connect with {KEY}")

    client, _, _ = make_client(explode)
    with pytest.raises(TinyFishError) as excinfo:
        client.get_run(RUN_ID)
    assert KEY not in str(excinfo.value)


def test_evidence_steps_keeps_only_steps_with_screenshot_and_html():
    detail = RunDetail(
        run_id=RUN_ID,
        status="COMPLETED",
        steps=[RunStep(id="a", screenshot="s", html="h"), RunStep(id="b", screenshot="s"),
               RunStep(id="c", html="h"), RunStep(id="d")],
    )
    assert [s.id for s in evidence_steps(detail)] == ["a"]


# --- artifacts ------------------------------------------------------------


def test_download_screenshot_uses_the_api_key_endpoint_not_the_step_link():
    client, rec, _ = make_client(lambda r: httpx.Response(200, content=JPEG, headers={"content-type": "image/jpeg"}))
    data, mime = client.download_screenshot(RUN_ID, "evt_1")
    assert data == JPEG and mime == "image/jpeg"
    request = rec.requests[0]
    assert request.url.path == f"/v1/runs/{RUN_ID}/steps/evt_1/screenshot"
    assert request.headers["X-API-Key"] == KEY


def test_download_screenshot_accepts_png():
    client, _, _ = make_client(lambda r: httpx.Response(200, content=PNG))
    assert client.download_screenshot(RUN_ID, "evt_1")[1] == "image/png"


def test_download_screenshot_rejects_non_images():
    client, _, _ = make_client(lambda r: httpx.Response(200, content=b"<html>not an image</html>"))
    with pytest.raises(TinyFishError):
        client.download_screenshot(RUN_ID, "evt_1")


def test_download_html_uses_the_api_key_endpoint():
    client, rec, _ = make_client(lambda r: httpx.Response(200, content=b"<html>hi</html>", headers={"content-type": "text/html"}))
    assert client.download_html(RUN_ID, "evt_1") == b"<html>hi</html>"
    assert rec.requests[0].url.path == f"/v1/runs/{RUN_ID}/steps/evt_1/html"


def test_downloads_are_size_capped(monkeypatch):
    monkeypatch.setattr("app.services.tinyfish.MAX_HTML_BYTES", 50)
    client, _, _ = make_client(lambda r: httpx.Response(200, content=b"x" * 100))
    with pytest.raises(TinyFishError) as excinfo:
        client.download_html(RUN_ID, "evt_1")
    assert "size limit" in str(excinfo.value)


def test_streamed_downloads_without_a_declared_length_are_still_capped(monkeypatch):
    monkeypatch.setattr("app.services.tinyfish.MAX_HTML_BYTES", 50)

    def chunks():
        for _ in range(5):
            yield b"x" * 30  # 150 bytes in total, no content-length header

    client, _, _ = make_client(lambda r: httpx.Response(200, content=chunks()))
    with pytest.raises(TinyFishError) as excinfo:
        client.download_html(RUN_ID, "evt_1")
    assert "size limit" in str(excinfo.value)


def test_streamed_downloads_under_the_cap_are_returned_whole(monkeypatch):
    monkeypatch.setattr("app.services.tinyfish.MAX_HTML_BYTES", 500)

    def chunks():
        for _ in range(5):
            yield b"x" * 30

    client, _, _ = make_client(lambda r: httpx.Response(200, content=chunks()))
    assert client.download_html(RUN_ID, "evt_1") == b"x" * 150


def test_downloads_reject_oversized_declared_length(monkeypatch):
    monkeypatch.setattr("app.services.tinyfish.MAX_HTML_BYTES", 50)
    client, _, _ = make_client(lambda r: httpx.Response(200, content=b"x" * 10, headers={"content-length": "9999"}))
    with pytest.raises(TinyFishError):
        client.download_html(RUN_ID, "evt_1")


def test_redirects_are_not_followed_and_never_receive_the_key():
    def route(request):
        if request.url.host == "agent.tinyfish.ai":
            return httpx.Response(302, headers={"location": "https://evil.example/steal"})
        raise AssertionError("the client followed a redirect")

    client, rec, _ = make_client(route)
    with pytest.raises(TinyFishError):
        client.download_html(RUN_ID, "evt_1")
    assert all(r.url.host == "agent.tinyfish.ai" for r in rec.requests)


@pytest.mark.parametrize("call", ["start_run", "get_run", "cancel_run"])
def test_api_calls_never_follow_redirects(call):
    def route(request):
        if request.url.host == "agent.tinyfish.ai":
            return httpx.Response(307, headers={"location": "https://evil.example/steal"})
        raise AssertionError("the client followed a redirect")

    client, rec, _ = make_client(route)
    try:
        {"start_run": lambda: client.start_run("https://example.com/"),
         "get_run": lambda: client.get_run(RUN_ID),
         "cancel_run": lambda: client.cancel_run(RUN_ID)}[call]()
    except TinyFishError:
        pass
    assert rec.requests and all(r.url.host == "agent.tinyfish.ai" for r in rec.requests)


def test_download_404_is_not_retried():
    client, rec, _ = make_client(lambda r: httpx.Response(404, json={"error": {"code": "NOT_FOUND", "message": "gone"}}))
    with pytest.raises(TinyFishError):
        client.download_html(RUN_ID, "evt_1")
    assert len(rec.requests) == 1


def test_download_retries_server_errors():
    responses = iter([httpx.Response(500), httpx.Response(200, content=b"<p>ok</p>")])
    client, rec, sleeps = make_client(lambda r: next(responses))
    assert client.download_html(RUN_ID, "evt_1") == b"<p>ok</p>"
    assert len(rec.requests) == 2 and len(sleeps) == 1


@pytest.mark.parametrize("bad", ["../x", "a/b", ""])
def test_invalid_step_ids_are_rejected(bad):
    client, rec, _ = make_client(lambda r: httpx.Response(200, content=JPEG))
    with pytest.raises(TinyFishError):
        client.download_screenshot(RUN_ID, bad)
    assert rec.requests == []


# --- cancelling -----------------------------------------------------------


def test_cancel_run_posts_to_the_cancel_endpoint():
    client, rec, _ = make_client(lambda r: httpx.Response(200, json={}))
    assert client.cancel_run(RUN_ID) is True
    assert rec.requests[0].method == "POST"
    assert rec.requests[0].url.path == f"/v1/runs/{RUN_ID}/cancel"


def test_cancel_run_failure_returns_false_instead_of_raising():
    client, _, _ = make_client(lambda r: httpx.Response(500))
    assert client.cancel_run(RUN_ID) is False


# --- watching a run -------------------------------------------------------


def scripted(*payloads):
    """Serves the given run states in order for GET, and records cancels."""
    states = iter(payloads)
    last = {"v": None}

    def route(request):
        if request.url.path.endswith("/cancel"):
            return httpx.Response(200, json={})
        try:
            last["v"] = next(states)
        except StopIteration:
            pass
        return last["v"]

    return route


def cancels(rec):
    return [r for r in rec.requests if r.url.path.endswith("/cancel")]


def test_watch_returns_when_the_run_completes():
    route = scripted(run_json("RUNNING", [step("e1")]), run_json("COMPLETED", [step("e1"), step("e2", "Task completed")]))
    client, rec, sleeps = make_client(route)
    watched = client.watch_run(RUN_ID)
    assert watched.completed_normally and watched.aborted_reason is None
    assert [s.id for s in watched.detail.steps] == ["e1", "e2"]
    assert len(sleeps) == 1 and cancels(rec) == []


def test_watch_returns_failed_runs_without_aborting():
    client, rec, _ = make_client(scripted(run_json("FAILED", [step()], error={"code": "X"})))
    watched = client.watch_run(RUN_ID)
    assert watched.detail.status == "FAILED"
    assert not watched.completed_normally and watched.aborted_reason is None


def test_watch_cancels_when_the_guard_blocks_an_action():
    route = scripted(
        run_json("RUNNING", [step("e1", "Open the cart")]),
        run_json("RUNNING", [step("e1", "Open the cart"), step("e2", "Entering the credit card number")]),
        run_json("CANCELLED", [step("e1", "Open the cart"), step("e2", "Entering the credit card number")]),
    )
    client, rec, _ = make_client(route)
    watched = client.watch_run(RUN_ID)
    assert watched.aborted_reason == "guard:payment_details"
    assert watched.blocked_action == "Entering the credit card number"
    assert len(cancels(rec)) == 1
    assert watched.detail.status == "CANCELLED"  # final state fetched after the cancel


def test_watch_screens_each_step_only_once():
    seen = []

    def guard(action):
        seen.append(action)
        return ActionVerdict(allowed=True)

    route = scripted(
        run_json("RUNNING", [step("e1", "A")]),
        run_json("RUNNING", [step("e1", "A"), step("e2", "B")]),
        run_json("COMPLETED", [step("e1", "A"), step("e2", "B")]),
    )
    client, _, _ = make_client(route)
    client.watch_run(RUN_ID, guard=guard)
    assert seen == ["A", "B"]


def test_watch_uses_a_custom_guard():
    route = scripted(run_json("RUNNING", [step("e1", "anything")]), run_json("CANCELLED", [step("e1", "anything")]))
    client, rec, _ = make_client(route)
    watched = client.watch_run(RUN_ID, guard=lambda a: ActionVerdict(False, "custom", "x"))
    assert watched.aborted_reason == "guard:custom" and len(cancels(rec)) == 1


def test_watch_cancels_when_the_step_limit_is_exceeded():
    steps = [step(f"e{i}", f"Look at page {i}") for i in range(4)]
    route = scripted(run_json("RUNNING", steps), run_json("CANCELLED", steps))
    client, rec, _ = make_client(route, audit_max_steps=3)
    watched = client.watch_run(RUN_ID)
    assert watched.aborted_reason == "step_limit" and len(cancels(rec)) == 1


def test_watch_allows_exactly_the_step_limit():
    steps = [step(f"e{i}", f"Look at page {i}") for i in range(3)]
    client, rec, _ = make_client(scripted(run_json("COMPLETED", steps)), audit_max_steps=3)
    assert client.watch_run(RUN_ID).aborted_reason is None


def test_watch_cancels_after_the_deadline():
    ticks = iter([0.0, 10.0, 999.0, 999.0, 999.0])
    route = scripted(run_json("RUNNING", [step()]), run_json("RUNNING", [step()]), run_json("CANCELLED", [step()]))
    client, rec, _ = make_client(route, audit_timeout_seconds=60)
    watched = client.watch_run(RUN_ID, clock=lambda: next(ticks))
    assert watched.aborted_reason == "timeout" and len(cancels(rec)) == 1


def test_watch_cancels_and_raises_when_polling_keeps_failing():
    def route(request):
        if request.url.path.endswith("/cancel"):
            return httpx.Response(200, json={})
        return httpx.Response(503)

    client, rec, _ = make_client(route)
    with pytest.raises(TinyFishError):
        client.watch_run(RUN_ID)
    assert len(cancels(rec)) == 1


def test_watch_keeps_last_state_if_the_post_cancel_fetch_fails():
    state = {"gets": 0}

    def route(request):
        if request.url.path.endswith("/cancel"):
            return httpx.Response(200, json={})
        state["gets"] += 1
        if state["gets"] == 1:
            return run_json("RUNNING", [step("e1", "Click Place order")])
        return httpx.Response(503)

    client, _, _ = make_client(route)
    watched = client.watch_run(RUN_ID)
    assert watched.aborted_reason == "guard:purchase"
    assert [s.id for s in watched.detail.steps] == ["e1"]
