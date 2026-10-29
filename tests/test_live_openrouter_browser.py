"""Live OpenRouter Model-Driven Playwright Browser Acceptance Suite (BRICK-006 Phase 9).

Executes genuine OpenRouter inference (openai/gpt-4o-mini) against real headless Chromium
browser sessions to verify:
1. Live model tool selection: browser_navigate and browser_extract_text execution.
2. Multi-turn browser planning and conversation persistence across sequential turns.
3. Live Human-in-the-Loop (HITL) approval interruption and resumption for mutating actions.
4. Strict budget reconciliation ensuring total suite cost remains negligible (< $0.05 USD).
"""

import os
import uuid
from typing import Any

import pytest
from dotenv import load_dotenv

from javed.agent.checkpointer import AgentCheckpointerManager
from javed.agent.runtime import AgentRuntimeManager
from javed.browser.engine import BrowserEngineManager
from javed.browser.tools import BrowserSession
from javed.config import Settings
from javed.mcp.approval_store import ApprovalStore
from javed.schemas.agent import AgentStreamRequest

load_dotenv()

# Global accumulator to track total OpenRouter API test spend
_TOTAL_TEST_SPEND_USD: float = 0.0


def _track_cost(usage_data: dict[str, Any]) -> float:
    """Record and accumulate test spend from stream run_completed usage metadata."""
    global _TOTAL_TEST_SPEND_USD
    cost = float(usage_data.get("cost_usd") or 0.0)
    _TOTAL_TEST_SPEND_USD += cost
    return cost


@pytest.fixture
def live_settings(tmp_path: Any) -> Settings:
    """Provide isolated configuration with real OpenRouter API key and temporary databases."""
    api_key = os.getenv("OPENROUTER_API_KEY", "").strip()
    if not api_key:
        pytest.skip("OPENROUTER_API_KEY not configured in environment")

    checkpoints_db = tmp_path / "live_browser_checkpoints.db"
    approvals_db = tmp_path / "live_browser_approvals.db"

    return Settings(
        openrouter_api_key=api_key,
        openrouter_default_model="openai/gpt-4o-mini",
        openrouter_auto_router_cost_tier="low",
        agent_checkpoint_db_path=str(checkpoints_db),
        agent_approvals_db_path=str(approvals_db),
    )


@pytest.fixture
async def live_browser_runtime(live_settings: Settings) -> Any:
    """Spin up live runtime connected to genuine Playwright browser session with isolated stores."""
    approval_store = ApprovalStore(db_path=live_settings.agent_approvals_db_path)
    await approval_store.initialize()

    checkpointer_mgr = AgentCheckpointerManager(db_path=live_settings.agent_checkpoint_db_path)

    browser_engine = BrowserEngineManager(headless=True)
    browser_session = BrowserSession(engine=browser_engine)

    runtime = AgentRuntimeManager(
        settings=live_settings,
        checkpointer_manager=checkpointer_mgr,
        approval_store=approval_store,
        enable_browser=True,
        browser_session=browser_session,
        browser_approval_required=True,
    )
    await runtime.initialize()

    yield runtime

    # Clean process and context teardown
    await runtime.close()
    await browser_session.close()
    await browser_engine.close()
    await checkpointer_mgr.close()
    await approval_store.close()


@pytest.mark.asyncio
async def test_live_browser_navigation_and_text_extraction(
    live_browser_runtime: AgentRuntimeManager,
) -> None:
    """Verify live model calls browser_navigate and browser_extract_text on example.com."""
    thread_id = f"thread_live_nav_{uuid.uuid4().hex[:8]}"
    req = AgentStreamRequest(
        thread_id=thread_id,
        message=(
            "Use the browser_navigate tool to visit https://example.com, then use "
            "browser_extract_text to read the page content. What is the main heading?"
        ),
        model="openai/gpt-4o-mini",
    )

    events = []
    async for ev in live_browser_runtime.stream_agent(req):
        events.append(ev)

    event_types = [e.event for e in events]
    assert "run_started" in event_types
    assert "tool_started" in event_types
    assert "tool_completed" in event_types
    assert "run_completed" in event_types

    # Verify browser_navigate was selected and executed against real Chromium
    tools_executed = [e.data.get("tool") for e in events if e.event == "tool_completed"]
    assert "browser_navigate" in tools_executed

    # Verify tool completed output contains real navigation details
    nav_completed = next(
        e
        for e in events
        if e.event == "tool_completed" and e.data.get("tool") == "browser_navigate"
    )
    nav_out = nav_completed.data.get("output", "")
    assert "Example Domain" in nav_out or "200" in nav_out

    # Verify final model synthesis mentions Example Domain
    run_comp = next(e for e in events if e.event == "run_completed")
    content = run_comp.data.get("content", "").lower()
    assert "example" in content or "domain" in content

    # Telemetry and cost tracking
    usage = run_comp.data.get("usage", {})
    cost = _track_cost(usage)
    assert usage.get("prompt_tokens", 0) > 0
    assert usage.get("completion_tokens", 0) > 0
    assert cost < 0.02  # Well within individual turn budget


