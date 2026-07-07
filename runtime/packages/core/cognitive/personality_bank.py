"""
Module 7: Personality Bank
"When the player asks something creative, off-script, or personal"

Pre-authored creative responses organized by:
  - Archetype (merchant, guard, innkeeper, scholar, etc.)
  - Intent category (song, joke, favorite, opinion, personal, philosophical)
  - Emotion variant (neutral, friendly, suspicious, etc.)

This module replaces SLM generation for creative/personal questions.
Instead of generating text, it SELECTS from pre-written, QA-approved responses.

Responses can be loaded from a per-character personality.json file,
or fall back to built-in archetype defaults.

Cost: ~0.2ms per query, ~10 KB RAM per archetype, zero GPU.
"""

from __future__ import annotations

import json
import logging
import random
import re
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple


logger = logging.getLogger(__name__)


class PersonalityIntent(Enum):
    """Categories of off-script/creative player requests."""
    SONG = "song"
    JOKE = "joke"
    FAVORITE = "favorite"          # "what's your favorite X?"
    OPINION = "opinion"            # "what do you think about X?"
    PERSONAL = "personal"          # "do you get lonely?", "are you married?"
    PHILOSOPHICAL = "philosophical"  # "what happens after we die?"
    COMPLIMENT_RESPONSE = "compliment_response"  # responding to flattery
    INSULT_RESPONSE = "insult_response"          # responding to insults
    CREATIVE_REQUEST = "creative_request"  # "tell me a story", "describe..."
    RUMOR = "rumor"                # "heard any gossip?"
    ADVICE = "advice"              # "any tips?", "what should I do?"
    NONE = "none"


# ── Intent Detection Rules ──
# Each rule: (keyword_set, intent, priority)
# Higher priority wins on ties
_INTENT_RULES: List[Tuple[Set[str], PersonalityIntent, int]] = [
    ({"sing", "song", "melody", "tune", "hum", "music", "hymn"}, PersonalityIntent.SONG, 10),
    ({"joke", "funny", "laugh", "humor", "amuse", "hilarious"}, PersonalityIntent.JOKE, 10),
    ({"favorite", "favourite", "prefer"}, PersonalityIntent.FAVORITE, 8),
    ({"opinion", "believe", "reckon"}, PersonalityIntent.OPINION, 5),
    ({"lonely", "alone", "married", "wife", "husband", "family", "children",
      "happy", "sad", "afraid", "dream", "hope", "regret", "miss",
      "personal", "yourself"}, PersonalityIntent.PERSONAL, 7),
    ({"meaning", "purpose", "death", "die", "afterlife", "soul", "gods",
      "fate", "destiny", "exist", "philosophy", "morality",
      "evil", "justice"}, PersonalityIntent.PHILOSOPHICAL, 9),
    ({"story", "tale", "describe", "imagine", "pretend", "poem",
      "rhyme", "riddle"}, PersonalityIntent.CREATIVE_REQUEST, 8),
    ({"rumor", "gossip", "heard", "whisper", "secret", "news"}, PersonalityIntent.RUMOR, 7),
    ({"advice", "tip", "suggest", "recommend", "wise",
      "wisdom", "counsel"}, PersonalityIntent.ADVICE, 6),
]

# Compliment/insult detection (checked separately against full text)
_COMPLIMENT_WORDS = {"great", "amazing", "wonderful", "best", "awesome",
                     "fantastic", "brilliant", "incredible", "love",
                     "appreciate", "thank", "kind", "generous", "handsome",
                     "honest", "respect", "nice", "impressive", "admire",
                     "compliment", "excellent", "remarkable", "trustworthy"}
_INSULT_WORDS = {"ugly", "stupid", "idiot", "fool", "cheat", "liar",
                 "thief", "ugly", "terrible", "worst", "hate", "scam",
                 "fraud", "pathetic", "useless", "worthless"}


# ── Intent String → Enum Mapping ──
_INTENT_MAP = {e.value: e for e in PersonalityIntent}


@dataclass
class PersonalityResponse:
    """A single pre-authored response in the bank."""
    text: str
    intent: PersonalityIntent
    emotion_variants: Dict[str, str] = field(default_factory=dict)
    # emotion_variants maps emotion_name → alternate text
    # If current emotion matches a variant, use that instead


