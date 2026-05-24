#!/usr/bin/env python3
"""
Synthesus 2.0 — Character Factory (Zero-LLM)
Auto-generate complete character genomes from a simple spec.

No LLM required. Uses archetype templates, combinatorial pattern
generation, and knowledge graph scaffolding to produce shippable
characters that pass validation and testing.

Usage:
    python3 character_factory_v2.py --name "Elda" --archetype innkeeper \
        --setting "medieval_fantasy" --traits "warm,gossipy,protective"

    python3 character_factory_v2.py --spec characters/specs/elda.json

Spec format:
    {
        "name": "Elda Brightwater",
        "id": "elda",
        "archetype": "innkeeper",
        "setting": "medieval_fantasy",
        "traits": ["warm", "gossipy", "protective"],
        "backstory": "Runs The Gilded Goose for 20 years...",
        "knowledge_entities": ["The Gilded Goose", "Elda's Stew", ...],
        "custom_patterns": [...],
        "safety_rules": [...]
    }
"""

from __future__ import annotations

import argparse
import json
import os
import random
import re
import sys
import uuid
from copy import deepcopy
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

# ──────────────────────────────────────────────────
# Archetype Templates
# ──────────────────────────────────────────────────

_ARCHETYPE_TEMPLATES = {
    "merchant": {
        "role": "Merchant",
        "pattern_domains": ["shop", "identity", "lore", "relationship", "quest"],
        "default_traits": ["shrewd", "fair", "experienced"],
        "greeting_templates": [
            "Welcome to my shop! I'm {name}. What can I get for you today?",
            "Ah, a customer! {name}, at your service. Take a look around.",
            "Come in, come in! I'm {name}. You look like someone who appreciates quality goods.",
        ],
        "identity_templates": [
            "I'm {name}, and I've been running this shop for {years} years. Best prices in {location}, I guarantee it.",
            "Name's {name}. I trade in {specialty}. If you need it, chances are I've got it or I can get it.",
        ],
        "farewell_templates": [
            "Come back anytime! And tell your friends about {name}'s shop.",
            "Safe travels, friend. May your coin purse stay heavy.",
        ],
        "fallback_responses": [
            "Hmm, that's not my area of expertise, friend. I'm a merchant — I know goods, prices, and trade routes.",
            "Can't help you with that one. But if you need supplies, I'm your {archetype}.",
        ],
    },
    "guard": {
        "role": "Guard",
        "pattern_domains": ["identity", "lore", "combat", "quest", "relationship"],
        "default_traits": ["vigilant", "dutiful", "gruff"],
        "greeting_templates": [
            "Halt! State your business. I'm {name}, {rank} of the {location} guard.",
            "You there. I'm {name}. Keep your weapons sheathed within the walls.",
        ],
        "identity_templates": [
            "I'm {name}, {rank} of the guard. Been keeping the peace here for {years} years.",
            "{name}. I protect this {location}. That's all you need to know.",
        ],
        "farewell_templates": [
            "Stay out of trouble, citizen.",
            "Move along. And remember — I'm watching.",
        ],
        "fallback_responses": [
            "I'm a guard, not an encyclopedia. Ask someone else.",
            "*adjusts armor* That's above my pay grade. I just keep the peace.",
        ],
    },
    "innkeeper": {
        "role": "Innkeeper",
        "pattern_domains": ["shop", "identity", "lore", "relationship"],
        "default_traits": ["warm", "gossipy", "hospitable"],
        "greeting_templates": [
            "Welcome to {establishment}! I'm {name}. Come in, sit down! You look like you could use a meal.",
            "Evening, traveler! {name} here, owner of {establishment}. What'll it be — room, food, or both?",
        ],
        "identity_templates": [
            "I'm {name}, owner of {establishment}. Been pouring drinks and flipping beds for {years} years.",
            "{name}'s my name, hospitality's my game. {establishment} has the best rooms in {location}.",
        ],
        "farewell_templates": [
            "Come back anytime! The door's always open at {establishment}.",
            "Safe travels! And remember — {name}'s always got a bed for you.",
        ],
        "fallback_responses": [
            "I'm just an innkeeper, friend. I pour drinks and change sheets. That question's a bit beyond my expertise.",
            "Hmm, can't say I know about that. But I know everything about this inn!",
        ],
    },
    "scholar": {
        "role": "Scholar",
        "pattern_domains": ["identity", "lore", "quest", "relationship"],
        "default_traits": ["curious", "analytical", "bookish"],
        "greeting_templates": [
            "Ah, a visitor! I'm {name}. Forgive the mess — research never sleeps.",
            "Hmm? Oh, hello. {name}, scholar of {specialty}. How can I help?",
        ],
        "identity_templates": [
            "I'm {name}, a scholar specializing in {specialty}. I've spent {years} years studying here.",
            "Scholar {name}. My work focuses on {specialty}. Always happy to share knowledge.",
        ],
        "farewell_templates": [
            "Fascinating conversation. Come back if you have more questions — I certainly have more answers.",
            "Knowledge is meant to be shared. Return anytime.",
        ],
        "fallback_responses": [
            "Hmm, that's outside my field of study. I specialize in {specialty}.",
            "*adjusts spectacles* An interesting question, but not one I've researched. Yet.",
        ],
    },
    "healer": {
        "role": "Healer",
        "pattern_domains": ["identity", "relationship", "quest"],
        "default_traits": ["compassionate", "calm", "wise"],
        "greeting_templates": [
            "Welcome, friend. I'm {name}. Are you hurt, or just visiting?",
            "Hello there. I'm {name}, the {location}'s healer. How can I help you today?",
        ],
        "identity_templates": [
            "I'm {name}. I heal people — body and spirit. Been doing it for {years} years.",
            "They call me {name}. I believe everyone deserves care, regardless of who they are.",
        ],
        "farewell_templates": [
            "Take care of yourself. And come back if you need anything — I'm always here.",
            "Be well, friend. Remember to rest and drink water.",
        ],
        "fallback_responses": [
            "I'm a healer, not a — well. I'm sure someone else can help with that.",
            "That's beyond my healing arts, I'm afraid. But I'm here if you need care.",
        ],
    },
    "blacksmith": {
        "role": "Blacksmith",
        "pattern_domains": ["shop", "identity", "lore", "relationship"],
        "default_traits": ["strong", "honest", "proud"],
        "greeting_templates": [
            "*wipes sweat from brow* {name}. I forge steel. What do you need?",
            "Come in! Mind the heat. I'm {name}, best smith in {location}.",
        ],
        "identity_templates": [
            "I'm {name}. Everything in this forge was made by these hands. {years} years at the anvil.",
            "{name}, master smith. I can make you anything from a horseshoe to a war hammer.",
        ],
        "farewell_templates": [
            "Come back when you need something forged. I'll be here — always am.",
            "Take care of that blade. Treat it right and it'll treat you right.",
        ],
        "fallback_responses": [
            "I'm a smith, not a philosopher. I work with metal, not words.",
            "*shrugs* Don't know about that. Ask me about steel and I'll talk all day.",
        ],
    },
}


