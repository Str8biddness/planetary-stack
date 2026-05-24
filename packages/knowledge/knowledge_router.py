"""
Hybrid Knowledge Router — Intelligent Knowledge Source Routing for Synthesus.

Routes queries to the appropriate knowledge source based on query classification:
- Facts/General knowledge → Wikipedia
- Current events/Real-time → Web Search  
- Uploaded documents → RAG Document Store
- Personal/Game context → Knowledge Cloud

Provides unified interface with source attribution for reasoning transparency.
"""

import asyncio
import logging
import re
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Callable
from enum import Enum

logger = logging.getLogger(__name__)


class KnowledgeSource(Enum):
    """Available knowledge sources."""
    WIKIPEDIA = "wikipedia"
    WEB_SEARCH = "web_search"
    DOCUMENT_STORE = "document_store"
    KNOWLEDGE_CLOUD = "knowledge_cloud"
    DISTILLATION_RAG = "distillation_rag"
    FALLBACK = "fallback"


@dataclass
class KnowledgeResult:
    """Result from a knowledge source."""
    content: str
    source: KnowledgeSource
    confidence: float
    metadata: Dict[str, Any] = field(default_factory=dict)
    retrieval_time_ms: float = 0.0
    sources: List[str] = field(default_factory=list)


@dataclass
class RouterDecision:
    """The router's decision for a query."""
    primary_source: KnowledgeSource
    secondary_sources: List[KnowledgeSource]
    reasoning: str
    confidence: float
    query_classification: str


class QueryClassifier:
    """Classifies queries to determine optimal knowledge source."""
    
    # Patterns for classification
    PATTERNS = {
        "current_events": [
            r"\b(today|yesterday|now|recently|latest|news|current|happening)\b",
            r"\b(2024|2025|2026)\b",  # Recent years
            r"\b(just announced|breaking|update)\b",
        ],
        "historical_facts": [
            r"\b(when did|what year|historically|in history|ancient|century|decade)\b",
            r"\b(who invented|who discovered|first|origin of|history of)\b",
            r"\b(wikipedia|according to|definition of|what is|who is)\b",
        ],
        "personal_context": [
            r"\b(my|your|we|our|us|you said|previously|earlier|last time)\b",
            r"\b(my document|my file|uploaded|you mentioned)\b",
            r"\b(remember when|as I told you|in my)\b",
        ],
        "technical_domain": [
            r"\b(document|pdf|paper|article|research|study|report)\b",
            r"\b(code|function|api|library|framework|programming)\b",
            r"\b(data|analysis|dataset|statistics|metrics)\b",
        ],
        "complex_reasoning": [
            r"\b(explain|how does|why does|what if|analyze|compare)\b",
            r"\b(step by step|detailed|comprehensive|in depth|thoroughly)\b",
            r"\b(multiple|complex|intricate|relationship|connection)\b",
        ],
    }
    
    def classify(self, query: str) -> Dict[str, float]:
        """Classify query and return confidence scores for each type."""
        query_lower = query.lower()
        scores = {}
        
        for category, patterns in self.PATTERNS.items():
            score = 0.0
            for pattern in patterns:
                if re.search(pattern, query_lower):
                    score += 0.3
            scores[category] = min(score, 1.0)
        
        # Default to historical_facts if no strong signals
        if max(scores.values(), default=0) < 0.3:
            scores["historical_facts"] = 0.5
        
        return scores


