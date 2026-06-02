import os

import pytest

from odyssey.concierge.agent import build_spike_agent
from odyssey.concierge.guardrail import before_tool_callback


class _FakeTool:
    def __init__(self, name):
        self.name = name


class _Ctx:
    def __init__(self, state):
        self.state = state


def test_guardrail_blocks_checkout_without_cart():
    blocked = before_tool_callback(
        tool=_FakeTool("complete_trip"), args={}, tool_context=_Ctx({})
    )
    assert blocked is not None and "deny" in str(blocked).lower()


def test_guardrail_allows_search():
    assert (
        before_tool_callback(
            tool=_FakeTool("plan_trip"), args={}, tool_context=_Ctx({})
        )
        is None
    )


def test_spike_agent_constructs():
    # Offline check: the agent (with a require_confirmation tool + guardrail) builds without error.
    agent = build_spike_agent()
    assert agent.name == "odyssey_spike"
    assert any(
        getattr(t, "name", "") == "complete_purchase" for t in agent.tools
    ) or len(agent.tools) == 2


@pytest.mark.skipif(
    not os.environ.get("GOOGLE_API_KEY"), reason="needs Gemini key to run the agent"
)
@pytest.mark.asyncio
async def test_purchase_tool_requests_confirmation():
    from google.adk.runners import InMemoryRunner
    from google.genai import types

    runner = InMemoryRunner(agent=build_spike_agent())
    session = await runner.session_service.create_session(
        app_name="spike", user_id="u"
    )
    msg = types.Content(
        role="user", parts=[types.Part(text="book the demo item")]
    )
    saw = False
    async for event in runner.run_async(
        user_id="u", session_id=session.id, new_message=msg
    ):
        for part in event.content.parts if event.content else []:
            if (
                getattr(part, "function_call", None)
                and part.function_call.name == "adk_request_confirmation"
            ):
                saw = True
    assert saw, "purchase tool must pause for human confirmation"
