import asyncio
import pytest
from core.synthesus_master import SynthesusMaster


@pytest.mark.asyncio
async def test_deductive_query():
    master = SynthesusMaster()
    result = await master.think("Given that user_authenticated and admin_privileges_granted, therefore system_access_allowed?")
    assert result["t"] == 1
    assert len(master.state.narrative.timeline) == 1
    event = master.state.narrative.timeline[0]
    assert event.engines_used == ["deductive"]
    assert "Proved goal" in event.summary
    assert event.proof_trace != ""


@pytest.mark.asyncio
async def test_inductive_query_with_logs():
    master = SynthesusMaster()
    logs = [
        {"timestamp": 1.0, "features": {"cpu_usage": 0.8, "memory_usage": 0.6}, "outcome": "high_load"},
        {"timestamp": 2.0, "features": {"cpu_usage": 0.3, "memory_usage": 0.4}, "outcome": "normal"},
    ]
    result = await master.think("Are there any patterns in recent system load?", system_logs=logs)
    assert result["t"] == 1
    assert len(master.state.narrative.timeline) == 1
    event = master.state.narrative.timeline[0]
    assert "inductive" in event.engines_used
    assert "Detected" in event.summary


@pytest.mark.asyncio
async def test_abductive_query():
    master = SynthesusMaster()
    result = await master.think("Why is the system experiencing a slowdown and timeouts?")
    assert result["t"] == 1
    assert len(master.state.narrative.timeline) == 1
    event = master.state.narrative.timeline[0]
    assert "abductive" in event.engines_used
    assert "Generated" in event.summary
    assert len(event.explanations) > 0


@pytest.mark.asyncio
async def test_state_increment_and_accumulation():
    master = SynthesusMaster()
    await master.think("Test query 1")
    assert master.state.t == 1
    await master.think("Test query 2")
    assert master.state.t == 2
    assert len(master.state.narrative.timeline) == 2


@pytest.mark.asyncio
async def test_crystallized_facts_growth():
    master = SynthesusMaster()
    await master.think("Given that A and B, therefore C?")
    assert "C" in master.state.crystallized.facts
    assert master.state.crystallized.facts["C"] is True
