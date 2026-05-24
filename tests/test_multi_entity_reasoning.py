import pytest
import asyncio
from pathlib import Path
from core.knowledge_cloud import KnowledgeCloud
from cognitive.cognitive_engine import CognitiveEngine

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
    """Garen the Knight - character data for synthesis."""
    return {
        "bio": {
            "name": "Garen",
            "archetype": "knight",
            "role": "Defender of Ironhaven"
        },
        "patterns": {
            "synthetic_patterns": [
                {"response": "I stand for the Duke and his people."},
                {"response": "Law and order are the pillars of Ironhaven."}
            ]
        }
    }

@pytest.mark.asyncio
async def test_relational_lookup_logic(knowledge_cloud):
    """Verify that lookup_multi returns multiple related entities."""
    # Searching for Duke and Ironhaven should return both
    # Note: Duke Aldric requires trust=60.0
    results = knowledge_cloud.lookup_multi("Duke Aldric and Ironhaven", trust=60.0, top_k=2)
    
    entity_ids = [r["entity_id"] for r in results]
    assert "duke_aldric" in entity_ids
    assert "ironhaven" in entity_ids
    
    # Verify relations are present
    duke_res = next(r for r in results if r["entity_id"] == "duke_aldric")
    assert duke_res["entity_name"] == "Duke Aldric"
    assert duke_res["related"]["rules"] == "Ironhaven"

@pytest.mark.asyncio
async def test_multi_entity_synthesis(knowledge_cloud, character_data):
    """Verify that synthesis bridges multiple entities naturally."""
    engine = CognitiveEngine(
        character_id="garen",
        bio=character_data["bio"],
        patterns=character_data["patterns"],
        knowledge_cloud=knowledge_cloud
    )
    
    # Query involving person and place
    query = "Who is Duke Aldric and where does he rule?"
    
    # Set high trust to bypass gates
    engine.relationships.apply_event("player_456", "saved_life") # trust 50 -> 80
    
    result = await engine.process_query(
        player_id="player_456",
        query=query
    )
    
    assert result["source"] == "knowledge_cloud"
    response = result["response"]
    print(f"\n[MULTI-ENTITY RESPONSE]: {response}")
    
    # Factual check: should mention Duke AND Ironhaven
    low_resp = response.lower()
    assert "duke" in low_resp or "aldric" in low_resp
    assert "ironhaven" in low_resp
    
    # Relational check: should contain some bridging logic
    # (Since we injected "The Duke Aldric is rules Ironhaven" into the corpus)
    # The synthesis might generate something like "Duke Aldric rules Ironhaven"
    assert any(bridge in low_resp for bridge in ["rules", "governed", "city", "ruler"])

@pytest.mark.asyncio
async def test_disjoint_entities(knowledge_cloud, character_data):
    """Verify synthesis handles two entities that are NOT related."""
    engine = CognitiveEngine(
        character_id="garen",
        bio=character_data["bio"],
        patterns=character_data["patterns"],
        knowledge_cloud=knowledge_cloud
    )
    
    # Query for two unrelated things (Dragon and Healing Potion)
    query = "Tell me about dragons and healing potions."
    results = await engine.process_query(player_id="p1", query=query)
    
    response = results["response"].lower()
    print(f"\n[DISJOINT RESPONSE]: {response}")
    
    assert "dragon" in response or "reptilian" in response
    assert "potion" in response or "healing" in response
