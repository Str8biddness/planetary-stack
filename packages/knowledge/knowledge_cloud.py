#!/usr/bin/env python3
"""
Knowledge Cloud — External Semantic Knowledge Repository
AIVM Synthesus 2.0

A shared, semantically searchable knowledge repository that all characters
can query during inference. Unlike per-character knowledge.json files
(which store personal knowledge), the Knowledge Cloud stores world-level
entities: creatures, locations, factions, items, events, and concepts
that any NPC can reference.

Architecture:
  1. Structured knowledge entries stored as JSON in data/knowledge_cloud/
  2. SwarmEmbedder (TF-IDF + SVD) encodes descriptions + facts → 128-dim vectors
  3. FAISS IndexFlatIP for sub-millisecond cosine similarity search
  4. KnowledgeGraph-compatible lookup() interface for cognitive engine integration

Cost: <2ms per search (1000 entries), ~50KB shared embedder, zero GPU.
"""

from __future__ import annotations

import json
import logging
import os
import re
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

import numpy as np

try:
    from knowledge_integration.cloud_sync import bootstrap_knowledge_cache
except Exception:
    bootstrap_knowledge_cache = None


def _should_bootstrap_knowledge_cache(local_root: Path) -> bool:
    """Check if the knowledge cache should be bootstrapped based on directory name.

    Args:
        local_root: The root directory path to check.

    Returns:
        True if the directory name is 'data', False otherwise.
    """
    return local_root.name == "data"


logger = logging.getLogger(__name__)


# ── Data Classes ──────────────────────────────────────────────────────

