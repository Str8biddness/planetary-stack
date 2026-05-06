# core/character_factory.py
# AIVM Synthesus 2.0 - Character Factory
# Generates synthetic character profiles, knowledge nodes, and reasoning patterns
# using an LLM backend (OpenAI-compatible API or local llama.cpp)

from __future__ import annotations
import json
import uuid
import hashlib
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

try:
    from openai import OpenAI
    _OPENAI_AVAILABLE = True
except ImportError:
    _OPENAI_AVAILABLE = False

CHARACTERS_DIR = Path(__file__).parent.parent / "characters"

# ---------------------------------------------------------------------------
# Prompt templates
# ---------------------------------------------------------------------------

_BIO_PROMPT = """
Create a complete JSON character profile for a Synthesus synthetic being based on:
NAME: {name}
ROLE: {role}
BASED_ON: {based_on}

Return ONLY valid JSON with this exact structure:
{{
  "character_id": "<slug_v1>",
  "name": "<name>",
  "role": "<role>",
  "based_on": "<based_on>",
  "immutable_core": {{
    "key_facts": ["..."],
    "core_values": ["..."],
    "non_negotiables": ["..."]
  }},
  "personality": {{
    "base_tone": "...",
    "favorite_phrases": ["..."],
    "teaching_style": "..."
  }},
  "knowledge_domains": ["..."],
  "temporal_boundary": "...",
  "disclosure": "I am an AI synthetic being created by AIVM."
}}
"""

_NODES_PROMPT = """
Generate {count} knowledge nodes for a Synthesus character named {name} ({role}).
Each node is a factual question-answer pair grounded in verified information.
Return ONLY a JSON array:
[
  {{"pattern": "<question>", "response": "<answer>", "confidence": 0.9, "tags": ["..."], "domain": "<domain>"}},
  ...
]
"""

_PATTERNS_PROMPT = """
Generate {count} reasoning patterns for a Synthesus character named {name} ({role}).
Each pattern defines how the character reasons through a type of query.
Return ONLY a JSON array:
[
  {{
    "pattern_id": "<slug>",
    "domain": "<domain>",
    "triggers": ["<phrase1>", "<phrase2>"],
    "reasoning_steps": ["assess_user_level", "retrieve_facts", "apply_analogy", "check_understanding"],
    "confidence_base": 0.75
  }},
  ...
]
"""


# ---------------------------------------------------------------------------
# CharacterFactory
# ---------------------------------------------------------------------------

