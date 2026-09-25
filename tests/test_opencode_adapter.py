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
