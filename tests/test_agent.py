from app.agent import run_turn
from app.providers.base import ModelReply, ToolCall


class FakeProvider:
    def __init__(self):
        self.calls = 0

    async def chat(self, messages, tools=None):
        self.calls += 1
        if self.calls == 1:
            return ModelReply(content=None, tool_calls=[ToolCall(id="1", name="nope", arguments="{}")])
        assert messages[-1]["role"] == "tool"
        return ModelReply(content="done")


async def test_loop_runs_tool_then_answers():
    assert await run_turn([{"role": "user", "content": "hi"}], provider=FakeProvider()) == "done"
