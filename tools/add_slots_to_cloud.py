#!/usr/bin/env python3
"""
Auto-add slot declarations to existing Knowledge Cloud entries.
Makes 35 entries chainable by adding [entity], [topic], [emotion], [time] slots.
"""

import json
import re
from pathlib import Path

def add_slots_to_entry(entry: dict) -> dict:
    """Add appropriate slots to a knowledge entry based on its content."""

    entity_id = entry["entity_id"]
    entity_type = entry["entity_type"]
    description = entry["description"]
    tags = entry.get("tags", [])

    # Initialize slots list
    slots = []

    # [entity] slot - most entries can reference other entities
    if entity_type in ["creature", "location", "item", "person", "faction", "event"]:
        slots.append("[entity]")

    # [topic] slot - based on tags and entity type
    if any(tag in tags for tag in ["combat", "lore", "quest"]) or entity_type == "creature":
        slots.append("[topic]")
    elif any(tag in tags for tag in ["commerce", "shopping"]) or entity_type == "faction":
        slots.append("[topic]")

    # [emotion] slot - for entries that might trigger emotional responses
    if "emotion_variants" in entry or any(tag in tags for tag in ["combat", "quest", "danger"]):
        slots.append("[emotion]")

    # [time] slot - for locations/events that might be time-sensitive
    if entity_type in ["location", "event"] or "time" in description.lower():
        slots.append("[time]")

    # Special cases
    if entity_id == "dragon":
        # Dragons are perfect for chaining - can connect to combat, locations, emotions
        slots = ["[entity]", "[topic]", "[emotion]"]
        # Update description to include slots
        entry["description"] = "Dragons are ancient, fearsome reptilian creatures of immense power. Legends say they once ruled the skies over the Northern Mountains before retreating into deep caverns beneath the Frostpeak range. [entity] is a [topic] creature of great [emotion] danger."

    elif entity_id == "ironhaven":
        slots = ["[entity]", "[topic]", "[time]"]
        entry["description"] = "Ironhaven is a bustling trade city built where the Northern Road meets the Silverflow River. Home to the Merchant's Alliance and governed by Duke Aldric, it serves as the commercial heart of the region with the busiest market this side of the mountains. [entity] thrives with [topic] activity in the [time] hours."

    elif entity_id == "blackhollow":
        slots = ["[entity]", "[topic]", "[emotion]", "[time]"]
        entry["description"] = "Blackhollow is a dark, dense stretch of forest on the Northern Road about two days' ride from Ironhaven. The trees grow thick and the road narrows dangerously. Three caravans have gone missing there in recent months, and merchants speak of shadows in the treeline. [entity] fills travelers with [emotion] dread in the [time] hours."

    elif entity_id == "missing_caravans":
        slots = ["[entity]", "[topic]", "[emotion]"]
        entry["description"] = "Three merchant caravans have vanished on the Northern Road in the past two months. Two were found empty — drivers reported being robbed by something fast and invisible. The third hasn't been found at all. The Merchant's Alliance is in crisis. The [entity] mystery creates [emotion] tension in [topic] circles."

    elif entity_id == "duke_aldric":
        slots = ["[entity]", "[topic]", "[emotion]"]
        entry["description"] = "Duke Aldric rules Ironhaven and the surrounding territory. A pragmatic but increasingly strained leader, he maintains order through alliances with the Merchant's Alliance and his personal guard. Rumors suggest his coffers are thinner than he lets on. [entity] maintains [emotion] control over [topic] matters."

    elif entity_id == "northern_road":
        slots = ["[entity]", "[topic]", "[time]"]
        entry["description"] = "The Northern Road is the primary trade artery running from Ironhaven through Blackhollow and up to the mountain passes. It's been the lifeline of commerce for the Merchant's Alliance for centuries, though recent caravan disappearances have made it increasingly dangerous. [entity] carries [topic] caravans through all [time] hours."

    elif entity_id == "troll":
        slots = ["[entity]", "[topic]", "[emotion]"]
        entry["description"] = "Trolls are hulking, dim-witted creatures that dwell under bridges and in dark caves along trade routes. They're not especially dangerous alone, but a pack of them can overwhelm even experienced fighters. [entity] inspires [emotion] annoyance in [topic] encounters."

    elif entity_id == "shadow_wraith":
        slots = ["[entity]", "[topic]", "[emotion]", "[time]"]
        entry["description"] = "Shadow Wraiths are spectral entities that manifest in places of great suffering or dark magic. They drain the warmth from the living and leave a cold that seeps into the bones. Some say the missing caravans in Blackhollow were taken by wraiths. [entity] fills victims with [emotion] terror in the [time] hours."

    elif entity_id == "dire_wolf":
        slots = ["[entity]", "[topic]", "[emotion]"]
        entry["description"] = "Dire wolves are massive predators twice the size of their common cousins. They hunt in packs across the Northern Road and the forests beyond. Experienced hunters know to travel in groups when dire wolves are about. [entity] commands [emotion] respect in [topic] hunts."

    elif entity_id == "merchants_alliance":
        slots = ["[entity]", "[topic]", "[time]"]
        entry["description"] = "The Merchant's Alliance is the powerful trade guild that controls commerce across the region. They negotiate tariffs with the duke, organize caravan escorts, settle trade disputes, and maintain the trade roads. Without them, the regional economy would collapse. [entity] manages [topic] operations around the clock in [time] hours."

    elif entity_id == "silvermoor_silk":
        slots = ["[entity]", "[topic]", "[emotion]"]
        entry["description"] = "Silvermoor Silk is the finest textile in the realm — lightweight, durable, and available in colors that never fade. The enchanted varieties woven by the Weavers' Guild can resist fire, repel water, and even mend small tears on their own. [entity] brings [emotion] delight to [topic] enthusiasts."

    elif entity_id == "healing_potion":
        slots = ["[entity]", "[topic]", "[time]"]
        entry["description"] = "Healing potions are alchemical remedies that accelerate the body's natural recovery. Quality varies wildly — a good one from a trained herbalist can mend a broken bone in hours, while a cheap market potion might just cure a headache. [entity] provides [topic] relief when needed most in [time] hours."

    elif entity_id == "starfire_essence":
        slots = ["[entity]", "[topic]", "[emotion]"]
        entry["description"] = "Starfire Essence is a rare alchemical compound that glows with an ethereal inner light. Used in high-end enchantments and the creation of magical artifacts, it's worth more than its weight in gold. [entity] inspires [emotion] awe among [topic] practitioners."

    elif entity_id == "frostbloom":
        slots = ["[entity]", "[topic]", "[emotion]"]
        entry["description"] = "Frostbloom is an extremely rare arctic flower that only blooms during the harshest winter storms. Its tincture was the cure for the devastating Winter Fever that swept the region five years ago. [entity] brought [emotion] hope during the [topic] crisis."

    elif entity_id == "winter_fever":
        slots = ["[entity]", "[topic]", "[emotion]", "[time]"]
        entry["description"] = "A devastating plague that swept through the region five years ago during an unusually harsh winter. It claimed hundreds of lives including many prominent citizens. The herbalists eventually developed a cure from frostbloom flowers. The [entity] created [emotion] despair in [topic] communities [time] ago."

    elif entity_id == "enchantment":
        slots = ["[entity]", "[topic]", "[emotion]"]
        entry["description"] = "The magical art of imbuing objects with supernatural properties. Practiced by trained enchanters using specialized reagents, it ranges from simple glow-charms to complex battle enchantments that can turn the tide of war. [entity] inspires [emotion] wonder among [topic] students."

    elif entity_id == "haggling":
        slots = ["[entity]", "[topic]", "[time]"]
        entry["description"] = "The art of negotiation over prices — an essential skill in any marketplace. Experienced merchants know that the posted price is merely a starting point. Relationship, timing, and charm all factor into the final deal. [entity] is crucial in [topic] dealings, especially at [time] close."

    elif entity_id == "trade_routes":
        slots = ["[entity]", "[topic]", "[time]"]
        entry["description"] = "The network of roads and paths connecting the major cities and towns of the region. The Northern Road is the primary artery, but secondary routes connect Redstone, the coastal towns, and the mountain settlements. Trade routes are the lifeblood of the economy. [entity] facilitate [topic] movement in all [time] hours."

    elif entity_id == "guild_law":
        slots = ["[entity]", "[topic]", "[time]"]
        entry["description"] = "The body of rules and regulations governing commerce, guild membership, and trade disputes in the region. Enforced by the Merchant's Alliance with the backing of ducal authority, it covers everything from tariffs to quality standards. [entity] governs [topic] practices year-round in [time] hours."

    # Add slots to entry
    if slots:
        entry["slots"] = slots

    return entry

def main():
    """Process the world_lore.json file to add slots to all entries."""
    data_dir = Path("data/knowledge_cloud")
    world_lore_path = data_dir / "world_lore.json"

    if not world_lore_path.exists():
        print("❌ world_lore.json not found")
        return

    # Load existing data
    with open(world_lore_path, 'r', encoding='utf-8') as f:
        data = json.load(f)

    # Process each entry
    updated_entries = []
    entries_with_slots = 0

    for entry in data.get("entries", []):
        updated_entry = add_slots_to_entry(entry.copy())
        updated_entries.append(updated_entry)

        if "slots" in updated_entry:
            entries_with_slots += 1

    # Save back
    data["entries"] = updated_entries

    with open(world_lore_path, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

    print(f"✅ Added slots to {entries_with_slots}/{len(updated_entries)} entries")
    print("📁 Updated data/knowledge_cloud/world_lore.json")

if __name__ == "__main__":
    main()