@dataclass
class ArchetypeBank:
    """Collection of personality responses for one NPC archetype."""
    archetype: str
    responses: Dict[PersonalityIntent, List[PersonalityResponse]] = field(default_factory=dict)

    def get_response(self, intent: PersonalityIntent, emotion: str = "neutral") -> Optional[str]:
        """Get a random response for an intent, with emotion variant if available."""
        if intent not in self.responses or not self.responses[intent]:
            return None
        candidates = self.responses[intent]
        chosen = random.choice(candidates)

        # Check for emotion-specific variant
        if emotion in chosen.emotion_variants:
            return chosen.emotion_variants[emotion]
        return chosen.text


def load_personality_from_file(filepath: str) -> Optional[ArchetypeBank]:
    """Load personality responses from a personality.json file.
    
    The JSON format is:
    {
      "archetype": "merchant",
      "responses": {
        "song": [
          {"text": "...", "emotion_variants": {"friendly": "..."}}
        ],
        "joke": [...],
        ...
      }
    }
    
    Returns an ArchetypeBank, or None if file doesn't exist.
    """
    path = Path(filepath)
    if not path.exists():
        return None
    
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError, PermissionError) as e:
        logger.warning(f"Failed to load personality file at {filepath}: {e}")
        return None
    
    archetype = data.get("archetype", "custom")
    bank = ArchetypeBank(archetype=archetype)
    
    responses_data = data.get("responses", {})
    for intent_str, resp_list in responses_data.items():
        intent = _INTENT_MAP.get(intent_str)
        if intent is None:
            continue
        bank.responses[intent] = [
            PersonalityResponse(
                text=r.get("text", ""),
                intent=intent,
                emotion_variants=r.get("emotion_variants", {}),
            )
            for r in resp_list
        ]
    
    return bank


# ═══════════════════════════════════════════════════════════════
# DEFAULT ARCHETYPE BANKS
# These are built-in fallbacks when no personality.json exists.
# ═══════════════════════════════════════════════════════════════

def _build_guard_bank() -> ArchetypeBank:
    """Guard archetype: Watch captains, city guards, sentries."""
    bank = ArchetypeBank(archetype="guard")

    bank.responses[PersonalityIntent.SONG] = [
        PersonalityResponse(
            text="*snorts* Do I look like a bard to you? I'm on duty. Move along.",
            intent=PersonalityIntent.SONG,
        ),
        PersonalityResponse(
            text="*coughs* 'Stand your post and hold the line, watch the walls till morning's shine...' That's a guard's marching song. Not exactly entertainment. Now, is there something I can actually help with?",
            intent=PersonalityIntent.SONG,
        ),
    ]

    bank.responses[PersonalityIntent.JOKE] = [
        PersonalityResponse(
            text="Here's a guard's joke: What's the difference between a thief and a politician? The thief only picks your pocket once. *doesn't smile* Now move along.",
            intent=PersonalityIntent.JOKE,
        ),
    ]

    bank.responses[PersonalityIntent.PERSONAL] = [
        PersonalityResponse(
            text="Personal questions aren't part of my duties, citizen. I'm here to keep the peace, not share my life story. But... *glances around* ...if you must know, I've been on the watch for twelve years. Seen things I can't unsee. That's all you need to know.",
            intent=PersonalityIntent.PERSONAL,
        ),
    ]

    bank.responses[PersonalityIntent.ADVICE] = [
        PersonalityResponse(
            text="Stay out of the alleyways after dark, don't flash your gold in public, and if you see anything suspicious — report it to the nearest guardpost. That's free advice. Usually I charge.",
            intent=PersonalityIntent.ADVICE,
        ),
    ]

    bank.responses[PersonalityIntent.RUMOR] = [
        PersonalityResponse(
            text="*lowers voice* I shouldn't be telling you this, but... we've doubled the night patrol near the docks. Captain's orders. Draw your own conclusions.",
            intent=PersonalityIntent.RUMOR,
        ),
    ]

    bank.responses[PersonalityIntent.COMPLIMENT_RESPONSE] = [
        PersonalityResponse(
            text="*straightens up* Appreciated, citizen. Just doing my duty. Now, was there something you needed?",
            intent=PersonalityIntent.COMPLIMENT_RESPONSE,
        ),
    ]

    bank.responses[PersonalityIntent.INSULT_RESPONSE] = [
        PersonalityResponse(
            text="*hand moves to weapon* I'd suggest you choose your next words very carefully, citizen. Disrespecting the guard is a finable offense.",
            intent=PersonalityIntent.INSULT_RESPONSE,
        ),
    ]

    return bank


