import pytest
import asyncio
from unittest.mock import MagicMock, AsyncMock

from domains.gm.gm_adapter import GameMasterAdapter

@pytest.mark.asyncio
async def test_gm_adapter_routing():
    # Create mock engine factory
    mock_engine = MagicMock()
    mock_engine.process_query = AsyncMock(return_value={
        "response": "Hello traveler.",
        "confidence": 0.9,
        "emotion": "neutral"
    })
    
    def mock_factory(char_id):
        if char_id in ("narrator", "garen"):
            return mock_engine
        return None
        
    adapter = GameMasterAdapter("test_session", mock_factory, "narrator")
    
    # 1. Test World action (should route to narrator)
    res = await adapter.process_query("I look around", "player1")
    assert res["character"] == "narrator"
    assert "Hello traveler" in res["response"]
    assert "world_context" in res["debug"]
    assert res["debug"]["world_tick"] > 0
    
    # Ensure world context was passed to ML context
    call_args = mock_engine.process_query.call_args[1]
    assert "world_state" in call_args["ml_context"]
    assert "Weather" in call_args["ml_context"]["world_state"]
    
    # 2. Test NPC specific action
    # Mock the region summary so Garen is guaranteed to be present
    adapter.world.get_region_summary = MagicMock(return_value={
        "region": "riverside",
        "npcs_present": ["garen"],
        "weather": {"condition": "clear", "temperature": 22}
    })
    
    res2 = await adapter.process_query("I talk to Garen", "player1")
    
    # It should correctly identify "garen"
    assert res2["character"] == "garen"
    assert res2["source"] == "gm_adapter_garen"

@pytest.mark.asyncio
async def test_gm_adapter_unavailable_npc():
    def mock_factory(char_id):
        return None
        
    adapter = GameMasterAdapter("test_session", mock_factory, "narrator")
    adapter.current_region = "riverside"
    
    res = await adapter.process_query("I talk to Garen", "player1")
    assert res["confidence"] == 0.0
    assert "unavailable" in res["response"]
