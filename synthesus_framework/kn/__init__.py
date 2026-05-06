"""
KN Module — Knowledge Network for Synthesus
============================================

The KN provides persistent, queryable memory of entities, relationships, and facts.
Organised as a graph of typed nodes connected by weighted edges.

Key Classes:
- KNode: Base knowledge node
- PersonNode, PlaceNode, ItemNode, FactionNode, EventNode, KnowledgeNode: Specialized nodes
- Edge: Directed weighted relationship between nodes
- KnowledgeNetwork: Core graph manager with search, context, and serialization
- SemanticIndexer: FAISS-backed vector semantic search
- EntityLinker: Text-to-node mention resolution
- GraphConnector: Bulk import pipeline for external data

Usage:
    from kn import KnowledgeNetwork, SemanticIndexer, EntityLinker, GraphConnector
    from kn.node import NodeType, KNode

    kn = KnowledgeNetwork(index_path="data/kn_index.json", graph_path="data/knowledge_graph.pkl")
    kn.register_node(KNode(id="dragon", node_type=NodeType.CREATURE, content="..."))

    indexer = SemanticIndexer(kn=kn)
    indexer.index_nodes(kn.list_nodes())
    results = indexer.search("fire-breathing creatures", top_k=5)

    linker = EntityLinker(kn=kn)
    result = linker.link_mention("The Red Dragon")

    connector = GraphConnector(kn=kn, linker=linker, indexer=indexer)
    connector.import_json("data/world_lore.json")
"""

from .node import (
    NodeType,
    EdgeType,
    Edge,
    KNode,
    PersonNode,
    PlaceNode,
    ItemNode,
    FactionNode,
    EventNode,
    KnowledgeNode,
    create_node,
)

from .network import KnowledgeNetwork
from .semantic_indexer import SemanticIndexer
from .entity_linker import EntityLinker
from .graph_connector import GraphConnector

__all__ = [
    # node types
    "NodeType",
    "EdgeType",
    "Edge",
    "KNode",
    "PersonNode",
    "PlaceNode",
    "ItemNode",
    "FactionNode",
    "EventNode",
    "KnowledgeNode",
    "create_node",
    # core graph
    "KnowledgeNetwork",
    # search
    "SemanticIndexer",
    # linking
    "EntityLinker",
    # import
    "GraphConnector",
]