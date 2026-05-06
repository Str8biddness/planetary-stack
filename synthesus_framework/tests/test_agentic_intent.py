import pytest
import asyncio
from pathlib import Path
from core.knowledge_cloud import KnowledgeCloud
from cognitive.cognitive_engine import CognitiveEngine

PROJ_ROOT = Path(__file__).parent.parent

@pytest.fixture
def knowledge_cloud():
    """Load the updated world_lore.json for testing."""
    data_dir = PROJ_ROOT / "data" / "knowledge_cloud"
    return KnowledgeCloud(data_dir=str(data_dir))

@pytest.fixture
def character_data():
    """Generic character for testing."""
    return {
        "bio": {"name": "TestNPC", "archetype": "merchant"},
        "patterns": {"synthetic_patterns": [{"response": "I see you're interested in the world."}]}
    }

@pytest.mark.asyncio
async def test_agentic_intent_match(knowledge_cloud, character_data):
    """Verify that matching intent triggers knowledge-defined actions."""
    engine = CognitiveEngine(
        character_id="test_npc",
        bio=character_data["bio"],
        patterns=character_data["patterns"],
        knowledge_cloud=knowledge_cloud
    )
    
    # Query for Healing Potion with 'shop_buy' intent
    # Note: 'shop_buy' is mapped to ['open_item_shop', 'examine_potion_animation']
    result = await engine.process_query(
        player_id="p1",
        query="I'd like to buy a healing potion",
        ml_context={"intent": "shop_buy"}
    )
    
    assert result["source"] == "knowledge_cloud"
    
    # Check if actions were triggered
    actions = result["actions_taken"]
    action_names = [a["action"] for a in actions]
    
    assert "open_item_shop" in action_names
    assert "examine_potion_animation" in action_names
    
    # Verify description is present
    action_desc = next(a["description"] for a in actions if a["action"] == "open_item_shop")
    assert "Triggered action" in action_desc
    assert "Healing Potion" in action_desc

@pytest.mark.asyncio
async def test_agentic_intent_mismatch(knowledge_cloud, character_data):
    """Verify that mismatched intent does NOT trigger actions."""
    engine = CognitiveEngine(
        character_id="test_npc",
        bio=character_data["bio"],
        patterns=character_data["patterns"],
        knowledge_cloud=knowledge_cloud
    )
    
    # Query for Healing Potion with 'lore_query' intent (not mapped to actions)
    result = await engine.process_query(
        player_id="p1",
        query="Tell me about healing potions",
        ml_context={"intent": "lore_query"}
    )
    
    # Actions should be empty or at least not contain shop actions
    action_names = [a["action"] for a in result["actions_taken"]]
    assert "open_item_shop" not in action_names

@pytest.mark.asyncio
async def test_multi_entity_agentic_actions(knowledge_cloud, character_data):
    """Verify that multiple entities can contribute to the action list."""
    engine = CognitiveEngine(
        character_id="test_npc",
        bio=character_data["bio"],
        patterns=character_data["patterns"],
        knowledge_cloud=knowledge_cloud
    )
    
    # Query for Ironhaven and healing potions with 'shop_buy' intent
    # Ironhaven: ['open_market_ui', ...]
    # Healing Potion: ['open_item_shop', ...]
    result = await engine.process_query(
        player_id="p1",
        query="What can I buy in Ironhaven? Any healing potions?",
        ml_context={"intent": "shop_buy"}
    )
    
    action_names = [a["action"] for a in result["actions_taken"]]
    
    assert "open_market_ui" in action_names
    assert "open_item_shop" in action_names
