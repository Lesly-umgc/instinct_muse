"""Regression tests for the chat-reply pipeline (v0.1.3 bugs).

Covers: replies surviving a Hub restart (lost session mapping), errors and
timeouts being persisted as visible assistant messages, auto-titling from the
first user message, and server-side chat deletion.
"""
import asyncio

import pytest

import app.api as api
from app.api import Hub
from app.engines import EngineEvent
from app.store import Store


class FakeEngine:
    id = "fake"
    name = "Fake"

    def __init__(self, reply: str = "Hi there", fail: Exception | None = None, delay: float = 0.0):
        self.reply = reply
        self.fail = fail
        self.delay = delay
        self.aborted: list[str] = []

    async def create_session(self, title: str | None = None) -> str:
        return "ses_fake"

    async def send(self, session_id: str, text: str, provider_id=None, model_id=None) -> None:
        if self.delay:
            await asyncio.sleep(self.delay)
        if self.fail:
            raise self.fail

    async def abort(self, session_id: str) -> None:
        self.aborted.append(session_id)


@pytest.fixture
def hub(tmp_path):
    store = Store(str(tmp_path / "test.db"))
    h = Hub(store)
    yield h
    store.close()


def make_conv(h: Hub, title: str = "New chat") -> dict:
    return h.store.create_conversation(title, "fake", None)


async def test_reply_persisted_without_prior_mapping(hub):
    """After a service restart the Hub forgot session->conversation mappings;
    the reply must still be persisted and broadcast, not silently dropped."""
    engine = FakeEngine()
    hub.engines["fake"] = engine
    conv = make_conv(hub)
    # Simulate a pre-restart conversation: it has an engine session, but the
    # Hub has never seen it this run.
    hub.store.set_engine_session(conv["id"], "ses_old")
    assert "ses_old" not in hub._sessions

    await hub.send_user_message(conv["id"], "hello")
    # send must have re-registered the mapping
    assert hub._sessions["ses_old"] == conv["id"]

    await hub._handle_event(engine, EngineEvent("text_delta", "ses_old", "Hi there"))
    await hub._handle_event(engine, EngineEvent("message_done", "ses_old"))
    msgs = hub.store.list_messages(conv["id"])
    assert [m["role"] for m in msgs] == ["user", "assistant"]
    assert msgs[1]["content"] == "Hi there"


async def test_autotitle_from_first_message(hub):
    hub.engines["fake"] = FakeEngine()
    conv = make_conv(hub)
    await hub.send_user_message(conv["id"], "can you write a code for me?")
    assert hub.store.get_conversation(conv["id"])["title"] == "can you write a code for me?"
    # Second message must not rename again
    await hub.send_user_message(conv["id"], "thanks")
    assert hub.store.get_conversation(conv["id"])["title"] == "can you write a code for me?"


async def test_autotitle_truncates_long_message(hub):
    hub.engines["fake"] = FakeEngine()
    conv = make_conv(hub)
    await hub.send_user_message(conv["id"], "word " * 30)
    title = hub.store.get_conversation(conv["id"])["title"]
    assert title.endswith("...") and len(title) <= 52


async def test_timeout_persists_visible_error(hub, monkeypatch):
    monkeypatch.setattr(api, "REPLY_TIMEOUT_SECONDS", 0.05)
    engine = FakeEngine(delay=5.0)
    hub.engines["fake"] = engine
    conv = make_conv(hub)
    await hub.send_user_message(conv["id"], "slow question")  # must not raise
    assert engine.aborted == ["ses_fake"]
    msgs = hub.store.list_messages(conv["id"])
    assert [m["role"] for m in msgs] == ["user", "assistant"]
    assert msgs[1]["content"].startswith("Error:") and "took too long" in msgs[1]["content"]


async def test_engine_error_persists_visible_error(hub):
    hub.engines["fake"] = FakeEngine(fail=RuntimeError("boom"))
    conv = make_conv(hub)
    await hub.send_user_message(conv["id"], "hi")  # must not raise
    msgs = hub.store.list_messages(conv["id"])
    assert [m["role"] for m in msgs] == ["user", "assistant"]
    assert "boom" in msgs[1]["content"]


