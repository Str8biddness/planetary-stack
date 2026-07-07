"""
Distillation RAG Source — Lightweight Transformer + ChromaDB for Synthesus

Integrates Knowledge Distillation from ConsciousLlmAi repo:
- DistilGPT-2 for text generation
- DistilBERT for Q&A and classification
- ChromaDB vector store (alternative to FAISS)
- In-memory fallback for resource-constrained environments

Provides RAG-augmented responses with distilled model inference.
"""

import logging
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple
from datetime import datetime
from pathlib import Path

logger = logging.getLogger(__name__)

# Optional dependencies with graceful fallback
HAS_TRANSFORMERS = False
HAS_CHROMADB = False

try:
    from transformers import pipeline, AutoTokenizer
    HAS_TRANSFORMERS = True
except ImportError:
    logger.warning("transformers not available - distillation features limited")

try:
    import chromadb
    from chromadb.config import Settings
    HAS_CHROMADB = True
except ImportError:
    logger.warning("chromadb not available - using in-memory storage")


@dataclass
class DistillationResult:
    """Result from distillation-based knowledge retrieval."""
    answer: str
    sources: List[Dict[str, Any]]
    confidence: float
    model_used: str
    retrieval_method: str  # "chromadb" or "in-memory"
    latency_ms: float = 0.0
    metadata: Dict[str, Any] = field(default_factory=dict)


class DistillationModelManager:
    """
    Manages lightweight pre-distilled models for text generation,
    summarization, and Q&A with minimal resource footprint.
    """
    
    def __init__(self, cache_dir: str = "./model_cache", device: str = "cpu"):
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(exist_ok=True)
        self.device = device
        self.models: Dict[str, Any] = {}
        self.metadata = {
            "initialized_at": datetime.now().isoformat(),
            "models": {},
            "has_transformers": HAS_TRANSFORMERS,
        }
        
        if HAS_TRANSFORMERS:
            self._initialize_models()
        else:
            logger.warning("Transformers not available. Model features limited.")
    
    def _initialize_models(self):
        """Initialize lightweight distilled models."""
        try:
            # Text generation with DistilGPT-2
            logger.info("Loading DistilGPT-2 for text generation...")
            self.models['text_generation'] = pipeline(
                "text-generation",
                model="distilgpt2",
                device=-1 if self.device == "cpu" else 0,
                max_length=128,
                truncation=True,
            )
            self.metadata["models"]["text_generation"] = "distilgpt2"
            
            # Classification with BART-MNLI (zero-shot)
            logger.info("Loading zero-shot classification model...")
            self.models['classification'] = pipeline(
                "zero-shot-classification",
                model="facebook/bart-large-mnli",
                device=-1 if self.device == "cpu" else 0,
            )
            self.metadata["models"]["classification"] = "facebook/bart-large-mnli"
            
            # Q&A with DistilBERT
            logger.info("Loading Q&A model...")
            self.models['qa'] = pipeline(
                "question-answering",
                model="deepset/distilbert-base-uncased-squad2",
                device=-1 if self.device == "cpu" else 0,
            )
            self.metadata["models"]["qa"] = "deepset/distilbert-base-uncased-squad2"
            
            logger.info(f"Successfully initialized {len(self.models)} distillation models")
            
        except Exception as e:
            logger.error(f"Error initializing distillation models: {e}")
            self.metadata["initialization_error"] = str(e)
    
    def generate_text(self, prompt: str, max_length: int = 100) -> str:
        """Generate text using DistilGPT-2."""
        if 'text_generation' not in self.models:
            return "[Distillation models not available - install transformers]"
        
        try:
            result = self.models['text_generation'](
                prompt,
                max_length=max_length,
                num_return_sequences=1,
                temperature=0.7,
                top_p=0.9,
                do_sample=True,
            )
            return result[0]['generated_text']
        except Exception as e:
            logger.error(f"Text generation error: {e}")
            return f"[Generation error: {str(e)[:100]}]"
    
    def answer_question(self, question: str, context: str) -> Dict[str, Any]:
        """Answer questions using DistilBERT-based Q&A model."""
        if 'qa' not in self.models:
            return {"error": "Q&A model not loaded", "answer": "", "score": 0.0}
        
        try:
            result = self.models['qa'](
                question=question,
                context=context[:2000],  # Limit context length
            )
            return {
                "question": question,
                "answer": result['answer'],
                "score": float(result['score']),
                "start": result.get('start', 0),
                "end": result.get('end', 0),
            }
        except Exception as e:
            logger.error(f"Q&A error: {e}")
            return {"error": str(e), "answer": "", "score": 0.0}
    
    def classify_intent(self, text: str, candidate_labels: List[str]) -> Dict[str, Any]:
        """Classify text intent using zero-shot classification."""
        if 'classification' not in self.models:
            return {"error": "Classification model not loaded"}
        
        try:
            result = self.models['classification'](
                text,
                candidate_labels,
                multi_label=False,
            )
            return {
                "text": text,
                "labels": result['labels'],
                "scores": result['scores'],
                "top_label": result['labels'][0],
                "top_score": result['scores'][0],
            }
        except Exception as e:
            logger.error(f"Classification error: {e}")
            return {"error": str(e)}
    
    def get_simple_embeddings(self, texts: List[str]) -> List[List[float]]:
        """Generate simple embeddings using tokenizer."""
        if not HAS_TRANSFORMERS:
            return [[0.0] * 128 for _ in texts]
        
        try:
            tokenizer = AutoTokenizer.from_pretrained("distilbert-base-uncased")
            embeddings = []
            for text in texts:
                tokens = tokenizer.encode(
                    text,
                    max_length=128,
                    padding='max_length',
                    truncation=True,
                )
                # Normalize token IDs to float embeddings
                embeddings.append([float(t) / 30522.0 for t in tokens[:128]])
            return embeddings
        except Exception as e:
            logger.error(f"Embedding error: {e}")
            return [[0.0] * 128 for _ in texts]
    
    def get_model_info(self) -> Dict[str, Any]:
        """Get information about loaded models."""
        return {
            "device": self.device,
            "models_loaded": list(self.models.keys()),
            "metadata": self.metadata,
        }


