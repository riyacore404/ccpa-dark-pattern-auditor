import asyncio
from contextlib import asynccontextmanager
from uuid import uuid4

import pytest
import redis
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

import app.api.v1.audits as audits_module
from app.api.deps import get_app_settings, get_progress_source, get_repository
from app.core.config import Settings
from app.main import create_app

TOKEN = "w" * 32


class FakeReader:
    def __init__(self, events):
        self._events = list(events)

    async def next(self, timeout):
        if self._events:
            item = self._events.pop(0)
            if isinstance(item, Exception):
                raise item
            return item
        await asyncio.sleep(0.01)
        return None


class FakeSource:
    def __init__(self, events=(), subscribe_error=None):
        self.events = events
        self.subscribe_error = subscribe_error
        self.subscribed = []

    @asynccontextmanager
    async def subscribe(self, session_id):
        if self.subscribe_error:
            raise self.subscribe_error
        self.subscribed.append(session_id)
        yield FakeReader(self.events)


class FakeRepo:
    def __init__(self, summary):
        self.summary = summary

    def get_session_summary(self, session_id):
        return self.summary


def summary(status="RUNNING", **kw):
    row = dict(id=uuid4(), status=status, step_count=1, finding_count=2, error_code=None)
    row.update(kw)
    return row


def make(summary_row, events=(), subscribe_error=None, **settings_kw):
    values = dict(api_access_token=TOKEN, cors_origins="http://localhost:3000")
    values.update(settings_kw)
    settings = Settings(_env_file=None, **values)
    source = FakeSource(events, subscribe_error)
    app = create_app(settings)
    app.dependency_overrides[get_app_settings] = lambda: settings
    app.dependency_overrides[get_repository] = lambda: FakeRepo(summary_row)
    app.dependency_overrides[get_progress_source] = lambda: source
    return TestClient(app), source


def url(row):
    return f"/api/v1/ws/audits/{row['id'] if row else uuid4()}"


def auth(ws, token=TOKEN):
    ws.send_json({"type": "auth", "token": token})


def expect_rejected(client, path, send=None, headers=None):
    with pytest.raises(WebSocketDisconnect) as info:
        with client.websocket_connect(path, headers=headers or {}) as ws:
            if send is not None:
                ws.send_text(send) if isinstance(send, str) else ws.send_json(send)
            ws.receive_json()
    assert info.value.code == 1008


def test_wrong_token_is_rejected():
    row = summary()
    client, source = make(row)
    expect_rejected(client, url(row), send={"type": "auth", "token": "x" * 32})
    assert source.subscribed == []


@pytest.mark.parametrize(
    "message",
    [{"type": "hello"}, {"token": TOKEN}, {"type": "auth"}, {"type": "auth", "token": 123}, ["auth", TOKEN], "not json"],
)
def test_malformed_first_messages_are_rejected(message):
    row = summary()
    client, source = make(row)
    expect_rejected(client, url(row), send=message)
    assert source.subscribed == []


def test_silence_times_out(monkeypatch):
    monkeypatch.setattr(audits_module, "AUTH_TIMEOUT_SECONDS", 0.2)
    row = summary()
    client, _ = make(row)
    expect_rejected(client, url(row))


def test_token_in_the_url_does_not_authenticate(monkeypatch):
    monkeypatch.setattr(audits_module, "AUTH_TIMEOUT_SECONDS", 0.2)
    row = summary()
    client, _ = make(row)
    expect_rejected(client, url(row) + f"?token={TOKEN}")


def test_unconfigured_token_rejects_everyone():
    row = summary()
    client, _ = make(row, api_access_token=None)
    expect_rejected(client, url(row), send={"type": "auth", "token": TOKEN})


def test_disallowed_origin_is_rejected_before_any_message():
    row = summary()
    client, source = make(row)
    expect_rejected(client, url(row), headers={"origin": "https://evil.example"})
    assert source.subscribed == []


