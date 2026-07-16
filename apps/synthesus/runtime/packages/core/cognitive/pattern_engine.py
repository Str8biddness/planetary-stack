#!/usr/bin/env python3
"""
PatternEngine — Generative Pattern Reasoning Module (V4.1 Beta)
AIVM Synthesus 2.0

Synthesizes unique, non-templated responses by "predicting" 
language based on character-specific patterns found in KAL.
"""

from __future__ import annotations

import logging
import time
from typing import Any, Dict, List, Optional

from ml.pattern_lm import PatternLM
from ml.dialogue_ranker import DialogueRanker

logger = logging.getLogger(__name__)


class PatternEngine:
    """
    Cognitive module that generates responses by chaining pattern word-transitions.
    Mixes transient FAISS-retrieved patterns with a massive global out-of-core LM.
    """

    def __init__(self, ranker: Optional[DialogueRanker] = None, global_db_path: str = "D:/synthesus_data/data/pattern_lm.db", substrate: Any = None):
        self._ranker = ranker or DialogueRanker()
        self.global_db_path = global_db_path
        self.substrate = substrate
        
        # Connect to the trillion-parameter out-of-core SQLite backend
        import os
        self.global_lm = PatternLM(order=3, db_path=self.global_db_path, substrate=self.substrate)
        # If DB exists, it's considered fitted (avoids loading everything into memory to check)
        self.global_lm._fitted = os.path.exists(self.global_db_path) or (self.substrate is not None)

    async def generate_response(
        self, 
        query: str, 
        kal_context: Dict[str, Any], 
        character_id: str = "global",
        temperature: float = 0.8
    ) -> Optional[Dict[str, Any]]:
        """
        Generate a response based on the retrieved KAL nodes, gracefully backing off 
        to the massive global parameter cloud if local domain knowledge is too sparse.
        """
        start_time = time.time()
        # kal_context can be a dict or a KalResult pydantic model
        nodes = kal_context.get("results") if isinstance(kal_context, dict) else getattr(kal_context, "results", [])
        if not nodes:
            return None

        # 1. Harvest corpus from KAL nodes
        corpus = []
        for node in nodes:
            content = getattr(node, "content", "")
            if "A:" in content:
                response_part = content.split("A:", 1)[1].strip()
                corpus.append(response_part)
            else:
                corpus.append(content)

        if not corpus:
            logger.info(f"PatternEngine: Transient Corpus is empty for {character_id}. Relying completely on Global Parameter Cloud.")

        logger.info(f"PatternEngine: Fitting transient LM on corpus of size {len(corpus)}")

        # 2. Build transient LM for this specific domain context
        transient_lm = PatternLM(order=1)
        if corpus:
            transient_lm.fit(corpus)

        # 3. Determine seed text
        seed = ""
        if corpus:
            words = transient_lm.tokenize(corpus[0])
            if words:
                import random
                seed = random.choice(words[:min(len(words), 3)])

        if not seed:
            seed_options = list(self.global_lm._transitions_by_order.get(0, {}).get(tuple(), {"The": 1}).keys())
            import random
            seed = random.choice(seed_options) if seed_options else "The"
            
        # 4. Generate with Interpolation & Backoff
        tokens = transient_lm.tokenize(seed)
        generated = []
        stop_tokens = [".", "!", "?", "\n"]
        
        import collections
        for _ in range(50):
            # High-quality transient domain knowledge
            transient_cands = transient_lm._get_candidates(tokens)
            
            # Massive general world knowledge (handles sparse/less vast domains)
            global_cands = {}
            if self.global_lm._fitted:
                global_cands = self.global_lm._get_candidates(tokens)
            
            mixed = collections.defaultdict(int)
            
            # Weight transient strongly (it's highly relevant to this exact moment/KAL retrieval)
            for k, v in transient_cands.items():
                mixed[k] += v * 20
                
            # Global provides diversity and smooths out the distribution
            for k, v in global_cands.items():
                mixed[k] += v
                
            if not mixed:
                break
                
            next_word = transient_lm._sample(mixed, temperature)
            tokens.append(next_word)
            generated.append(next_word)
            
            if next_word in stop_tokens:
                break

        # Reconstruct string
        import re
        generated_text = " ".join(generated)
        generated_text = re.sub(r'\s+([.,!?])', r'\1', generated_text)
        
        # Include seed at the start if it isn't punctuation
        if seed not in stop_tokens and not generated_text.startswith(seed):
             generated_text = f"{seed} {generated_text}"
             generated_text = generated_text.strip()
             generated_text = generated_text[0].upper() + generated_text[1:] if len(generated_text) > 0 else generated_text

        if len(generated_text.split()) < 2:
            return None

        latency_ms = (time.time() - start_time) * 1000

        return {
            "response": generated_text,
            "source": "pattern_engine",
            "confidence": 0.75,
            "debug": {
                "corpus_size": len(corpus),
                "seed": seed,
                "generation_latency_ms": round(latency_ms, 2),
                "character": character_id,
            }
        }

    async def synthesize_knowledge(
        self,
        knowledge_texts: List[str],
        voice_texts: List[str],
        query: str,
        temperature: float = 0.7,
        max_words: int = 40
    ) -> Optional[str]:
        """
        Synthesizes a response that blends factual knowledge with a character's voice.
        
        Args:
            knowledge_texts: List of factual descriptions and facts
            voice_texts: List of character-specific dialogue patterns for style
            query: The original player query to help seed the generation
            temperature: Sampling temperature
            max_words: Limit on output length
        """
        start_time = time.time()
        
        # 1. Clean and Prepare corpora
        k_corpus = [t.strip() for t in knowledge_texts if t.strip()]
        v_corpus = [t.strip() for t in voice_texts if t.strip()]
        
        if not k_corpus:
            return None
            
        # 2. Build transient LMs
        # We use a higher order for knowledge to preserve multi-word facts
        k_lm = PatternLM(order=2)
        k_lm.fit(k_corpus)
        
        # We use a lower order for voice to allow more "bleeding" into the style
        v_lm = PatternLM(order=1)
        if v_corpus:
            v_lm.fit(v_corpus)
            
        # 3. Determine seed text from query or knowledge
        import random
        tokens = k_lm.tokenize(query)
        # Find a noun or meaningful word from the query that exists in the knowledge
        seed = None
        for token in tokens:
            if len(token) > 3 and token in k_lm._transitions_by_order[0][tuple()]:
                seed = token
                break
        
        if not seed:
            seed_tokens = k_lm.tokenize(k_corpus[0])
            seed = random.choice(seed_tokens[:3]) if seed_tokens else "The"
            
        # 4. Generate with Weighted Blending
        curr_tokens = [seed]
        generated = [seed]
        stop_tokens = [".", "!", "?", "\n"]
        
        import collections
        for _ in range(max_words):
            k_cands = k_lm._get_candidates(curr_tokens)
            v_cands = v_lm._get_candidates(curr_tokens) if v_corpus else {}
            
            def normalize(counts):
                total = sum(counts.values()) or 1
                return {k: v / total for k, v in counts.items()}

            k_probs = normalize(k_cands)
            v_probs = normalize(v_cands)
            
            g_cands = self.global_lm._get_candidates(curr_tokens) if self.global_lm._fitted else {}
            g_probs = normalize(g_cands)
            
            # Blend probabilities
            mixed = collections.defaultdict(float)
            
            # Knowledge tokens get top priority (grounding)
            for k, p in k_probs.items():
                mixed[k] += p * 0.9  # 90% weight to knowledge (FAACTS FIRST)
                
            # Voice tokens provide the style/glue
            for k, p in v_probs.items():
                mixed[k] += p * 0.08  # 8% weight to character style
                
            # Global LM provides general language connectivity
            for k, p in g_probs.items():
                mixed[k] += p * 0.02  # 2% weight to general grammar
            
            if not mixed:
                break
                
            next_word = k_lm._sample(mixed, temperature)
            curr_tokens.append(next_word)
            generated.append(next_word)
            
            if next_word in stop_tokens:
                break
                
        # Reconstruct string
        import re
        result = " ".join(generated)
        result = re.sub(r'\s+([.,!?])', r'\1', result)
        
        # Capitalize and clean
        if result:
            result = result[0].upper() + result[1:]
            
        latency_ms = (time.time() - start_time) * 1000
        logger.debug(f"PatternEngine: Synthesized knowledge in {latency_ms:.1f}ms")
        
        return result

