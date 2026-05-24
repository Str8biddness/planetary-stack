"""
Knowledge Network — Core graph management for Synthesus.
"""

from __future__ import annotations

import json
import logging
import pickle
import time
from collections import defaultdict
from collections import deque
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

from .node import Edge, EdgeType, KNode, NodeType

logger = logging.getLogger(__name__)


class KnowledgeNetwork:
    """
    Persistent, queryable memory of entities, relationships, and facts.
    Organised as a graph of typed nodes connected by weighted edges.

    Usage:
        kn = KnowledgeNetwork()
        kn.register_node(PersonNode(id="gorn", role="merchant", content="..."))
        kn.add_edge("gorn", "tavern", EdgeType.LOCATED_AT)
        results = kn.search("merchant", top_k=5)
    """

    def __init__(
        self,
        index_path: Optional[str] = None,
        graph_path: Optional[str] = None,
        auto_save: bool = True,
        save_interval: int = 300,
    ):
        """Initialize the Knowledge Network.
        
        Args:
            index_path: Optional path to load/store the node index (JSON).
            graph_path: Optional path to load/store edge graph (pickle).
            auto_save: If True, auto-save when dirty and save_interval elapsed.
            save_interval: Seconds between auto-save checks (default 300).
        
        Attributes:
            _nodes: Dict mapping node ID -> KNode instance.
            _edges: List of all Edge objects.
            _edges_by_source: Dict mapping source ID -> list of outgoing edges.
            _edges_by_target: Dict mapping target ID -> list of incoming edges.
            _nodes_by_type: Dict mapping NodeType -> list of node IDs.
        """
        self._nodes: Dict[str, KNode] = {}
        self._edges: List[Edge] = []
        self._edges_by_source: Dict[str, List[Edge]] = defaultdict(list)
        self._edges_by_target: Dict[str, List[Edge]] = defaultdict(list)
        self._nodes_by_type: Dict[NodeType, List[str]] = defaultdict(list)
        self._dirty = False

        self.index_path = Path(index_path) if index_path else None
        self.graph_path = Path(graph_path) if graph_path else None
        self.auto_save = auto_save
        self.save_interval = save_interval
        self._last_save = time.time()

        if self.index_path and self.index_path.exists():
            self._load_index()
        if self.graph_path and self.graph_path.exists():
            self._load_graph()

    # ------------------------------------------------------------------
    # Node management
    # ------------------------------------------------------------------

    def register_node(self, node: KNode, replace: bool = False) -> bool:
        """Register a node in the network. Returns True if newly added."""
        if node.id in self._nodes:
            if not replace:
                logger.debug("Node %s already exists, skipping", node.id)
                return False
            old_node = self._nodes[node.id]
            if old_node.node_type != node.node_type:
                self._nodes_by_type[old_node.node_type].remove(node.id)

        self._nodes[node.id] = node
        if node.id not in self._nodes_by_type[node.node_type]:
            self._nodes_by_type[node.node_type].append(node.id)
        self._dirty = True
        logger.debug("Registered node: %s (%s)", node.id, node.node_type.value)
        return True

    def get_node(self, node_id: str) -> Optional[KNode]:
        """Retrieve a node by its ID.
        
        Args:
            node_id: The unique identifier of the node.
        
        Returns:
            The KNode if found, otherwise None.
        """
        return self._nodes.get(node_id)

    def remove_node(self, node_id: str) -> bool:
        """Remove a node and all its connected edges from the network.
        
        Args:
            node_id: The unique identifier of the node to remove.
        
        Returns:
            True if the node was found and removed, False otherwise.
        """
        node = self._nodes.pop(node_id, None)
        if node is None:
            return False
        self._nodes_by_type[node.node_type].remove(node_id)
        for edge in list(self._edges):
            if edge.source_id == node_id or edge.target_id == node_id:
                self._edges.remove(edge)
                self._edges_by_source[edge.source_id].remove(edge)
                self._edges_by_target[edge.target_id].remove(edge)
        self._dirty = True
        return True

    def update_node(self, node_id: str, **kwargs) -> Optional[KNode]:
        """Update mutable attributes of an existing node.
        
        Args:
            node_id: The unique identifier of the node to update.
            **kwargs: Key-value pairs of attributes to update.
        
        Returns:
            The updated KNode if found, None otherwise.
        """
        node = self._nodes.get(node_id)
        if node is None:
            return None
        for key, val in kwargs.items():
            if hasattr(node, key):
                setattr(node, key, val)
        node.updated_at = time.time()
        node.version += 1
        self._dirty = True
        return node

    def list_nodes(self, node_type: Optional[NodeType] = None) -> List[KNode]:
        """List all nodes, optionally filtered by type.
        
        Args:
            node_type: If provided, only return nodes of this type.
        
        Returns:
            List of KNode objects.
        """
        if node_type:
            ids = self._nodes_by_type.get(node_type, [])
            return [self._nodes[nid] for nid in ids if nid in self._nodes]
        return list(self._nodes.values())

    # ------------------------------------------------------------------
    # Edge management
    # ------------------------------------------------------------------

    def add_edge(
        self,
        source_id: str,
        target_id: str,
        edge_type: EdgeType = EdgeType.RELATED_TO,
        weight: float = 1.0,
        bidirectional: bool = False,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Optional[Edge]:
        """Add a directed weighted edge between two nodes."""
        if source_id not in self._nodes or target_id not in self._nodes:
            logger.warning("add_edge: source=%s or target=%s not found", source_id, target_id)
            return None

        edge = Edge(
            source_id=source_id,
            target_id=target_id,
            edge_type=edge_type,
            weight=weight,
            bidirectional=bidirectional,
            metadata=metadata or {},
        )
        self._edges.append(edge)
        self._edges_by_source[source_id].append(edge)
        self._edges_by_target[target_id].append(edge)

        if bidirectional:
            reverse = Edge(
                source_id=target_id,
                target_id=source_id,
                edge_type=edge_type,
                weight=weight,
                bidirectional=False,
                metadata=metadata or {},
            )
            self._edges.append(reverse)
            self._edges_by_source[target_id].append(reverse)
            self._edges_by_target[source_id].append(reverse)

        self._dirty = True
        return edge

    def get_edges_from(self, node_id: str) -> List[Edge]:
        """Get all outgoing edges from a node.
        
        Args:
            node_id: The source node identifier.
        
        Returns:
            List of Edge objects originating from the node.
        """
        return list(self._edges_by_source.get(node_id, []))

    def get_edges_to(self, node_id: str) -> List[Edge]:
        """Get all incoming edges to a node.
        
        Args:
            node_id: The target node identifier.
        
        Returns:
            List of Edge objects pointing to the node.
        """
        return list(self._edges_by_target.get(node_id, []))

    def get_neighbors(
        self,
        node_id: str,
        edge_type: Optional[EdgeType] = None,
        direction: str = "out",
        min_weight: float = 0.0,
    ) -> List[Tuple[KNode, Edge]]:
        """Get neighbouring nodes with edge info. direction: 'out', 'in', 'both'."""
        results = []
        visited: Set[str] = set()

        if direction in ("out", "both"):
            for edge in self._edges_by_source.get(node_id, []):
                if edge_type and edge.edge_type != edge_type:
                    continue
                if edge.weight < min_weight:
                    continue
                neighbor = self._nodes.get(edge.target_id)
                if neighbor and edge.target_id not in visited:
                    results.append((neighbor, edge))
                    visited.add(edge.target_id)

        if direction in ("in", "both"):
            for edge in self._edges_by_target.get(node_id, []):
                if edge_type and edge.edge_type != edge_type:
                    continue
                if edge.weight < min_weight:
                    continue
                neighbor = self._nodes.get(edge.source_id)
                if neighbor and edge.source_id not in visited:
                    results.append((neighbor, edge))
                    visited.add(edge.source_id)

        return results

    def remove_edge(self, source_id: str, target_id: str, edge_type: EdgeType = EdgeType.RELATED_TO) -> bool:
        """Remove an edge from the network.
        
        Args:
            source_id: The edge source node ID.
            target_id: The edge target node ID.
            edge_type: The type of edge to remove (default RELATED_TO).
        
        Returns:
            True if the edge was found and removed, False otherwise.
        """
        for edge in list(self._edges):
            if edge.source_id == source_id and edge.target_id == target_id and edge.edge_type == edge_type:
                self._edges.remove(edge)
                if edge in self._edges_by_source[source_id]:
                    self._edges_by_source[source_id].remove(edge)
                if edge in self._edges_by_target[target_id]:
                    self._edges_by_target[target_id].remove(edge)
                self._dirty = True
                return True
        return False

    # ------------------------------------------------------------------
    # Context retrieval
    # ------------------------------------------------------------------

    def get_context(
        self,
        node_id: str,
        depth: int = 2,
        edge_type: Optional[EdgeType] = None,
        min_weight: float = 0.0,
    ) -> Dict[str, Any]:
        """Retrieve contextual subgraph around a node up to given depth."""
        if depth <= 0:
            return self._node_summary(node_id)

        visited: Set[str] = set([node_id])
        frontier = deque([(node_id, 0)])
        layers: Dict[int, List[KNode]] = defaultdict(list)

        while frontier:
            current_id, current_depth = frontier.popleft()
            if current_depth >= depth:
                continue
            neighbors_with_edges = self.get_neighbors(
                current_id, edge_type=edge_type, direction="both", min_weight=min_weight
            )

            for neighbor, _ in neighbors_with_edges:
                if neighbor.id not in visited:
                    visited.add(neighbor.id)
                    layers[current_depth + 1].append(neighbor)
                    frontier.append((neighbor.id, current_depth + 1))

        return {
            "center": node_id,
            "depth": depth,
            "nodes": {
                nid: self._node_summary(nid)
                for nid in visited
                if nid in self._nodes
            },
            "layers": {
                d: [n.id for n in nodes]
                for d, nodes in layers.items()
            },
        }

    def _node_summary(self, node_id: str) -> Dict[str, Any]:
        """Build a dict summary of a node for context retrieval.
        
        Args:
            node_id: The node identifier.
        
        Returns:
            Dict with id, type, display_name, description, tags, and edge counts.
        """
        node = self._nodes.get(node_id)
        if not node:
            return {"error": "node not found"}
        return {
            "id": node.id,
            "type": node.node_type.value,
            "display_name": node.display_name,
            "description": node.description,
            "tags": node.tags,
            "outgoing": len(self._edges_by_source.get(node_id, [])),
            "incoming": len(self._edges_by_target.get(node_id, [])),
        }

    def subgraph(
        self,
        node_ids: List[str],
        include_edges: bool = True,
    ) -> Dict[str, Any]:
        """Extract a subgraph containing only the given nodes."""
        nodes = {nid: self._nodes[nid].to_dict() for nid in node_ids if nid in self._nodes}
        edges = []
        if include_edges:
            for edge in self._edges:
                if edge.source_id in nodes and edge.target_id in nodes:
                    edges.append(edge.to_dict())
        return {"nodes": nodes, "edges": edges, "count": len(nodes)}

    # ------------------------------------------------------------------
    # Search (simple keyword + tag search; semantic search via SemanticIndexer)
    # ------------------------------------------------------------------

    def search(
        self,
        query: str,
        top_k: int = 10,
        node_type: Optional[NodeType] = None,
        tags: Optional[List[str]] = None,
        min_weight: float = 0.0,
    ) -> List[Tuple[KNode, float, str]]:
        """
        Simple keyword/tag search. Returns list of (node, score, match_reason).
        For semantic search use SemanticIndexer.
        """
        query_lower = query.lower()
        query_terms = set(query_lower.split())
        candidates = self.list_nodes(node_type=node_type)

        results: List[Tuple[KNode, float, str]] = []
        for node in candidates:
            score = 0.0
            reasons = []

            if query_lower in node.display_name.lower():
                score += 10.0
                reasons.append("name_match")
            if query_lower in node.content.lower():
                score += 5.0
                reasons.append("content_match")
            if query_lower in node.description.lower():
                score += 3.0
                reasons.append("description_match")
            for term in query_terms:
                if term in node.id.lower():
                    score += 2.0
                    reasons.append("id_match")
                if term in " ".join(node.tags).lower():
                    score += 3.0
                    reasons.append("tag_match")
                if term in " ".join(node.aliases).lower():
                    score += 1.5
                    reasons.append("alias_match")

            if tags:
                tag_set = set(t.lower() for t in node.tags)
                overlap = query_terms & tag_set
                score += len(overlap) * 2.0

            if score > 0:
                results.append((node, score, "|".join(reasons)))

        results.sort(key=lambda x: x[1], reverse=True)
        return results[:top_k]

    # ------------------------------------------------------------------
    # Serialization
    # ------------------------------------------------------------------

    def save_index(self, path: Optional[str] = None) -> str:
        """Serialize nodes to JSON."""
        out_path = Path(path) if path else self.index_path
        if not out_path:
            raise ValueError("No index path specified")

        data = {
            "version": 1,
            "saved_at": time.time(),
            "node_count": len(self._nodes),
            "nodes": {nid: node.to_dict() for nid, node in self._nodes.items()},
        }
        out_path.parent.mkdir(parents=True, exist_ok=True)
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        self._dirty = False
        self._last_save = time.time()
        logger.info("KN index saved: %s (%d nodes)", out_path, len(self._nodes))
        return str(out_path)

    def _load_index(self) -> None:
        """Load node index from JSON file at index_path."""
        try:
            with open(self.index_path, encoding="utf-8") as f:
                data = json.load(f)
            nodes_data = data.get("nodes", {})
            for nid, ndata in nodes_data.items():
                node = KNode.from_dict(ndata)
                self._nodes[nid] = node
                self._nodes_by_type[node.node_type].append(nid)
            logger.info("KN index loaded: %d nodes from %s", len(self._nodes), self.index_path)
        except Exception as e:
            logger.error("Failed to load KN index: %s", e)

    def save_graph(self, path: Optional[str] = None) -> str:
        """Serialize edges to pickle."""
        out_path = Path(path) if path else self.graph_path
        if not out_path:
            raise ValueError("No graph path specified")

        data = {
            "version": 1,
            "saved_at": time.time(),
            "edge_count": len(self._edges),
            "edges": [e.to_dict() for e in self._edges],
        }
        out_path.parent.mkdir(parents=True, exist_ok=True)
        with open(out_path, "wb") as f:
            pickle.dump(data, f, protocol=pickle.HIGHEST_PROTOCOL)
        logger.info("KN graph saved: %s (%d edges)", out_path, len(self._edges))
        return str(out_path)

    def _load_graph(self) -> None:
        """Load edge graph from pickle file at graph_path."""
        try:
            with open(self.graph_path, "rb") as f:
                data = pickle.load(f)
            edges_data = data.get("edges", [])
            for edata in edges_data:
                edge = Edge.from_dict(edata)
                self._edges.append(edge)
                self._edges_by_source[edge.source_id].append(edge)
                self._edges_by_target[edge.target_id].append(edge)
            logger.info("KN graph loaded: %d edges from %s", len(self._edges), self.graph_path)
        except Exception as e:
            logger.error("Failed to load KN graph: %s", e)

    def auto_save_check(self) -> None:
        """Check if auto-save is needed."""
        if self.auto_save and self._dirty:
            elapsed = time.time() - self._last_save
            if elapsed >= self.save_interval:
                if self.index_path:
                    self.save_index()
                if self.graph_path:
                    self.save_graph()

    def stats(self) -> Dict[str, Any]:
        """Return network statistics.
        
        Returns:
            Dict with total_nodes, total_edges, nodes_by_type, and dirty flag.
        """
        return {
            "total_nodes": len(self._nodes),
            "total_edges": len(self._edges),
            "nodes_by_type": {nt.value: len(ids) for nt, ids in self._nodes_by_type.items()},
            "dirty": self._dirty,
        }