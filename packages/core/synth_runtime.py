# core/synth_runtime.py
# Synthesus 2.0 - Synth Runtime
# Top-level runtime that wires all subsystems and exposes a clean public API

from __future__ import annotations

import asyncio
import json
import logging
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from hemisphere_bridge import HemisphereBridge
from pattern_engine import PatternEngine
from els_bridge import ELSBridge
# Knowledge package imports
import sys
from pathlib import Path
PROJ_ROOT_LIB = Path(__file__).resolve().parent.parent.parent
if str(PROJ_ROOT_LIB / "packages" / "knowledge") not in sys.path:
    sys.path.insert(0, str(PROJ_ROOT_LIB / "packages" / "knowledge"))
if str(PROJ_ROOT_LIB / "packages" / "reasoning") not in sys.path:
    sys.path.insert(0, str(PROJ_ROOT_LIB / "packages" / "reasoning"))
if str(PROJ_ROOT_LIB / "packages" / "kernel") not in sys.path:
    sys.path.insert(0, str(PROJ_ROOT_LIB / "packages" / "kernel"))
if str(PROJ_ROOT_LIB / "packages" / "aivm") not in sys.path:
    sys.path.insert(0, str(PROJ_ROOT_LIB / "packages" / "aivm"))

from memory_store import MemoryStore
from knowledge_cloud import KnowledgeCloud
from universal_substrate import UniversalSubstrate
from reasoning_core import ReasoningCore, ReasoningResult
from hardware_cloud_bridge import create_bridged_emul_engine
from quantum_simulator_bridge import QuantumSimulatorBridge
from web_scraper import WebScraper
from manifestation_engine import ManifestationEngine
from vpu_coordinator import VpuCoordinator
from sllm_coordinator import SllmCoordinator
from hybrid_transformer_coordinator import HybridTransformerCoordinator
from mirror_sync_bridge import MirrorSyncBridge

# AIVM Kernel imports
from aivm.kernel.core import AIVMKernel
from aivm.kernel.types import PersonaIdentity, SchedulerClass, PermissionLevel

logger = logging.getLogger(__name__)

PROJ_ROOT = Path(__file__).resolve().parent.parent

# ---------------------------------------------------------------------------
# SynthRuntime
# ---------------------------------------------------------------------------

