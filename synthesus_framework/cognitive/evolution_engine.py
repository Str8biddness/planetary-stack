import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional, cast
try:
    from core.synthesus_master import SynthesusMaster # type: ignore
    from core.conscious_state import NarrativeEvent # type: ignore
except ImportError:
    # Fallback for different execution contexts
    import sys
    sys.path.append(str(Path(__file__).parent.parent))
    from core.synthesus_master import SynthesusMaster # type: ignore
    from core.conscious_state import NarrativeEvent # type: ignore

logger = logging.getLogger(__name__)

class CharacterEvolutionEngine:
    """
    Synthesizes conversation history and mental states into persistent character growth.
    
    This engine bridges the gap between ephemeral 'thinking' and persistent 'identity'.
    It updates bio.json and knowledge.json based on NarrativeEvents.
    """
    
    def __init__(self, characters_root: str = "characters"):
        self.root = Path(characters_root)

    async def evolve_character(self, character_id: str, master: SynthesusMaster) -> Dict[str, Any]:
        """
        Runs a 'Synthesis Session' for a character.
        Analyzes recent narrative events and updates character files.
        """
        char_dir = self.root / character_id
        if not char_dir.exists():
            return {"error": f"Character directory {char_dir} not found"}

        timeline = master.state.narrative.timeline
        if not timeline:
            return {"status": "no_history", "message": "No narrative events to synthesize."}

        # 1. Extract recent interactions (last 10 events)
        recent_events = timeline[-10:]
        
        # 2. Use the Master's abductive/inductive engines to generate a 'Synthesis Directive'
        # We simulate a 'meta-thought' queries to the master
        synthesis_query = f"Based on the last {len(recent_events)} interactions, what new knowledge or personality traits have I acquired? Format as JSON directives: {{\"add_knowledge\": [], \"update_traits\": {{}}}}"
        
        try:
            # We use the master's own thinking to evolve itself
            logger.info(f"Running synthesis for {character_id} with query: {synthesis_query}")
            result = await master.think(synthesis_query, character_id=character_id)
            logger.info(f"Synthesis result event: {result.get('event')}")
            logger.info(f"Synthesis result answer: {result.get('answer')}")
            # In a real scenario, we'd parse the 'answer' or 'explanations'.
            # For this implementation, we'll use a rule-based heuristic powered by the Master's explanations.
            
            directives = self._parse_synthesis_directives(result, recent_events)
            
            # 3. Apply updates to character files
            updates = self._apply_directives(character_id, directives)
            
            return {
                "status": "success",
                "character_id": character_id,
                "directives": directives,
                "files_updated": updates
            }
        except Exception as e:
            logger.error(f"Evolution failed for {character_id}: {e}")
            return {"error": str(e)}

    def _parse_synthesis_directives(self, think_result: Dict[str, Any], recent_events: Optional[List[Any]] = None) -> Dict[str, Any]:
        """Parse directives from master's answer, scan narrative history, or harvest high-confidence beliefs."""
        directives = {
            "add_knowledge": [],
            "update_traits": {}
        }
        
        answer = think_result.get("answer", "")
        
        # 1. Try to find JSON block in answer
        try:
            if "{" in answer and "}" in answer:
                start = answer.find("{")
                end = answer.rfind("}") + 1
                json_str = answer[start:end]
                parsed = json.loads(json_str)
                if isinstance(parsed, dict):
                    if "add_knowledge" in parsed:
                        directives["add_knowledge"].extend(parsed["add_knowledge"]) # type: ignore
                    if "update_traits" in parsed:
                        directives["update_traits"].update(parsed["update_traits"]) # type: ignore
                    if directives["add_knowledge"] or directives["update_traits"]:
                        return directives
        except Exception:
            pass

        # 2. Harvest High-Confidence Beliefs from Context
        context = think_result.get("context", {})
        beliefs = context.get("beliefs", {})
        for belief, score in beliefs.items():
            if score >= 0.7:
                insight = f"Confirmed Belief: {belief} (Confidence: {score:.2f})"
                if insight not in directives["add_knowledge"]:
                    cast(List[str], directives["add_knowledge"]).append(insight)

        # 3. Heuristic scan of the current 'think' result
        event = think_result.get("event")
        if event:
            explanations = getattr(event, "explanations", [])
            for exp in explanations:
                el = str(exp).lower()
                if any(x in el for x in ["caused by", "pattern", "because", "learned"]):
                    if str(exp) not in directives["add_knowledge"]:
                        cast(List[str], directives["add_knowledge"]).append(str(exp))

        # 4. Deep scan of recent narrative history if still thin
        if len(directives["add_knowledge"]) < 2 and recent_events:
            for ev in recent_events:
                explanations = getattr(ev, "explanations", [])
                for exp in explanations:
                    el = str(exp).lower()
                    if any(x in el for x in ["caused by", "pattern", "insight"]):
                        if str(exp) not in cast(List[str], directives["add_knowledge"]):
                            cast(List[str], directives["add_knowledge"]).append(str(exp))
        
        return directives

    def _apply_directives(self, character_id: str, directives: Dict[str, Any]) -> List[str]:
        """Write updates to knowledge.json and bio.json."""
        char_dir = self.root / character_id
        updated_files = []

        # Update Knowledge
        if directives["add_knowledge"]:
            kg_path = char_dir / "knowledge.json"
            try:
                data = {}
                if kg_path.exists():
                    with open(kg_path, 'r') as f:
                        data = json.load(f)
                
                # Add new nodes/edges (simplified for now)
                if "evolution_notes" not in data:
                    data["evolution_notes"] = [] # type: ignore
                
                notes_list = cast(List[str], data["evolution_notes"])
                add_list = cast(List[str], directives["add_knowledge"])
                for note in add_list:
                    if note not in notes_list:
                        notes_list.append(note)
                
                with open(kg_path, 'w') as f:
                    json.dump(data, f, indent=4)
                updated_files.append("knowledge.json")
            except Exception as e:
                logger.error(f"Failed to update knowledge.json: {e}")

        # Update Bio (Personality)
        if directives["update_traits"]:
            bio_path = char_dir / "bio.json"
            try:
                data = {}
                if bio_path.exists():
                    with open(bio_path, 'r') as f:
                        data = json.load(f)
                
                # Update traits
                if "traits" not in data:
                    data["traits"] = {} # type: ignore
                
                traits_dict = cast(Dict[str, Any], data["traits"])
                traits_dict.update(directives["update_traits"])
                
                with open(bio_path, 'w') as f:
                    json.dump(data, f, indent=4)
                updated_files.append("bio.json")
            except Exception as e:
                logger.error(f"Failed to update bio.json: {e}")

        return updated_files
