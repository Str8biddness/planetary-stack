#!/usr/bin/env python3
"""
Lore Forge — Synthetic Narrative Grounding Generator
Synthesus 2.0

Generates high-fidelity, structured lore nodes for the Knowledge Cloud.
Uses SlotFiller tags ([entity], [time], [emotion], etc.) to enable
deterministic synthesis by the CognitiveEngine.
"""

import json
import logging
import sys
from pathlib import Path
from typing import List, Dict, Any

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from core.knowledge_cloud import KnowledgeCloud, KnowledgeEntry

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

def generate_synthetic_lore() -> List[KnowledgeEntry]:
    """Define the synthetic lore nodes."""
    entries = []

    # 1. Factions
    entries.append(KnowledgeEntry(
        entity_id="ironhaven_watch",
        entity="The Ironhaven Watch",
        entity_type="faction",
        description="The Ironhaven Watch is the city's primary law enforcement body. Founded by Duke Aldric's father, they maintain [entity] order across all [time] shifts. Most citizens feel [emotion] safety when they see the blue-cloaked guards.",
        facts=[
            "Headquartered in the North Tower",
            "Commanded by Captain Valerius",
            "Recently increased patrols near the market due to smuggling rumors",
            "Standard equipment includes silver-etched spears and heavy shields"
        ],
        relations={
            "serves": "Duke Aldric",
            "monitors": "Ironhaven Market",
            "rivals": "Shadow Syndicate"
        },
        tags=["world_info", "faction", "law_enforcement"],
        depth="familiar",
        slots=["[entity]", "[time]", "[emotion]"]
    ))

    # 2. Historical Events
    entries.append(KnowledgeEntry(
        entity_id="the_great_flood",
        entity="The Great Flood of '84",
        entity_type="event",
        description="The Great Flood occurred when the Silverflow River breached the southern walls. It was a [time] of [emotion] loss for the city. [entity] still bears the watermarks on the lower docks.",
        facts=[
            "Destroyed over 200 homes in the Low District",
            "Led to the construction of the Silverflow Levees",
            "The Merchant's Alliance funded the rebuilding effort",
            "Many ancient records were lost to the water"
        ],
        relations={
            "affected": "Ironhaven",
            "caused_by": "Silverflow River",
            "led_to": "Silverflow Levees"
        },
        tags=["history", "event", "ironhaven"],
        depth="acquainted",
        slots=["[time]", "[emotion]", "[entity]"]
    ))

    # 3. Key Locations
    entries.append(KnowledgeEntry(
        entity_id="scorched_plains",
        entity="The Scorched Plains",
        entity_type="location",
        description="The Scorched Plains are a desolate expanse east of the mountains. Legend says they were created by dragon fire during the [time] wars. Travelers report [emotion] sightings of [entity] in the heat haze.",
        facts=[
            "Ground is covered in black, glass-like obsidian",
            "No rain has fallen here for three centuries",
            "Home to fire-resistant flora like Cinderbrush",
            "Rumored to contain the ruins of the First City"
        ],
        relations={
            "east_of": "Frostpeak range",
            "contains": "Cinderbrush",
            "site_of": "First City ruins"
        },
        tags=["world_info", "location", "danger"],
        depth="rumor",
        slots=["[time]", "[emotion]", "[entity]"]
    ))
    
    # 4. Narrative Lineage
    entries.append(KnowledgeEntry(
        entity_id="house_aldric",
        entity="House Aldric",
        entity_type="faction",
        description="House Aldric has ruled Ironhaven for five generations. Their [time] lineage is defined by [emotion] devotion to [entity] prosperity. Duke Aldric is the current patriarch.",
        facts=[
            "Sigil is a silver hawk over an iron anvil",
            "Motto: 'Strength in Stability'",
            "Holds extensive land rights along the Northern Road",
            "Known for supporting the Merchant's Alliance"
        ],
        relations={
            "patriarch": "Duke Aldric",
            "rules": "Ironhaven",
            "allied_with": "Merchant's Alliance"
        },
        tags=["world_info", "faction", "politics"],
        depth="familiar",
        slots=["[time]", "[emotion]", "[entity]"]
    ))

    # 5. Add more depth...
    entries.append(KnowledgeEntry(
        entity_id="shadow_syndicate",
        entity="The Shadow Syndicate",
        entity_type="faction",
        description="The Shadow Syndicate is a rumored criminal organization operating in the back alleys of Ironhaven. They deal in [entity] and thrive during the [time] hours. Most merchants feel [emotion] dread when they see the black-sealed letters.",
        facts=[
            "Operates out of the Low District cellars",
            "Controlled by the 'Masked Hand'",
            "Maintains a web of informants across the Silverflow River",
            "Known for high-stakes smuggling and information brokering"
        ],
        relations={
            "rivals": "Ironhaven Watch",
            "extorts": "Small-scale traders",
            "headquarters": "Low District"
        },
        tags=["world_info", "faction", "criminal"],
        depth="rumor",
        slots=["[entity]", "[time]", "[emotion]"]
    ))

    # 6. Geography
    entries.append(KnowledgeEntry(
        entity_id="silverflow_river",
        entity="Silverflow River",
        entity_type="location",
        description="The Silverflow River is the lifeline of Ironhaven, providing water and transport for the [entity]. It flows with [emotion] strength during the [time] thaw.",
        facts=[
            "Source is high in the Frostpeak range",
            "Fed by dozens of mountain springs",
            "Carries trade barges from the northern territories",
            "The Silverflow Bridge is the only stone crossing for 50 miles"
        ],
        relations={
            "source": "Frostpeak range",
            "crosses": "Ironhaven",
            "lifeline_of": "The Merchant's Alliance"
        },
        tags=["world_info", "location", "geography"],
        depth="familiar",
        slots=["[entity]", "[emotion]", "[time]"]
    ))

    # 7. More Factions
    entries.append(KnowledgeEntry(
        entity_id="weavers_guild",
        entity="Silvermoor Weavers' Guild",
        entity_type="faction",
        description="The Weavers' Guild produces the world-renowned enchanted silk. Their [time] workshops are places of [emotion] focus for [entity] apprentices.",
        facts=[
            "Master weavers use moon-silver needles",
            "Trademark blue dye is made from crushed azure-beetles",
            "Only 12 apprentices are accepted each year",
            "Located in the High District of Silvermoor"
        ],
        relations={
            "based_in": "Silvermoor",
            "produces": "Silvermoor Silk",
            "monopolizes": "Azure Dye"
        },
        tags=["world_info", "faction", "commerce"],
        depth="familiar",
        slots=["[time]", "[emotion]", "[entity]"]
    ))

    # 8. Creatures
    entries.append(KnowledgeEntry(
        entity_id="frost_drake",
        entity="Frost Drake",
        entity_type="creature",
        description="Frost Drakes are smaller cousins of true dragons. They hunt in the [time] fog of the mountains. [entity] inspires [emotion] caution in travelers.",
        facts=[
            "Breathes a cone of sub-zero mist",
            "Scales are hard as diamonds",
            "Lacks the intelligence of a true dragon",
            "Primarily feeds on mountain goats"
        ],
        relations={
            "related_to": "Dragon",
            "hunts_in": "Frostpeak Pass",
            "preys_on": "Mountain Goats"
        },
        tags=["creature", "danger", "lore"],
        depth="acquainted",
        slots=["[time]", "[entity]", "[emotion]"]
    ))

    # 9. Key Personalities
    entries.append(KnowledgeEntry(
        entity_id="captain_valerius",
        entity="Captain Valerius",
        entity_type="person",
        description="Valerius is the stern commander of the Ironhaven Watch. His [time] rounds are a source of [emotion] stability for the [entity].",
        facts=[
            "A veteran of the Border Wars",
            "Known for carrying a scorched shield from a dragon encounter",
            "Strict adherent to Guild Law",
            "Resides in the North Tower barracks"
        ],
        relations={
            "commands": "Ironhaven Watch",
            "loyal_to": "Duke Aldric",
            "enemy_of": "Shadow Syndicate"
        },
        tags=["person", "ironhaven", "military"],
        depth="familiar",
        slots=["[time]", "[emotion]", "[entity]"]
    ))

    # 11. Locations
    entries.append(KnowledgeEntry(
        entity_id="frostpeak_range",
        entity="Frostpeak Range",
        entity_type="location",
        description="The Frostpeak Range forms the northern border of the region. Its [time] peaks are a source of [emotion] awe for the [entity].",
        facts=[
            "Home to several dormant volcanoes",
            "Glaciers here never melt, even in summer",
            "Contains the only known deposits of moon-silver",
            "The air is so thin that only drakes can fly comfortably"
        ],
        relations={
            "border_of": "The Northern Territories",
            "contains": "Moon-silver deposits",
            "home_of": "Frost Drakes"
        },
        tags=["location", "geography", "lore"],
        depth="familiar",
        slots=["[time]", "[emotion]", "[entity]"]
    ))

    # 12. More Personalities
    entries.append(KnowledgeEntry(
        entity_id="duke_aldric_father",
        entity="Duke Valerius I",
        entity_type="person",
        description="The father of the current Duke, known for founding the Ironhaven Watch. His [time] legacy is one of [emotion] discipline for the [entity].",
        facts=[
            "Ended the Great Smuggling Wars",
            "Commissioned the Silverflow Bridge",
            "Known as the 'Iron Duke'",
            "Died during the Great Flood of '84"
        ],
        relations={
            "father_of": "Duke Aldric",
            "founder_of": "Ironhaven Watch",
            "hero_of": "Ironhaven"
        },
        tags=["person", "history", "ironhaven"],
        depth="familiar",
        slots=["[time]", "[emotion]", "[entity]"]
    ))

    # 14. More Events
    entries.append(KnowledgeEntry(
        entity_id="treaty_of_silvermoor",
        entity="Treaty of Silvermoor",
        entity_type="event",
        description="This treaty ended the decades-long trade war. It was a [time] of [emotion] relief for the [entity] kingdoms.",
        facts=[
            "Signed in the High District of Silvermoor",
            "Established the current tariff rates for the Merchant's Alliance",
            "Brokered by Duke Valerius I",
            "Signed exactly 25 years before the Great Flood"
        ],
        relations={
            "ended": "Great Smuggling Wars",
            "brokered_by": "Duke Valerius I",
            "affects": "Merchant's Alliance"
        },
        tags=["history", "event", "politics"],
        depth="familiar",
        slots=["[time]", "[emotion]", "[entity]"]
    ))

    # 16. Trade Goods
    entries.append(KnowledgeEntry(
        entity_id="azure_beetle",
        entity="Azure Beetle",
        entity_type="creature",
        description="A small, glowing beetle found in the Silvermoor wetlands. Its [time] harvest is a source of [emotion] wealth for [entity] trappers.",
        facts=[
            "Primary source of the Silvermoor blue dye",
            "Exoskeleton glows with a soft cyan light",
            "Feeds exclusively on moonpetal pollen",
            "Population has declined since the Great Flood"
        ],
        relations={
            "found_in": "Silvermoor Wetlands",
            "source_of": "Azure Dye",
            "preyed_on_by": "Frost Drakes"
        },
        tags=["creature", "commerce", "silvermoor"],
        depth="familiar",
        slots=["[time]", "[emotion]", "[entity]"]
    ))

    # 17. Landmarks
    entries.append(KnowledgeEntry(
        entity_id="north_tower",
        entity="The North Tower",
        entity_type="location",
        description="The North Tower is the tallest structure in Ironhaven and HQ of the Watch. Its [time] beacon provides [emotion] guidance for [entity] travelers.",
        facts=[
            "Houses the Captain's office and barracks",
            "The ground floor contains the city's main armory",
            "Built during the reign of Duke Valerius I",
            "Overlooks the entire Silverflow Bridge"
        ],
        relations={
            "hq_of": "Ironhaven Watch",
            "overlooks": "Silverflow Bridge",
            "built_by": "Duke Valerius I"
        },
        tags=["location", "ironhaven", "military"],
        depth="intimate",
        slots=["[time]", "[emotion]", "[entity]"]
    ))

    # 18. Historical Figures
    entries.append(KnowledgeEntry(
        entity_id="masked_hand",
        entity="The Masked Hand",
        entity_type="person",
        description="The elusive leader of the Shadow Syndicate. Their [time] influence is a source of [emotion] concern for [entity] authorities.",
        facts=[
            "Identity is a closely guarded secret",
            "Rumored to be a disgraced former Watch officer",
            "Controls all black-market trade in the Low District",
            "Always leaves a black-sealed letter at the scene"
        ],
        relations={
            "leads": "Shadow Syndicate",
            "rival_of": "Captain Valerius",
            "operates_in": "Low District"
        },
        tags=["person", "criminal", "mystery"],
        depth="rumor",
        slots=["[time]", "[emotion]", "[entity]"]
    ))

    # 20. Trade Routes
    entries.append(KnowledgeEntry(
        entity_id="silverflow_bridge",
        entity="The Silverflow Bridge",
        entity_type="location",
        description="The only stone bridge crossing the Silverflow for 50 miles. Its [time] traffic is a source of [emotion] wealth for [entity] tax collectors.",
        facts=[
            "Commissioned by Duke Valerius I",
            "Survived the Great Flood of '84 with minor damage",
            "Constructed from granite quarried in the Frostpeak",
            "Guarded 24/7 by a detachment of the Ironhaven Watch"
        ],
        relations={
            "crosses": "Silverflow River",
            "commissioned_by": "Duke Valerius I",
            "guarded_by": "Ironhaven Watch"
        },
        tags=["location", "ironhaven", "commerce"],
        depth="familiar",
        slots=["[time]", "[emotion]", "[entity]"]
    ))

    # 21. Alchemy
    entries.append(KnowledgeEntry(
        entity_id="mana_crystal",
        entity="Crystallized Mana",
        entity_type="item",
        description="Solidified magical energy found in high-mana zones. Its [time] glow is a source of [emotion] power for [entity] enchanters.",
        facts=[
            "Primarily sourced from the heart of the Scorched Plains",
            "Must be handled with lead-lined gloves",
            "Used to power heavy-duty enchantments",
            "Highly explosive if exposed to open flame"
        ],
        relations={
            "found_in": "Scorched Plains",
            "used_by": "Enchanters",
            "related_to": "Obsidian Blade"
        },
        tags=["item", "magic", "danger"],
        depth="acquainted",
        slots=["[time]", "[emotion]", "[entity]"]
    ))

    # 22. Factions (Criminal)
    entries.append(KnowledgeEntry(
        entity_id="low_district",
        entity="The Low District",
        entity_type="location",
        description="The poorest area of Ironhaven, built on the river's edge. Its [time] streets are a source of [emotion] danger for [entity] residents.",
        facts=[
            "Almost entirely submerged during the Great Flood",
            "Headquarters of the Shadow Syndicate",
            "Known for its floating markets and narrow alleys",
            "Constantly monitored by Watch patrols"
        ],
        relations={
            "part_of": "Ironhaven",
            "home_of": "Shadow Syndicate",
            "affected_by": "Great Flood"
        },
        tags=["location", "ironhaven", "criminal"],
        depth="familiar",
        slots=["[time]", "[emotion]", "[entity]"]
    ))

    return entries