class SynthRuntime:
    """
    Synthesus 2.0 top-level runtime.
    Now powered by the formal AIVM Kernel (Contract v0.1).
    """

    def __init__(
        self,
        data_dir: Optional[str] = None,
        characters_dir: Optional[str] = None,
        knowledge_cloud: Optional[KnowledgeCloud] = None,
        substrate: Optional[UniversalSubstrate] = None,
        left_model: str = "left",
        right_model: str = "right",
        guest_mode: bool = False,
    ):
        self.data_dir = Path(data_dir) if data_dir else PROJ_ROOT / "data"
        self.characters_dir = Path(characters_dir) if characters_dir else PROJ_ROOT / "characters"
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.characters_dir.mkdir(parents=True, exist_ok=True)

        self.left_model = left_model
        self.right_model = right_model
        self.guest_mode = guest_mode

        # Initialize Core Agentic Tools (Available to AIVM Kernel)
        self._scraper = WebScraper()
        self._manifestation = ManifestationEngine(
            framework_root=Path(__file__).resolve().parent.parent,
            iso_root=Path("/home/dakin/customiso")
        )

        # AIOS Hardware Integration (EmulEngine)
        try:
            self._emul_engine = create_bridged_emul_engine()
            if self._emul_engine.initialize():
                self._host_profile = self._emul_engine.get_host_map()
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
                
                # Attach Tool Handlers (Disabled for direct access in Guest Mode)
                if not self.guest_mode:
                    def _handle_vnd_search(query: str):
                        asyncio.create_task(self._process_vnd_ingress(query))
                    self._emul_engine.set_network_handler(_handle_vnd_search)
                    logger.info("AIOS Cloud Ingress (VND) active")

                    # Initialize Swarm Orchestrators
                    self._vpu_coordinator = VpuCoordinator(self._emul_engine)
                    self._vpu_coordinator.initialize_swarm()
                    self._sllm_coordinator = SllmCoordinator(self._emul_engine)
                    self._sllm_coordinator.initialize_sllm()
                    self._hybrid_transformer = HybridTransformerCoordinator(self._emul_engine)
                    self._hybrid_transformer.initialize_vad()
                else:
                    logger.info("AIOS Agentic Tools DISABLED for direct access (Guest Mode)")

                # Attach Mirror Sync (VMD) Handler (Global sync is allowed)
                self._mirror = MirrorSyncBridge()
                def _handle_vmd_trigger():
                    self._mirror.trigger_sync()
                self._emul_engine.set_sync_handler(_handle_vmd_trigger)
                self._mirror.set_callback(lambda s, t: self._emul_engine.update_sync_state(s, t))
                logger.info("AIOS Mirror Sync handler attached")

        except Exception as exc:
            logger.warning("AIOS Hardware Layer unavailable: %s", exc)

        # Shared subsystems
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

        # --- THE SPINE: AIVM Kernel ---
        self._aivm_kernel = AIVMKernel(
            knowledge_cloud=self._knowledge_cloud,
            memory_store=self._memory_store,
            manifestation_engine=self._manifestation,
            scraper=self._scraper,
            safe_mode=self.guest_mode # Enforce contract §10 on ISO
        )

        self._pattern_engine = PatternEngine(db_path=str(self.data_dir / "patterns.db"))
        self._els_bridge = ELSBridge(
            db_path=str(self.data_dir / "interactions.db"),
            patterns_path=str(self.data_dir / "candidate_patterns.json"),
        )
        self._hemisphere_bridge = HemisphereBridge()

        # Per-character reasoning cores (lazy)
        self._cores: Dict[str, ReasoningCore] = {}
        self._conversation_cores: Dict[str, Any] = {}

        logger.info("SynthRuntime (AIVM-Native) initialized")

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
        return self.characters_dir / character_id

    def _write_json(self, path: Path, data: Dict[str, Any]) -> None:
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

        # Create formal AIVM NPC Node
        identity = PersonaIdentity(id=character_id, name=name, archetype=archetype)
        permission = PermissionLevel.AGENT if kwargs.get("permission") == "agent" else PermissionLevel.GUEST
        self._aivm_kernel.spawn_npc(
            identity, 
            scheduler=SchedulerClass.REALTIME_SUPPORTING,
            permission=permission
        )

        return {"character_id": character_id, "path": str(char_dir), "bio": bio, "manifest": manifest}

    def load_character(self, character_id: str) -> Optional[Dict[str, Any]]:
        char_dir = self._character_dir(character_id)
        if not char_dir.exists():
            return None
        loaded: Dict[str, Any] = {"character_id": character_id, "path": str(char_dir)}
        for name in ("bio.json", "manifest.json", "knowledge.json", "patterns.json", "personality.json"):
            file_path = char_dir / name
            if file_path.exists():
                loaded[name[:-5]] = json.loads(file_path.read_text(encoding="utf-8"))
        
        # Ensure NPC is spawned in kernel if loaded
        if character_id not in self._aivm_kernel._npcs:
            bio = loaded.get("bio", {})
            identity = PersonaIdentity(
                id=character_id, 
                name=bio.get("name", character_id), 
                archetype=bio.get("archetype", "default")
            )
            # Authorization & Priority
            perm_str = bio.get("permission") or bio.get("aivm_metadata", {}).get("permission_level", "guest")
            permission = PermissionLevel.AGENT if perm_str == "agent" else PermissionLevel.GUEST
            
            sched_str = bio.get("scheduler") or bio.get("aivm_metadata", {}).get("scheduler_class", "realtime_supporting")
            try:
                scheduler = SchedulerClass(sched_str)
            except ValueError:
                scheduler = SchedulerClass.REALTIME_SUPPORTING

            self._aivm_kernel.spawn_npc(identity, permission=permission, scheduler=scheduler)

        return loaded

    def list_characters(self) -> List[str]:
        if not self.characters_dir.exists():
            return []
        return sorted([p.name for p in self.characters_dir.iterdir() if p.is_dir()])

    # ------------------------------------------------------------------
    # Inference
    # ------------------------------------------------------------------

    async def _process_vnd_ingress(self, query: str):
        if not self._scraper or not self._knowledge_cloud:
            return

        try:
            article = await self._scraper.scrape(query)
            if article:
                from knowledge_cloud import KnowledgeEntry
                entry = KnowledgeEntry(
                    entity_id=f"ingress_{int(time.time())}",
                    entity=article.title,
                    description=article.summary,
                    facts=article.facts,
                    tags=["cloud_ingress", "real_time"],
                    updated_at=time.time()
                )
                self._knowledge_cloud.upsert_entry(entry)
                if self._emul_engine:
                    self._emul_engine.map_parameter(entry.entity_id)
            if self._emul_engine:
                self._emul_engine.set_network_status(2)
        except Exception:
            if self._emul_engine:
                self._emul_engine.set_network_status(3)

    async def respond_async(
        self,
        character_id: str,
        user_input: str,
        context: Optional[str] = None,
        session_id: Optional[str] = None,
    ) -> ReasoningResult:
        """Main inference endpoint using the AIVM Kernel (Async)."""
        core = self._get_core(character_id)
        if hasattr(core, "set_shared_layers"):
            core.set_shared_layers(
                knowledge_cloud=self._knowledge_cloud,
                substrate=self._substrate,
                memory_store=self._memory_store,
            )
        
        # Ensure NPC is spawned in kernel
        if character_id not in self._aivm_kernel._npcs:
            self.load_character(character_id)

        # Execute Canonical 12-step Tick via AIVM Kernel (Scheduled)
        kernel_res = await self._aivm_kernel.tick_scheduled(character_id, {
            "user_input": user_input,
            "session_id": session_id,
            "context": context
        })

        # Map kernel result back to ReasoningResult for UI compatibility
        return ReasoningResult(
            session_id=session_id or str(time.time()),
            character_id=character_id,
            query=user_input,
            final_response=kernel_res.get("response", ""),
            success=(kernel_res.get("status") == "success"),
            metadata=kernel_res.get("metadata", {})
        )

    def respond(
        self,
        character_id: str,
        user_input: str,
        context: Optional[str] = None,
        session_id: Optional[str] = None,
    ) -> ReasoningResult:
        """Synchronous wrapper for respond_async."""
        try:
            loop = asyncio.get_running_loop()
            return loop.run_until_complete(self.respond_async(character_id, user_input, context, session_id))
        except RuntimeError:
            return asyncio.run(self.respond_async(character_id, user_input, context, session_id))

    # ------------------------------------------------------------------
    # Memory (Delegates to formal VMD if possible)
    # ------------------------------------------------------------------

    def remember(
        self,
        character_id: str,
        content: str,
        memory_type: str = "semantic",
        importance: float = 0.7,
        tags: Optional[List[str]] = None,
    ) -> None:
        npc = self._aivm_kernel._npcs.get(character_id)
        if npc and "VMD" in npc.mounted_devices:
            npc.mounted_devices["VMD"].write(content, memory_type, importance)
        else:
            self._memory_store.store(character_id, content, memory_type, importance, tags)

    def remember_episodic(self, character_id: str, content: str, importance: float = 0.5):
        self.remember(character_id, content, "episodic", importance)

    def remember_semantic(self, character_id: str, content: str, importance: float = 0.7):
        self.remember(character_id, content, "semantic", importance)

    def remember_procedural(self, character_id: str, content: str, importance: float = 0.7):
        self.remember(character_id, content, "procedural", importance)

    def remember_working(self, character_id: str, content: str, importance: float = 0.3):
        self.remember(character_id, content, "working", importance)

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _get_core(self, character_id: str) -> ReasoningCore:
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
        return core

    def _get_conversational_engine(self, character_id: str) -> Any:
        return self._conversation_cores.get(character_id)