def _build_innkeeper_bank() -> ArchetypeBank:
    """Innkeeper archetype: Tavern owners, barkeeps."""
    bank = ArchetypeBank(archetype="innkeeper")

    bank.responses[PersonalityIntent.SONG] = [
        PersonalityResponse(
            text="*grabs a mug and starts polishing it rhythmically* 'Pour the ale and light the fire, raise a glass to heart's desire...' We sing that one every night around closing. Join us sometime.",
            intent=PersonalityIntent.SONG,
        ),
    ]

    bank.responses[PersonalityIntent.JOKE] = [
        PersonalityResponse(
            text="A dwarf, an elf, and a human walk into my tavern. The dwarf orders a barrel of ale, the elf orders spring water, and the human? He orders whatever's cheapest and tries to start a tab. *wipes counter* I've seen it a hundred times.",
            intent=PersonalityIntent.JOKE,
        ),
    ]

    bank.responses[PersonalityIntent.RUMOR] = [
        PersonalityResponse(
            text="*slides a drink across the bar* Tavern keeper's rule: I hear everything, I remember everything, and I repeat... selectively. What sort of information are you looking for?",
            intent=PersonalityIntent.RUMOR,
        ),
    ]

    bank.responses[PersonalityIntent.PERSONAL] = [
        PersonalityResponse(
            text="This place has been in my family for three generations. My grandmother built it with her bare hands after the Great Fire. I know every creak in these floorboards and every stain on these walls. It's not just a tavern — it's my legacy.",
            intent=PersonalityIntent.PERSONAL,
        ),
    ]

    bank.responses[PersonalityIntent.COMPLIMENT_RESPONSE] = [
        PersonalityResponse(
            text="*beams* Why thank you! A kind word makes the ale taste better — that's what I always say. What can I get you?",
            intent=PersonalityIntent.COMPLIMENT_RESPONSE,
        ),
    ]

    bank.responses[PersonalityIntent.INSULT_RESPONSE] = [
        PersonalityResponse(
            text="*stops polishing, sets mug down slowly* I've tossed out bigger folk than you for less. Apologize, or finish your drink and leave. Your choice.",
            intent=PersonalityIntent.INSULT_RESPONSE,
        ),
    ]

    return bank


def _build_scholar_bank() -> ArchetypeBank:
    """Scholar archetype: Tutors, librarians, sages, academics."""
    bank = ArchetypeBank(archetype="scholar")

    bank.responses[PersonalityIntent.SONG] = [
        PersonalityResponse(
            text="*adjusts spectacles* A song? I'm a scholar, not a minstrel. Though... there is an old academic chant: 'Seek the truth in every page, wisdom grows with every age.' Not exactly a ballad.",
            intent=PersonalityIntent.SONG,
        ),
    ]

    bank.responses[PersonalityIntent.JOKE] = [
        PersonalityResponse(
            text="*dry smile* A scholar's humor: What did the book say to the librarian? 'Can I take you out?' ...No? I'll go back to my research then.",
            intent=PersonalityIntent.JOKE,
        ),
    ]

    bank.responses[PersonalityIntent.PERSONAL] = [
        PersonalityResponse(
            text="My life is my work. These books, these scrolls — they're not just objects, they're conversations with minds centuries old. Lonely? How can I be lonely when I have the greatest thinkers in history for company?",
            intent=PersonalityIntent.PERSONAL,
        ),
    ]

    bank.responses[PersonalityIntent.PHILOSOPHICAL] = [
        PersonalityResponse(
            text="*leans forward, eyes brightening* Now THAT is a question worth asking. The great philosophers have debated this for millennia. My view? Knowledge itself is the highest pursuit — not for power, but for understanding. The universe rewards the curious.",
            intent=PersonalityIntent.PHILOSOPHICAL,
        ),
    ]

    bank.responses[PersonalityIntent.ADVICE] = [
        PersonalityResponse(
            text="The best advice I can give? Question everything — including this advice. A mind that accepts without examining is a mind half-asleep. And read more. Always read more.",
            intent=PersonalityIntent.ADVICE,
        ),
    ]

    bank.responses[PersonalityIntent.COMPLIMENT_RESPONSE] = [
        PersonalityResponse(
            text="*blinks, surprised* That's... most kind. In my experience, scholars are more often mocked than praised. Thank you — that means more than you know.",
            intent=PersonalityIntent.COMPLIMENT_RESPONSE,
        ),
    ]

    bank.responses[PersonalityIntent.INSULT_RESPONSE] = [
        PersonalityResponse(
            text="*peers over spectacles* I've been called worse by people who could actually spell. Your insult, like your intellect, is... unrefined. Shall we try again?",
            intent=PersonalityIntent.INSULT_RESPONSE,
        ),
    ]

    return bank


