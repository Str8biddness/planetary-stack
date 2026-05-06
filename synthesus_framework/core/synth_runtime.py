# core/synth_runtime.py
# Synthesus 2.0 - Synth Runtime
# Top-level runtime that wires all subsystems and exposes a clean public API

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from .hemisphere_bridge import HemisphereBridge
from .pattern_engine import PatternEngine
from .els_bridge import ELSBridge
from .memory_store import MemoryStore
from .reasoning_core import ReasoningCore, ReasoningResult

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# SynthRuntime
# ---------------------------------------------------------------------------

class SynthRuntime:
    """
    Synthesus 2.0 top-level runtime.

    Usage:
        runtime = SynthRuntime()
        runtime.create_character("synth", "Synth", "default")
        result = runtime.respond("synth", "Hello, tell me about reasoning.")
        print(result.final_response)
    """

    def __init__(
        self,
        characters_dir: str = "characters",
        data_dir: str = "data",
        left_model: str = "left",
        right_model: str = "right",
    ):
        self.characters_dir = Path(characters_dir)
        self.data_dir = data_dir
        self.left_model = left_model
        self.right_model = right_model
        self.characters_dir.mkdir(parents=True, exist_ok=True)

        # Shared subsystems
        self._pattern_engine = PatternEngine(db_path=f"{data_dir}/patterns.db")
        self._els_bridge = ELSBridge(
            db_path=f"{data_dir}/interactions.db",
            patterns_path=f"{data_dir}/candidate_patterns.json",
        )
        self._memory_store = MemoryStore(db_path=f"{data_dir}/memory.db")
        self._hemisphere_bridge = HemisphereBridge()

        # Per-character reasoning cores (lazy)
        self._cores: Dict[str, ReasoningCore] = {}

        logger.info("SynthRuntime initialized")

    @staticmethod
    def _memory_texts(items: List[Any]) -> List[str]:
        """Normalize memory recall results to plain text."""
        texts: List[str] = []
        for item in items:
            if isinstance(item, str):
                text = item.strip()
            else:
                text = getattr(item, "content", "")
                if isinstance(text, str):
                    text = text.strip()
            if text:
                texts.append(text)
        return texts

    # ------------------------------------------------------------------
    # Character management
    # ------------------------------------------------------------------

    def _character_dir(self, character_id: str) -> Path:
        """Get the directory path for a specific character.
        
        Args:
            character_id (str): The unique identifier of the character.
            
        Returns:
            Path: The directory path object.
        """
        return self.characters_dir / character_id

    def _write_json(self, path: Path, data: Dict[str, Any]) -> None:
        """Helper to write a dictionary to a JSON file.
        
        Args:
            path (Path): The file path to write to.
            data (Dict[str, Any]): The data to serialize.
        """
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")

    def create_character(
        self,
        character_id: str,
        name: str,
        archetype: str = "default",
        traits: Optional[List[str]] = None,
        backstory: str = "",
        **kwargs,
    ) -> Dict[str, Any]:
        char_dir = self._character_dir(character_id)
        char_dir.mkdir(parents=True, exist_ok=True)

        bio = {
            "character_id": character_id,
            "name": name,
            "role": archetype,
            "archetype": archetype,
            "traits": traits or [],
            "backstory": backstory,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "created_by": "synth_runtime",
            "metadata": kwargs,
        }
        manifest = {
            "character_id": character_id,
            "name": name,
            "archetype": archetype,
            "files": ["bio.json", "manifest.json"],
            "created_at": bio["created_at"],
        }
        self._write_json(char_dir / "bio.json", bio)
        self._write_json(char_dir / "manifest.json", manifest)
        return {"character_id": character_id, "path": str(char_dir), "bio": bio, "manifest": manifest}

    def load_character(self, character_id: str) -> Optional[Dict[str, Any]]:
        """Load character bio and manifest from disk.
        
        Args:
            character_id (str): The unique identifier of the character.
            
        Returns:
            Optional[Dict[str, Any]]: Dictionary with character data or None if not found.
        """
        char_dir = self._character_dir(character_id)
        if not char_dir.exists():
            return None
        loaded: Dict[str, Any] = {"character_id": character_id, "path": str(char_dir)}
        for name in ("bio.json", "manifest.json", "knowledge.json"):
            file_path = char_dir / name
            if file_path.exists():
                loaded[name[:-5]] = json.loads(file_path.read_text(encoding="utf-8"))
        return loaded

    def list_characters(self) -> List[str]:
        """List all available character IDs in the characters directory.
        
        Returns:
            List[str]: Sorted list of character IDs.
        """
        if not self.characters_dir.exists():
            return []
        return sorted([p.name for p in self.characters_dir.iterdir() if p.is_dir()])

    # ------------------------------------------------------------------
    # Inference
    # ------------------------------------------------------------------

    def respond(
        self,
        character_id: str,
        user_input: str,
        context: Optional[str] = None,
        session_id: Optional[str] = None,
    ) -> ReasoningResult:
        """Main inference endpoint. Returns a full ReasoningResult."""
        core = self._get_core(character_id)
        memory_context = self._build_memory_context(character_id, user_input)
        merged_context = self._merge_contexts(context, memory_context)
        result = core.reason(
            query=user_input,
            context=merged_context,
            session_id=session_id,
        )

        self.remember_episodic(
            character_id=character_id,
            content=f"User: {user_input}\nSynth: {result.final_response}",
            importance=0.5,
        )

        return result

    # ------------------------------------------------------------------
    # Memory
    # ------------------------------------------------------------------

    def remember(
        self,
        character_id: str,
        content: str,
        memory_type: str = "semantic",
        importance: float = 0.7,
        tags: Optional[List[str]] = None,
    ) -> None:
        """Route a memory to the appropriate layer in the memory store.
        
        Args:
            character_id (str): The character ID.
            content (str): The memory content.
            memory_type (str): Layer to store in ('episodic', 'semantic', 'procedural', 'working').
            importance (float): Memory importance weight [0.0, 1.0].
            tags (Optional[List[str]]): Optional tags for the memory.
        """
        memory_type = (memory_type or "semantic").lower()
        if memory_type == "episodic":
            self.remember_episodic(character_id, content, importance, tags)
        elif memory_type == "procedural":
            self.remember_procedural(character_id, content, importance, tags)
        elif memory_type == "working":
            self.remember_working(character_id, content, importance, tags)
        else:
            self.remember_semantic(character_id, content, importance, tags)

    def remember_episodic(
        self,
        character_id: str,
        content: str,
        importance: float = 0.5,
        tags: Optional[List[str]] = None,
    ) -> None:
        """Store an episodic memory (event history).
        
        Args:
            character_id (str): The character ID.
            content (str): The memory content.
            importance (float): Memory importance weight.
            tags (Optional[List[str]]): Optional tags.
        """
        self._memory_store.store_episodic(character_id, content, importance=importance, tags=tags)

    def remember_semantic(
        self,
        character_id: str,
        content: str,
        importance: float = 0.7,
        tags: Optional[List[str]] = None,
    ) -> None:
        """Store a semantic memory (durable fact).
        
        Args:
            character_id (str): The character ID.
            content (str): The memory content.
            importance (float): Memory importance weight.
            tags (Optional[List[str]]): Optional tags.
        """
        self._memory_store.store_semantic(character_id, content, importance=importance, tags=tags)

    def remember_procedural(
        self,
        character_id: str,
        content: str,
        importance: float = 0.7,
        tags: Optional[List[str]] = None,
    ) -> None:
        """Store a procedural memory (behavioral rule).
        
        Args:
            character_id (str): The character ID.
            content (str): The memory content.
            importance (float): Memory importance weight.
            tags (Optional[List[str]]): Optional tags.
        """
        self._memory_store.store_procedural(character_id, content, importance=importance, tags=tags)

    def remember_working(
        self,
        character_id: str,
        content: str,
        importance: float = 0.3,
        tags: Optional[List[str]] = None,
    ) -> None:
        """Store a working memory (volatile task state).
        
        Args:
            character_id (str): The character ID.
            content (str): The memory content.
            importance (float): Memory importance weight.
            tags (Optional[List[str]]): Optional tags.
        """
        self._memory_store.store_working(character_id, content, importance=importance, tags=tags)

    def recall(
        self,
        character_id: str,
        query: str,
        top_k: int = 5,
        memory_type: Optional[str] = None,
    ) -> List[str]:
        """Recall memories across all or specific layers based on semantic query.
        
        Args:
            character_id (str): The character ID.
            query (str): The semantic search query.
            top_k (int): Number of memories to return.
            memory_type (Optional[str]): Specific layer to search in.
            
        Returns:
            List[str]: List of recalled memory contents.
        """
        if memory_type:
            memories = self._memory_store.recall(
                character_id=character_id,
                query=query,
                memory_type=memory_type,
                top_k=top_k,
            )
        else:
            memories = self._memory_store.recall(
                character_id=character_id,
                query=query,
                top_k=top_k,
            )
        return [m.content for m in memories]

    def recall_episodic(self, character_id: str, query: str, top_k: int = 5) -> List[str]:
        """Recall episodic memories.
        
        Args:
            character_id (str): The character ID.
            query (str): Semantic search query.
            top_k (int): Number of results.
            
        Returns:
            List[str]: List of memory contents.
        """
        return self._memory_texts(self._memory_store.recall_episodic(character_id, query, top_k=top_k))

    def recall_semantic(self, character_id: str, query: str, top_k: int = 5) -> List[str]:
        """Recall semantic memories.
        
        Args:
            character_id (str): The character ID.
            query (str): Semantic search query.
            top_k (int): Number of results.
            
        Returns:
            List[str]: List of memory contents.
        """
        return self._memory_texts(self._memory_store.recall_semantic(character_id, query, top_k=top_k))

    def recall_procedural(self, character_id: str, query: str, top_k: int = 5) -> List[str]:
        """Recall procedural memories.
        
        Args:
            character_id (str): The character ID.
            query (str): Semantic search query.
            top_k (int): Number of results.
            
        Returns:
            List[str]: List of memory contents.
        """
        return self._memory_texts(self._memory_store.recall_procedural(character_id, query, top_k=top_k))

    def recall_working(self, character_id: str, query: str, top_k: int = 5) -> List[str]:
        """Recall working memories.
        
        Args:
            character_id (str): The character ID.
            query (str): Semantic search query.
            top_k (int): Number of results.
            
        Returns:
            List[str]: List of memory contents.
        """
        return self._memory_texts(self._memory_store.recall_working(character_id, query, top_k=top_k))

    def _build_memory_context(self, character_id: str, query: str, top_k: int = 3) -> str:
        """Build a compact memory summary for the reasoning prompt."""
        sections: List[str] = []
        layer_specs = [
            ("Semantic memory", self.recall_semantic(character_id, query, top_k=top_k)),
            ("Episodic memory", self.recall_episodic(character_id, query, top_k=top_k)),
            ("Procedural memory", self.recall_procedural(character_id, query, top_k=top_k)),
            ("Working memory", self.recall_working(character_id, query, top_k=top_k)),
        ]
        for label, items in layer_specs:
            cleaned = [item.strip() for item in items if item and item.strip()]
            if cleaned:
                sections.append(f"--- {label} ---\n" + "\n".join(f"- {item}" for item in cleaned))
        return "\n\n".join(sections)

    @staticmethod
    def _merge_contexts(*parts: Optional[str]) -> Optional[str]:
        """Merge non-empty context fragments into a single prompt context."""
        cleaned = [part.strip() for part in parts if part and part.strip()]
        if not cleaned:
            return None
        return "\n\n".join(cleaned)

    # ------------------------------------------------------------------
    # Pattern management
    # ------------------------------------------------------------------

    def add_pattern(
        self,
        character_id: str,
        trigger: str,
        response_template: str,
        pattern_type: str = "reasoning",
        weight: float = 1.0,
    ) -> None:
        """Manually add a reasoning or response pattern for a character.
        
        Args:
            character_id (str): The character ID.
            trigger (str): Trigger text or pattern.
            response_template (str): Response template.
            pattern_type (str): Pattern category ('reasoning', 'response').
            weight (float): Importance weight [0.0, 1.0].
        """
        self._pattern_engine.add_pattern(
            character_id=character_id,
            pattern_type=pattern_type,
            trigger=trigger,
            response_template=response_template,
            weight=weight,
        )

    def review_candidates(
        self,
        character_id: str,
        approve_all: bool = False,
    ) -> int:
        """Approve pending ELS candidate patterns into the pattern engine."""
        candidates = self._els_bridge.get_candidates(
            character_id=character_id, status="pending"
        )
        approved = []
        for c in candidates:
            if approve_all or c.get("score", 0) > 0.6:
                approved.append(c)
        if approved:
            return self._els_bridge.integrate_patterns(
                character_id=character_id, approved=approved
            )
        return 0

    # ------------------------------------------------------------------
    # Stats
    # ------------------------------------------------------------------

    def stats(self, character_id: str) -> Dict[str, Any]:
        """Retrieve runtime statistics for a character including memory and patterns.
        
        Args:
            character_id (str): The character ID.
            
        Returns:
            Dict[str, Any]: Dictionary containing statistical metrics.
        """
        core = self._get_core(character_id)
        return {
            **core.stats(),
            "memory": self._memory_store.stats(character_id),
        }

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _get_core(self, character_id: str) -> ReasoningCore:
        """Internal helper to get or create a ReasoningCore for a character.
        
        Args:
            character_id (str): The character ID.
            
        Returns:
            ReasoningCore: The active core for the character.
        """
        if character_id not in self._cores:
            self._cores[character_id] = ReasoningCore(
                character_id=character_id,
                hemisphere_bridge=self._hemisphere_bridge,
                pattern_engine=self._pattern_engine,
                els_bridge=self._els_bridge,
                left_model=self.left_model,
                right_model=self.right_model,
            )
        return self._cores[character_id]


# ---------------------------------------------------------------------------
# Module-level convenience
# ---------------------------------------------------------------------------

_default_runtime: Optional[SynthRuntime] = None


def get_runtime(**kwargs) -> SynthRuntime:
    """Return the module-level singleton runtime, creating it if needed."""
    global _default_runtime
    if _default_runtime is None:
        _default_runtime = SynthRuntime(**kwargs)
    return _default_runtime
