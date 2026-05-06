#!/usr/bin/env python3
"""
CharacterVoice — Personality-specific response styling for pattern chains.
AIVM Synthesus 2.0 — Adds character personality to chained responses.

WHAT THIS MODULE DOES:
  Integrates character personality traits into the chain rendering process.
  Applies personality-specific prefixes, suffixes, and slot binding preferences.
  Ensures NPC responses maintain consistent voice across chained patterns.

INTEGRATION POINTS:
  - SequenceLinker.render_chain_text() — Applies voice styling during rendering
  - SlotFiller._extract_from_context() — Personality-biased slot resolution
  - CognitiveEngine — Passes character voice config to modules

VOICE STYLING FEATURES:
  - Personality-based prefixes/suffixes (e.g., "Ah, well..." for thoughtful NPCs)
  - Archetype-specific slot preferences (merchants prefer [topic]=commerce)
  - Emotional voice variations (afraid NPCs use more hesitant language)
  - Archetype chains (warriors prefer combat-related transitions)

USAGE:
  voice = CharacterVoice("merchant", personality_config)
  styled_response = voice.style_chained_response(
      chain_text="Dragons are dangerous creatures.",
      emotion="curious",
      context={"intent": "ask_about"}
  )
  # Result: "Ah, dragons you say? Quite the dangerous creatures, they are!"

AUTHOR: Cascade
DATE: 2026-04-06
VERSION: v1.0 - Personality integration for chains
"""

from __future__ import annotations

import random
import logging
from typing import Any, Dict, List, Optional, Set
from dataclasses import dataclass

logger = logging.getLogger(__name__)

# ── Voice Configuration ─────────────────────────────────────────────────────

@dataclass
class VoiceConfig:
    """Configuration for character voice styling."""
    prefixes: Dict[str, List[str]]  # emotion -> prefix options
    suffixes: Dict[str, List[str]]  # emotion -> suffix options
    slot_preferences: Dict[str, Dict[str, float]]  # slot_type -> value -> preference_weight
    archetype_chains: Dict[str, List[str]]  # archetype -> preferred pattern types
    hesitation_markers: List[str]  # "um", "well", "ah"
    emphasis_markers: List[str]  # "indeed", "truly", "quite"

# ── Predefined Voice Configurations ────────────────────────────────────────

