"""
GraphConnector — Connects external data sources to the Knowledge Network.
Handles batch linking, edge creation, and data import pipelines.
"""

from __future__ import annotations

import json
import logging
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from .node import Edge, EdgeType, KNode, NodeType

logger = logging.getLogger(__name__)


class GraphConnector:
    """
    Bridges external data sources into the KN graph.

    Handles:
    - Bulk import of structured data as nodes + edges
    - Automatic edge creation from relationships in source data
    - Merging duplicate nodes via entity linking
    - Edge weight calibration based on source reliability
    - Progress tracking and resumable imports

    Usage:
        connector = GraphConnector(kn=knowledge_network, linker=entity_linker)
        connector.import_json("path/to/world_lore.json", create_edges=True)
    """

    def __init__(
        self,
        kn=None,
        linker=None,
        indexer=None,
        auto_save: bool = True,
    ):
        """
        Initializes the GraphConnector.

        Args:
            kn: The KnowledgeNetwork instance to connect to.
            linker: The entity linker for merging duplicate nodes.
            indexer: The semantic indexer for indexing nodes.
            auto_save: Whether to automatically save changes to the KN.
        """
        self.kn = kn
        self.linker = linker
        self.indexer = indexer
        self.auto_save = auto_save
        self._import_stats: Dict[str, Any] = {}
        self._session_id = int(time.time())

    # ------------------------------------------------------------------
    # Bulk node import
    # ------------------------------------------------------------------

    def import_nodes(
        self,
        nodes_data: List[Dict[str, Any]],
        node_type: Optional[NodeType] = None,
        source: str = "import",
        replace: bool = False,
    ) -> Tuple[int, int]:
        """
        Bulk import nodes from dict list.

        Returns:
            (added_count, skipped_count)
        """
        added = 0
        skipped = 0

        for ndata in nodes_data:
            try:
                nid = ndata.get("id")
                if not nid:
                    continue

                ntype = node_type or NodeType(ndata.get("node_type", "unknown"))

                existing = self.kn.get_node(nid) if self.kn else None
                if existing and not replace:
                    skipped += 1
                    continue

                node = KNode(
                    id=nid,
                    node_type=ntype,
                    content=ndata.get("content", ""),
                    display_name=ndata.get("display_name", nid.replace("_", " ").title()),
                    description=ndata.get("description", ""),
                    tags=ndata.get("tags", []),
                    aliases=ndata.get("aliases", []),
                    facts=ndata.get("facts", []),
                    source=source,
                    metadata=ndata.get("metadata", {}),
                    confidence=ndata.get("confidence", 0.7),
                    depth=ndata.get("depth", "acquainted"),
                )

                self.kn.register_node(node, replace=replace)
                if self.indexer:
                    self.indexer.index_node(node)
                added += 1

            except Exception as e:
                logger.warning("Failed to import node %s: %s", ndata.get("id", "?"), e)
                skipped += 1

        if self.auto_save:
            self.kn.auto_save_check()

        return added, skipped

    # ------------------------------------------------------------------
    # Edge creation
    # ------------------------------------------------------------------

    def import_edges(
        self,
        edges_data: List[Dict[str, Any]],
        weight_map: Optional[Dict[str, float]] = None,
        auto_create_nodes: bool = False,
    ) -> Tuple[int, int]:
        """
        Bulk import edges from dict list.

        Args:
            edges_data: List of {source_id, target_id, edge_type, weight, bidirectional}
            weight_map: Optional mapping to override edge weights
            auto_create_nodes: Create missing nodes automatically

        Returns:
            (added_count, failed_count)
        """
        added = 0
        failed = 0
        weight_map = weight_map or {}

        for edata in edges_data:
            try:
                src = edata.get("source_id")
                tgt = edata.get("target_id")
                if not src or not tgt:
                    failed += 1
                    continue

                if auto_create_nodes:
                    if self.kn.get_node(src) is None:
                        self.kn.register_node(KNode(id=src, node_type=NodeType.UNKNOWN))
                    if self.kn.get_node(tgt) is None:
                        self.kn.register_node(KNode(id=tgt, node_type=NodeType.UNKNOWN))

                etype_str = edata.get("edge_type", "related_to")
                etype = EdgeType(etype_str) if isinstance(etype_str, str) else etype_str

                weight = weight_map.get(f"{src}|{tgt}", edata.get("weight", 1.0))
                bidir = edata.get("bidirectional", False)

                edge = self.kn.add_edge(src, tgt, etype, weight, bidir)
                if edge:
                    added += 1
                else:
                    failed += 1

            except Exception as e:
                logger.warning("Failed to import edge %s->%s: %s",
                               edata.get("source_id"), edata.get("target_id"), e)
                failed += 1

        if self.auto_save:
            self.kn.auto_save_check()

        return added, failed

    # ------------------------------------------------------------------
    # JSON import pipeline
    # ------------------------------------------------------------------

    def import_json(
        self,
        path: str,
        create_edges: bool = True,
        node_type: Optional[NodeType] = None,
        default_edge_type: EdgeType = EdgeType.RELATED_TO,
    ) -> Dict[str, Any]:
        """
        Import nodes and edges from a JSON file.

        Expected JSON structure:
        {
            "nodes": [...],
            "edges": [...],
            "metadata": { "source": "..." }
        }

        Or flat list of nodes:
        [...]

        Returns:
            dict with import stats
        """
        path = Path(path)
        if not path.exists():
            return {"error": f"File not found: {path}"}

        with open(path, encoding="utf-8") as f:
            data = json.load(f)

        session_id = self._session_id
        self._import_stats = {"session_id": session_id, "started_at": time.time()}
        nodes_data = []
        edges_data = []

        if isinstance(data, dict):
            nodes_data = data.get("nodes", [])
            edges_data = data.get("edges", [])
            self._import_stats["source"] = data.get("metadata", {}).get("source", path.name)
        elif isinstance(data, list):
            nodes_data = data
            self._import_stats["source"] = path.name

        source = self._import_stats.get("source", "import")
        added_nodes, skipped_nodes = self.import_nodes(nodes_data, node_type, source)
        self._import_stats["nodes_added"] = added_nodes
        self._import_stats["nodes_skipped"] = skipped_nodes

        if create_edges and edges_data:
            added_edges, failed_edges = self.import_edges(edges_data)
            self._import_stats["edges_added"] = added_edges
            self._import_stats["edges_failed"] = failed_edges

        self._import_stats["duration_s"] = round(time.time() - self._import_stats["started_at"], 2)
        self._import_stats["completed_at"] = time.time()

        logger.info("GraphConnector import complete: %s", self._import_stats)
        return self._import_stats

    # ------------------------------------------------------------------
    # World lore seeding
    # ------------------------------------------------------------------

    def seed_from_lore(
        self,
        lore_data: List[Dict[str, Any]],
        base_weight: float = 0.8,
    ) -> Dict[str, int]:
        """
        Seed the KN from world lore entries (e.g. existing knowledge_cloud JSON).
        Creates PersonNode, PlaceNode, etc. based on type hints in the data.
        """
        type_map = {
            "person": NodeType.PERSON,
            "place": NodeType.PLACE,
            "item": NodeType.ITEM,
            "faction": NodeType.FACTION,
            "event": NodeType.EVENT,
            "creature": NodeType.CREATURE,
            "knowledge": NodeType.KNOWLEDGE,
        }

        added_nodes = 0
        added_edges = 0

        for entry in lore_data:
            nid = entry.get("id") or entry.get("name", "").lower().replace(" ", "_")
            if not nid:
                continue

            ntype_str = entry.get("type", "unknown").lower()
            ntype = type_map.get(ntype_str, NodeType.UNKNOWN)

            tags = entry.get("tags", [])
            if ntype_str not in tags:
                tags = [ntype_str] + tags

            node = KNode(
                id=nid,
                node_type=ntype,
                content=entry.get("description", entry.get("text", "")),
                display_name=entry.get("name", nid.replace("_", " ").title()),
                description=entry.get("description", ""),
                tags=tags,
                aliases=entry.get("aliases", []),
                facts=entry.get("facts", []),
                source=entry.get("source", "world_lore"),
                confidence=entry.get("confidence", base_weight),
                depth=entry.get("depth", "acquainted"),
            )

            if self.kn.register_node(node):
                added_nodes += 1
                if self.indexer:
                    self.indexer.index_node(node)

            rels = entry.get("relations", [])
            for rel in rels:
                target = rel.get("target", "")
                rtype = rel.get("type", "related_to")
                weight = rel.get("weight", base_weight)
                if target:
                    self.kn.add_edge(nid, target, EdgeType(rtype), weight)
                    added_edges += 1

        return {"nodes_added": added_nodes, "edges_added": added_edges}

    # ------------------------------------------------------------------
    # Stats
    # ------------------------------------------------------------------

    def get_stats(self) -> Dict[str, Any]:
        """
        Returns the import statistics and KN status.

        Returns:
            A dictionary containing session ID, import stats, and KN metrics.
        """
        return {
            **self._import_stats,
            "session_id": self._session_id,
            "kn_stats": self.kn.stats() if self.kn else {},
        }