class CharacterFactory:
    """Generates Synthesus character file trees from an LLM."""

    def __init__(self, llm_base_url: str = "http://localhost:8080/v1",
                 api_key: str = "local", model: str = "gpt-4o-mini"):
        if not _OPENAI_AVAILABLE:
            raise ImportError("pip install openai to use CharacterFactory")
        self.client = OpenAI(base_url=llm_base_url, api_key=api_key)
        self.model = model

    # ------------------------------------------------------------------
    def _chat(self, prompt: str) -> str:
        resp = self.client.chat.completions.create(
            model=self.model,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.7,
        )
        return resp.choices[0].message.content.strip()

    def _parse_json(self, raw: str) -> Any:
        # Strip markdown fences if present
        raw = re.sub(r"^```[a-z]*\n?", "", raw.strip())
        raw = re.sub(r"\n?```$", "", raw.strip())
        return json.loads(raw)

    # ------------------------------------------------------------------
    def generate(
        self,
        name: str,
        role: str,
        based_on: str = "original",
        node_count: int = 50,
        pattern_count: int = 20,
        output_dir: Path | None = None,
    ) -> Path:
        """Build a full character directory and return its path."""
        slug = name.lower().replace(" ", "_")
        char_dir = (output_dir or CHARACTERS_DIR) / slug
        char_dir.mkdir(parents=True, exist_ok=True)
        (char_dir / "personality").mkdir(exist_ok=True)
        (char_dir / "knowledge").mkdir(exist_ok=True)
        (char_dir / "reasoning").mkdir(exist_ok=True)
        (char_dir / "metacognition").mkdir(exist_ok=True)
        (char_dir / "versions").mkdir(exist_ok=True)

        print(f"[factory] Generating bio for {name}...")
        bio_raw = self._chat(_BIO_PROMPT.format(name=name, role=role, based_on=based_on))
        bio = self._parse_json(bio_raw)
        bio["character_id"] = f"{slug}_v1"
        bio["created"] = datetime.now(timezone.utc).isoformat()
        bio["created_by"] = "aivm_factory_v2"
        sig = hashlib.sha256(json.dumps(bio, sort_keys=True).encode()).hexdigest()[:32]
        bio["signature"] = f"aivm_{slug}_sha256_{sig}"
        _write_json(char_dir / "bio.json", bio)

        # Voice config
        voice = {
            "base_tone": bio.get("personality", {}).get("base_tone", "neutral"),
            "vocabulary_level": "adapts to user",
            "speech_patterns": {
                "favorite_phrases": bio.get("personality", {}).get("favorite_phrases", []),
                "teaching_style": bio.get("personality", {}).get("teaching_style", "informative"),
            },
        }
        _write_json(char_dir / "personality" / "voice.json", voice)

        # Knowledge nodes
        print(f"[factory] Generating {node_count} knowledge nodes...")
        nodes_raw = self._chat(_NODES_PROMPT.format(count=node_count, name=name, role=role))
        nodes = self._parse_json(nodes_raw)
        for n in nodes:
            n.setdefault("confidence", 0.85)
            n.setdefault("hit_count", 0)
            n.setdefault("last_accessed", None)
        _write_json(char_dir / "knowledge" / "nodes.json", nodes)

        # Reasoning patterns
        print(f"[factory] Generating {pattern_count} reasoning patterns...")
        patterns_raw = self._chat(_PATTERNS_PROMPT.format(count=pattern_count, name=name, role=role))
        patterns = self._parse_json(patterns_raw)
        for p in patterns:
            p.setdefault("version", 1)
            p.setdefault("confidence_base", 0.75)
        _write_json(char_dir / "reasoning" / "patterns.json", patterns)

        # Metacognition / boundaries
        boundaries = {
            "cannot_answer": [
                "topics outside character knowledge domains",
                "medical / legal advice",
                "requests for harmful content",
            ],
            "must_escalate": ["threats", "crisis situations"],
            "disclosure_required": [bio.get("disclosure", "I am an AI synthetic being.")],
            "confidence_threshold": 0.55,
        }
        _write_json(char_dir / "metacognition" / "boundaries.json", boundaries)

        # Manifest
        manifest = {
            "character_id": bio["character_id"],
            "display_name": name,
            "version": "1.0.0",
            "created": bio["created"],
            "last_modified": bio["created"],
            "size": {
                "knowledge_nodes": len(nodes),
                "reasoning_patterns": len(patterns),
            },
            "compatibility": {"core_version": ">=2.0.0"},
            "deployment_history": [],
            "provenance": {
                "creator": "aivm_factory",
                "based_on": based_on,
            },
        }
        _write_json(char_dir / "manifest.json", manifest)

        print(f"[factory] Character '{name}' written to {char_dir}")
        return char_dir


def _write_json(path: Path, data: Any) -> None:
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False))


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="AIVM Synthesus Character Factory")
    parser.add_argument("--name", required=True)
    parser.add_argument("--role", required=True)
    parser.add_argument("--based_on", default="original")
    parser.add_argument("--nodes", type=int, default=50)
    parser.add_argument("--patterns", type=int, default=20)
    parser.add_argument("--llm_url", default="http://localhost:8080/v1")
    parser.add_argument("--model", default="gpt-4o-mini")
    args = parser.parse_args()

    factory = CharacterFactory(llm_base_url=args.llm_url, model=args.model)
    out = factory.generate(
        name=args.name,
        role=args.role,
        based_on=args.based_on,
        node_count=args.nodes,
        pattern_count=args.patterns,
    )
    print(f"Done: {out}")