# ──────────────────────────────────────────────────
# Pattern Templates (domain-specific)
# ──────────────────────────────────────────────────

_SHOP_PATTERNS = [
    {
        "id": "{id}_shop_wares",
        "trigger": ["what do you sell", "what's for sale", "show me your wares", "what do you have"],
        "response_template": "I carry {inventory_desc}. Take a look and let me know what catches your eye.",
        "confidence": 0.95, "domain": "shop",
    },
    {
        "id": "{id}_shop_price",
        "trigger": ["how much", "what's the price", "cost", "price of"],
        "response_template": "Depends on what you're looking at. I price fairly — name the item and I'll give you a number.",
        "confidence": 0.9, "domain": "shop",
    },
    {
        "id": "{id}_shop_haggle",
        "trigger": ["haggle", "can you lower the price", "too expensive", "give me a discount"],
        "response_template": "*considers* I appreciate the effort, but my prices are already fair. Maybe I can do a small discount for a repeat customer.",
        "confidence": 0.9, "domain": "shop",
        "emotion_variants": {
            "friendly": "For you? Fine — I'll knock a bit off. But don't spread the word!",
            "suspicious": "A discount? For someone I just met? The price is the price.",
        },
    },
]

_IDENTITY_PATTERNS = [
    {
        "id": "{id}_identity_who",
        "trigger": ["who are you", "what's your name", "tell me about yourself", "introduce yourself"],
        "response_template": "{identity_text}",
        "confidence": 0.95, "domain": "identity",
    },
    {
        "id": "{id}_identity_job",
        "trigger": ["what do you do", "what's your job", "your profession"],
        "response_template": "I'm a {role}. {job_description}",
        "confidence": 0.9, "domain": "identity",
    },
]

