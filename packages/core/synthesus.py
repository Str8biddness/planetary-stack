"""Synthesus 2.0 - Main Engine Class"""
import asyncio
import logging
from pathlib import Path
from typing import Optional, Dict, Any

from synth_runtime import SynthRuntime
from reasoning_core import ReasoningCore
from rag_pipeline import RAGPipeline
from pattern_engine import PatternEngine
from memory_store import MemoryStore
from hemisphere_bridge import HemisphereBridge
from character_factory import CharacterFactory

logger = logging.getLogger(__name__)


class Synthesus:
    """AIVM Synthesus 2.0 - Dual-Hemisphere Synthetic Intelligence Engine"""

    VERSION = "2.0.0"

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        """
        Initializes the Synthesus engine with the given configuration.

        Args:
            config: An optional dictionary containing configuration settings for
                various subsystems (memory, patterns, reasoning, etc.).
        """
        self.config = config or {}
        self._initialized = False
        self.runtime: Optional[SynthRuntime] = None
        self.reasoning: Optional[ReasoningCore] = None
        self.rag: Optional[RAGPipeline] = None
        self.pattern_engine: Optional[PatternEngine] = None
        self.memory: Optional[MemoryStore] = None
        self.bridge: Optional[HemisphereBridge] = None
        self.character_factory: Optional[CharacterFactory] = None
        logger.info(f"Synthesus {self.VERSION} instantiated")

    def initialize(self) -> bool:
        """Initialize all engine subsystems."""
        try:
            logger.info("Initializing Synthesus engine...")
            self.memory = MemoryStore(self.config.get("memory", {}))
            self.pattern_engine = PatternEngine(self.config.get("patterns", {}))
            self.reasoning = ReasoningCore(self.config.get("reasoning", {}))
            self.rag = RAGPipeline(self.config.get("rag", {}))
            self.bridge = HemisphereBridge(
                left_config=self.config.get("left_hemisphere", {}),
                right_config=self.config.get("right_hemisphere", {})
            )
            self.character_factory = CharacterFactory(
                pattern_engine=self.pattern_engine,
                memory_store=self.memory
            )
            self.runtime = SynthRuntime(
                bridge=self.bridge,
                memory=self.memory,
                reasoning=self.reasoning
            )
            self._initialized = True
            logger.info("Synthesus engine initialized successfully")
            return True
        except Exception as e:
            logger.error(f"Failed to initialize Synthesus: {e}")
            return False

    async def process(self, input_text: str, character_id: str = "default") -> Dict[str, Any]:
        """Process input through the dual-hemisphere pipeline."""
        if not self._initialized:
            raise RuntimeError("Synthesus not initialized. Call initialize() first.")
        return await self.runtime.process_input(input_text, character_id)

    def spawn_character(self, archetype: str, name: str, **kwargs) -> Dict[str, Any]:
        """Spawn a new NPC character from an archetype."""
        if not self._initialized:
            raise RuntimeError("Synthesus not initialized.")
        return self.character_factory.create(archetype=archetype, name=name, **kwargs)

    def shutdown(self):
        """Gracefully shut down the engine."""
        if self.runtime:
            self.runtime.shutdown()
        self._initialized = False
        logger.info("Synthesus engine shut down")

    def __repr__(self) -> str:
        """
        Returns a string representation of the Synthesus engine instance.

        Returns:
            A string indicating the version and initialization status.
        """
        status = "initialized" if self._initialized else "uninitialized"
        return f"<Synthesus v{self.VERSION} [{status}]>"