class WikipediaSource:
    """Wikipedia API integration for general facts."""
    
    def __init__(self, cache_size: int = 100):
        self.cache: Dict[str, KnowledgeResult] = {}
        self.cache_size = cache_size
    
    async def query(self, query: str, top_k: int = 3) -> KnowledgeResult:
        """Query Wikipedia for factual information."""
        start = time.time()
        
        # Check cache
        cache_key = f"wiki:{query.lower().strip()}"
        if cache_key in self.cache:
            result = self.cache[cache_key]
            result.retrieval_time_ms = (time.time() - start) * 1000
            return result
        
        try:
            # Use httpx for async HTTP
            import httpx
            
            # Wikipedia search API
            search_url = "https://en.wikipedia.org/w/api.php"
            params = {
                "action": "query",
                "list": "search",
                "srsearch": query,
                "format": "json",
                "srlimit": top_k,
            }
            
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get(search_url, params=params)
                data = response.json()
                
                search_results = data.get("query", {}).get("search", [])
                
                if not search_results:
                    return KnowledgeResult(
                        content="",
                        source=KnowledgeSource.WIKIPEDIA,
                        confidence=0.0,
                        retrieval_time_ms=(time.time() - start) * 1000,
                    )
                
                # Get snippets from top results
                contents = []
                sources = []
                for result in search_results[:top_k]:
                    snippet = result.get("snippet", "").replace("<span class=\"searchmatch\">", "**").replace("</span>", "**")
                    title = result.get("title", "")
                    if snippet:
                        contents.append(f"**{title}**: {snippet}")
                        sources.append(f"Wikipedia: {title}")
                
                content = "\n\n".join(contents) if contents else ""
                confidence = min(len(search_results) * 0.3, 0.9)
                
                knowledge_result = KnowledgeResult(
                    content=content,
                    source=KnowledgeSource.WIKIPEDIA,
                    confidence=confidence,
                    metadata={"results_count": len(search_results)},
                    retrieval_time_ms=(time.time() - start) * 1000,
                    sources=sources,
                )
                
                # Cache result
                if len(self.cache) >= self.cache_size:
                    self.cache.pop(next(iter(self.cache)))
                self.cache[cache_key] = knowledge_result
                
                return knowledge_result
                
        except Exception as e:
            logger.error(f"Wikipedia query error: {e}")
            return KnowledgeResult(
                content="",
                source=KnowledgeSource.WIKIPEDIA,
                confidence=0.0,
                retrieval_time_ms=(time.time() - start) * 1000,
                metadata={"error": str(e)},
            )


class WebSearchSource:
    """Web search integration for current events (DuckDuckGo)."""
    
    def __init__(self, cache_size: int = 50):
        self.cache: Dict[str, KnowledgeResult] = {}
        self.cache_size = cache_size
    
    async def query(self, query: str, top_k: int = 3) -> KnowledgeResult:
        """Query web search for current information."""
        start = time.time()
        
        cache_key = f"web:{query.lower().strip()}"
        if cache_key in self.cache:
            result = self.cache[cache_key]
            result.retrieval_time_ms = (time.time() - start) * 1000
            return result
        
        try:
            # Use DuckDuckGo HTML interface (no API key required)
            import httpx
            from urllib.parse import quote_plus
            
            search_query = quote_plus(query)
            url = f"https://html.duckduckgo.com/html/?q={search_query}"
            
            async with httpx.AsyncClient(timeout=15.0, follow_redirects=True) as client:
                headers = {
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
                }
                response = await client.get(url, headers=headers)
                
                # Simple parsing of results
                html = response.text
                results = []
                sources = []
                
                # Extract result snippets (basic regex parsing)
                import re
                result_blocks = re.findall(r'<a class="result__a"[^>]*>(.*?)</a>.*?<a class="result__snippet"[^>]*>(.*?)</a>', html, re.DOTALL)
                
                for i, (title, snippet) in enumerate(result_blocks[:top_k]):
                    # Clean HTML tags
                    clean_snippet = re.sub(r'<[^>]+>', '', snippet)
                    clean_title = re.sub(r'<[^>]+>', '', title)
                    if clean_snippet:
                        results.append(f"**{clean_title}**: {clean_snippet}")
                        sources.append(f"Web: {clean_title}")
                
                content = "\n\n".join(results) if results else ""
                confidence = min(len(results) * 0.25, 0.8)
                
                knowledge_result = KnowledgeResult(
                    content=content,
                    source=KnowledgeSource.WEB_SEARCH,
                    confidence=confidence,
                    metadata={"results_count": len(results)},
                    retrieval_time_ms=(time.time() - start) * 1000,
                    sources=sources,
                )
                
                if len(self.cache) >= self.cache_size:
                    self.cache.pop(next(iter(self.cache)))
                self.cache[cache_key] = knowledge_result
                
                return knowledge_result
                
        except Exception as e:
            logger.error(f"Web search error: {e}")
            return KnowledgeResult(
                content="",
                source=KnowledgeSource.WEB_SEARCH,
                confidence=0.0,
                retrieval_time_ms=(time.time() - start) * 1000,
                metadata={"error": str(e)},
            )