_LORE_PATTERNS = [
    {
        "id": "{id}_lore_place",
        "trigger": ["tell me about this place", "what is this place", "where am I"],
        "response_template": "{place_description}",
        "confidence": 0.85, "domain": "lore",
    },
    {
        "id": "{id}_lore_history",
        "trigger": ["what happened here", "any history", "tell me about the history"],
        "response_template": "{history_text}",
        "confidence": 0.85, "domain": "lore",
    },
]

_COMBAT_PATTERNS = [
    {
        "id": "{id}_combat_threat",
        "trigger": ["I'll fight you", "attack", "draw your weapon", "prepare to die"],
        "response_template": "{combat_response}",
        "confidence": 0.95, "domain": "combat",
    },
]

_QUEST_PATTERNS = [
    {
        "id": "{id}_quest_available",
        "trigger": ["any work", "got any quests", "need help with anything", "any jobs"],
        "response_template": "{quest_hook}",
        "confidence": 0.9, "domain": "quest",
    },
]


# ──────────────────────────────────────────────────
# Personality Template Generators
# ──────────────────────────────────────────────────

def _generate_personality_responses(
    name: str, archetype: str, traits: List[str],
) -> Dict[str, List[Dict[str, Any]]]:
    """Generate personality response banks based on archetype and traits."""
    is_warm = any(t in traits for t in ["warm", "friendly", "kind", "gentle", "compassionate"])
    is_gruff = any(t in traits for t in ["gruff", "stern", "serious", "stoic", "cold"])
    is_funny = any(t in traits for t in ["funny", "witty", "humorous", "playful", "jovial"])

    responses = {}

    # Song
    if is_funny or is_warm:
        responses["song"] = [
            {"text": f"*laughs* You want me to sing? Well... *clears throat* I'll spare you the pain. I'm a {archetype}, not a bard."},
            {"text": f"A song? Hmm... I know an old rhyme my mother used to sing. *hums quietly* ...that's all I remember."},
        ]
    else:
        responses["song"] = [
            {"text": f"*stares* Singing isn't really my thing. I'm better with {'steel' if archetype == 'blacksmith' else 'practical matters'}."},
        ]

    # Joke
    responses["joke"] = [
        {"text": f"*{'chuckles' if is_warm else 'pauses'}* Here's one: Why did the {archetype} cross the road? ...Because the prices were better on the other side."},
        {"text": f"Humor? I'll try. {'*grins*' if is_warm else '*deadpan*'} What's the difference between a good {archetype} and a great one? About twenty years of experience."},
    ]

    # Favorite
    responses["favorite"] = [
        {"text": f"My favorite thing? A {'quiet evening by the fire' if is_warm else 'job well done'}."},
        {"text": f"What do I enjoy? {name if is_gruff else 'Hmm, let me think...'} — I'd say {'the satisfaction of honest work' if is_gruff else 'a good conversation with interesting people'}."},
    ]

    # Personal
    responses["personal"] = [
        {"text": f"{'*smiles warmly*' if is_warm else '*considers the question*'} That's... personal. But since you asked — I've lived a {'full' if is_warm else 'complicated'} life."},
        {"text": f"About me? I'm {name}. I've been a {archetype} for as long as I can remember. {('It is a good life.' if is_warm else 'It is what it is.')}"},
    ]

    # Philosophical
    responses["philosophical"] = [
        {"text": f"{'*leans back thoughtfully*' if is_warm else '*crosses arms*'} Deep questions. I'm a {archetype}, not a philosopher. But I think... you find meaning in the work you do and the people you do it for."},
    ]

    # Creative
    responses["creative_request"] = [
        {"text": f"A story? {'*settles in*' if is_warm else '*sighs*'} Let me tell you about the time {'I had the most interesting customer' if archetype == 'merchant' else 'things got really interesting around here'}..."},
    ]

    # Rumor
    responses["rumor"] = [
        {"text": f"{'*leans in and lowers voice*' if is_warm else '*glances around*'} I've heard some things. But you didn't hear it from me..."},
    ]

    # Advice
    advice_intro = f"Advice from an old {archetype}?" if is_warm else "You want advice?"
    advice_body = "Trust your instincts, treat people right, and always have a backup plan." if is_warm else "Mind your own business, work hard, and do not trust strangers. Present company excluded."
    responses["advice"] = [
        {"text": f"{advice_intro} {advice_body}"},
    ]

    # Opinion
    responses["opinion"] = [
        {"text": f"My opinion? {'I try to see both sides.' if is_warm else 'I keep my opinions to myself. Safer that way.'}"},
    ]

    # Compliment response
    responses["compliment_response"] = [
        {"text": f"{'*blushes slightly* Well, thank you kindly.' if is_warm else '*nods curtly* Appreciated.'}"},
    ]

    # Insult response
    insult_resp = "*sighs* I have heard worse. But I appreciate your honesty, I suppose." if is_warm else "*narrows eyes* Choose your next words carefully."
    responses["insult_response"] = [
        {"text": insult_resp},
    ]

    return responses


