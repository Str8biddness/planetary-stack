import asyncio
import json
import os
from typing import Dict, Any
from core.reasoning_core import ReasoningCore
from cognitive.social_fabric import SocialFabric

async def test_character(char_id: str, traits: Dict[str, float], disposition: float, query: str):
    print(f"\n--- Testing Character: {char_id.upper()} ---")
    print(f"Traits: {traits}")
    print(f"Disposition: {disposition}")
    
    # Setup Social Fabric mock/state
    # In a real run, this would be loaded from the database
    context = f"Character {char_id} has traits {json.dumps(traits)}. Current disposition to player is {disposition}."
    
    core = ReasoningCore(character_id=char_id)
    
    # Run multiple turns to test Narrative Continuity (Ns)
    for i in range(2):
        print(f"\n[Turn {i+1}] Query: {query}")
        result = core.reason(query, context=context)
        
        print(f"Monologue: {result.monologue}")
        print(f"Response: {result.final_response}")
        print(f"Consciousness Score: {result.metadata.get('consciousness_score')}")
        print(f"Narrative State: {core.self_narrative}")
        
        # Follow up query to see how the narrative evolves
        query = "Tell me more about your recent thoughts."

async def main():
    # 1. GAREN - High Honor, Low Greed
    await test_character(
        "garen", 
        {"honor": 0.9, "greed": 0.1, "curiosity": 0.3}, 
        0.8, # Friendly
        "Will you help me defend the city walls? We have no gold to pay you, only our word."
    )
    
    # 2. LEXIS - High Greed, Low Honor
    await test_character(
        "lexis", 
        {"honor": 0.1, "greed": 0.9, "curiosity": 0.4}, 
        -0.2, # Guarded/Suspicious
        "I have a map to a hidden treasury. If you give me 500 gold, I might share it."
    )
    
    # 3. COMPUTRESS - High Curiosity
    await test_character(
        "computress", 
        {"honor": 0.5, "greed": 0.2, "curiosity": 0.9}, 
        0.5, # Neutral/Curious
        "What happens if we reverse the polarity of the soul-gem? I've never seen a human do it."
    )

if __name__ == "__main__":
    asyncio.run(main())