@dataclass
class KnowledgeEntry:
    """A single knowledge node in the cloud."""
    entity_id: str                          # "dragon", "ironhaven_market"
    entity: str                             # "Dragon" (display name)
    entity_type: str = "concept"            # creature, location, item, faction, event, concept
    description: str = ""                   # Full prose description for NPC responses
    attributes: Dict[str, Any] = field(default_factory=dict)   # {"danger": 9, "rarity": "legendary"}
    facts: List[str] = field(default_factory=list)             # ["Breathes fire", "Guards hoards"]
    relations: Dict[str, Any] = field(default_factory=dict)    # {"weak_to": "ice", "feared_by": "villagers"}
    tags: List[str] = field(default_factory=list)              # ["combat", "lore", "quest"]
    aliases: List[str] = field(default_factory=list)           # ["wyrm", "fire drake"]
    depth: str = "acquainted"               # intimate, familiar, acquainted, rumor
    trust_threshold: float = 0.0            # Trust needed to access (0 = public knowledge)
    agentic_actions: Dict[str, List[str]] = field(default_factory=dict) # {"shop_buy": ["open_shop"]}
    emotion_variants: Dict[str, str] = field(default_factory=dict)  # {"afraid": "...", "friendly": "..."}
    slots: List[str] = field(default_factory=list)  # ["[entity]", "[emotion]"] for slot filling
    updated_at: float = 0.0                # Last refresh time for prioritizing new lore

    def to_dict(self) -> Dict[str, Any]:
        """Convert the KnowledgeEntry to a dictionary.

        Returns:
            A dictionary representation of the knowledge entry.
        """
        return {
            "entity_id": self.entity_id,
            "entity": self.entity,
            "entity_type": self.entity_type,
            "description": self.description,
            "attributes": self.attributes,
            "facts": self.facts,
            "relations": self.relations,
            "tags": self.tags,
            "aliases": self.aliases,
            "depth": self.depth,
            "trust_threshold": self.trust_threshold,
            "agentic_actions": self.agentic_actions,
            "emotion_variants": self.emotion_variants,
            "slots": self.slots,
            "updated_at": self.updated_at,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "KnowledgeEntry":
        """Create a KnowledgeEntry from a dictionary.

        Args:
            data: The dictionary containing knowledge entry data.

        Returns:
            A new KnowledgeEntry instance.
        """
        return cls(
            entity_id=data.get("entity_id", data.get("entity", "unknown").lower().replace(" ", "_")),
            entity=data.get("entity", data.get("display_name", "Unknown")),
            entity_type=data.get("entity_type", "concept"),
            description=data.get("description", ""),
            attributes=data.get("attributes", {}),
            facts=data.get("facts", []),
            relations=data.get("relations", {}),
            tags=data.get("tags", []),
            aliases=data.get("aliases", []),
            depth=data.get("depth", "acquainted"),
            trust_threshold=data.get("trust_threshold", 0.0),
            agentic_actions=data.get("agentic_actions", {}),
            emotion_variants=data.get("emotion_variants", {}),
            slots=data.get("slots", []),
            updated_at=float(data.get("updated_at", data.get("last_updated", 0.0)) or 0.0),
        )

    def get_embedding_text(self) -> str:
        """Composite text used for semantic embedding."""
        parts = [self.entity, self.description]
        parts.extend(self.facts)
        parts.extend(self.aliases)
        for tag in self.tags:
            parts.append(tag)
        return " ".join(p for p in parts if p)


@dataclass
class KnowledgeResult:
    """A search result from the Knowledge Cloud."""
    entry: KnowledgeEntry
    similarity: float           # Cosine similarity score (0-1)
    source: str = "knowledge_cloud"


# ── Depth → Confidence Mapping ───────────────────────────────────────

_DEPTH_CONFIDENCE = {
    "intimate": 0.90,
    "familiar": 0.80,
    "acquainted": 0.70,
    "rumor": 0.55,
    "unknown": 0.30,
}


# ── Main Knowledge Cloud Class ───────────────────────────────────────

class KnowledgeCloud:
    """
    Shared semantic knowledge repository for Synthesus 2.0.

    All characters can query this cloud during inference. The cloud stores
    world-level knowledge (creatures, locations, factions, etc.) that
    supplements each character's personal knowledge graph.

    Usage:
        cloud = KnowledgeCloud(data_dir="data/knowledge_cloud")
        result = cloud.lookup("tell me about dragons", emotion="neutral", trust=50.0)
        # → {"response": "...", "entity_id": "dragon", "confidence": 0.70, ...}
    """

    def __init__(
        self,
        data_dir: str = "data/knowledge_cloud",
        similarity_floor: float = 0.30,
        vqd: Optional[Any] = None,
    ):
        """Initialize the KnowledgeCloud.

        Args:
            data_dir: Directory where knowledge entries are stored.
            similarity_floor: Minimum cosine similarity score for search results.
            vqd: Optional Virtual Quantum Device instance for accelerated ranking.
        """
        self.data_dir = Path(data_dir)
        self.similarity_floor = similarity_floor
        self.vqd = vqd

        # Storage
        self._entries: Dict[str, KnowledgeEntry] = {}
        self._alias_index: Dict[str, str] = {}

        # Embedder / FAISS index
        self._embedder = None
        self._embedder_load_time_ms = 0.0
        self._index = None
        self._index_ids: List[str] = []
        self._enabled = False
        self._build_time_ms = 0.0

        # Stats
        self._total_searches = 0
        self._total_hits = 0
        self._total_misses = 0

        self._load_entries()
        if self._entries:
            self._build_index()

    def _get_embedder(self):
        """Get or initialize the SwarmEmbedder.

        Returns:
            The SwarmEmbedder instance.
        """
        if self._embedder is None:
            start = time.time()
            from ml.swarm_embedder import SwarmEmbedder
            self._embedder = SwarmEmbedder(dim=128)
            self._embedder_load_time_ms = (time.time() - start) * 1000
            logger.info(f"KnowledgeCloud: SwarmEmbedder ready in {self._embedder_load_time_ms:.0f}ms")
        return self._embedder

    def upsert_entry(self, entry: KnowledgeEntry, persist: bool = True):
        """
        Add or update a knowledge entry in the cloud.
        Used by NPCs to record 'witnessed' events (Phase 12).
        """
        entry.updated_at = time.time()
        self._entries[entry.entity_id] = entry
        self._update_alias_index(entry)
        self._build_index()

        if persist:
            self._persist_evolution(entry)

    def _persist_evolution(self, entry: KnowledgeEntry):
        """Append or update a record in evolution.json."""
        evo_path = self.data_dir / "evolution.json"

        data = {"version": "1.0.0", "entries": []}
        if evo_path.exists():
            try:
                data = json.loads(evo_path.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                pass

        # Update existing or append
        entries = data.get("entries", [])
        found = False
        for i, existing in enumerate(entries):
            if existing.get("entity_id") == entry.entity_id:
                entries[i] = entry.to_dict()
                found = True
                break

        if not found:
            entries.append(entry.to_dict())

        data["entries"] = entries
        data["last_updated"] = time.time()

        try:
            evo_path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
        except Exception as e:
            logger.error(f"KnowledgeCloud: Failed to persist evolution: {e}")

    # ── Public API ────────────────────────────────────────────────────

    def lookup(
        self,
        query: str,
        emotion: str = "neutral",
        trust: float = 50.0,
        top_k: int = 1,
        tags_filter: Optional[List[str]] = None,
    ) -> Optional[Dict[str, Any]]:
        """
        KnowledgeGraph-compatible lookup interface.

        Searches the cloud for the most relevant knowledge entry matching
        the query. Returns a response dict compatible with the cognitive
        engine's fallback cascade.

        Args:
            query: Player's message text
            emotion: Current NPC emotion (for variant selection)
            trust: Player trust level (for gated knowledge)
            top_k: Number of candidates to consider
            tags_filter: Optional list of tags to filter by

        Returns:
            {
                "response": str,
                "entity_id": str,
                "entity_name": str,
                "entity_type": str,
                "depth": str,
                "source": "knowledge_cloud",
                "confidence": float,
                "has_secret": bool,
                "related": dict,
                "facts": list,
                "attributes": dict,
            }
            or None if no match found.
        """
        results = self.search(query, top_k=max(top_k, 3), tags_filter=tags_filter)

        if not results:
            self._total_misses += 1
            return None

        for result in results:
            entry = result.entry
            if trust < entry.trust_threshold:
                continue

            response = entry.description
            if emotion in entry.emotion_variants:
                response = entry.emotion_variants[emotion]

            response = re.sub(r"\[\?[^\]]+\]", "", response)
            response = re.sub(r"\[[^\]]+\]", "", response)
            response = re.sub(r"\s+", " ", response).strip()

            supporting_fact = self._select_supporting_fact(entry, query, response)
            if supporting_fact:
                response = f"{response} {supporting_fact}.".strip()
                response = re.sub(r"\s+", " ", response).strip()

            confidence = _DEPTH_CONFIDENCE.get(entry.depth, 0.70)
            confidence = confidence * min(result.similarity / 0.5, 1.0)
            confidence = min(confidence, 0.95)

            self._total_hits += 1

            return {
                "response": response,
                "entity_id": entry.entity_id,
                "entity_name": entry.entity,
                "entity_type": entry.entity_type,
                "depth": entry.depth,
                "source": "knowledge_cloud",
                "confidence": round(confidence, 4),
                "has_secret": trust >= entry.trust_threshold and entry.trust_threshold > 0,
                "related": entry.relations,
                "facts": entry.facts,
                "attributes": entry.attributes,
                "aliases": entry.aliases,
                "similarity": round(result.similarity, 4),
            }

        self._total_misses += 1
        return None

    def lookup_multi(
        self,
        query: str,
        emotion: str = "neutral",
        trust: float = 0.0,
        top_k: int = 3,
        tags_filter: Optional[List[str]] = None,
    ) -> List[Dict[str, Any]]:
        """
        Lookup multiple relevant entities for reasoning.

        Returns a list of result dictionaries, sorted by similarity.
        """
        results = self.search(query, top_k=top_k, tags_filter=tags_filter)
        if not results:
            return []

        query_terms = self._query_terms(query)
        top_similarity = results[0].similarity if results else 0.0
        found_results = []
        for idx, result in enumerate(results):
            entry = result.entry
            if trust < entry.trust_threshold:
                continue

            query_overlap = self._entry_query_overlap(entry, query_terms)
            alias_hit = self._entry_alias_hit(entry, query)
            if idx > 0 and not alias_hit:
                min_overlap = 1 if idx == 1 else 2
                min_similarity = max(top_similarity * (0.85 if idx == 1 else 0.92), self.similarity_floor)
                if query_overlap < min_overlap and result.similarity < min_similarity:
                    continue

            response = entry.description
            if emotion in entry.emotion_variants:
                response = entry.emotion_variants[emotion]

            response = re.sub(r"\[\?[^\]]+\]", "", response)
            response = re.sub(r"\[[^\]]+\]", "", response)
            response = re.sub(r"\s+", " ", response).strip()

            supporting_fact = self._select_supporting_fact(entry, query, response)
            if supporting_fact:
                response = f"{response} {supporting_fact}.".strip()
                response = re.sub(r"\s+", " ", response).strip()

            confidence = _DEPTH_CONFIDENCE.get(entry.depth, 0.70)
            confidence = confidence * min(result.similarity / 0.5, 1.0)

            found_results.append({
                "response": response,
                "entity_id": entry.entity_id,
                "entity_name": entry.entity,
                "entity_type": entry.entity_type,
                "depth": entry.depth,
                "source": "knowledge_cloud",
                "confidence": round(min(confidence, 0.95), 4),
                "has_secret": trust >= entry.trust_threshold and entry.trust_threshold > 0,
                "related": entry.relations,
                "facts": entry.facts,
                "attributes": entry.attributes,
                "agentic_actions": entry.agentic_actions,
                "aliases": entry.aliases,
                "similarity": round(result.similarity, 4),
                "slots": entry.slots,
            })

        if found_results:
            self._total_hits += 1
        else:
            self._total_misses += 1

        return found_results

    def search(
        self,
        query: str,
        top_k: int = 5,
        tags_filter: Optional[List[str]] = None,
    ) -> List[KnowledgeResult]:
        """
        Semantic search across all knowledge entries.

        Returns ranked results with similarity scores, optionally
        filtered by tags.
        """
        self._total_searches += 1

        if not self._enabled or self._index is None:
            return []

        embedder = self._get_embedder()

        # First: try alias/name matching (fast path for exact entity references)
        q_lower = query.lower()
        alias_match = self._match_by_alias(q_lower)

        # Then: semantic search via FAISS
        try:
            q_emb = embedder.embed_texts([query])
            q_emb = np.array(q_emb, dtype=np.float32)

            k = min(top_k * 2, len(self._index_ids))
            if k < 1:
                return alias_match[:top_k] if alias_match else []

            scores, indices = self._index.search(q_emb, k)
        except Exception as e:
            logger.warning(f"KnowledgeCloud: FAISS search failed: {e}")
            return alias_match[:top_k] if alias_match else []

        # Merge alias matches with semantic matches
        seen_ids: Set[str] = set()
        alias_ids: Set[str] = {am.entry.entity_id for am in alias_match}
        results: List[KnowledgeResult] = []

        # Alias matches go first (high confidence exact-name hits)
        for am in alias_match:
            if am.entry.entity_id not in seen_ids:
                seen_ids.add(am.entry.entity_id)
                results.append(am)

        # Semantic matches
        for score, idx in zip(scores[0], indices[0]):
            if idx < 0:
                continue
            if score < self.similarity_floor:
                continue

            entity_id = self._index_ids[idx]
            if entity_id in seen_ids:
                # Boost existing alias match with semantic score
                for r in results:
                    if r.entry.entity_id == entity_id:
                        r.similarity = max(r.similarity, float(score))
                continue

            entry = self._entries.get(entity_id)
            if not entry:
                continue

            seen_ids.add(entity_id)
            results.append(KnowledgeResult(entry=entry, similarity=float(score)))

        # Apply tag filter
        if tags_filter:
            tags_set = set(t.lower() for t in tags_filter)
            results = [r for r in results if tags_set.intersection(set(t.lower() for t in r.entry.tags))]

        # Sort by similarity descending, but keep direct alias hits ahead of pure semantic matches.
        results.sort(key=lambda r: (r.entry.entity_id not in alias_ids, -r.similarity))

        if self.vqd and results:
            results = self._quantum_rerank(query, results[:top_k * 2])

        return results[:top_k]

    def _quantum_rerank(self, query: str, candidates: List[KnowledgeResult]) -> List[KnowledgeResult]:
        """Perform a probabilistic quantum pass on candidates using the VQD."""
        if not candidates:
            return []

        try:
            # 1. Setup VQD (Assume it's initialized by Runtime)
            # Port 0x18: QUBIT_COUNT = log2(candidates)
            n_qubits = int(np.ceil(np.log2(len(candidates))))
            n_qubits = max(1, min(n_qubits, 10)) # Cap for simulation speed
            
            # Port 0x20: GATE_OPCODE = 1 (Hadamard for superposition)
            self.vqd.write64(0x18, n_qubits)
            self.vqd.write64(0x20, 1) # GATE_H
            self.vqd.write64(0x48, 1) # COMMAND_COMPUTE

            # Port 0x50: LAST_RESULT
            quantum_seed = self.vqd.read64(0x50)
            
            # 2. Use quantum seed to probabilisticly boost candidates
            # (Simulating Grover interference based on keyword overlap)
            query_terms = self._query_terms(query)
            reranked = []
            for i, res in enumerate(candidates):
                overlap = self._entry_query_overlap(res.entry, query_terms)
                # Probabilistic interference: use quantum seed as a modifier
                interference = (quantum_seed ^ hash(res.entry.entity_id)) % 100 / 1000.0
                res.similarity += (overlap * 0.05) + interference
                reranked.append(res)
            
            reranked.sort(key=lambda r: r.similarity, reverse=True)
            logger.info(f"KnowledgeCloud: Quantum reranked {len(candidates)} candidates (Seed: {quantum_seed})")
            return reranked
        except Exception as e:
            logger.warning(f"KnowledgeCloud: Quantum reranking failed: {e}")
            return candidates

    def get_entries_by_depth(self, depth: str, limit: int = 5) -> List[Dict[str, Any]]:
        """Retrieve entries by their depth level (e.g. 'rumor', 'intimate')."""
        matches = [e for e in self._entries.values() if e.depth == depth]
        matches.sort(key=lambda e: (e.updated_at, len(e.facts)), reverse=True)

        results = []
        for entry in matches[:limit]:
            results.append(entry.to_dict())
        return results

    def add_entry(self, entry: KnowledgeEntry) -> bool:
        """Add a knowledge entry and rebuild the index."""
        self._entries[entry.entity_id] = entry
        self._update_alias_index(entry)
        self._save_entries()
        self._build_index()
        logger.info(f"KnowledgeCloud: Added entry '{entry.entity_id}' ({entry.entity_type})")
        return True

    def remove_entry(self, entity_id: str) -> bool:
        """Remove a knowledge entry by ID."""
        if entity_id not in self._entries:
            return False
        entry = self._entries.pop(entity_id)
        # Clean up alias index
        for alias in entry.aliases + [entry.entity]:
            key = alias.lower()
            if key in self._alias_index and self._alias_index[key] == entity_id:
                del self._alias_index[key]
        self._save_entries()
        self._build_index()
        logger.info(f"KnowledgeCloud: Removed entry '{entity_id}'")
        return True

    def update_entry(self, entity_id: str, updates: Dict[str, Any]) -> bool:
        """Update fields on an existing entry."""
        if entity_id not in self._entries:
            return False
        entry = self._entries[entity_id]
        for key, value in updates.items():
            if hasattr(entry, key):
                setattr(entry, key, value)
        self._update_alias_index(entry)
        self._save_entries()
        self._build_index()
        return True

    def get_entry(self, entity_id: str) -> Optional[KnowledgeEntry]:
        """Get a specific entry by ID."""
        return self._entries.get(entity_id)

    def list_entries(
        self,
        entity_type: Optional[str] = None,
        tags: Optional[List[str]] = None,
    ) -> List[KnowledgeEntry]:
        """List entries with optional filtering."""
        entries = list(self._entries.values())
        if entity_type:
            entries = [e for e in entries if e.entity_type == entity_type]
        if tags:
            tags_set = set(t.lower() for t in tags)
            entries = [e for e in entries if tags_set.intersection(set(t.lower() for t in e.tags))]
        return entries

    def rebuild_index(self) -> None:
        """Force rebuild the FAISS index."""
        self._build_index()

    def get_stats(self) -> Dict[str, Any]:
        """Return cloud statistics."""
        type_counts: Dict[str, int] = {}
        for entry in self._entries.values():
            type_counts[entry.entity_type] = type_counts.get(entry.entity_type, 0) + 1

        return {
            "enabled": self._enabled,
            "total_entries": len(self._entries),
            "type_breakdown": type_counts,
            "total_aliases": len(self._alias_index),
            "total_searches": self._total_searches,
            "total_hits": self._total_hits,
            "total_misses": self._total_misses,
            "hit_rate": round(self._total_hits / max(self._total_searches, 1) * 100, 1),
            "build_time_ms": round(self._build_time_ms, 1),
            "similarity_floor": self.similarity_floor,
            "embedder_load_time_ms": round(self._embedder_load_time_ms, 1),
        }

    # ── Internal Methods ──────────────────────────────────────────────

    def _match_by_alias(self, query_lower: str) -> List[KnowledgeResult]:
        """Match entities by name/alias substring in the query."""
        matches = []
        seen_ids: Set[str] = set()

        for alias, entity_id in self._alias_index.items():
            if alias in query_lower:
                # Word boundary check for short aliases (avoid false positives)
                if len(alias) <= 3:
                    pattern = r'\b' + re.escape(alias) + r'\b'
                    if not re.search(pattern, query_lower):
                        continue
                entry = self._entries.get(entity_id)
                if entry and entity_id not in seen_ids:
                    # Score proportional to alias length
                    # For exact match: 0.5 + 1.0 * 0.5 = 1.0
                    score = 0.5 + (len(alias) / max(len(query_lower), 1) * 0.5)

                    # Ensure exact word-for-word matches get a tiny boost to 1.0
                    if alias == query_lower:
                        score = 1.0

                    matches.append(KnowledgeResult(entry=entry, similarity=score))
                    seen_ids.add(entity_id)

        # Sort by similarity (longer alias → higher score → first)
        matches.sort(key=lambda r: r.similarity, reverse=True)
        return matches

    def _query_terms(self, query: str) -> Set[str]:
        """Extract significant terms from a query string.

        Args:
            query: The input query string.

        Returns:
            A set of lowercased significant words (excluding stop words).
        """
        terms = set(re.findall(r"[a-z]+", query.lower()))
        stop_words = {
            "the", "a", "an", "and", "or", "to", "of", "in", "on", "at", "for", "with", "by",
            "is", "are", "was", "were", "be", "do", "does", "did", "what", "where", "when",
            "who", "how", "why", "tell", "me", "about", "this", "that", "these", "those", "they",
            "it", "its", "their", "there", "here", "from", "as", "into", "than", "then",
        }
        return {term for term in terms if term not in stop_words}

    def _entry_query_overlap(self, entry: KnowledgeEntry, query_terms: Set[str]) -> int:
        """Calculate the number of query terms that overlap with a knowledge entry.

        Args:
            entry: The knowledge entry to check.
            query_terms: The set of terms to look for.

        Returns:
            The count of overlapping terms.
        """
        haystacks = [
            entry.entity,
            entry.description,
            " ".join(entry.facts),
            " ".join(entry.aliases),
            " ".join(entry.tags),
            " ".join(f"{k} {v}" for k, v in entry.relations.items()),
        ]
        haystack = " ".join(h.lower() for h in haystacks if h)
        return sum(1 for term in query_terms if term in haystack)

    def _entry_alias_hit(self, entry: KnowledgeEntry, query: str) -> bool:
        """Check if any of the entry's aliases or name appear in the query.

        Args:
            entry: The knowledge entry to check.
            query: The query string.

        Returns:
            True if there is an alias hit with word boundary protection, False otherwise.
        """
        query_lower = query.lower()
        candidates = [entry.entity.lower(), *(alias.lower() for alias in entry.aliases)]
        for alias in candidates:
            if alias in query_lower:
                if len(alias) <= 3 and not re.search(r'\b' + re.escape(alias) + r'\b', query_lower):
                    continue
                return True
        return False

    def _select_supporting_fact(self, entry: KnowledgeEntry, query: str, response: str) -> str:
        """Select a supporting fact from the entry based on query and response overlap.

        Args:
            entry: The knowledge entry containing facts.
            query: The user query.
            response: The generated response.

        Returns:
            The most relevant supporting fact, or an empty string if none are relevant enough.
        """
        query_terms = self._query_terms(query)
        response_terms = self._query_terms(response)
        best_fact = ""
        best_score = 0
        for fact in entry.facts:
            fact_terms = self._query_terms(fact)
            overlap = len((fact_terms & query_terms) | (fact_terms & response_terms))
            if overlap > best_score:
                best_score = overlap
                best_fact = fact
        return best_fact if best_score >= 2 else ""

    def _update_alias_index(self, entry: KnowledgeEntry) -> None:
        """Update the alias index for a single entry."""
        self._alias_index[entry.entity.lower()] = entry.entity_id
        for alias in entry.aliases:
            self._alias_index[alias.lower()] = entry.entity_id

    def _load_entries(self) -> None:
        """Load all knowledge entries from JSON files in data_dir."""
        # Fix: Only bootstrap if the directory is empty or missing critical files
        has_lore = (self.data_dir / "world_lore.json").exists()

        if not has_lore and bootstrap_knowledge_cache is not None and _should_bootstrap_knowledge_cache(self.data_dir.parent):
            try:
                report = bootstrap_knowledge_cache(self.data_dir.parent)
                if report.get("downloaded"):
                    logger.info(
                        "KnowledgeCloud: bootstrapped from cloud: %s",
                        ", ".join(report.get("downloaded", [])),
                    )
            except Exception as e:
                logger.warning(f"KnowledgeCloud: cloud bootstrap skipped: {e}")

        if not self.data_dir.exists():
            self.data_dir.mkdir(parents=True, exist_ok=True)
            logger.info(f"KnowledgeCloud: Created data directory at {self.data_dir}")
            return

        allowed_files = {"world_lore.json", "test_entries.json", "evolution.json"}
        ignored_files = {"transitions.json", "learned_transitions.json", "chaining_patterns.json"}

        loaded = 0
        for json_file in self.data_dir.glob("*.json"):
            if json_file.name in ignored_files:
                continue
            if json_file.name not in allowed_files and json_file.name != "evolution.json":
                continue
            try:
                with open(json_file, "r", encoding="utf-8") as f:
                    data = json.load(f)

                entries_data = data if isinstance(data, list) else data.get("entries", [])

                for entry_data in entries_data:
                    entry = KnowledgeEntry.from_dict(entry_data)
                    self._entries[entry.entity_id] = entry
                    self._update_alias_index(entry)
                    loaded += 1

            except Exception as e:
                logger.warning(f"KnowledgeCloud: Failed to load {json_file}: {e}")

        logger.info(f"KnowledgeCloud: Loaded {loaded} entries from {self.data_dir}")
        self._load_evolution()

    def _load_evolution(self) -> None:
        """Load character-witnessed knowledge from evolution.json."""
        evo_path = self.data_dir / "evolution.json"
        if not evo_path.exists():
            return

        try:
            data = json.loads(evo_path.read_text(encoding="utf-8"))
            entries_data = data.get("entries", [])
            for entry_data in entries_data:
                entry = KnowledgeEntry.from_dict(entry_data)
                self._entries[entry.entity_id] = entry
                self._update_alias_index(entry)
            logger.info(f"KnowledgeCloud: Loaded {len(entries_data)} evolution entries")
        except Exception as e:
            logger.warning(f"KnowledgeCloud: Failed to load evolution data: {e}")

    def _save_entries(self) -> None:
        """Persist all entries back to a single JSON file."""
        self.data_dir.mkdir(parents=True, exist_ok=True)
        output_path = self.data_dir / "world_lore.json"

        entries_list = [entry.to_dict() for entry in self._entries.values()]
        data = {
            "version": "1.0.0",
            "description": "Synthesus Knowledge Cloud — Shared World Knowledge",
            "entries": entries_list,
        }

        try:
            with open(output_path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            logger.info(f"KnowledgeCloud: Saved {len(entries_list)} entries to {output_path}")
        except Exception as e:
            logger.error(f"KnowledgeCloud: Failed to save entries: {e}")

    def _build_index(self) -> None:
        """Build FAISS index over all entry embedding texts."""
        if not self._entries:
            self._enabled = False
            return

        try:
            import faiss
        except ImportError:
            logger.warning("KnowledgeCloud: faiss-cpu not available, semantic search disabled")
            self._enabled = False
            return

        start = time.time()
        embedder = self._get_embedder()

        # Build embedding texts
        entry_ids = []
        texts = []
        for eid, entry in self._entries.items():
            text = entry.get_embedding_text()
            if text.strip():
                entry_ids.append(eid)
                texts.append(text)

        if not texts:
            self._enabled = False
            return

        # Fit embedder if needed, then encode
        if not embedder.is_fitted:
            embedder.fit(texts)

        embeddings = embedder.embed_texts(texts)
        embeddings = np.array(embeddings, dtype=np.float32)

        # Build FAISS inner-product index
        dim = embeddings.shape[1]
        self._index = faiss.IndexFlatIP(dim)
        self._index.add(embeddings)
        self._index_ids = entry_ids

        self._enabled = True
        self._build_time_ms = (time.time() - start) * 1000

        logger.info(
            f"KnowledgeCloud: Indexed {len(texts)} entries "
            f"in {self._build_time_ms:.0f}ms (dim={dim})"
        )
