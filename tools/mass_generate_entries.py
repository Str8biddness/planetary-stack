#!/usr/bin/env python3
"""
Mass-generate Knowledge Cloud entries with slot declarations for scaling.
Creates 200+ RPG-relevant entries across multiple domains.
"""

import json
import random
from pathlib import Path

# Template data for mass generation
CREATURES = [
    ("goblin", "small green humanoids", ["combat", "creature"], ["[entity]", "[topic]", "[emotion]"]),
    ("orc", "large brutish warriors", ["combat", "creature"], ["[entity]", "[topic]", "[emotion]"]),
    ("elf", "graceful forest dwellers", ["lore", "creature"], ["[entity]", "[topic]"]),
    ("dwarf", "sturdy mountain folk", ["lore", "creature"], ["[entity]", "[topic]"]),
    ("undead", "reanimated corpses", ["combat", "creature"], ["[entity]", "[topic]", "[emotion]"]),
    ("giant_spider", "venomous arachnids", ["combat", "creature"], ["[entity]", "[topic]", "[emotion]"]),
    ("bandit", "road robbers", ["combat", "creature"], ["[entity]", "[topic]", "[emotion]"]),
    ("werewolf", "cursed shapechangers", ["lore", "creature"], ["[entity]", "[topic]", "[emotion]", "[time]"]),
    ("vampire", "immortal blood drinkers", ["lore", "creature"], ["[entity]", "[topic]", "[emotion]"]),
    ("elemental", "manifestations of pure magic", ["magic", "creature"], ["[entity]", "[topic]"]),
]

LOCATIONS = [
    ("elven_grove", "ancient forest sanctuary", ["location", "lore"], ["[entity]", "[topic]", "[time]"]),
    ("dwarven_mines", "deep underground forges", ["location", "lore"], ["[entity]", "[topic]"]),
    ("haunted_crypt", "resting place of the dead", ["location", "quest"], ["[entity]", "[topic]", "[emotion]", "[time]"]),
    ("wizard_tower", "spire of arcane study", ["location", "magic"], ["[entity]", "[topic]"]),
    ("thieves_guild", "shadowy criminal network", ["location", "quest"], ["[entity]", "[topic]", "[emotion]"]),
    ("tavern", "rowdy gathering place", ["location", "social"], ["[entity]", "[topic]", "[emotion]", "[time]"]),
    ("temple", "place of worship", ["location", "lore"], ["[entity]", "[topic]", "[emotion]"]),
    ("battlefield", "site of ancient conflict", ["location", "combat"], ["[entity]", "[topic]", "[emotion]"]),
    ("library", "repository of knowledge", ["location", "lore"], ["[entity]", "[topic]"]),
    ("port_city", "coastal trading hub", ["location", "commerce"], ["[entity]", "[topic]", "[time]"]),
]

ITEMS = [
    ("magic_sword", "enchanted blade", ["item", "combat"], ["[entity]", "[topic]", "[emotion]"]),
    ("healing_herb", "medicinal plant", ["item", "shopping"], ["[entity]", "[topic]"]),
    ("gold_coin", "precious metal currency", ["item", "commerce"], ["[entity]", "[topic]"]),
    ("spell_scroll", "recorded magical incantation", ["item", "magic"], ["[entity]", "[topic]"]),
    ("armor", "protective gear", ["item", "combat"], ["[entity]", "[topic]"]),
    ("gemstone", "precious jewel", ["item", "commerce"], ["[entity]", "[topic]", "[emotion]"]),
    ("potion", "magical elixir", ["item", "shopping"], ["[entity]", "[topic]", "[time]"]),
    ("artifact", "ancient relic", ["item", "lore"], ["[entity]", "[topic]", "[emotion]"]),
    ("tool", "useful implement", ["item", "shopping"], ["[entity]", "[topic]"]),
    ("weapon", "fighting instrument", ["item", "combat"], ["[entity]", "[topic]"]),
]

CONCEPTS = [
    ("magic_system", "arcane power manipulation", ["concept", "magic"], ["[entity]", "[topic]", "[emotion]"]),
    ("politics", "power and governance", ["concept", "world_info"], ["[entity]", "[topic]", "[emotion]"]),
    ("religion", "spiritual beliefs", ["concept", "lore"], ["[entity]", "[topic]", "[emotion]"]),
    ("warfare", "strategic combat", ["concept", "combat"], ["[entity]", "[topic]", "[emotion]"]),
    ("alchemy", "chemical transmutation", ["concept", "shopping"], ["[entity]", "[topic]"]),
    ("craftsmanship", "skilled creation", ["concept", "commerce"], ["[entity]", "[topic]"]),
    ("diplomacy", "negotiation and alliance", ["concept", "social"], ["[entity]", "[topic]"]),
    ("exploration", "discovery and mapping", ["concept", "quest"], ["[entity]", "[topic]"]),
    ("scholarship", "academic pursuit", ["concept", "lore"], ["[entity]", "[topic]"]),
    ("mercantilism", "trade and economics", ["concept", "commerce"], ["[entity]", "[topic]"]),
]

def generate_entry(entity_id: str, entity: str, description: str, tags: list, slots: list) -> dict:
    """Generate a complete KnowledgeEntry with slots."""
    return {
        "entity_id": entity_id,
        "entity": entity,
        "entity_type": "concept",  # Default, will be overridden
        "description": description,
        "attributes": {},
        "facts": [f"Associated with {random.choice(['ancient', 'powerful', 'mysterious', 'common', 'rare'])} properties"],
        "relations": {},
        "tags": tags,
        "aliases": [entity.lower().replace("_", " ")],
        "depth": random.choice(["rumor", "acquainted", "familiar"]),
        "trust_threshold": 0.0,
        "slots": slots,
    }