class DocumentStoreSource:
    """RAG-based document store for uploaded documents."""
    
    def __init__(self, rag_pipeline=None):
        self.rag_pipeline = rag_pipeline
        self.documents: Dict[str, Dict[str, Any]] = {}
    
    async def query(self, query: str, namespace: Optional[str] = None, top_k: int = 3) -> KnowledgeResult:
        """Query uploaded documents via RAG."""
        start = time.time()
        
        if self.rag_pipeline is None:
            return KnowledgeResult(
                content="",
                source=KnowledgeSource.DOCUMENT_STORE,
                confidence=0.0,
                metadata={"error": "RAG pipeline not initialized"},
            )
        
        try:
            # Query RAG pipeline
            namespaces = [namespace] if namespace else None
            result = await self.rag_pipeline.retrieve(
                query=query,
                namespaces=namespaces,
                top_k=top_k,
            )
            
            context = result.get("context", "")
            sources_data = result.get("sources", [])
            
            sources = [f"Document: {s.get('pattern', 'Unknown')[:50]}..." for s in sources_data]
            
            confidence = min(len(sources_data) * 0.3, 0.9) if sources_data else 0.0
            
            return KnowledgeResult(
                content=context,
                source=KnowledgeSource.DOCUMENT_STORE,
                confidence=confidence,
                metadata={"documents_found": len(sources_data)},
                retrieval_time_ms=(time.time() - start) * 1000,
                sources=sources,
            )
            
        except Exception as e:
            logger.error(f"Document store query error: {e}")
            return KnowledgeResult(
                content="",
                source=KnowledgeSource.DOCUMENT_STORE,
                confidence=0.0,
                retrieval_time_ms=(time.time() - start) * 1000,
                metadata={"error": str(e)},
            )
    
    def add_document(self, doc_id: str, content: str, metadata: Dict[str, Any]):
        """Add a document to the store."""
        self.documents[doc_id] = {
            "content": content,
            "metadata": metadata,
            "added_at": time.time(),
        }


