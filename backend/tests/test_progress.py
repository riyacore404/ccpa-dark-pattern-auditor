"""Unit tests run always. The Redis tests run only when TEST_REDIS_URL points
at a throwaway Redis, for example redis://localhost:6379/9."""

import asyncio
import json
import os

import pytest

from app.services.progress import (
    EventReader,
    RedisProgressPublisher,
    RedisProgressSource,
    channel_for,
)

REDIS_URL = os.environ.get("TEST_REDIS_URL")
needs_redis = pytest.mark.skipif(not REDIS_URL, reason="set TEST_REDIS_URL to run Redis tests")


class RecordingClient:
    def __init__(self):
        self.published = []

    def publish(self, channel, payload):
        self.published.append((channel, payload))


def test_channel_name_is_per_session():
    assert channel_for("abc") == "audit-progress:abc"


def test_publisher_sends_compact_json_to_the_session_channel():
    client = RecordingClient()
    publisher = RedisProgressPublisher("redis://unused", client=client)
    publisher({"event": "step_captured", "session_id": "s-1", "step_number": 2})
    (channel, payload), = client.published
    assert channel == "audit-progress:s-1"
    assert json.loads(payload) == {"event": "step_captured", "session_id": "s-1", "step_number": 2}
    assert " " not in payload


def test_publisher_errors_propagate_so_the_runner_can_log_them():
    class Broken:
        def publish(self, channel, payload):
            raise ConnectionError("down")

    with pytest.raises(ConnectionError):
        RedisProgressPublisher("redis://unused", client=Broken())({"session_id": "s", "event": "x"})


class FakePubSub:
    def __init__(self, messages):
        self.messages = list(messages)

    async def get_message(self, ignore_subscribe_messages, timeout):
        return self.messages.pop(0) if self.messages else None


def run(coro):
    return asyncio.run(coro)


def test_reader_parses_json_and_skips_junk():
    reader = EventReader(FakePubSub([
        {"data": b'{"event":"ok"}'}, {"data": b"not json"}, {"data": b"[1,2]"}, {"data": None},
    ]))
    assert run(reader.next(0.05)) == {"event": "ok"}
    assert run(reader.next(0.05)) is None
    assert run(reader.next(0.05)) is None
    assert run(reader.next(0.05)) is None
    assert run(reader.next(0.05)) is None


@needs_redis
def test_published_events_reach_a_subscriber_and_only_for_their_session():
    publisher = RedisProgressPublisher(REDIS_URL)
    source = RedisProgressSource(REDIS_URL)

    async def scenario():
        async with source.subscribe("s-one") as reader:
            publisher({"event": "other", "session_id": "s-two"})
            publisher({"event": "mine", "session_id": "s-one", "step_number": 3})
            first = await reader.next(2)
            nothing = await reader.next(0.2)
            return first, nothing

    first, nothing = run(scenario())
    assert first == {"event": "mine", "session_id": "s-one", "step_number": 3}
    assert nothing is None


@needs_redis
def test_unreachable_redis_raises_instead_of_hanging():
    import redis

    async def scenario():
        async with RedisProgressSource("redis://127.0.0.1:1/0").subscribe("s"):
            pass

    with pytest.raises((redis.RedisError, OSError)):
        run(scenario())
