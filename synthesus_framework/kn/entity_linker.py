"""
EntityLinker — Resolves textual mentions to canonical KN nodes.
Handles co-reference, alias resolution, and fuzzy matching.
"""

from __future__ import annotations

import logging
import re
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set, Tuple

logger = logging.getLogger(__name__)


@dataclass
class LinkResult:
    """Result of an entity linking operation.

    Attributes:
        node_id: Canonical ID of the resolved node.
        canonical_name: Primary display name of the node.
        mention_text: Original text snippet that was resolved.
        link_type: Category of match (e.g., 'exact', 'fuzzy', 'substring').
        confidence: Similarity score between 0.0 and 1.0.
        alternatives: List of other potential matches as (node_id, link_type, confidence).
    """
    node_id: str
    canonical_name: str
    mention_text: str
    link_type: str = "exact"
    confidence: float = 1.0
    alternatives: List[Tuple[str, str, float]] = field(default_factory=list)


class EntityLinker:
    """
    Resolves textual mentions (names, aliases, pronouns) to canonical KNode IDs.

    Features:
    - Exact lookup via display_name and aliases
    - Case-insensitive matching
    - Fuzzy matching via substring and edit-distance
    - Disambiguation by node type and tags
    - Co-reference chain tracking

    Usage:
        linker = EntityLinker(kn=knowledge_network)
        result = linker.link_mention("Gorn the merchant", types=["person"])
        if result:
            print(f"Resolved to: {result.node_id}")
    """

    def __init__(
        self,
        kn=None,
        min_fuzzy_score: float = 0.75,
        max_candidates: int = 10,
        cache_size: int = 1000,
    ):
        """
        Initialize the EntityLinker.

        Args:
            kn: Optional KnowledgeNetwork instance to resolve against.
            min_fuzzy_score: Minimum similarity score (0.0–1.0) for fuzzy matches.
            max_candidates: Maximum number of alternative candidates to return.
            cache_size: Maximum number of lookup results to cache (LRU eviction).
        """
        self.kn = kn
        self.min_fuzzy_score = min_fuzzy_score
        self.max_candidates = max_candidates
        self._cache: Dict[Tuple[str, Tuple[str, ...]], LinkResult] = {}
        self._cache_order: List[Tuple[str, Tuple[str, ...]]] = []
        self._cache_size = cache_size

        self._alias_index: Dict[str, List[str]] = {}
        self._name_index: Dict[str, str] = {}
        self._built = False

    def build_indices(self) -> None:
        """Build fast-lookup indices from the KN."""
        if self.kn is None:
            return
        self._alias_index.clear()
        self._name_index.clear()

        for node in self.kn.list_nodes():
            name_lower = node.display_name.lower() if node.display_name else node.id.lower()
            self._name_index[name_lower] = node.id
            for alias in node.aliases:
                al_lower = alias.lower()
                if al_lower not in self._alias_index:
                    self._alias_index[al_lower] = []
                self._alias_index[al_lower].append(node.id)

        self._built = True
        logger.info("EntityLinker indices built: %d names, %d aliases",
                    len(self._name_index), len(self._alias_index))

    def _ensure_built(self) -> None:
        """Lazily builds indices on the first use if they haven't been built yet."""
        if not self._built:
            self.build_indices()

    def link_mention(
        self,
        mention: str,
        types: Optional[List[str]] = None,
        tags: Optional[List[str]] = None,
        prefer_ids: Optional[List[str]] = None,
    ) -> Optional[LinkResult]:
        """
        Resolve a textual mention to a canonical node ID.

        Args:
            mention: Text to resolve (name, alias, partial match).
            types: Optional list of allowed NodeType string values.
            tags: Optional list of required tags.
            prefer_ids: IDs to prefer in ambiguous cases.

        Returns:
            LinkResult with resolved node_id, or None if unresolved.
        """
        self._ensure_built()
        if not mention or not mention.strip():
            return None

        cache_key = (mention.strip().lower(), tuple(sorted(types or [])) if types else ())
        if cache_key in self._cache:
            return self._cache[cache_key]

        mention_lower = mention.strip().lower()
        candidates: List[Tuple[str, str, float]] = []
        # 1. Exact alias match
        if mention_lower in self._alias_index:
            for nid in self._alias_index[mention_lower]:
                candidates.append((nid, "exact_alias", 1.0))

        # 2. Exact name match
        if mention_lower in self._name_index:
            nid = self._name_index[mention_lower]
            if not any(nid == c[0] for c in candidates):
                candidates.append((nid, "exact_name", 1.0))

        # 3. Substring match on display_name and aliases
        for name_lower, nid in self._name_index.items():
            if mention_lower in name_lower or name_lower in mention_lower:
                score = len(mention_lower) / max(len(name_lower), 1)
                if score >= self.min_fuzzy_score and not any(nid == c[0] for c in candidates):
                    candidates.append((nid, "substring", score))

        for alias_lower, nids in self._alias_index.items():
            for nid in nids:
                if mention_lower in alias_lower or alias_lower in mention_lower:
                    score = len(mention_lower) / max(len(alias_lower), 1)
                    if score >= self.min_fuzzy_score and not any(nid == c[0] for c in candidates):
                        candidates.append((nid, "substring_alias", score))
        # 4. Fuzzy match via edit distance
        fuzzy_candidates = self._fuzzy_match(mention_lower)
        for nid, score in fuzzy_candidates:
            if not any(nid == c[0] for c in candidates):
                candidates.append((nid, "fuzzy", score))
        # 5. Filter and score by type + tags
        scored = self._filter_and_score(candidates, types, tags, prefer_ids)

        if not scored:
            result = None
        else:
            top_id, top_link_type, top_score = scored[0]
            alternatives = [
                (nid, ltype, score)
                for nid, ltype, score in scored[1:self.max_candidates]
            ]
            result = LinkResult(
                node_id=top_id,
                canonical_name=self._get_canonical_name(top_id),
                mention_text=mention.strip(),
                link_type=top_link_type,
                confidence=top_score,
                alternatives=alternatives,
            )

        self._update_cache(cache_key, result)
        return result

    def _fuzzy_match(self, mention: str) -> List[Tuple[str, float]]:
        """Performs simple edit-distance-based fuzzy matching against all known names.

        Args:
            mention: The mention string to match.

        Returns:
            A list of tuples containing (node_id, similarity_score), sorted by score descending.
        """
        try:
            import Levenshtein
            has_lev = True
        except ImportError:
            has_lev = False

        candidates = []
        for name_lower, nid in self._name_index.items():
            if has_lev:
                dist = Levenshtein.distance(mention, name_lower)
                max_len = max(len(mention), len(name_lower))
                score = 1.0 - (dist / max_len) if max_len > 0 else 0.0
            else:
                score = self._simple_fuzzy(mention, name_lower)
            if score >= self.min_fuzzy_score:
                candidates.append((nid, score))

        return sorted(candidates, key=lambda x: x[1], reverse=True)

    def _simple_fuzzy(self, s1: str, s2: str) -> float:
        """Calculates Dice-coefficient similarity between two strings.

        Used as a fallback when the Levenshtein library is unavailable.

        Args:
            s1: The first string.
            s2: The second string.

        Returns:
            The similarity score between 0.0 and 1.0.
        """
        if not s1 or not s2:
            return 0.0
        set1 = set(s1[i:i+2] for i in range(len(s1)-1))
        set2 = set(s2[i:i+2] for i in range(len(s2)-1))
        if not set1 or not set2:
            return 0.0
        intersection = len(set1 & set2)
        return (2.0 * intersection) / (len(set1) + len(set2))

    def _filter_and_score(
        self,
        candidates: List[Tuple[str, str, float]],
        types: Optional[List[str]],
        tags: Optional[List[str]],
        prefer_ids: Optional[List[str]],
    ) -> List[Tuple[str, str, float]]:
        """Filters candidates by type and tag requirements and calculates final preference scores.

        Args:
            candidates: List of (node_id, link_type, base_score) tuples.
            types: Optional list of allowed NodeType string values.
            tags: Optional list of required tags.
            prefer_ids: List of node IDs to favor in case of ambiguity.

        Returns:
            Sorted list of candidates with adjusted final scores.
        """
        scored: List[Tuple[str, str, float]] = []

        for nid, link_type, base_score in candidates:
            node = self.kn.get_node(nid) if self.kn else None
            if not node:
                continue

            type_score = 1.0
            if types and node.node_type.value not in types:
                type_score = 0.3

            tag_score = 1.0
            if tags:
                node_tags = set(node.tags)
                overlap = node_tags & set(tags)
                tag_score = len(overlap) / max(len(tags), 1)

            prefer_score = 0.0
            if prefer_ids and nid in prefer_ids:
                prefer_score = 0.2

            final_score = base_score * type_score * tag_score + prefer_score
            scored.append((nid, link_type, final_score))

        scored.sort(key=lambda x: x[2], reverse=True)
        return scored

    def _get_canonical_name(self, node_id: str) -> str:
        """Retrieves the display name of a node, falling back to its ID if not found.

        Args:
            node_id: The unique identifier of the node.

        Returns:
            The display name or ID of the node.
        """
        node = self.kn.get_node(node_id) if self.kn else None
        if node:
            return node.display_name or node.id
        return node_id

    def _update_cache(self, key: Tuple[str, Tuple[str, ...]], result: Optional[LinkResult]) -> None:
        """Updates the internal LRU cache with a new linking result.

        Args:
            key: The cache key (mention, types).
            result: The LinkResult to cache.
        """
        if len(self._cache) >= self._cache_size:
            oldest = self._cache_order.pop(0)
            self._cache.pop(oldest, None)
        self._cache[key] = result
        self._cache_order.append(key)

    def link_batch(
        self,
        mentions: List[str],
        types: Optional[List[str]] = None,
        tags: Optional[List[str]] = None,
    ) -> List[Optional[LinkResult]]:
        """Resolves a list of mentions in a single batch operation.

        Args:
            mentions: List of text mentions to resolve.
            types: Optional list of allowed node types.
            tags: Optional list of required tags.

        Returns:
            A list of LinkResult objects corresponding to each mention.
        """
        return [
            self.link_mention(m, types=types, tags=tags)
            for m in mentions
        ]

    def stats(self) -> Dict[str, Any]:
        """Returns diagnostic statistics for the EntityLinker instance.

        Returns:
            A dictionary containing index status, counts, and cache usage.
        """
        return {
            "indices_built": self._built,
            "name_count": len(self._name_index),
            "alias_count": len(self._alias_index),
            "cache_size": len(self._cache),
        }