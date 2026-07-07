import pytest
import asyncio
from cognitive.cognitive_engine import CognitiveEngine
from core.knowledge_cloud import KnowledgeCloud
from pathlib import Path
import json
import shutil
import os

@pytest.fixture
def data_dir(tmp_path):
    d = tmp_path / "data" / "knowledge_cloud"
    d.mkdir(parents=True)
    
    world_lore = {
        "version": "1.0.0",
        "description": "Test Lore",
        "entries": [
            {
                "entity_id": "black_dragon",
                "entity": "The Black Dragon",
                "entity_type": "creature",
                "description": "A legendary dragon of old.",
                "facts": ["Seen over the Frostpeak range"],
                "depth": "rumor"
            }
        ]
    }
    with open(d / "world_lore.json", "w") as f:
        json.dump(world_lore, f)
        
    return d

@pytest.mark.asyncio
async def test_proactive_lore_volunteer(data_dir):
    # 1. Setup Cloud & NPCs
    cloud = KnowledgeCloud(data_dir=str(data_dir))
    
    # NPC A (The Witness)
    npc_a = CognitiveEngine(character_id="witness_npc", knowledge_cloud=cloud)
    
    # NPC B (The Gossiper)
    npc_b = CognitiveEngine(character_id="gossip_npc", knowledge_cloud=cloud)
    
    # 2. NPC A witnesses a NEW spicy rumor
    new_fact = "The Black Dragon has returned to the scorched plains!"
    npc_a.record_witness_event(entity_id="black_dragon", fact=new_fact, depth="rumor")
    
    # Ensure index rebuilds (usually async or immediate in our case)
    # Actually, in our implementation it reloads on search if stale or immediately
    
    # 3. Player starts a conversation with NPC B (Turn 1)
    # Query must be a generic greeting or blank to avoid intent overrides (but Turn 1 usually yields greeting)
    res = await npc_b.process_query(player_id="p1", 
                                    query="Hello!", 
                                    ml_context={"trust": 70.0})
    
    # NPC B should lead with the rumor proactively
    response = res["response"].lower()
    print(f"NPC B Greeting: {response}")
    
    assert "whispers" in response or "heard" in response
    assert "returned to the scorched plains" in response
    
    # 4. Turn 2: Since player already heard it, it should NOT trigger again
    res_2 = await npc_b.process_query(player_id="p1", 
                                      query="What else?", 
                                      ml_context={"trust": 70.0})
    
    response_2 = res_2["response"].lower()
    # Should be a normal response now, not the rumor
    assert "returned to the scorched plains" not in response_2