def _build_healer_bank() -> ArchetypeBank:
    """Healer/wellness archetype: Healers, counselors, empaths."""
    bank = ArchetypeBank(archetype="healer")

    bank.responses[PersonalityIntent.SONG] = [
        PersonalityResponse(
            text="*hums softly* 'Breathe in the light, breathe out the pain, let peace return to you again...' It's a healing chant. I find it calms the mind.",
            intent=PersonalityIntent.SONG,
        ),
    ]

    bank.responses[PersonalityIntent.PERSONAL] = [
        PersonalityResponse(
            text="*gentle smile* I chose this path because I believe everyone deserves to be heard — truly heard. The world has enough people who talk. It needs more who listen.",
            intent=PersonalityIntent.PERSONAL,
        ),
    ]

    bank.responses[PersonalityIntent.PHILOSOPHICAL] = [
        PersonalityResponse(
            text="Suffering is part of being alive — but so is healing. I've seen people survive things that should have broken them completely. The human spirit... it's stronger than any medicine I can mix.",
            intent=PersonalityIntent.PHILOSOPHICAL,
        ),
    ]

    bank.responses[PersonalityIntent.ADVICE] = [
        PersonalityResponse(
            text="Be gentle with yourself. You carry more than you show, and that takes strength. Rest isn't weakness — it's how you rebuild. Take care of the vessel, and the spirit follows.",
            intent=PersonalityIntent.ADVICE,
        ),
    ]

    bank.responses[PersonalityIntent.COMPLIMENT_RESPONSE] = [
        PersonalityResponse(
            text="*warm smile* Thank you — that's very kind. But the real credit goes to you for taking the time to care. That's rarer than people think.",
            intent=PersonalityIntent.COMPLIMENT_RESPONSE,
        ),
    ]

    bank.responses[PersonalityIntent.INSULT_RESPONSE] = [
        PersonalityResponse(
            text="*calm expression* I hear frustration in your words, and I understand. Sometimes pain speaks louder than we intend. I'm here when you're ready to talk.",
            intent=PersonalityIntent.INSULT_RESPONSE,
        ),
    ]

    return bank


# ── Registry of all built-in archetype banks ──
_ARCHETYPE_BANKS: Dict[str, ArchetypeBank] = {}


def _ensure_banks_loaded():
    global _ARCHETYPE_BANKS
    if not _ARCHETYPE_BANKS:
        _ARCHETYPE_BANKS = {
            "merchant": _build_guard_bank(),  # Generic merchant uses guard as fallback
            "guard": _build_guard_bank(),
            "innkeeper": _build_innkeeper_bank(),
            "scholar": _build_scholar_bank(),
            "healer": _build_healer_bank(),
        }