def test_delete_conversation_removes_chat_and_messages(hub):
    conv = make_conv(hub)
    hub.store.add_message(conv["id"], "user", "hi")
    hub.store.add_artifact("document", "/tmp/x.md", "x.md", "body", conversation_id=conv["id"])
    hub.store.delete_conversation(conv["id"])
    assert hub.store.get_conversation(conv["id"]) is None
    assert hub.store.list_messages(conv["id"]) == []
    # Library artifacts survive the chat being deleted
    assert hub.store.find_artifact_by_path("/tmp/x.md") is not None


class SlowSessionEngine(FakeEngine):
    async def create_session(self, title: str | None = None) -> str:
        await asyncio.sleep(5.0)
        return "ses_late"


async def test_session_create_timeout_persists_visible_error(hub, monkeypatch):
    """If OpenCode hangs while starting the session, the failure must surface
    in the chat - not vanish into the log (the Montreal-trip bug)."""
    monkeypatch.setattr(api, "SESSION_TIMEOUT_SECONDS", 0.05)
    hub.engines["fake"] = SlowSessionEngine()
    conv = make_conv(hub)
    await hub.send_user_message(conv["id"], "plan a trip")  # must not raise
    msgs = hub.store.list_messages(conv["id"])
    assert [m["role"] for m in msgs] == ["user", "assistant"]
    assert msgs[1]["content"].startswith("Error:") and "took too long" in msgs[1]["content"]


def test_startup_marks_interrupted_turn(hub):
    """A conversation whose last message is from the user lost its turn with
    the previous process; the sweep says so, and stays idempotent."""
    conv = make_conv(hub)
    hub.store.add_message(conv["id"], "user", "unanswered")
    hub._mark_interrupted_turns()
    msgs = hub.store.list_messages(conv["id"])
    assert msgs[-1]["role"] == "assistant" and "interrupted" in msgs[-1]["content"]
    hub._mark_interrupted_turns()
    assert len(hub.store.list_messages(conv["id"])) == 2


def test_startup_leaves_answered_chats_alone(hub):
    conv = make_conv(hub)
    hub.store.add_message(conv["id"], "user", "hi")
    hub.store.add_message(conv["id"], "assistant", "hello")
    hub._mark_interrupted_turns()
    assert len(hub.store.list_messages(conv["id"])) == 2

async def test_stop_turn_aborts_engine_and_keeps_partial_reply(hub):
    engine = FakeEngine(delay=5.0)
    hub.engines["fake"] = engine
    conv = make_conv(hub)
    task = asyncio.create_task(hub.send_user_message(conv["id"], "draft a reply"))
    hub._turns[conv["id"]] = task
    while not hub.store.get_conversation(conv["id"])["engine_session_id"]:
        await asyncio.sleep(0)
    sid = hub.store.get_conversation(conv["id"])["engine_session_id"]
    await hub._handle_event(engine, EngineEvent("text_delta", sid, "Partial"))
    await hub.stop_turn(conv["id"])
    assert engine.aborted == [sid]
    assert "Partial" in hub.store.list_messages(conv["id"])[-1]["content"]
    assert "Stopped" in hub.store.list_messages(conv["id"])[-1]["content"]
    await hub._handle_event(engine, EngineEvent("message_done", sid))
    assert len(hub.store.list_messages(conv["id"])) == 2

async def test_stop_during_session_creation_is_visible(hub):
    class SlowCreate(FakeEngine):
        async def create_session(self, title=None):
            await asyncio.sleep(5)
            return "ses_slow"

    hub.engines["fake"] = SlowCreate()
    conv = make_conv(hub)
    task = asyncio.create_task(hub.send_user_message(conv["id"], "hello"))
    hub._turns[conv["id"]] = task
    while not hub.store.list_messages(conv["id"]):
        await asyncio.sleep(0)
    await hub.stop_turn(conv["id"])
    assert [m["content"] for m in hub.store.list_messages(conv["id"])] == ["hello", "Reply stopped."]

async def test_stop_racing_with_finished_reply_does_not_add_second_assistant(hub):
    engine = FakeEngine()
    hub.engines["fake"] = engine
    conv = make_conv(hub)
    await hub.send_user_message(conv["id"], "hello")
    sid = hub.store.get_conversation(conv["id"])["engine_session_id"]
    await hub._handle_event(engine, EngineEvent("text_delta", sid, "Finished"))
    await hub._handle_event(engine, EngineEvent("message_done", sid))
    task = asyncio.create_task(asyncio.sleep(10))
    hub._turns[conv["id"]] = task
    await hub.stop_turn(conv["id"])
    assert [m["content"] for m in hub.store.list_messages(conv["id"])] == ["hello", "Finished"]