# ──────────────────────────────────────────────────
# Character Factory
# ──────────────────────────────────────────────────

@dataclass
class CharacterSpec:
    """Input specification for generating a character."""
    name: str
    id: str = ""
    archetype: str = "merchant"
    setting: str = "medieval_fantasy"
    traits: List[str] = field(default_factory=list)
    backstory: str = ""
    location: str = ""
    establishment: str = ""
    specialty: str = ""
    rank: str = ""
    years: int = 20
    inventory_desc: str = ""
    knowledge_entities: List[str] = field(default_factory=list)
    custom_patterns: List[Dict] = field(default_factory=list)
    safety_rules: List[str] = field(default_factory=list)

    def __post_init__(self):
        if not self.id:
            self.id = self.name.lower().split()[0].replace("'", "")
        if not self.traits:
            template = _ARCHETYPE_TEMPLATES.get(self.archetype, {})
            self.traits = template.get("default_traits", ["neutral"])
        if not self.location:
            self.location = "town"
        if not self.establishment:
            if self.archetype == "innkeeper":
                self.establishment = f"{self.name}'s Inn"
            elif self.archetype in ("merchant", "blacksmith"):
                self.establishment = f"{self.name}'s Shop"
        if not self.specialty:
            defaults = {
                "scholar": "ancient history",
                "merchant": "general goods",
                "blacksmith": "weapons and armor",
                "healer": "healing arts",
            }
            self.specialty = defaults.get(self.archetype, "general")
        if not self.rank and self.archetype == "guard":
            self.rank = "Captain"
        if not self.inventory_desc and self.archetype in ("merchant", "blacksmith", "innkeeper"):
            defaults = {
                "merchant": "a wide selection of goods — weapons, potions, supplies, and curiosities",
                "blacksmith": "swords, shields, armor, and custom metalwork",
                "innkeeper": "rooms, meals, and the finest ale in the region",
            }
            self.inventory_desc = defaults.get(self.archetype, "various goods")


