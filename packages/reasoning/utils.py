"""
Reasoning Layer Utilities - Shared Constants and Helper Functions
"""

from __future__ import annotations
from typing import Dict, List, Any, Set
import re

class DomainKeywords:
    """
    Central registry of domain keywords for routing and decomposition.
    """
    KEYWORDS = {
        "character": [
            "npc", "character", "personality", "ally", "enemy", "companion",
            "backstory", "motivation", "emotion", "dialogue", "avatar", "hero",
            "villain", "mentor", "quest giver", "merchant", "follower",
        ],
        "world": [
            "world", "environment", "location", "setting", "terrain",
            "economy", "faction", "kingdom", "city", "quest", "dungeon",
            "wilderness", "village", "castle", "region", "map", "landscape",
        ],
        "strategy": [
            "strategy", "tactic", "battle", "combat", "plan", "win",
            "defeat", "resource", "army", "formation", "flank", "siege",
            "defense", "offense", "build order", "economy", "rush",
        ],
        "narrative": [
            "story", "plot", "narrative", "quest", "adventure", "event",
            "backstory", "prologue", "epilogue", "arc", "chapter",
            "conflict", "resolution", "climax",
        ],
        "dialogue": [
            "say", "speak", "talk", "converse", "respond", "reply",
            "greet", "question", "answer", "utterance", "voice", "tone",
        ],
        "emotion": [
            "feel", "emotion", "mood", "happy", "sad", "angry", "fear",
            "joy", "sorrow", "excitement", "anxiety", "rage", "hope",
        ],
        "knowledge": [
            "know", "knowledge", "fact", "lore", "history", "information",
            "learn", "discover", "understand", "remember", "recall",
        ],
        "code": [
            "code", "function", "class", "implement", "debug", "refactor",
            "algorithm", "syntax", "programming", "variable", "loop", "module",
            "api", "runtime", "compile", "exception", "test", "bug", "import",
            "python", "javascript", "typescript", "java", "c++", "rust", "go",
            "software", "package", "dependency", "library", "framework",
        ],
        "math": [
            "calculate", "equation", "solve", "compute", "math", "algebra",
            "geometry", "calculus", "derivative", "integral", "matrix", "vector",
            "probability", "statistics", "regression", "optimize", "formula",
            "theorem", "proof", "graph", "number", "arithmetic", "sum", "product",
        ],
    }

def classify_domain(text: str) -> str:
    """Heuristic domain classifier based on keyword and phrase matching."""
    text_lower = text.lower()
    scores: Dict[str, float] = {}

    for domain, keywords in DomainKeywords.KEYWORDS.items():
        score = 0.0
        for kw in keywords:
            if kw in text_lower:
                # Boost score for multi-word phrase matches
                if " " in kw:
                    score += 2.0
                else:
                    score += 1.0
        if score > 0:
            scores[domain] = score

    if not scores:
        return "general"
    return max(scores, key=scores.get)

def extract_sentences(text: str) -> List[str]:
    """Split text into sentences using basic punctuation."""
    sentences = re.split(r'[.!?]+', text)
    return [s.strip() for s in sentences if s.strip()]

def get_jaccard_similarity(text_a: str, text_b: str) -> float:
    """Compute word-level Jaccard similarity between two texts."""
    words_a = set(re.findall(r'\w+', text_a.lower()))
    words_b = set(re.findall(r'\w+', text_b.lower()))
    if not words_a or not words_b:
        return 0.0
    intersection = words_a & words_b
    union = words_a | words_b
    return len(intersection) / len(union)