def test_disallowed_origin_is_rejected_even_with_the_correct_token():
    row = summary()
    client, source = make(row)
    expect_rejected(
        client, url(row),
        send={"type": "auth", "token": TOKEN},
        headers={"origin": "https://evil.example"},
    )
    assert source.subscribed == []


def test_allowed_origin_and_no_origin_are_accepted():
    row = summary("COMPLETED")
    client, _ = make(row)
    for headers in ({"origin": "http://localhost:3000"}, {}):
        with client.websocket_connect(url(row), headers=headers) as ws:
            auth(ws)
            assert ws.receive_json()["event"] == "snapshot"


def test_unknown_audit_gets_an_error_then_is_closed():
    client, _ = make(None)
    with pytest.raises(WebSocketDisconnect) as info:
        with client.websocket_connect(f"/api/v1/ws/audits/{uuid4()}") as ws:
            auth(ws)
            assert ws.receive_json()["event"] == "error"
            ws.receive_json()
    assert info.value.code == 1008


def test_unauthenticated_clients_cannot_probe_which_audits_exist():
    client, _ = make(None)
    expect_rejected(client, f"/api/v1/ws/audits/{uuid4()}", send={"type": "auth", "token": "x" * 32})


def test_invalid_session_id_is_refused():
    row = summary()
    client, _ = make(row)
    with pytest.raises(WebSocketDisconnect):
        with client.websocket_connect("/api/v1/ws/audits/not-a-uuid") as ws:
            ws.receive_json()


def test_finished_audit_sends_a_snapshot_and_closes():
    row = summary("FAILED", error_code="TIMEOUT")
    client, source = make(row)
    with client.websocket_connect(url(row)) as ws:
        auth(ws)
        snap = ws.receive_json()
        assert snap == {
            "event": "snapshot", "session_id": str(row["id"]), "status": "FAILED",
            "step_count": 1, "finding_count": 2, "error_code": "TIMEOUT",
        }
        with pytest.raises(WebSocketDisconnect) as info:
            ws.receive_json()
        assert info.value.code == 1000


def test_running_audit_streams_events_in_order_and_closes_after_the_last():
    row = summary("RUNNING")
    events = [
        {"event": "step_captured", "session_id": str(row["id"]), "step_number": 1},
        {"event": "step_analyzed", "session_id": str(row["id"]), "step_number": 1, "findings": 2, "rejected": 0},
        {"event": "session_finished", "session_id": str(row["id"]), "status": "COMPLETED", "error_code": None},
    ]
    client, source = make(row, events)
    with client.websocket_connect(url(row)) as ws:
        auth(ws)
        assert ws.receive_json()["status"] == "RUNNING"
        assert [ws.receive_json()["event"] for _ in range(3)] == [
            "step_captured", "step_analyzed", "session_finished",
        ]
        with pytest.raises(WebSocketDisconnect) as info:
            ws.receive_json()
        assert info.value.code == 1000
    assert source.subscribed == [row["id"]]


def test_quiet_periods_produce_heartbeats():
    row = summary("RUNNING")
    client, _ = make(row, [None, {"event": "session_finished", "session_id": "x", "status": "COMPLETED", "error_code": None}])
    with client.websocket_connect(url(row)) as ws:
        auth(ws)
        ws.receive_json()
        assert ws.receive_json() == {"event": "ping"}
        assert ws.receive_json()["event"] == "session_finished"


def test_progress_channel_outage_is_reported_cleanly():
    row = summary()
    client, _ = make(row, subscribe_error=redis.ConnectionError("redis://:secretpw@host down"))
    with client.websocket_connect(url(row)) as ws:
        auth(ws)
        message = ws.receive_json()
        assert message == {"event": "error", "message": "Progress channel unavailable."}
        with pytest.raises(WebSocketDisconnect) as info:
            ws.receive_json()
        assert info.value.code == 1011
