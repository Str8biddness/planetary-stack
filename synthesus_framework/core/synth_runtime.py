# core/synth_runtime.py
# Synthesus 2.0 - Synth Runtime
# Top-level runtime that wires all subsystems and exposes a clean public API

from __future__ import annotations

import asyncio
import json
import logging
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from .hemisphere_bridge import HemisphereBridge
from .pattern_engine import PatternEngine
from .els_bridge import ELSBridge
from .memory_store import MemoryStore
from .knowledge_cloud import KnowledgeCloud
from .universal_substrate import UniversalSubstrate
from .reasoning_core import ReasoningCore, ReasoningResult
from kernel.hardware_cloud_bridge import create_bridged_emul_engine
from kernel.quantum_simulator_bridge import QuantumSimulatorBridge
from .web_scraper import WebScraper
from .manifestation_engine import ManifestationEngine
from .vpu_coordinator import VpuCoordinator
from .sllm_coordinator import SllmCoordinator
from kernel.mirror_sync_bridge import MirrorSyncBridge

logger = logging.getLogger(__name__)

PROJ_ROOT = Path(__file__).resolve().parent.parent

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
        knowledge_cloud: Optional[KnowledgeCloud] = None,
        substrate: Optional[UniversalSubstrate] = None,
    ):
        self.characters_dir = Path(characters_dir)
        self.data_dir = Path(data_dir)
        self.left_model = left_model
        self.right_model = right_model
        self.characters_dir.mkdir(parents=True, exist_ok=True)
        self.data_dir.mkdir(parents=True, exist_ok=True)

        # AIOS Hardware Layer
        self._emul_engine = None
        self._host_profile = {}
        try:
            # Paths relative to framework root (where data_dir is)
            self._emul_engine = create_bridged_emul_engine(
                top_k=5,
                index_path=self.data_dir / "knowledge_cache" / "faiss.index",
                metadata_path=self.data_dir / "knowledge_cache" / "faiss_metadata.json",
                model_dir=self.data_dir / "knowledge_cache" / "models",
            )
            if self._emul_engine.initialize():
                host_map = self._emul_engine.get_host_map()
                self._host_profile = {
                    "cpu": {
                        "model": host_map.cpu.model,
                        "cores": host_map.cpu.cores,
                        "features": list(host_map.cpu.features),
                    },
                    "memory": {
                        "total_mb": host_map.memory.total_ram_mb,
                        "free_mb": 0, # Not yet bound in C++
                    }
                }
                logger.info("AIOS Hardware Layer initialized: %s", self._host_profile["cpu"]["model"])

                # Initialize AIOS Devices
                try:
                    import _synthesus_kernel as kernel
                    self._vqd = kernel.VirtualQuantumDevice(0xF1000000, 0x1000)
                    self._vqd_bridge = QuantumSimulatorBridge()
                    self._vqd.set_executor(self._vqd_bridge.execute)
                    logger.info("AIOS Virtual Quantum Device active")
                except Exception as q_exc:
                    logger.warning("VQD initialization failed: %s", q_exc)
                    self._vqd = None
                
                # Attach Cloud Ingress (VND) Handler
                self._scraper = WebScraper()
                def _handle_vnd_search(query: str):
                    asyncio.create_task(self._process_vnd_ingress(query))
                self._emul_engine.set_network_handler(_handle_vnd_search)
                logger.info("AIOS Cloud Ingress handler attached")

                # Attach Mirror Sync (VMD) Handler
                self._mirror = MirrorSyncBridge()
                def _handle_vmd_trigger():
                    self._mirror.trigger_sync()
                self._emul_engine.set_sync_handler(_handle_vmd_trigger)
                self._mirror.set_callback(lambda s, t: self._emul_engine.update_sync_state(s, t))
                logger.info("AIOS Mirror Sync handler attached")

                # Initialize Manifestation Engine (The Freezer)
                self._manifestation = ManifestationEngine(
                    framework_root=Path(__file__).resolve().parent.parent,
                    iso_root=Path("/home/dakin/customiso")
                )

                # Initialize VPU Swarm Coordinator
                self._vpu_coordinator = VpuCoordinator(self._emul_engine)
                self._vpu_coordinator.initialize_swarm()

                # Initialize SLLM (Synthetic LLM) Coordinator
                self._sllm_coordinator = SllmCoordinator(self._emul_engine)
                self._sllm_coordinator.initialize_sllm()

        except Exception as exc:
            logger.warning("AIOS Hardware Layer unavailable: %s", exc)

        # Shared subsystems
        self._pattern_engine = PatternEngine(db_path=str(self.data_dir / "patterns.db"))
        self._els_bridge = ELSBridge(
            db_path=str(self.data_dir / "interactions.db"),
            patterns_path=str(self.data_dir / "candidate_patterns.json"),
        )
        self._memory_store = MemoryStore(db_path=str(self.data_dir / "memory.db"))
        self._knowledge_cloud = knowledge_cloud
        self._substrate = substrate
        if self._knowledge_cloud is None:
            try:
                self._knowledge_cloud = KnowledgeCloud(
                    data_dir=str(self.data_dir / "knowledge_cloud"),
                    vqd=getattr(self, "_vqd", None)
                )
            except Exception as exc:
                logger.warning("KnowledgeCloud unavailable: %s", exc)
                self._knowledge_cloud = None
        if self._substrate is None:
            try:
                self._substrate = UniversalSubstrate(
                    local_data_dir=str(self.data_dir),
                    local_char_dir=str(self.characters_dir),
                    knowledge_cloud_dir=str(self.data_dir / "knowledge_cloud"),
                )
            except Exception as exc:
                logger.warning("UniversalSubstrate unavailable: %s", exc)
                self._substrate = None
        self._hemisphere_bridge = HemisphereBridge()

        # Per-character reasoning cores (lazy)
        self._cores: Dict[str, ReasoningCore] = {}
        self._conversation_cores: Dict[str, Any] = {}

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
        for name in ("bio.json", "manifest.json", "knowledge.json", "patterns.json", "personality.json"):
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

    async def _process_vnd_ingress(self, query: str):
        """Asynchronously fulfill a VND search request and update the Knowledge Cloud."""
        if not self._scraper or not self._knowledge_cloud:
            return

        logger.info(f"CloudIngress: Processing query from VND -> {query}")
        try:
            article = await self._scraper.scrape(query)
            if article:
                # 1. Create KnowledgeEntry
                from .knowledge_cloud import KnowledgeEntry
                entry = KnowledgeEntry(
                    entity_id=f"ingress_{int(time.time())}",
                    entity=article.title,
                    description=article.summary,
                    facts=article.facts,
                    tags=["cloud_ingress", "real_time"],
                    updated_at=time.time()
                )
                
                # 2. Inject into Cloud
                self._knowledge_cloud.upsert_entry(entry)
                
                # 3. DMA-Transfer to VPD
                if self._emul_engine:
                    self._emul_engine.map_parameter(entry.entity_id)
                
                logger.info(f"CloudIngress: Successfully distilled '{article.title}' into AI memory")
            
            # Reset VND Status to Ready (2)
            if self._emul_engine:
                self._emul_engine.set_network_status(2)
                
        except Exception as e:
            logger.error(f"CloudIngress: Failed to process query '{query}': {e}")
            if self._emul_engine:
                self._emul_engine.set_network_status(3) # Error

    def respond(
        self,
        character_id: str,
        user_input: str,
        context: Optional[str] = None,
        session_id: Optional[str] = None,
    ) -> ReasoningResult:
        """Main inference endpoint. Returns a full ReasoningResult."""
        core = self._get_core(character_id)
        if hasattr(core, "set_shared_layers"):
            core.set_shared_layers(
                knowledge_cloud=self._knowledge_cloud,
                substrate=self._substrate,
                memory_store=self._memory_store,
            )

        memory_context = self._build_memory_context(character_id, user_input)
        knowledge_context = self._build_knowledge_context(character_id, user_input)
        parameter_context = self._build_parameter_context(character_id)
        hardware_context = self._build_hardware_context()
        merged_context = self._merge_contexts(context, memory_context, knowledge_context, parameter_context, hardware_context)

        conversational_core = self._get_conversational_engine(character_id)
        if conversational_core is not None:
            async def _invoke_conversational():
                outcome = conversational_core.process_query(
                    player_id=character_id,
                    query=user_input,
                    thinking_layer_available=False,
                    ml_context={"runtime_context": merged_context or ""},
                )
                if hasattr(outcome, "__await__"):
                    outcome = await outcome
                return outcome

            try:
                asyncio.get_running_loop()
            except RuntimeError:
                outcome = asyncio.run(_invoke_conversational())
            else:
                with ThreadPoolExecutor(max_workers=1) as executor:
                    outcome = executor.submit(asyncio.run, _invoke_conversational()).result()

            if isinstance(outcome, dict):
                response_text = str(outcome.get("response") or outcome.get("text") or "")
                latency_ms = float(outcome.get("latency_ms") or 0.0)
                result = ReasoningResult(
                    session_id=session_id or str(datetime.now(timezone.utc).timestamp()),
                    character_id=character_id,
                    query=user_input,
                    final_response=response_text,
                    steps=[],
                    total_latency_ms=latency_ms,
                    success=True,
                    metadata={
                        "source": outcome.get("source", "cognitive_engine"),
                        "confidence": outcome.get("confidence", 0.0),
                        "debug": outcome.get("debug", {}),
                    },
                )
                self.remember_episodic(
                    character_id=character_id,
                    content=f"User: {user_input}\nSynth: {result.final_response}",
                    importance=0.5,
                )
                return result

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

    def _build_knowledge_context(self, character_id: str, query: str, top_k: int = 3) -> str:
        """Build a compact shared-knowledge summary for the reasoning prompt."""
        if self._knowledge_cloud is None:
            return ""
        try:
            results = self._knowledge_cloud.lookup_multi(query, top_k=top_k, trust=0.0)
        except Exception:
            return ""
        if not results:
            return ""
        lines: List[str] = []
        for result in results:
            entity = result.get("entity_name") or result.get("entity_id") or "unknown"
            response = (result.get("response") or "").strip()
            facts = result.get("facts") or []
            fact_text = "; ".join(str(f) for f in facts[:3] if f)
            line = f"- {entity}: {response}" if response else f"- {entity}"
            if fact_text:
                line += f" | facts: {fact_text}"
            lines.append(line)
        return "--- Knowledge Cloud ---\n" + "\n".join(lines)

    def _build_parameter_context(self, character_id: str) -> str:
        """Build a compact shared-parameter summary for the reasoning prompt."""
        if self._substrate is None:
            return ""
        snippets: List[str] = []
        for namespace in ("bio", "patterns", "knowledge", "personality"):
            try:
                entry = self._substrate.get_parameter(f"char_{character_id}.{namespace}")
            except Exception:
                entry = None
            if not entry or not isinstance(entry, dict):
                continue
            value = entry.get("value")
            if value is None:
                continue
            if isinstance(value, (dict, list)):
                preview = json.dumps(value, ensure_ascii=False)[:300]
            else:
                preview = str(value)[:300]
            snippets.append(f"- {namespace}: {preview}")
        if not snippets:
            return ""
        return "--- Parameter Cloud ---\n" + "\n".join(snippets)

    def _build_hardware_context(self) -> str:
        """Build a compact hardware-awareness summary for the reasoning prompt."""
        if not self._host_profile:
            return ""
        
        cpu = self._host_profile.get("cpu", {})
        mem = self._host_profile.get("memory", {})
        
        features = ", ".join(cpu.get("features", [])[:10])
        if len(cpu.get("features", [])) > 10:
            features += "..."

        lines = [
            f"- CPU: {cpu.get('model', 'Unknown')} ({cpu.get('cores', 0)} cores)",
            f"- Features: {features}",
            f"- Memory: {mem.get('total_mb', 0)}MB total, {mem.get('free_mb', 0)}MB free",
        ]
        
        return "--- AIOS Hardware Profile ---\n" + "\n".join(lines)

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


    def get_shared_layers(self) -> Dict[str, Any]:
        return {
            "knowledge_cloud": self._knowledge_cloud,
            "substrate": self._substrate,
            "pattern_engine": self._pattern_engine,
            "memory_store": self._memory_store,
        }

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
        core = self._cores[character_id]
        if hasattr(core, "knowledge_cloud"):
            core.knowledge_cloud = self._knowledge_cloud
        if hasattr(core, "substrate"):
            core.substrate = self._substrate
        return core

    def _get_conversational_engine(self, character_id: str):
        """Load a character genome-backed cognitive engine for direct conversation when available."""
        if character_id in self._conversation_cores:
            return self._conversation_cores[character_id]

        char_dir = self._character_dir(character_id)
        if not char_dir.exists():
            return None

        loaded = self.load_character(character_id)
        if not loaded or "bio" not in loaded:
            return None

        patterns = loaded.get("patterns") or {}
        if not patterns:
            return None

        try:
            from cognitive.cognitive_engine import CognitiveEngine
            engine = CognitiveEngine(
                character_id=character_id,
                bio=loaded.get("bio", {}),
                patterns=patterns,
                persist_dir=str(self.data_dir / "characters" / character_id),
                char_dir=str(char_dir),
                substrate=self._substrate,
                knowledge_cloud=self._knowledge_cloud,
            )
            if hasattr(engine, "set_shared_layers"):
                engine.set_shared_layers(
                    knowledge_cloud=self._knowledge_cloud,
                    substrate=self._substrate,
                    memory_store=self._memory_store,
                )
            self._conversation_cores[character_id] = engine
            return engine
        except Exception as exc:
            logger.warning("Conversation engine unavailable for %s: %s", character_id, exc)
            return None


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
