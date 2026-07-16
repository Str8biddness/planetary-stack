"""
Game Master Domain Adapter

This adapter routes queries in the Game Master domain. It maintains a 
WorldSimulator instance for the session, manages world state ticks, and 
routes player input to either the Narrator or specific NPCs present in the scene.
"""
import logging
from typing import Any, Callable, Dict, List, Optional
import time

from world.coordinator import WorldSimulator
from cognitive.cognitive_engine import CognitiveEngine

logger = logging.getLogger(__name__)

class GameMasterAdapter:
    def __init__(
        self, 
        session_id: str, 
        engine_factory: Callable[[str], Optional[CognitiveEngine]],
        narrator_id: str = "narrator"
    ):
        self.session_id = session_id
        self.engine_factory = engine_factory
        self.narrator_id = narrator_id
        
        # Initialize a dedicated world simulator for this session
        logger.info(f"Initializing World Simulator for GM session: {session_id}")
        self.world = WorldSimulator.create_fantasy_world(seed=hash(session_id) % 10000)
        
        # Keep track of the player's current region
        self.current_region = "riverside"

    async def process_query(self, query_text: str, player_id: str, ml_context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Process a query within the Game Master domain."""
        t0 = time.time()
        
        # 1. Advance the world simulation
        # In a real game, we might only tick if time passes, but for simplicity, 
        # we tick on every major action or use a probability.
        world_summary = self.world.tick()
        
        # 2. Extract world context for the current region
        region_summary = self.world.get_region_summary(self.current_region)
        world_context_str = self._format_world_context(region_summary)
        
        # 3. Detect if the player is talking to a specific NPC
        target_npc_id = self._detect_target_npc(query_text, region_summary)
        
        responder_id = target_npc_id if target_npc_id else self.narrator_id
        engine = self.engine_factory(responder_id)
        
        if not engine:
            return {
                "response": f"[System] The character '{responder_id}' is unavailable.",
                "confidence": 0.0,
                "source": "gm_adapter",
                "character": responder_id
            }

        # Inject world context into ml_context so the CognitiveEngine can use it
        if ml_context is None:
            ml_context = {}
        ml_context["world_state"] = world_context_str

        # 4. Route to Cognitive Engine
        result = await engine.process_query(
            player_id=player_id,
            query=f"[World Context: {world_context_str}]\nPlayer Action: {query_text}",
            thinking_layer_available=True,
            ml_context=ml_context
        )

        latency = (time.time() - t0) * 1000
        
        return {
            "response": result.get("response", ""),
            "confidence": result.get("confidence", 0.8),
            "source": f"gm_adapter_{responder_id}",
            "character": responder_id,
            "latency_ms": latency,
            "emotion": result.get("emotion"),
            "debug": {
                "world_tick": world_summary["tick"],
                "region": self.current_region,
                "world_context": world_context_str
            }
        }

    def _format_world_context(self, region_summary: Dict[str, Any]) -> str:
        """Format the region summary into a prompt-friendly string."""
        context_parts = []
        
        if "weather" in region_summary:
            w = region_summary["weather"]
            context_parts.append(f"Weather: {w.get('condition', 'clear')}, Temp: {w.get('temperature', 20)}C")
            
        if "npcs_present" in region_summary:
            npcs = region_summary["npcs_present"]
            if npcs:
                context_parts.append(f"NPCs present: {', '.join(npcs)}")
            else:
                context_parts.append("You are alone here.")
                
        time_str = f"Day {self.world.current_day}, Hour {self.world.current_hour}:00"
        context_parts.insert(0, f"Time: {time_str}")
        
        return " | ".join(context_parts)

    def _detect_target_npc(self, query_text: str, region_summary: Dict[str, Any]) -> Optional[str]:
        """Simple heuristic to detect if the player is addressing a specific NPC."""
        query_lower = query_text.lower()
        
        # Check if any present NPC's name is in the query
        present_npcs = region_summary.get("npcs_present", [])
        for npc in present_npcs:
            if npc.lower() in query_lower:
                return npc.lower()
                
        return None
