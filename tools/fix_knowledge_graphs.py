import json
import os
from pathlib import Path

def get_base_dir():
    return Path(__file__).parent.parent / "characters"

def fix_types_and_add_missing(char_id, kg_data):
    # Valid types: person, place, item, faction, event, concept
    entities = kg_data.get("entities", {})
    
    # Track missing references we need to add
    missing_refs = set()
    
    for eid, e_data in entities.items():
        # Fix types
        old_type = e_data.get("entity_type")
        if old_type == "organization":
            e_data["entity_type"] = "faction"
        elif old_type == "technology":
            e_data["entity_type"] = "concept"
            
        # Collect missing related_entities
        for related in e_data.get("related_entities", []):
            if related not in entities:
                missing_refs.add(related)
                
    # Auto-generate missing entities as concepts
    for missing in missing_refs:
        entities[missing] = {
            "entity_type": "concept",
            "display_name": missing.replace("_", " ").title(),
            "depth": "familiar",
            "description": f"{missing.replace('_', ' ').title()} is a component of the system.",
            "relationship_to_npc": "a component I interact with",
            "related_entities": []
        }
        
    kg_data["entities"] = entities
    return kg_data

def add_cross_character_relationships(char_id, kg_data):
    # Ensure every character knows about the other main characters as "person"
    main_chars = ["synthesus", "computress", "lexis", "synth", "haven", "garen"]
    entities = kg_data.get("entities", {})
    
    for other in main_chars:
        if other != char_id and other not in entities:
            # We don't add full cross-links everywhere to keep it simple, but we add basic awareness
            entities[other] = {
                "entity_type": "person",
                "display_name": other.capitalize(),
                "depth": "acquainted",
                "description": f"{other.capitalize()} is one of the other characters in the Synthesus system.",
                "relationship_to_npc": "a fellow AI character",
                "related_entities": ["aivm"] if "aivm" in entities else []
            }
            
    kg_data["entities"] = entities
    return kg_data

def main():
    base_dir = get_base_dir()
    for entry in os.listdir(base_dir):
        char_dir = base_dir / entry
        kg_path = char_dir / "knowledge.json"
        
        if kg_path.exists():
            with open(kg_path, "r") as f:
                kg_data = json.load(f)
                
            kg_data = fix_types_and_add_missing(entry, kg_data)
            kg_data = add_cross_character_relationships(entry, kg_data)
            
            with open(kg_path, "w") as f:
                json.dump(kg_data, f, indent=2)
            
            print(f"Fixed and expanded knowledge graph for {entry}")

if __name__ == "__main__":
    main()