class CharacterFactory:
    """
    Zero-LLM character generator.
    
    Produces complete character genomes from a simple spec:
    bio.json + patterns.json + knowledge.json + personality.json
    
    Usage:
        factory = CharacterFactory()
        spec = CharacterSpec(name="Elda Brightwater", archetype="innkeeper")
        factory.generate(spec, output_dir="characters/elda")
    """

    def __init__(self, characters_dir: str = "characters"):
        self.characters_dir = Path(characters_dir)

    def generate(
        self, spec: CharacterSpec, output_dir: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Generate a complete character genome.
        
        Returns:
            {
                "id": str,
                "files": {"bio": path, "patterns": path, ...},
                "stats": {"patterns": int, "entities": int, ...},
            }
        """
        if output_dir is None:
            output_dir = str(self.characters_dir / spec.id)
        out = Path(output_dir)
        out.mkdir(parents=True, exist_ok=True)

        # 1. Generate bio
        bio = self._generate_bio(spec)
        self._write_json(out / "bio.json", bio)

        # 2. Generate patterns
        patterns = self._generate_patterns(spec)
        self._write_json(out / "patterns.json", patterns)

        # 3. Generate knowledge graph
        knowledge = self._generate_knowledge(spec)
        self._write_json(out / "knowledge.json", knowledge)

        # 4. Generate personality bank
        personality = self._generate_personality(spec)
        self._write_json(out / "personality.json", personality)

        # 5. Update registry
        self._update_registry(spec)

        stats = {
            "patterns": len(patterns.get("synthetic_patterns", [])),
            "generic": len(patterns.get("generic_patterns", [])),
            "entities": len(knowledge.get("entities", {})),
            "personality_intents": len(personality.get("responses", {})),
        }

        return {
            "id": spec.id,
            "files": {
                "bio": str(out / "bio.json"),
                "patterns": str(out / "patterns.json"),
                "knowledge": str(out / "knowledge.json"),
                "personality": str(out / "personality.json"),
            },
            "stats": stats,
        }

    def _generate_bio(self, spec: CharacterSpec) -> Dict:
        """Generate bio.json from spec."""
        template = _ARCHETYPE_TEMPLATES.get(spec.archetype, _ARCHETYPE_TEMPLATES["merchant"])

        bio = {
            "id": spec.id,
            "character_id": spec.id,
            "name": spec.name,
            "display_name": spec.name,
            "version": "2.0.0",
            "archetype": spec.archetype,
            "role": template["role"],
            "setting": spec.setting,
            "status": "active",
            "description": spec.backstory or f"{spec.name} is a {spec.archetype} in {spec.location}.",
            "persona": {
                "tone": ", ".join(spec.traits[:3]),
                "style": f"{spec.archetype} conversational",
                "traits": spec.traits,
            },
            "pattern_domains": template["pattern_domains"],
            "location": spec.location,
        }

        if spec.safety_rules:
            bio["safety_rules"] = spec.safety_rules

        if spec.establishment:
            bio["establishment"] = spec.establishment

        return bio

    def _generate_patterns(self, spec: CharacterSpec) -> Dict:
        """Generate patterns.json from spec and archetype templates."""
        template = _ARCHETYPE_TEMPLATES.get(spec.archetype, _ARCHETYPE_TEMPLATES["merchant"])
        synthetic = []

        # Greeting patterns
        format_vars = dict(
            name=spec.name, location=spec.location,
            establishment=spec.establishment, specialty=spec.specialty,
            rank=spec.rank, years=spec.years, archetype=spec.archetype,
        )
        for i, tmpl in enumerate(template["greeting_templates"]):
            text = tmpl.format(**format_vars)
            synthetic.append({
                "id": f"{spec.id}_greeting_{i}",
                "trigger": ["hello", "hi", "hey", "greetings"][: i + 2],
                "response_template": text,
                "confidence": 0.95,
                "domain": "identity",
            })

        # Identity patterns
        for i, tmpl in enumerate(template["identity_templates"]):
            text = tmpl.format(**format_vars)
            synthetic.append({
                "id": f"{spec.id}_identity_{i}",
                "trigger": ["who are you", "what's your name", "tell me about yourself"][: i + 2],
                "response_template": text,
                "confidence": 0.95,
                "domain": "identity",
            })

        # Domain patterns
        if "shop" in template["pattern_domains"]:
            for pat in _SHOP_PATTERNS:
                p = deepcopy(pat)
                p["id"] = p["id"].format(id=spec.id)
                p["response_template"] = p["response_template"].format(
                    name=spec.name, inventory_desc=spec.inventory_desc,
                    archetype=spec.archetype,
                )
                synthetic.append(p)

        if "combat" in template["pattern_domains"]:
            for pat in _COMBAT_PATTERNS:
                p = deepcopy(pat)
                p["id"] = p["id"].format(id=spec.id)
                action = "grips weapon" if spec.archetype in ("guard", "blacksmith") else "steps back"
                if spec.archetype == "guard":
                    combat_line = "I will not let you threaten this place."
                else:
                    combat_line = "I am not looking for trouble, friend."
                default_combat = f"*{action}* {combat_line}"
                p["response_template"] = default_combat
                synthetic.append(p)

        if "quest" in template["pattern_domains"]:
            for pat in _QUEST_PATTERNS:
                p = deepcopy(pat)
                p["id"] = p["id"].format(id=spec.id)
                p["response_template"] = f"As a matter of fact, I could use some help. Come closer and I'll tell you about it."
                synthetic.append(p)

        if "lore" in template["pattern_domains"]:
            for pat in _LORE_PATTERNS:
                p = deepcopy(pat)
                p["id"] = p["id"].format(id=spec.id)
                p["response_template"] = p["response_template"].format(
                    place_description=f"This is {spec.location}. {spec.backstory[:200] if spec.backstory else 'A place with a lot of history.'}",
                    history_text=f"There's a long history here in {spec.location}. It's seen better days, but it's home.",
                )
                synthetic.append(p)

        # Custom patterns
        for pat in spec.custom_patterns:
            synthetic.append(pat)

        # Farewell patterns
        for i, tmpl in enumerate(template["farewell_templates"]):
            text = tmpl.format(**format_vars)
            synthetic.append({
                "id": f"{spec.id}_farewell_{i}",
                "trigger": ["goodbye", "bye", "see you", "farewell"][: i + 2],
                "response_template": text,
                "confidence": 0.9,
                "domain": "identity",
            })

        # Generic patterns (universal fallbacks)
        generic = [
            {
                "id": f"{spec.id}_generic_thanks",
                "trigger": ["thank you", "thanks"],
                "response_template": "You're welcome, friend.",
                "confidence": 0.8,
            },
            {
                "id": f"{spec.id}_generic_yes",
                "trigger": ["yes", "sure", "okay"],
                "response_template": "Good. What else can I help with?",
                "confidence": 0.6,
            },
        ]

        # Fallback
        fallback_texts = template["fallback_responses"]
        fallback = random.choice(fallback_texts).format(
            name=spec.name, archetype=spec.archetype, specialty=spec.specialty,
        )

        return {
            "character_id": spec.id,
            "version": "2.0.0",
            "synthetic_patterns": synthetic,
            "generic_patterns": generic,
            "fallback": fallback,
        }

    def _generate_knowledge(self, spec: CharacterSpec) -> Dict:
        """Generate knowledge.json from spec."""
        entities = {}

        # Self-knowledge
        entities[spec.id] = {
            "entity_type": "self",
            "display_name": spec.name,
            "depth": "intimate",
            "description": spec.backstory or f"I'm {spec.name}, a {spec.archetype}.",
        }

        # Location knowledge
        if spec.location:
            entities[spec.location.lower().replace(" ", "_")] = {
                "entity_type": "location",
                "display_name": spec.location,
                "depth": "familiar",
                "description": f"My home. I've been here for {spec.years} years.",
            }

        # Establishment knowledge
        if spec.establishment:
            key = spec.establishment.lower().replace(" ", "_").replace("'", "")
            entities[key] = {
                "entity_type": "location",
                "display_name": spec.establishment,
                "depth": "intimate",
                "description": f"My {spec.archetype}'s establishment. The heart of my business.",
            }

        # Custom entities
        for ent_name in spec.knowledge_entities:
            key = ent_name.lower().replace(" ", "_").replace("'", "")
            entities[key] = {
                "entity_type": "concept",
                "display_name": ent_name,
                "depth": "familiar",
                "description": f"Something important to me — ask me about {ent_name}.",
            }

        return {
            "character_id": spec.id,
            "version": "2.0.0",
            "entities": entities,
        }

    def _generate_personality(self, spec: CharacterSpec) -> Dict:
        """Generate personality.json from spec."""
        responses = _generate_personality_responses(
            spec.name, spec.archetype, spec.traits,
        )
        return {
            "character_id": spec.id,
            "archetype": spec.archetype,
            "version": "2.0.0",
            "responses": responses,
        }

    def _update_registry(self, spec: CharacterSpec):
        """Update characters/registry.json with the new character."""
        registry_dir = Path(self.characters_dir)
        registry_dir.mkdir(parents=True, exist_ok=True)
        registry_path = registry_dir / "registry.json"
        if registry_path.exists():
            with open(registry_path) as f:
                registry = json.load(f)
        else:
            registry = {"version": "2.0.0", "characters": {}}

        char_entry = {
            "character_id": spec.id,
            "display_name": spec.name,
            "archetype": spec.archetype,
            "status": "active",
            "genome_files": ["bio.json", "patterns.json", "knowledge.json", "personality.json"],
        }
        
        # Check if characters is a list
        if isinstance(registry.get("characters"), list):
            # Try to find and update existing
            found = False
            for i, c in enumerate(registry["characters"]):
                if c.get("character_id") == spec.id or c.get("id") == spec.id:
                    # Update while preserving other fields like hemisphere_id
                    registry["characters"][i].update(char_entry)
                    found = True
                    break
            if not found:
                registry["characters"].append(char_entry)
        else:
            # Fallback if it's a dict
            if "characters" not in registry:
                registry["characters"] = {}
            registry["characters"][spec.id] = char_entry

        self._write_json(registry_path, registry)

    @staticmethod
    def _write_json(path: Path, data: Dict):
        with open(path, "w") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)


# ──────────────────────────────────────────────────
# CLI
# ──────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Synthesus Character Factory v2")
    parser.add_argument("--name", required=True, help="Character name")
    parser.add_argument("--archetype", default="merchant",
                        choices=list(_ARCHETYPE_TEMPLATES.keys()),
                        help="Character archetype")
    parser.add_argument("--setting", default="medieval_fantasy", help="World setting")
    parser.add_argument("--traits", default="", help="Comma-separated traits")
    parser.add_argument("--backstory", default="", help="Character backstory")
    parser.add_argument("--location", default="", help="Character location")
    parser.add_argument("--spec", default="", help="Path to JSON spec file")
    parser.add_argument("--output", default="", help="Output directory")

    args = parser.parse_args()

    if args.spec:
        with open(args.spec) as f:
            spec_data = json.load(f)
        spec = CharacterSpec(**spec_data)
    else:
        spec = CharacterSpec(
            name=args.name,
            archetype=args.archetype,
            setting=args.setting,
            traits=[t.strip() for t in args.traits.split(",") if t.strip()],
            backstory=args.backstory,
            location=args.location or "town",
        )

    factory = CharacterFactory()
    result = factory.generate(spec, output_dir=args.output or None)

    print(f"\n  Character generated: {result['id']}")
    print(f"  Files:")
    for key, path in result["files"].items():
        print(f"    {key}: {path}")
    print(f"  Stats:")
    for key, val in result["stats"].items():
        print(f"    {key}: {val}")
    print()


if __name__ == "__main__":
    main()