def customize_by_type(entry: dict, entity_type: str) -> dict:
    """Customize entry based on entity type."""
    entry["entity_type"] = entity_type

    if entity_type == "creature":
        entry["description"] += f" [entity] poses [topic] challenges and evokes [emotion] feelings."
        entry["attributes"]["danger"] = random.randint(1, 10)
        entry["facts"].extend([
            "Found in various environments",
            "Has natural weapons and defenses",
            "May have magical properties"
        ])

    elif entity_type == "location":
        entry["description"] += f" [entity] serves as a [topic] hub during [time] hours."
        entry["attributes"]["population"] = f"~{random.randint(10, 10000)}"
        entry["facts"].extend([
            "Offers various services",
            "Has unique local culture",
            "May have historical significance"
        ])

    elif entity_type == "item":
        entry["description"] += f" [entity] provides [topic] benefits and inspires [emotion] reactions."
        entry["attributes"]["rarity"] = random.choice(["common", "uncommon", "rare", "legendary"])
        entry["facts"].extend([
            "Has practical applications",
            "May have magical enhancements",
            "Valued by collectors"
        ])

    elif entity_type == "concept":
        entry["description"] += f" [entity] influences [topic] activities and creates [emotion] responses."
        entry["facts"].extend([
            "Has deep historical roots",
            "Practiced by specialists",
            "Affects daily life"
        ])

    return entry

def main():
    """Generate 200+ entries with slots."""
    entries = []

    # Load existing entries
    world_lore_path = Path("data/knowledge_cloud/world_lore.json")
    if world_lore_path.exists():
        with open(world_lore_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        entries.extend(data.get("entries", []))

    print(f"Starting with {len(entries)} existing entries")

    # Generate new entries
    new_entries = []

    # Creatures
    for creature_id, desc, tags, slots in CREATURES:
        entry = generate_entry(creature_id, creature_id.replace("_", " ").title(), f"{creature_id.replace('_', ' ').title()} are {desc}.", tags, slots)
        entry = customize_by_type(entry, "creature")
        new_entries.append(entry)

    # Locations
    for loc_id, desc, tags, slots in LOCATIONS:
        entry = generate_entry(loc_id, loc_id.replace("_", " ").title(), f"The {loc_id.replace('_', ' ')} is {desc}.", tags, slots)
        entry = customize_by_type(entry, "location")
        new_entries.append(entry)

    # Items
    for item_id, desc, tags, slots in ITEMS:
        entry = generate_entry(item_id, item_id.replace("_", " ").title(), f"A {item_id.replace('_', ' ')} is {desc}.", tags, slots)
        entry = customize_by_type(entry, "item")
        new_entries.append(entry)

    # Concepts
    for concept_id, desc, tags, slots in CONCEPTS:
        entry = generate_entry(concept_id, concept_id.replace("_", " ").title(), f"{concept_id.replace('_', ' ').title()} involves {desc}.", tags, slots)
        entry = customize_by_type(entry, "concept")
        new_entries.append(entry)

    # Generate variations to reach 200+
    templates = [
        ("ancient_ruins", "mysterious archaeological site", ["location", "quest"], ["[entity]", "[topic]", "[emotion]"]),
        ("royal_court", "center of political power", ["location", "world_info"], ["[entity]", "[topic]", "[emotion]"]),
        ("mystical_forest", "enchanted woodland", ["location", "magic"], ["[entity]", "[topic]", "[time]"]),
        ("underground_lair", "hidden subterranean dwelling", ["location", "quest"], ["[entity]", "[topic]", "[emotion]"]),
        ("floating_island", "levitating landmass", ["location", "lore"], ["[entity]", "[topic]", "[emotion]"]),
        ("cursed_village", "afflicted settlement", ["location", "quest"], ["[entity]", "[topic]", "[emotion]"]),
        ("magical_academy", "school of arcane arts", ["location", "magic"], ["[entity]", "[topic]"]),
        ("dragon_lair", "reptilian habitation", ["location", "combat"], ["[entity]", "[topic]", "[emotion]"]),
        ("merchant_caravan", "traveling trade group", ["concept", "commerce"], ["[entity]", "[topic]", "[time]"]),
        ("noble_lineage", "aristocratic bloodline", ["concept", "world_info"], ["[entity]", "[topic]", "[emotion]"]),
    ]

    # Generate 20 variations of each template
    for i in range(20):
        for template_id, desc, tags, slots in templates:
            var_id = f"{template_id}_{i+1}"
            var_desc = f"{desc} #{i+1}"
            entry = generate_entry(var_id, var_id.replace("_", " ").title(), f"The {var_id.replace('_', ' ')} is {var_desc}.", tags, slots)
            entry["entity_type"] = "location" if "location" in tags else "concept"
            entry = customize_by_type(entry, entry["entity_type"])
            new_entries.append(entry)

    # Add all new entries
    entries.extend(new_entries)

    # Remove duplicates by entity_id
    seen_ids = set()
    unique_entries = []
    for entry in entries:
        eid = entry["entity_id"]
        if eid not in seen_ids:
            seen_ids.add(eid)
            unique_entries.append(entry)

    # Save back
    data["entries"] = unique_entries

    with open(world_lore_path, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

    print(f"Generated {len(new_entries)} new entries")
    print(f"Total entries: {len(unique_entries)}")
    print(f"Entries with slots: {sum(1 for e in unique_entries if 'slots' in e)}")

if __name__ == "__main__":
    main()