class HybridKnowledgeRouter:
    """
    Routes queries to optimal knowledge sources based on query classification.
    
    Provides unified interface with automatic source selection and merging.
    """
    
    def __init__(
        self,
        rag_pipeline=None,
        knowledge_cloud=None,
        enable_wikipedia: bool = True,
        enable_web_search: bool = True,
        enable_distillation: bool = True,
    ):
        self.classifier = QueryClassifier()
        
        # Initialize sources
        self.sources: Dict[KnowledgeSource, Any] = {}
        
        if enable_wikipedia:
            self.sources[KnowledgeSource.WIKIPEDIA] = WikipediaSource()
        
        if enable_web_search:
            self.sources[KnowledgeSource.WEB_SEARCH] = WebSearchSource()
        
        self.sources[KnowledgeSource.DOCUMENT_STORE] = DocumentStoreSource(rag_pipeline)
        
        if knowledge_cloud:
            self.sources[KnowledgeSource.KNOWLEDGE_CLOUD] = knowledge_cloud
        
        # Initialize distillation RAG source
        if enable_distillation:
            try:
                from core.distillation_rag_source import get_distillation_source
                self.sources[KnowledgeSource.DISTILLATION_RAG] = get_distillation_source()
                logger.info("Distillation RAG source initialized")
            except Exception as e:
                logger.warning(f"Failed to initialize distillation source: {e}")
        
        # Source routing map based on classification
        self.routing_map = {
            "current_events": [KnowledgeSource.WEB_SEARCH, KnowledgeSource.WIKIPEDIA],
            "historical_facts": [KnowledgeSource.WIKIPEDIA, KnowledgeSource.KNOWLEDGE_CLOUD],
            "personal_context": [KnowledgeSource.KNOWLEDGE_CLOUD, KnowledgeSource.DOCUMENT_STORE],
            "technical_domain": [KnowledgeSource.DOCUMENT_STORE, KnowledgeSource.WIKIPEDIA],
            "complex_reasoning": [KnowledgeSource.DISTILLATION_RAG, KnowledgeSource.WIKIPEDIA],
        }
    
    def decide_sources(self, query: str) -> RouterDecision:
        """Decide which sources to query based on classification."""
        classifications = self.classifier.classify(query)
        
        # Get highest scoring classification
        top_category = max(classifications, key=classifications.get)
        top_score = classifications[top_category]
        
        # Map to sources
        source_priority = self.routing_map.get(
            top_category, 
            [KnowledgeSource.WIKIPEDIA, KnowledgeSource.KNOWLEDGE_CLOUD]
        )
        
        # Filter to available sources
        available_sources = [s for s in source_priority if s in self.sources]
        
        if not available_sources:
            available_sources = [KnowledgeSource.FALLBACK]
        
        primary = available_sources[0]
        secondary = available_sources[1:] if len(available_sources) > 1 else []
        
        reasoning = f"Query classified as '{top_category}' ({top_score:.0%} confidence). "
        reasoning += f"Primary source: {primary.value}."
        if secondary:
            reasoning += f" Secondary: {', '.join(s.value for s in secondary)}."
        
        return RouterDecision(
            primary_source=primary,
            secondary_sources=secondary,
            reasoning=reasoning,
            confidence=top_score,
            query_classification=top_category,
        )
    
    async def query(
        self,
        query: str,
        force_source: Optional[KnowledgeSource] = None,
        merge_results: bool = True,
        top_k: int = 3,
    ) -> KnowledgeResult:
        """
        Query the knowledge system with automatic routing.
        
        Args:
            query: The user's question
            force_source: Optional source to force (bypasses routing)
            merge_results: Whether to merge primary + secondary results
            top_k: Number of results per source
            
        Returns:
            KnowledgeResult with content and source attribution
        """
        start = time.time()
        
        # Decide sources
        if force_source:
            decision = RouterDecision(
                primary_source=force_source,
                secondary_sources=[],
                reasoning=f"Forced source: {force_source.value}",
                confidence=1.0,
                query_classification="forced",
            )
        else:
            decision = self.decide_sources(query)
        
        logger.info(f"KnowledgeRouter: {decision.reasoning}")
        
        # Query primary source
        primary_result = await self._query_source(
            decision.primary_source, query, top_k
        )
        
        # Query secondary sources if merge enabled and primary confidence low
        all_results = [primary_result]
        if merge_results and primary_result.confidence < 0.7 and decision.secondary_sources:
            for secondary in decision.secondary_sources:
                secondary_result = await self._query_source(secondary, query, top_k)
                if secondary_result.confidence > 0.3:
                    all_results.append(secondary_result)
        
        # Merge results
        merged = self._merge_results(all_results, decision)
        merged.retrieval_time_ms = (time.time() - start) * 1000
        
        return merged
    
    async def _query_source(
        self,
        source: KnowledgeSource,
        query: str,
        top_k: int,
    ) -> KnowledgeResult:
        """Query a specific source."""
        source_handler = self.sources.get(source)
        
        if source_handler is None:
            return KnowledgeResult(
                content="",
                source=source,
                confidence=0.0,
                metadata={"error": "Source not available"},
            )
        
        try:
            if source == KnowledgeSource.WIKIPEDIA:
                return await source_handler.query(query, top_k)
            elif source == KnowledgeSource.WEB_SEARCH:
                return await source_handler.query(query, top_k)
            elif source == KnowledgeSource.DOCUMENT_STORE:
                return await source_handler.query(query, top_k=top_k)
            elif source == KnowledgeSource.DISTILLATION_RAG:
                # Distillation RAG source
                result = source_handler.query(query, use_rag=True, top_k=top_k)
                # Convert DistillationResult to KnowledgeResult
                return KnowledgeResult(
                    content=result.answer,
                    source=KnowledgeSource.DISTILLATION_RAG,
                    confidence=result.confidence,
                    metadata={
                        "model_used": result.model_used,
                        "retrieval_method": result.retrieval_method,
                        "sources": result.sources,
                    },
                    retrieval_time_ms=result.latency_ms,
                    sources=[f"{s.get('source_type', 'unknown')}: {s.get('content', '')[:50]}..." for s in result.sources] if result.sources else [],
                )
            elif source == KnowledgeSource.KNOWLEDGE_CLOUD:
                # Knowledge cloud uses lookup interface
                result = source_handler.lookup(query, top_k=top_k)
                if result:
                    return KnowledgeResult(
                        content=result.get("response", ""),
                        source=KnowledgeSource.KNOWLEDGE_CLOUD,
                        confidence=result.get("confidence", 0.5),
                        metadata=result,
                        sources=[f"KnowledgeCloud: {result.get('entity_name', 'Unknown')}"],
                    )
                return KnowledgeResult(
                    content="",
                    source=KnowledgeSource.KNOWLEDGE_CLOUD,
                    confidence=0.0,
                )
            else:
                return KnowledgeResult(
                    content="",
                    source=source,
                    confidence=0.0,
                    metadata={"error": "Unknown source type"},
                )
        except Exception as e:
            logger.error(f"Error querying {source.value}: {e}")
            return KnowledgeResult(
                content="",
                source=source,
                confidence=0.0,
                metadata={"error": str(e)},
            )
    
    def _merge_results(
        self,
        results: List[KnowledgeResult],
        decision: RouterDecision,
    ) -> KnowledgeResult:
        """Merge results from multiple sources."""
        if not results:
            return KnowledgeResult(
                content="",
                source=KnowledgeSource.FALLBACK,
                confidence=0.0,
                metadata={"routing_decision": decision.reasoning},
            )
        
        # Sort by confidence
        results = sorted(results, key=lambda r: r.confidence, reverse=True)
        
        # Build merged content
        content_parts = []
        all_sources = []
        total_confidence = 0.0
        
        for i, result in enumerate(results):
            if result.confidence > 0.2 and result.content:
                prefix = ""
                if i == 0:
                    prefix = f"[Primary: {result.source.value}]\n"
                else:
                    prefix = f"\n[Supplementary: {result.source.value}]\n"
                
                content_parts.append(prefix + result.content)
                total_confidence += result.confidence
                all_sources.extend(result.sources)
        
        merged_content = "\n\n".join(content_parts)
        avg_confidence = total_confidence / len(results) if results else 0.0
        
        # Use primary source but note it's merged
        primary = results[0]
        
        return KnowledgeResult(
            content=merged_content,
            source=primary.source,
            confidence=avg_confidence,
            metadata={
                "routing_decision": decision.reasoning,
                "sources_queried": [r.source.value for r in results],
                "source_confidences": {r.source.value: r.confidence for r in results},
            },
            sources=list(set(all_sources)),  # Deduplicate
        )


# Singleton instance
_router_instance: Optional[HybridKnowledgeRouter] = None


def get_knowledge_router(
    rag_pipeline=None,
    knowledge_cloud=None,
    enable_wikipedia: bool = True,
    enable_web_search: bool = True,
    enable_distillation: bool = True,
) -> HybridKnowledgeRouter:
    """Get or create the knowledge router singleton."""
    global _router_instance
    if _router_instance is None:
        _router_instance = HybridKnowledgeRouter(
            rag_pipeline=rag_pipeline,
            knowledge_cloud=knowledge_cloud,
            enable_wikipedia=enable_wikipedia,
            enable_web_search=enable_web_search,
            enable_distillation=enable_distillation,
        )
    return _router_instance
