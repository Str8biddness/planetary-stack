import pytest
import asyncio
from unittest.mock import patch, MagicMock

from amplification_wrapper import AmplificationPlane, AmplificationContext
from api.production_server import _detect_domain

@pytest.mark.asyncio
async def test_amplification_async_methods():
    """Test that the async wrappers execute properly."""
    # Mock _call_ts so we don't actually spawn Node.js
    plane = AmplificationPlane(enabled=True)
    plane._call_ts = MagicMock(return_value={"summaries": [{"id": 1}], "anomalyFlags": []})
    
    ctx = AmplificationContext(domain="chat", compute_budget=10)
    world_state = {"history": []}
    
    result = await plane.amplify_intake_async(ctx, world_state, {"query": "hello"})
    
    assert result.summaries == [{"id": 1}]
    plane._call_ts.assert_called_once()
    assert plane._call_ts.call_args[0][0] == "intake"


def test_domain_detection():
    """Test that the heuristic correctly classifies characters into domains."""
    # Test sysops
    assert _detect_domain("admin", None) == "sysops"
    assert _detect_domain("operator", None) == "sysops"
    
    # Test gm
    assert _detect_domain("narrator", None) == "gm"
    assert _detect_domain("custom_char", {"bio": {"archetype": "game_master"}}) == "gm"
    
    # Test chat
    assert _detect_domain("synth", None) == "chat"
    assert _detect_domain("scholar", {"bio": {"archetype": "scholar"}}) == "chat"


@pytest.mark.asyncio
async def test_circuit_breaker():
    """Test that repeated failures trip the circuit breaker."""
    plane = AmplificationPlane(enabled=True)
    plane._available = True # Force it to be available so it doesn't fail the initial check
    
    # Mock subprocess.run to raise TimeoutExpired
    import subprocess
    
    with patch("subprocess.run") as mock_run:
        mock_run.side_effect = subprocess.TimeoutExpired(cmd="npx", timeout=30)
        
        ctx = AmplificationContext(domain="chat")
        
        # It retries internally 2 times (default), and we expect a graceful fallback object
        result = await plane.amplify_intake_async(ctx, {}, {"query": "hello"})
        
        # Should fallback gracefully
        assert len(result.summaries) == 0
        
        # Run enough times to trip breaker (needs 3 consecutive failures)
        await plane.amplify_intake_async(ctx, {}, {})
        await plane.amplify_intake_async(ctx, {}, {})
        
        assert plane._consecutive_failures >= 3
        # Next call should immediately fail the circuit breaker check
        
        mock_run.reset_mock()
        await plane.amplify_intake_async(ctx, {}, {})
        
        # Because the circuit is broken, it shouldn't even attempt to run subprocess
        mock_run.assert_not_called()