VOICE_CONFIGS = {
    "merchant": VoiceConfig(
        prefixes={
            "curious": ["Ah, you ask about", "Let me tell you about", "Well now"],
            "afraid": ["Oh dear, regarding", "I'm not sure about", "Carefully now"],
            "excited": ["Splendid!", "Wonderful!", "Excellent question about"],
            "neutral": ["Regarding", "About", "Concerning"],
            "angry": ["Listen here about", "I must tell you about", "Pay attention to"]
        },
        suffixes={
            "curious": ["if you're interested.", "you know.", "I suppose."],
            "afraid": ["be careful now.", "I warn you.", "stay safe."],
            "excited": ["isn't it?", "quite remarkable!", "fascinating stuff!"],
            "neutral": ["that's all.", "I think.", "you see."],
            "angry": ["mark my words!", "don't forget it!", "understand?"]
        },
        slot_preferences={
            "topic": {"trade": 1.5, "commerce": 1.4, "gold": 1.3},
            "emotion": {"greed": 1.2, "satisfaction": 1.1},
            "time": {"market_close": 1.3, "bargaining_hour": 1.2}
        },
        archetype_chains=["commerce", "trade", "wealth"],
        hesitation_markers=["well now", "let me see", "hmm"],
        emphasis_markers=["quite profitable", "excellent value", "prime quality"]
    ),

    "warrior": VoiceConfig(
        prefixes={
            "curious": ["Listen up about", "You want to know about", "Pay attention to"],
            "afraid": ["Watch yourself with", "Be careful of", "Stay back from"],
            "excited": ["By the gods!", "Now this is", "Glorious"],
            "neutral": ["About", "Regarding", "Concerning"],
            "angry": ["Damn", "Curse those", "Fight against"]
        },
        suffixes={
            "curious": ["hear me?", "got that?", "understand?"],
            "afraid": ["or else!", "I warn you!", "be smart!"],
            "excited": ["what a battle!", "glorious victory!", "triumph!"],
            "neutral": ["that's it.", "plain and simple.", "done."],
            "angry": ["to hell!", "damn them!", "fight on!"]
        },
        slot_preferences={
            "topic": {"combat": 1.6, "battle": 1.5, "weapon": 1.4},
            "emotion": {"rage": 1.3, "courage": 1.2, "battle_lust": 1.1},
            "time": {"battle_time": 1.4, "war_season": 1.3}
        },
        archetype_chains=["combat", "battle", "war"],
        hesitation_markers=["by my blade", "steel and blood", "battle ready"],
        emphasis_markers=["deadly", "powerful", "unstoppable"]
    ),

    "scholar": VoiceConfig(
        prefixes={
            "curious": ["Fascinating question about", "Indeed, regarding", "Most interesting"],
            "afraid": ["Curious development with", "Some concern about", "Worrisome"],
            "excited": ["Eureka!", "Brilliant!", "Extraordinary"],
            "neutral": ["Regarding", "Concerning", "About"],
            "angry": ["Outrageous", "Unacceptable", "Scandalous"]
        },
        suffixes={
            "curious": ["most intriguing.", "how curious.", "fascinating indeed."],
            "afraid": ["we must be cautious.", "exercise care.", "be mindful."],
            "excited": ["what discovery!", "marvelous!", "astonishing!"],
            "neutral": ["that's established.", "clearly.", "evident."],
            "angry": ["utterly unacceptable!", "beyond belief!", "intolerable!"]
        },
        slot_preferences={
            "topic": {"lore": 1.5, "magic": 1.4, "history": 1.3},
            "emotion": {"wonder": 1.3, "curiosity": 1.2, "awe": 1.1},
            "time": {"ancient_times": 1.4, "historical_period": 1.3}
        },
        archetype_chains=["lore", "magic", "knowledge"],
        hesitation_markers=["hmm, let me think", "interesting", "curious indeed"],
        emphasis_markers=["well documented", "historically accurate", "scientifically proven"]
    ),

    "noble": VoiceConfig(
        prefixes={
            "curious": ["My dear, about", "Indeed, concerning", "How interesting"],
            "afraid": ["Oh heavens, regarding", "Most troubling", "Concerning"],
            "excited": ["Splendid!", "Delightful!", "Marvelous"],
            "neutral": ["Regarding", "About", "Concerning"],
            "angry": ["Outrageous!", "Unacceptable!", "Scandalous"]
        },
        suffixes={
            "curious": ["don't you think?", "quite.", "I daresay."],
            "afraid": ["most concerning.", "we must act.", "troubling indeed."],
            "excited": ["simply marvelous!", "delightful!", "splendid affair!"],
            "neutral": ["naturally.", "of course.", "as expected."],
            "angry": ["utterly outrageous!", "beyond the pale!", "unforgivable!"]
        },
        slot_preferences={
            "topic": {"politics": 1.5, "court": 1.4, "nobility": 1.3},
            "emotion": {"dignity": 1.2, "propriety": 1.1},
            "time": {"court_hours": 1.3, "ceremony_time": 1.2}
        },
        archetype_chains=["politics", "nobility", "court"],
        hesitation_markers=["my dear", "indeed", "well now"],
        emphasis_markers=["most proper", "highly appropriate", "befitting nobility"]
    )
}

# ── CharacterVoice Class ──────────────────────────────────────────────────

