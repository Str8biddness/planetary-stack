"""
Public Facade for the Expansion Drive.
Provides a stable, frozen API for ingestion and retrieval, hiding internal
connector and RAG mechanics.
"""

import asyncio
from typing import List, Dict, Any

from knowledge.rag_pipeline import RAGPipeline
from knowledge.connectors.registry import get_loader
from knowledge.connectors.base import IngestResult

class ExpansionDrive:
    def __init__(self, index_path: str = "./data/faiss.index", metadata_path: str = "./data/faiss_metadata.json"):
        self.rag = RAGPipeline(index_path=index_path, metadata_path=metadata_path)

    def ingest(self, connector: str, target: str, name: str) -> IngestResult:
        """
        Ingest a target (folder path, git repo URL, etc.) using the specified connector.
        """
        loader = get_loader(connector)
        result, _label = loader(self.rag, target, namespace=name)
        return result

    def retrieve(self, query: str) -> List[Dict[str, Any]]:
        """
        Search the entire index. Returns a list of source dicts.
        """
        res = self._run_async(self.rag.retrieve(query))
        return res.get("sources", [])

    def list_drives(self) -> List[Dict[str, Any]]:
        """
        List all ingested drives (namespaces) and their basic stats.
        """
        drives = {}
        for meta in self.rag._metadata:
            ns = meta.get("namespace")
            if not ns or ns == "general":
                continue
            if ns not in drives:
                drives[ns] = {
                    "namespace": ns,
                    "domain": meta.get("domain", ""),
                    "chunks": 0
                }
            drives[ns]["chunks"] += 1
        return list(drives.values())

    def preview(self, namespace: str, query: str, k: int = 5) -> List[Dict[str, Any]]:
        """
        Preview retrieved results scoped to a specific namespace.
        """
        res = self._run_async(self.rag.retrieve(query, namespaces=[namespace], top_k=k))
        return res.get("sources", [])

    def _run_async(self, coro):
        try:
            loop = asyncio.get_event_loop()
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            
        if loop.is_running():
            import nest_asyncio
            nest_asyncio.apply()
            
        return loop.run_until_complete(coro)
