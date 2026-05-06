import pytest
import asyncio
from pathlib import Path
from core.knowledge_cloud import KnowledgeCloud
from cognitive.cognitive_engine import CognitiveEngine
from cognitive.pattern_engine import PatternEngine

PROJ_ROOT = Path(__file__).parent.parent

@pytest.fixture
def knowledge_cloud():
    """Load the actual world_lore.json for testing."""
    data_dir = PROJ_ROOT / "data" / "knowledge_cloud"
    if not data_dir.exists() or not (data_dir / "world_lore.json").exists():
        pytest.skip("world_lore.json not found")
    return KnowledgeCloud(data_dir=str(data_dir))

@pytest.fixture
def character_data():
    """Sample character data for synthesis."""
    return {
        "bio": {
            "name": "Garen",
            "archetype": "knight",
            "role": "Defender of Ironhaven"
        },
        "patterns": {
            "synthetic_patterns": [
                {"trigger": "hello", "response": "Greetings, traveler. I stand guard over Ironhaven."},
                {"trigger": "danger", "response": "My blade is ready. No evil shall pass while I breathe."},
                {"trigger": "honor", "response": "Honor is the shield that protects our hearts."}
            ]
        }
    }

@pytest.mark.asyncio
async def test_knowledge_synthesis_flow(knowledge_cloud, character_data):
    """Verify that knowledge lookup triggers synthesis with character voice."""
    
    # Initialize engine with mocked KAL and substrate
    engine = CognitiveEngine(
        character_id="garen",
        bio=character_data["bio"],
        patterns=character_data["patterns"],
        knowledge_cloud=knowledge_cloud
    )
    
    # Query something in the cloud (Dragon)
    # We use a high-confidence query but ensure Garen doesn't have it in local knowledge
    query = "Tell me about dragons"
    
    # Mocking necessary parts for process_query
    from cognitive.conversation_tracker import ConversationTracker
    from cognitive.relationship_tracker import RelationshipTracker
    from cognitive.world_state_reactor import WorldStateReactor
    
    result = await engine.process_query(
        player_id="player_123",
        query=query
    )
    
    assert result is not None
    assert result["source"] == "knowledge_cloud"
    
    response = result["response"]
    print(f"\n[SYNTHESIZED RESPONSE]: {response}")
    
    # Assertions:
    # 1. Contains factual content (Dragon description mentions 'reptilian' or 'power')
    assert any(word in response.lower() for word in ["reptilian", "creature", "dragon", "fire"])
    
    # 2. Contains a prefix/hedging (one of the prefixes we defined)
    prefixes = ["heard whispers", "common knowledge", "say", "rumor", "certain", "memory", "fact", "listen", "word on the street"]
    assert any(p in response.lower() for p in prefixes)
    
    # 3. Source is tracked
    assert engine._cloud_handled == 1

@pytest.mark.asyncio
async def test_depth_hedging_selection(knowledge_cloud, character_data):
    """Verify different knowledge depths produce different prefixes."""
    engine = CognitiveEngine(
        character_id="garen",
        bio=character_data["bio"],
        patterns=character_data["patterns"],
        knowledge_cloud=knowledge_cloud
    )
    
    # Test Rumor (Dragon is rumor depth in seed data)
    dragon_result = knowledge_cloud.lookup("dragon", emotion="neutral", trust=50.0)
    assert dragon_result["depth"] == "rumor"
    
    response_rumor = await engine._synthesize_knowledge_response(dragon_result, "tell me about dragons", "test_player")
    print(f"\n[RUMOR RESPONSE]: {response_rumor}")
    rumor_prefixes = ["whispers", "some say", "rumor", "street"]
    assert any(p in response_rumor.lower() for p in rumor_prefixes)

    # Test Familiar (Ironhaven is familiar depth)
    ironhaven_result = knowledge_cloud.lookup("ironhaven", emotion="neutral", trust=50.0)
    assert ironhaven_result["depth"] == "familiar"
    
    response_familiar = await engine._synthesize_knowledge_response(ironhaven_result, "tell me about ironhaven", "test_player")
    print(f"\n[FAMILIAR RESPONSE]: {response_familiar}")
    familiar_prefixes = ["certain", "memory", "recall", "yes", "ah, yes"]
    assert any(p in response_familiar.lower() for p in familiar_prefixes)