class CharacterVoice:
    """
    Applies personality-specific styling to chained responses.

    Usage:
        voice = CharacterVoice("merchant")
        styled = voice.style_chained_response(
            chain_text="Dragons are dangerous creatures.",
            emotion="curious",
            context={"intent": "ask_about"}
        )
    """

    def __init__(self, archetype: str, custom_config: Optional[VoiceConfig] = None):
        """Initialize with archetype or custom config."""
        self.archetype = archetype
        self.config = custom_config or VOICE_CONFIGS.get(archetype, VOICE_CONFIGS["merchant"])

        if not self.config:
            logger.warning(f"No voice config for archetype '{archetype}', using default")
            self.config = VOICE_CONFIGS["merchant"]

    def style_chained_response(
        self,
        chain_text: str,
        emotion: str = "neutral",
        context: Optional[Dict[str, Any]] = None
    ) -> str:
        """
        Apply personality styling to a chained response.

        Args:
            chain_text: Raw chained response text
            emotion: Current emotion context
            context: Additional context (intent, etc.)

        Returns:
            Personality-styled response
        """
        context = context or {}

        # Get emotion-specific styling
        emotion = emotion.lower()
        prefixes = self.config.prefixes.get(emotion, self.config.prefixes.get("neutral", [""]))
        suffixes = self.config.suffixes.get(emotion, self.config.suffixes.get("neutral", [""]))

        # Apply prefix
        if prefixes:
            prefix = random.choice(prefixes)
            if prefix:
                chain_text = f"{prefix} {chain_text}"

        # Apply suffix
        if suffixes:
            suffix = random.choice(suffixes)
            if suffix:
                chain_text = f"{chain_text} {suffix}"

        # Add hesitation/emphasis based on context
        intent = context.get("intent", "")
        if intent in ["ask_about", "question"]:
            # Add hesitation for thoughtful responses
            if random.random() < 0.3:  # 30% chance
                hesitation = random.choice(self.config.hesitation_markers)
                chain_text = f"{hesitation}, {chain_text.lower()}"
        elif intent in ["combat", "danger"]:
            # Add emphasis for intense situations
            if random.random() < 0.4:  # 40% chance
                emphasis = random.choice(self.config.emphasis_markers)
                # Insert emphasis randomly in the text
                words = chain_text.split()
                if len(words) > 3:
                    insert_pos = random.randint(1, len(words) - 2)
                    words.insert(insert_pos, emphasis)
                    chain_text = " ".join(words)

        # Capitalize first letter
        if chain_text:
            chain_text = chain_text[0].upper() + chain_text[1:]

        return chain_text

    def get_slot_preferences(self, slot_type: str) -> Dict[str, float]:
        """Get personality preferences for slot values."""
        return self.config.slot_preferences.get(slot_type, {})

    def get_preferred_chains(self) -> List[str]:
        """Get archetype-preferred chain types."""
        return self.config.archetype_chains

    def customize_slot_binding(self, slot_name: str, candidates: List[str]) -> Optional[str]:
        """
        Choose slot value based on personality preferences.

        Args:
            slot_name: Type of slot (topic, emotion, etc.)
            candidates: Available values to choose from

        Returns:
            Preferred value or None
        """
        preferences = self.get_slot_preferences(slot_name)
        if not preferences:
            return None

        # Score candidates by preference
        scored = []
        for candidate in candidates:
            score = preferences.get(candidate.lower(), 1.0)
            scored.append((candidate, score))

        if scored:
            # Return highest preference (with some randomness)
            scored.sort(key=lambda x: x[1], reverse=True)
            top_score = scored[0][1]

            # If clear preference, use it 80% of time
            if top_score > 1.1 and random.random() < 0.8:
                return scored[0][0]

        return None

# ── Integration Functions ─────────────────────────────────────────────────

def integrate_voice_into_chainer():
    """
    Example of how to integrate CharacterVoice into SequenceLinker.

    This would be added to SequenceLinker.render_chain_text()
    """
    # Example integration code (not executed)
    """
    def render_chain_text(self, plan: ChainPlan, slot_bindings: Dict[str, str],
                         character_voice: Optional[CharacterVoice] = None) -> str:
        # ... existing rendering code ...

        # Apply voice styling
        if character_voice:
            sentences = []
            for step in plan.steps:
                text = step.pattern_text
                # ... slot filling ...

                # Apply personality styling
                styled_text = character_voice.style_chained_response(
                    text,
                    emotion=plan.context_bucket,  # Or from context
                    context={"intent": "inform"}
                )
                sentences.append(styled_text)

            return " ".join(sentences)
        else:
            # Original rendering
            return " ".join(sentences)
    """
    pass

# ── Module Test ───────────────────────────────────────────────────────────

if __name__ == "__main__":
    # Test different archetypes
    archetypes = ["merchant", "warrior", "scholar", "noble"]

    test_text = "Dragons are dangerous creatures that breathe fire."

    for archetype in archetypes:
        voice = CharacterVoice(archetype)
        styled = voice.style_chained_response(test_text, emotion="curious")
        print(f"{archetype.title()}: {styled}")

        # Test slot preferences
        topic_prefs = voice.get_slot_preferences("topic")
        if topic_prefs:
            print(f"  Topic preferences: {topic_prefs}")

    print("\nCustom voice test:")
    # Test custom config
    custom_config = VoiceConfig(
        prefixes={"excited": ["Wow!", "Amazing!"]},
        suffixes={"excited": ["incredible!", "fantastic!"]},
        slot_preferences={},
        archetype_chains=["magic"],
        hesitation_markers=["gosh"],
        emphasis_markers=["super"]
    )
    custom_voice = CharacterVoice("custom", custom_config)
    styled_custom = custom_voice.style_chained_response(test_text, emotion="excited")
    print(f"Custom: {styled_custom}")