def generate_transitions() -> Dict[str, Any]:
    """Generate the transition graph for the SequenceLinker."""
    return {
        "transitions": {
            "cloud_ironhaven": {
                "cloud_ironhaven_watch": {"weight": 0.8, "context_buckets": ["law_enforcement", "general"]},
                "cloud_house_aldric": {"weight": 0.9, "context_buckets": ["politics", "general"]},
                "cloud_the_great_flood": {"weight": 0.7, "context_buckets": ["history", "narrative"]},
                "cloud_silverflow_river": {"weight": 0.8, "context_buckets": ["geography", "general"]},
                "cloud_merchants_alliance": {"weight": 0.9, "context_buckets": ["commerce", "general"]},
                "cloud_north_tower": {"weight": 0.7, "context_buckets": ["location", "general"]},
                "cloud_low_district": {"weight": 0.6, "context_buckets": ["location", "criminal"]}
            },
            "cloud_house_aldric": {
                "cloud_ironhaven_watch": {"weight": 0.7, "context_buckets": ["law_enforcement", "general"]},
                "cloud_ironhaven": {"weight": 0.8, "context_buckets": ["general"]},
                "cloud_captain_valerius": {"weight": 0.6, "context_buckets": ["politics", "social"]},
                "cloud_duke_aldric_father": {"weight": 0.9, "context_buckets": ["history", "politics"]}
            },
            "cloud_ironhaven_watch": {
                "cloud_shadow_syndicate": {"weight": 0.9, "context_buckets": ["criminal", "tense"]},
                "cloud_ironhaven": {"weight": 0.7, "context_buckets": ["general"]},
                "cloud_captain_valerius": {"weight": 0.9, "context_buckets": ["law_enforcement", "general"]},
                "cloud_north_tower": {"weight": 0.8, "context_buckets": ["location", "military"]},
                "cloud_silverflow_bridge": {"weight": 0.7, "context_buckets": ["location", "commerce"]}
            },
            "cloud_scorched_plains": {
                "cloud_dragon": {"weight": 0.9, "context_buckets": ["lore", "danger"]},
                "cloud_obsidian_blade": {"weight": 0.8, "context_buckets": ["combat", "lore"]},
                "cloud_the_first_city": {"weight": 0.9, "context_buckets": ["history", "mystery"]},
                "cloud_mana_crystal": {"weight": 0.8, "context_buckets": ["magic", "lore"]}
            },
            "cloud_silverflow_river": {
                "cloud_the_great_flood": {"weight": 0.9, "context_buckets": ["history", "narrative"]},
                "cloud_ironhaven": {"weight": 0.7, "context_buckets": ["geography", "general"]},
                "cloud_silverflow_bridge": {"weight": 0.8, "context_buckets": ["location", "geography"]}
            },
            "cloud_dragon": {
                "cloud_frost_drake": {"weight": 0.8, "context_buckets": ["lore", "danger"]},
                "cloud_scorched_plains": {"weight": 0.7, "context_buckets": ["lore"]}
            },
            "cloud_moonpetal": {
                "cloud_healing_potion": {"weight": 0.8, "context_buckets": ["alchemy"]},
                "cloud_azure_beetle": {"weight": 0.7, "context_buckets": ["commerce", "creature"]},
                "cloud_moonpetal_tea": {"weight": 0.9, "context_buckets": ["alchemy", "social"]}
            },
            "cloud_frostpeak_range": {
                "cloud_frost_drake": {"weight": 0.9, "context_buckets": ["danger", "geography"]},
                "cloud_silverflow_river": {"weight": 0.7, "context_buckets": ["geography"]},
                "cloud_mana_crystal": {"weight": 0.6, "context_buckets": ["magic"]}
            },
            "cloud_merchants_alliance": {
                "cloud_treaty_of_silvermoor": {"weight": 0.8, "context_buckets": ["history", "politics"]},
                "cloud_ironhaven": {"weight": 0.7, "context_buckets": ["commerce"]},
                "cloud_azure_beetle": {"weight": 0.8, "context_buckets": ["commerce"]},
                "cloud_silverflow_bridge": {"weight": 0.9, "context_buckets": ["commerce"]}
            },
            "cloud_captain_valerius": {
                "cloud_border_wars": {"weight": 0.9, "context_buckets": ["history", "military"]},
                "cloud_ironhaven_watch": {"weight": 0.8, "context_buckets": ["law_enforcement"]}
            }
        },
        "metadata": {
            "version": "LoreForge-1.5",
            "description": "Stable multi-layered transitions",
            "num_edges": 45
        }
    }


def main():
    repo_root = Path(__file__).parent.parent
    data_dir = repo_root / "data" / "knowledge_cloud"
    
    cloud = KnowledgeCloud(data_dir=str(data_dir))
    
    logger.info(f"Lore Forge: Generating synthetic lore for {data_dir}...")
    
    entries = generate_synthetic_lore()
    
    count = 0
    for entry in entries:
        cloud.upsert_entry(entry, persist=True)
        logger.info(f"  Upserted: {entry.entity_id} ({entry.entity})")
        count += 1
        
    logger.info(f"Lore Forge: Successfully integrated {count} synthetic lore nodes.")
    
    # Generate and save transitions
    transitions = generate_transitions()
    transitions_path = data_dir / "transitions.json"
    with open(transitions_path, "w", encoding="utf-8") as f:
        json.dump(transitions, f, indent=2, ensure_ascii=False)
    logger.info(f"Lore Forge: Saved transitions to {transitions_path}")
    
    # Force rebuild index to ensure semantic search picks them up
    cloud.rebuild_index()
    logger.info("Knowledge Cloud index rebuilt.")

if __name__ == "__main__":
    main()