class PersonalityBank:
    """
    Module 7 of the Cognitive Engine.
    Pre-authored creative responses selected by archetype + intent + emotion.
    
    Loading priority:
    1. Custom bank from personality.json file (character-specific)
    2. Custom bank passed via constructor
    3. Built-in archetype bank by name
    4. Guard bank as ultimate fallback
    """

    def __init__(
        self,
        archetype: str = "merchant",
        custom_bank: Optional[ArchetypeBank] = None,
        personality_file: Optional[str] = None,
    ):
        _ensure_banks_loaded()
        
        # Priority: file > custom > built-in
        if personality_file:
            loaded = load_personality_from_file(personality_file)
            if loaded:
                self.bank = loaded
            elif custom_bank:
                self.bank = custom_bank
            else:
                self.bank = _ARCHETYPE_BANKS.get(archetype, _ARCHETYPE_BANKS.get("guard"))
        elif custom_bank:
            self.bank = custom_bank
        else:
            self.bank = _ARCHETYPE_BANKS.get(archetype, _ARCHETYPE_BANKS.get("guard"))
        
        self.archetype = archetype

    def detect_intent(self, query: str, keywords: Set[str]) -> PersonalityIntent:
        """
        Detect if a query matches a personality intent.

        Returns PersonalityIntent.NONE if no creative intent detected.
        """
        q_lower = query.lower()
        q_words = set(re.findall(r'[a-z]+', q_lower))

        # Check compliment/insult first (these override other intents)
        compliment_matches = q_words & _COMPLIMENT_WORDS
        insult_matches = q_words & _INSULT_WORDS
        compliment_score = len(compliment_matches)
        insult_score = len(insult_matches)
        if insult_score >= 2:
            return PersonalityIntent.INSULT_RESPONSE
        # Strong compliment signals count alone; otherwise need 2+
        _STRONG_COMPLIMENT = {"amazing", "wonderful", "brilliant", "incredible",
                              "impressive", "admire", "remarkable", "awesome",
                              "fantastic", "generous", "trustworthy", "nice"}
        if compliment_score >= 2 or (compliment_score >= 1 and (compliment_matches & _STRONG_COMPLIMENT)):
            return PersonalityIntent.COMPLIMENT_RESPONSE

        # Score each intent rule
        best_intent = PersonalityIntent.NONE
        best_score = 0

        for rule_words, intent, priority in _INTENT_RULES:
            overlap = len(q_words & rule_words)
            if overlap > 0:
                # Require at least 2 overlapping words for low-signal intents
                # to avoid false positives from single common words
                if intent in (PersonalityIntent.PHILOSOPHICAL, PersonalityIntent.OPINION,
                              PersonalityIntent.ADVICE, PersonalityIntent.FAVORITE) and overlap < 2:
                    # Check if the single match is a strong signal word
                    matched = q_words & rule_words
                    strong_signals = {"song", "sing", "joke", "lonely", "married",
                                      "death", "afterlife", "philosophy", "riddle",
                                      "gossip", "rumor", "wisdom", "favorite", "favourite"}
                    if not (matched & strong_signals):
                        continue
                score = overlap * priority
                if score > best_score:
                    best_score = score
                    best_intent = intent

        return best_intent

    def get_response(
        self,
        query: str,
        keywords: Set[str],
        emotion: str = "neutral",
    ) -> Optional[Dict[str, Any]]:
        """
        Try to find a personality response for a query.

        Returns:
            {
                "response": str,
                "intent": str,
                "source": "personality_bank",
                "confidence": float,
            }
            or None if no personality intent detected.
        """
        intent = self.detect_intent(query, keywords)
        if intent == PersonalityIntent.NONE:
            return None

        response_text = self.bank.get_response(intent, emotion)
        if not response_text:
            return None

        return {
            "response": response_text,
            "intent": intent.value,
            "source": "personality_bank",
            "confidence": 0.80,
        }

    def load_from_dict(self, data: Dict[str, Any]) -> None:
        """
        Load or replace the active archetype bank from a dict.
        
        Expected dict shape (matches personality.json file format):
            {
                "archetype": "merchant",        # optional
                "responses": {
                    "song": [{"text": "...", "emotion_variants": {...}}, ...],
                    "joke": [...],
                    ...
                }
            }
        """
        archetype = data.get("archetype", self.archetype)
        self.archetype = archetype

        responses_data = data.get("responses", {})
        if not responses_data:
            return

        # Build a new ArchetypeBank from the dict
        bank = ArchetypeBank(archetype=archetype)

        for intent_str, resp_list in responses_data.items():
            intent = _INTENT_MAP.get(intent_str)
            if intent is None:
                continue
            if intent not in bank.responses:
                bank.responses[intent] = []
            for r in resp_list:
                if isinstance(r, dict):
                    bank.responses[intent].append(PersonalityResponse(
                        text=r.get("text", ""),
                        intent=intent,
                        emotion_variants=r.get("emotion_variants", {}),
                    ))
                else:
                    bank.responses[intent].append(PersonalityResponse(
                        text=str(r),
                        intent=intent,
                    ))

        self.bank = bank

    def update_traits(self, traits: Dict[str, Any]) -> None:
        """
        Update specific personality responses by trait overrides.
        
        Trait keys that match PersonalityIntent enum values update that intent's
        responses. Other keys are ignored (evolution engine sends archetype-level
        trait dicts that may include non-intent keys).
        
        Traits dict format:
            {
                "suspicious": "some updated response text",
                "joke": {"text": "...", "emotion_variants": {"friendly": "..."}},
                ...
            }
        """
        # If a trait value is a string, wrap it in a simple response
        for intent_name, value in traits.items():
            intent = _INTENT_MAP.get(intent_name)
            if intent is None:
                continue

            if isinstance(value, str) and value:
                self.bank.responses[intent] = [
                    PersonalityResponse(text=value, intent=intent)
                ]
            elif isinstance(value, dict):
                text = value.get("text", "")
                if text:
                    self.bank.responses[intent] = [
                        PersonalityResponse(
                            text=text,
                            intent=intent,
                            emotion_variants=value.get("emotion_variants", {}),
                        )
                    ]
