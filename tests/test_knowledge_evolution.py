import pytest
import asyncio
from pathlib import Path
from core.knowledge_cloud import KnowledgeCloud
from cognitive.cognitive_engine import CognitiveEngine

PROJ_ROOT = Path(__file__).parent.parent

@pytest.fixture
def shared_cloud():
    """Load the world_lore.json into a shared cloud instance."""
    data_dir = PROJ_ROOT / "data" / "knowledge_cloud"
    # Ensure a fresh evolution file for testing
    evo_path = Path(data_dir) / "evolution.json"
    if evo_path.exists():
        evo_path.unlink()
        
    return KnowledgeCloud(data_dir=str(data_dir))

@pytest.fixture
def char_a():
    return {"bio": {"name": "Guard_A", "archetype": "guard"}, "patterns": {}}

@pytest.fixture
def char_b():
    return {"bio": {"name": "Scholar_B", "archetype": "scholar"}, "patterns": {}}

@pytest.mark.asyncio
async def test_knowledge_evolution_propagation(shared_cloud, char_a, char_b):
    """Verify that a fact witnessed by one NPC propagates to others."""
    # Initialize two NPCs sharing the same knowledge cloud
    npc_a = CognitiveEngine(character_id="guard_a", bio=char_a["bio"], 
                            patterns=char_a["patterns"], knowledge_cloud=shared_cloud)
    
    npc_b = CognitiveEngine(character_id="scholar_b", bio=char_b["bio"], 
                            patterns=char_b["patterns"], knowledge_cloud=shared_cloud)
    
    # 1. Initially, NPC B doesn't know about any new secret
    res_initial = await npc_b.process_query(player_id="p1", query="What's the latest rumor about Duke Aldric?")
    assert "secret alliance" not in res_initial["response"].lower()
    
    # 2. NPC A witnesses a secret event
    new_fact = "observed the Duke meeting with Shadow Wraiths at midnight"
    npc_a.record_witness_event(entity_id="duke_aldric", fact=new_fact, depth="rumor")
    
    # 3. NPC B is queried again about the Duke (with sufficient trust)
    res_final = await npc_b.process_query(player_id="p1", 
                                          query="What do you know about Duke Aldric's meetings?",
                                          ml_context={"trust": 70.0})
    
    # NPC B should now have the new fact in its synthesis corpus
    assert "shadow wraiths" in res_final["response"].lower()
    assert "midnight" in res_final["response"].lower()
    
    # 4. Persistence Check: Verify evolution.json was created
    evo_path = Path(shared_cloud.data_dir) / "evolution.json"
    assert evo_path.exists()
    
    # Clean up
    if evo_path.exists():
        evo_path.unlink()
