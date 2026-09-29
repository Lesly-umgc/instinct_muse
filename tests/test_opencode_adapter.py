import httpx
import pytest
import respx

from app.engines.opencode_server import OpenCodeServerEngine

BASE = "http://opencode.test"


@respx.mock
async def test_status_available():
    respx.get(f"{BASE}/global/health").mock(
        return_value=httpx.Response(200, json={"healthy": True, "version": "0.6.3"}))
    engine = OpenCodeServerEngine(BASE)
    status = await engine.status()
    assert status.available and "0.6.3" in status.detail
    await engine.aclose()


@respx.mock
async def test_status_unavailable():
    respx.get(f"{BASE}/global/health").mock(side_effect=httpx.ConnectError("refused"))
    engine = OpenCodeServerEngine(BASE)
    status = await engine.status()
    assert not status.available and "not reachable" in status.reason
    await engine.aclose()


@respx.mock
async def test_models_only_connected_providers():
    respx.get(f"{BASE}/provider").mock(return_value=httpx.Response(200, json={
        "all": [
            {"id": "opencode", "name": "OpenCode Zen",
             "models": {"big-pickle": {"name": "Big Pickle"}, "glm-5.3": {"name": "GLM 5.3"}}},
            {"id": "openai", "name": "OpenAI", "models": {"gpt-6": {"name": "GPT-6"}}},
        ],
        "default": {"opencode": "big-pickle"},
        "connected": ["opencode"],
    }))
    engine = OpenCodeServerEngine(BASE)
    models = await engine.models()
    ids = {(m.provider_id, m.model_id) for m in models}
    assert ("opencode", "big-pickle") in ids and ("openai", "gpt-6") not in ids
    assert any(m.is_default for m in models)
    await engine.aclose()


@respx.mock
async def test_session_send_and_permission_reply():
    respx.post(f"{BASE}/session").mock(return_value=httpx.Response(200, json={"id": "ses_1"}))
    prompt = respx.post(f"{BASE}/session/ses_1/message").mock(return_value=httpx.Response(200, json={"parts": [{"type": "text", "text": "Hello"}]}))
    perm = respx.post(f"{BASE}/session/ses_1/permissions/perm_1").mock(
        return_value=httpx.Response(200, json=True))
    engine = OpenCodeServerEngine(BASE)
    session_id = await engine.create_session("test")
    assert session_id == "ses_1"
    await engine.send(session_id, "make hello.md", "opencode", "big-pickle")
    events = engine.events()
    assert (await anext(events)).text == "Hello"
    assert (await anext(events)).type == "message_done"
    assert prompt.called
    body = prompt.calls.last.request.read()
    assert b"make hello.md" in body and b"big-pickle" in body
    await engine.reply_permission(session_id, "perm_1", "once", remember=False)
    assert b'"once"' in perm.calls.last.request.read()
    await engine.aclose()


@pytest.mark.parametrize("payload,expected", [
    ({"type": "message.part.updated",
      "properties": {"part": {"type": "text", "sessionID": "s1"}, "delta": "Hel"}},
     ("text_delta", "s1", "Hel")),
    ({"type": "permission.asked",
      "properties": {"id": "p1", "sessionID": "s1", "permission": "write"}},
     ("permission_request", "s1", "")),
    ({"type": "session.idle", "properties": {"sessionID": "s1"}},
     ("message_done", "s1", "")),
])
def test_normalize_events(payload, expected):
    ev = OpenCodeServerEngine._normalize(payload)
    assert ev is not None
    etype, session, text = expected
    assert ev.type == etype and ev.session_id == session and ev.text == text


def test_normalize_ignores_unknown():
    assert OpenCodeServerEngine._normalize({"type": "file.edited", "properties": {}}) is None

@respx.mock
async def test_sync_response_reconciles_provisional_sse_text():
    import asyncio
    started = asyncio.Event()
    finish = asyncio.Event()

    async def response(_):
        started.set()
        await finish.wait()
        return httpx.Response(200, json={"parts": [{"type": "text", "text": "Hello world"}]})

    respx.post(f"{BASE}/session/ses_1/message").mock(side_effect=response)
    engine = OpenCodeServerEngine(BASE)
    # No live stream needed: inject normalized SSE event while the sync request is pending.
    send_task = asyncio.create_task(engine.send("ses_1", "hi"))
    await started.wait()
    event = engine._normalize({"type": "message.part.updated", "properties": {
        "part": {"type": "text", "sessionID": "ses_1"}, "delta": "Hello"}})
    assert event and event.type == "text_delta"
    engine._streamed["ses_1"] += event.text
    await engine._responses.put(event)
    finish.set()
    await send_task
    events = engine.events()
    assert [(await anext(events)).text, (await anext(events)).text, (await anext(events)).type] == ["Hello", " world", "message_done"]
    await engine.aclose()


@respx.mock
async def test_sync_response_corrects_divergent_provisional_text():
    respx.post(f"{BASE}/session/ses_2/message").mock(return_value=httpx.Response(200, json={"parts": [{"type": "text", "text": "actual"}]}))
    engine = OpenCodeServerEngine(BASE)
    engine._streamed["ses_2"] = "incorrect"
    # Simulate an SSE update within the HTTP response handler so send can compare it.
    def response(_):
        engine._streamed["ses_2"] = "incorrect"
        return httpx.Response(200, json={"parts": [{"type": "text", "text": "actual"}]})
    respx.post(f"{BASE}/session/ses_2/message").mock(side_effect=response)
    await engine.send("ses_2", "hi")
    events = engine.events()
    first = await anext(events)
    assert first.type == "text_replace" and first.text == "actual"
    assert (await anext(events)).type == "message_done"
    await engine.aclose()

@respx.mock
async def test_idle_sse_does_not_finish_before_sync_response():
    import asyncio
    started = asyncio.Event()
    finish = asyncio.Event()

    async def response(_):
        started.set()
        await finish.wait()
        return httpx.Response(200, json={"parts": [{"type": "text", "text": "complete"}]})

    respx.post(f"{BASE}/session/ses_idle/message").mock(side_effect=response)
    # A short, in-memory SSE stream that emits idle ahead of the HTTP response.
    async def idle_sse(_):
        await asyncio.sleep(.01)
        return httpx.Response(200, text='data: {"type":"session.idle","properties":{"sessionID":"ses_idle"}}\n\n')
    respx.get(f"{BASE}/event").mock(side_effect=idle_sse)
    engine = OpenCodeServerEngine(BASE)
    events = engine.events()
    next_event = asyncio.create_task(anext(events))
    send_task = asyncio.create_task(engine.send("ses_idle", "hi"))
    await started.wait()
    await asyncio.sleep(.02)
    assert not next_event.done(), "SSE idle must not complete a turn before /message returns"
    finish.set()
    await send_task
    assert (await next_event).text == "complete"
    assert (await anext(events)).type == "message_done"
    await engine.aclose()