class DistillationRAGSource:
    """
    RAG source using distilled models + ChromaDB for Synthesus.
    
    Provides:
    - Vector storage with ChromaDB (or in-memory fallback)
    - DistilBERT-based Q&A on retrieved context
    - DistilGPT-2 for context-aware generation
    """
    
    def __init__(
        self,
        collection_name: str = "synthesus_distillation",
        persist_dir: str = "./data/chroma_distillation",
        device: str = "cpu",
    ):
        self.collection_name = collection_name
        self.persist_dir = persist_dir
        self.device = device
        
        # Initialize model manager
        self.model_manager = DistillationModelManager(device=device)
        
        # Initialize ChromaDB or fallback
        self.use_chromadb = HAS_CHROMADB
        self.client = None
        self.collection = None
        
        if HAS_CHROMADB:
            try:
                self.client = chromadb.Client(Settings(
                    chroma_db_impl="duckdb+parquet",
                    persist_directory=persist_dir,
                ))
                self.collection = self.client.get_or_create_collection(
                    name=collection_name
                )
                logger.info(f"ChromaDB initialized: {collection_name}")
            except Exception as e:
                logger.warning(f"ChromaDB init failed: {e}. Using in-memory.")
                self.use_chromadb = False
        
        # In-memory fallback storage
        self.knowledge_base: Dict[str, Dict[str, Any]] = {}
        self.knowledge_embeddings: Dict[str, List[float]] = {}
    
    def add_documents(
        self,
        documents: List[str],
        metadata_list: Optional[List[Dict]] = None,
    ) -> Dict[str, Any]:
        """Add documents to the knowledge base."""
        try:
            # Generate embeddings
            embeddings = self.model_manager.get_simple_embeddings(documents)
            
            if not embeddings:
                return {"error": "Failed to generate embeddings"}
            
            # Prepare IDs and metadata
            ids = [
                f"doc_{i}_{int(time.time() * 1000)}"
                for i in range(len(documents))
            ]
            metadatas = metadata_list or [
                {"source": "distillation_rag"} for _ in documents
            ]
            
            # Add to ChromaDB if available
            if self.use_chromadb and self.collection:
                try:
                    self.collection.add(
                        ids=ids,
                        embeddings=embeddings,
                        documents=documents,
                        metadatas=metadatas,
                    )
                except Exception as e:
                    logger.warning(f"ChromaDB add failed: {e}")
            
            # Store in memory
            for doc_id, doc, meta, emb in zip(ids, documents, metadatas, embeddings):
                self.knowledge_base[doc_id] = {
                    "content": doc,
                    "metadata": meta,
                    "added_at": datetime.now().isoformat(),
                }
                self.knowledge_embeddings[doc_id] = emb
            
            return {
                "status": "success",
                "documents_added": len(documents),
                "total_documents": len(self.knowledge_base),
                "storage_type": "chromadb" if self.use_chromadb else "in-memory",
            }
            
        except Exception as e:
            logger.error(f"Error adding documents: {e}")
            return {"error": str(e)}
    
    def _cosine_similarity(
        self,
        vec1: List[float],
        vec2: List[float],
    ) -> float:
        """Calculate cosine similarity between two vectors."""
        if not vec1 or not vec2:
            return 0.0
        
        dot_product = sum(a * b for a, b in zip(vec1, vec2))
        norm1 = sum(a ** 2 for a in vec1) ** 0.5
        norm2 = sum(b ** 2 for b in vec2) ** 0.5
        
        if norm1 == 0 or norm2 == 0:
            return 0.0
        return dot_product / (norm1 * norm2)
    
    def retrieve(
        self,
        query: str,
        top_k: int = 5,
    ) -> Tuple[List[Dict[str, Any]], str]:
        """Retrieve relevant documents for a query."""
        try:
            # Generate query embedding
            query_embedding = self.model_manager.get_simple_embeddings([query])[0]
            
            # Try ChromaDB first
            if self.use_chromadb and self.collection:
                try:
                    results = self.collection.query(
                        query_embeddings=[query_embedding],
                        n_results=top_k,
                        include=["documents", "metadatas", "distances"],
                    )
                    
                    retrieved = []
                    if results and results['documents']:
                        for doc, meta, distance in zip(
                            results['documents'][0],
                            results['metadatas'][0],
                            results['distances'][0],
                        ):
                            retrieved.append({
                                "content": doc,
                                "metadata": meta,
                                "relevance_score": 1 - (distance / 2),
                                "source_type": "chromadb",
                            })
                    
                    return retrieved, "chromadb"
                    
                except Exception as e:
                    logger.warning(f"ChromaDB query failed: {e}")
            
            # Fallback: in-memory cosine similarity
            scores = []
            for doc_id, embedding in self.knowledge_embeddings.items():
                score = self._cosine_similarity(query_embedding, embedding)
                scores.append((doc_id, score))
            
            # Sort by score
            scores.sort(key=lambda x: x[1], reverse=True)
            
            retrieved = []
            for doc_id, score in scores[:top_k]:
                doc_data = self.knowledge_base[doc_id]
                retrieved.append({
                    "content": doc_data["content"],
                    "metadata": doc_data["metadata"],
                    "relevance_score": score,
                    "source_type": "in-memory",
                })
            
            return retrieved, "in-memory"
            
        except Exception as e:
            logger.error(f"Error retrieving documents: {e}")
            return [], "error"
    
    def query(
        self,
        query: str,
        use_rag: bool = True,
        top_k: int = 3,
    ) -> DistillationResult:
        """
        Query with RAG-augmented distillation.
        
        1. Retrieve relevant documents
        2. Use DistilBERT Q&A on combined context
        3. Fall back to direct generation if needed
        """
        start = time.time()
        
        try:
            result = DistillationResult(
                answer="",
                sources=[],
                confidence=0.0,
                model_used="none",
                retrieval_method="none",
                latency_ms=0.0,
            )
            
            # Retrieve context
            if use_rag:
                retrieved_docs, method = self.retrieve(query, top_k=top_k)
                result.retrieval_method = method
                result.sources = retrieved_docs
                
                if retrieved_docs:
                    # Combine retrieved documents as context
                    context = "\n\n".join([
                        doc["content"]
                        for doc in retrieved_docs[:3]  # Limit context
                    ])
                    
                    # Answer with DistilBERT Q&A
                    qa_result = self.model_manager.answer_question(query, context)
                    
                    if "error" not in qa_result:
                        result.answer = qa_result.get("answer", "")
                        result.confidence = qa_result.get("score", 0.0)
                        result.model_used = "distilbert-qa"
                        result.metadata = {
                            "qa_start": qa_result.get("start", 0),
                            "qa_end": qa_result.get("end", 0),
                        }
                    else:
                        # Fall back to generation
                        prompt = f"Context: {context[:1000]}\n\nQuestion: {query}\n\nAnswer:"
                        result.answer = self.model_manager.generate_text(
                            prompt,
                            max_length=150,
                        )
                        result.confidence = 0.5
                        result.model_used = "distilgpt2"
                        result.metadata = {"fallback_to_generation": True}
                else:
                    # No retrieved documents - direct generation
                    result.answer = self.model_manager.generate_text(
                        f"Question: {query}\n\nAnswer:",
                        max_length=150,
                    )
                    result.confidence = 0.3
                    result.model_used = "distilgpt2-direct"
            else:
                # No RAG - direct generation
                result.answer = self.model_manager.generate_text(
                    f"Question: {query}\n\nAnswer:",
                    max_length=150,
                )
                result.confidence = 0.4
                result.model_used = "distilgpt2-direct"
            
            result.latency_ms = (time.time() - start) * 1000
            return result
            
        except Exception as e:
            logger.error(f"Distillation query error: {e}")
            return DistillationResult(
                answer=f"[Error: {str(e)[:100]}]",
                sources=[],
                confidence=0.0,
                model_used="error",
                retrieval_method="error",
                latency_ms=(time.time() - start) * 1000,
                metadata={"error": str(e)},
            )
    
    def get_stats(self) -> Dict[str, Any]:
        """Get statistics about the distillation source."""
        return {
            "collection_name": self.collection_name,
            "total_documents": len(self.knowledge_base),
            "storage_type": "chromadb" if self.use_chromadb else "in-memory",
            "model_info": self.model_manager.get_model_info(),
            "has_transformers": HAS_TRANSFORMERS,
            "has_chromadb": HAS_CHROMADB,
        }


# Singleton instance
_distillation_source_instance: Optional[DistillationRAGSource] = None


def get_distillation_source(
    collection_name: str = "synthesus_distillation",
    device: str = "cpu",
) -> DistillationRAGSource:
    """Get or create the distillation RAG source singleton."""
    global _distillation_source_instance
    if _distillation_source_instance is None:
        _distillation_source_instance = DistillationRAGSource(
            collection_name=collection_name,
            device=device,
        )
    return _distillation_source_instance