@pytest.mark.asyncio
async def test_live_browser_multiturn_planning_and_context(
    live_browser_runtime: AgentRuntimeManager,
) -> None:
    """Verify multi-turn browser planning maintains active page and thread state across turns."""
    thread_id = f"thread_live_multiturn_{uuid.uuid4().hex[:8]}"

    # Turn 1: Navigate to target
    req1 = AgentStreamRequest(
        thread_id=thread_id,
        message="Please use the browser_navigate tool to navigate to https://example.com.",
        model="openai/gpt-4o-mini",
    )
    turn1_events = [ev async for ev in live_browser_runtime.stream_agent(req1)]
    assert any(
        e.event == "tool_completed" and e.data.get("tool") == "browser_navigate"
        for e in turn1_events
    )
    comp1 = next(e for e in turn1_events if e.event == "run_completed")
    _track_cost(comp1.data.get("usage", {}))

    # Turn 2: Extract specific heading element from already-open page
    req2 = AgentStreamRequest(
        thread_id=thread_id,
        message="On that page, extract text from the 'h1' element using browser_extract_text.",
        model="openai/gpt-4o-mini",
    )
    turn2_events = [ev async for ev in live_browser_runtime.stream_agent(req2)]
    assert any(
        e.event == "tool_completed" and e.data.get("tool") == "browser_extract_text"
        for e in turn2_events
    )
    comp2 = next(e for e in turn2_events if e.event == "run_completed")
    _track_cost(comp2.data.get("usage", {}))

    # Turn 3: Conversational follow-up (no tool call needed)
    req3 = AgentStreamRequest(
        thread_id=thread_id,
        message="Based on what we just inspected, in 5 words or less, what is that page?",
        model="openai/gpt-4o-mini",
    )
    turn3_events = [ev async for ev in live_browser_runtime.stream_agent(req3)]
    comp3 = next(e for e in turn3_events if e.event == "run_completed")
    _track_cost(comp3.data.get("usage", {}))

    # Verify conversational synthesis without tool calls on turn 3
    turn3_tools = [e.data.get("tool") for e in turn3_events if e.event == "tool_started"]
    assert len(turn3_tools) == 0

    # Verify checkpointer persisted all turns under the same thread_id
    state = await live_browser_runtime.get_thread_state(thread_id)
    assert len(state.messages) >= 6  # 3 pairs of Human + AI (+ tool messages)


@pytest.mark.asyncio
async def test_live_browser_hitl_approval_and_resumption(
    live_browser_runtime: AgentRuntimeManager,
) -> None:
    """Verify mutating browser_click triggers HITL interrupt and resumes on approval."""
    thread_id = f"thread_live_hitl_{uuid.uuid4().hex[:8]}"

    # First navigate to page
    session = live_browser_runtime.get_browser_session()
    assert session is not None
    await session.navigate("https://example.com")

    # Request model to click an element (browser_click is mutating -> requires approval)
    req = AgentStreamRequest(
        thread_id=thread_id,
        message="Please click the link on the page using the browser_click tool with selector 'a'.",
        model="openai/gpt-4o-mini",
    )

    events_turn1 = []
    async for ev in live_browser_runtime.stream_agent(req):
        events_turn1.append(ev)

    event_types = [e.event for e in events_turn1]
    assert "approval_required" in event_types
    assert "run_completed" not in event_types
    assert "tool_started" not in event_types  # No execution prior to human approval

    appr_ev = next(e for e in events_turn1 if e.event == "approval_required")
    approval_id = appr_ev.data.get("approval_id")
    assert approval_id is not None
    assert appr_ev.data.get("tool_id") == "browser_click"
    assert appr_ev.data.get("server_id") == "browser"

    # Human user grants approval
    resume_events = []
    async for rev in live_browser_runtime.resume_agent(
        thread_id=thread_id,
        approval_id=approval_id,
        decision="approve",
        reason="Owner verified safe link target",
    ):
        resume_events.append(rev)

    resume_types = [e.event for e in resume_events]
    assert "approval_approved" in resume_types
    assert "agent_resumed" in resume_types
    assert "tool_started" in resume_types
    assert "tool_completed" in resume_types
    assert "run_completed" in resume_types

    # Track resume cost
    run_comp = next(e for e in resume_events if e.event == "run_completed")
    _track_cost(run_comp.data.get("usage", {}))


def test_budget_reconciliation() -> None:
    """Verify cumulative OpenRouter spend across all live test scenarios is well below $0.05 USD."""
    global _TOTAL_TEST_SPEND_USD
    # Even across multiple runs, cumulative spend for gpt-4o-mini must be negligible
    assert _TOTAL_TEST_SPEND_USD < 0.05, (
        f"Budget violation: Spend ${_TOTAL_TEST_SPEND_USD:.6f} exceeded $0.05 limit."
    )
