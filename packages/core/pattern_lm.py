#!/usr/bin/env python3
"""
PatternLM — Pattern-Based Language Model
AIVM Synthesus 2.0

A lightweight word-level N-Gram / Markov model designed to "predict" 
the next word based on character-specific patterns and lore.

Features:
- N-Gram transition matrix (default order=2).
- Probabilistic next-word sampling.
- Seamless integration with pattern corpora.
- Out-of-core scaling with SQLite backend.
- Stupid Backoff smoothing for domain diversification.
"""

from __future__ import annotations

import collections
import random
import re
import sqlite3
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Any


class PatternLM:
    """
    A word-level N-Gram model trained on character-specific patterns.
    """

    def __init__(self, order: int = 2, db_path: Optional[str] = None, substrate: Any = None):
        self.order = order
        self.db_path = db_path
        self.substrate = substrate
        self._fitted = False
        
        # In-memory transitions tracking
        self._transitions_by_order: Dict[int, Dict[Tuple[str, ...], Dict[str, int]]] = collections.defaultdict(
            lambda: collections.defaultdict(lambda: collections.defaultdict(int))
        )
        
        self._transitions: Dict[Tuple[str, ...], Dict[str, int]] = self._transitions_by_order[self.order]

        if self.db_path:
            self._init_db()

    def _init_db(self):
        db_file = Path(self.db_path)
        db_file.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(db_file) as conn:
            conn.execute('''
                CREATE TABLE IF NOT EXISTS ngrams (
                    order_n INTEGER,
                    context TEXT,
                    next_token TEXT,
                    count INTEGER,
                    PRIMARY KEY (order_n, context, next_token)
                )
            ''')
            # Index for fast lookups by context
            conn.execute('CREATE INDEX IF NOT EXISTS idx_context ON ngrams(order_n, context)')

    def tokenize(self, text: str) -> List[str]:
        """Simple word-level tokenizer."""
        # Clean and split, keeping some basic punctuation as markers
        text = text.lower()
        # Add spaces around punctuation we want to keep as tokens
        text = re.sub(r'([.,!?*])', r' \1 ', text)
        tokens = text.split()
        return tokens

    def fit(self, texts: List[str]):
        """Train the model on a corpus of patterns."""
        if not texts:
            return

        # Prepare batch updates if using database
        db_updates = collections.defaultdict(int)

        for text in texts:
            tokens = self.tokenize(text)
            if len(tokens) <= 1:
                continue

            # For each token, train on contexts of size 1 up to self.order
            for i in range(1, len(tokens)):
                next_token = tokens[i]
                for n in range(1, min(i, self.order) + 1):
                    context = tuple(tokens[i - n : i])
                    
                    if self.db_path:
                        db_updates[(n, " ".join(context), next_token)] += 1
                    else:
                        self._transitions_by_order[n][context][next_token] += 1
                        
                # Also capture 0-order (unigram) as a fallback starting point (empty context)
                if self.db_path:
                    db_updates[(0, "", next_token)] += 1
                else:
                    self._transitions_by_order[0][tuple()][next_token] += 1
        
        if self.db_path and db_updates:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                for (n, ctx_str, nxt), cnt in db_updates.items():
                    cursor.execute('''
                        INSERT INTO ngrams (order_n, context, next_token, count)
                        VALUES (?, ?, ?, ?)
                        ON CONFLICT(order_n, context, next_token) DO UPDATE SET count = count + ?
                    ''', (n, ctx_str, nxt, cnt, cnt))
                conn.commit()

        self._fitted = True

    def _get_candidates(self, context_tokens: List[str]) -> Dict[str, int]:
        """
        Get next token candidates. Handles Stupid Backoff to lower orders 
        if the requested context is not found in the model.
        """
        # Start from max possible order down to 0 (unigram baseline)
        for n in range(min(len(context_tokens), self.order), -1, -1):
            context = tuple(context_tokens[-n:]) if n > 0 else tuple()
            ctx_str = " ".join(context)

            # 1. Check Universal Substrate (Left Hemisphere)
            if self.substrate:
                # Key format: left_hemisphere.patterns.<order>.<context>
                sub_key = f"patterns.{n}.{ctx_str}" if ctx_str else f"patterns.{n}.__start__"
                sub_val = self.substrate.get_parameter(sub_key, domain="left_hemisphere")
                if sub_val:
                    return sub_val.get("value", {})

            # 2. Fallback to Local SQL or Memory
            if self.db_path:
                with sqlite3.connect(self.db_path) as conn:
                    cursor = conn.cursor()
                    cursor.execute('SELECT next_token, count FROM ngrams WHERE order_n=? AND context=?', (n, ctx_str))
                    rows = cursor.fetchall()
                    if rows:
                        return {r[0]: r[1] for r in rows}
            else:
                if context in self._transitions_by_order[n] and self._transitions_by_order[n][context]:
                    return self._transitions_by_order[n][context]
                    
        return {}

    def predict_next(self, current_tokens: List[str], top_k: int = 5) -> Dict[str, float]:
        """Predict the next word based on the current context."""
        if not self._fitted:
            return {}

        candidates = self._get_candidates(current_tokens)
        if not candidates:
            return {}

        total = sum(candidates.values())
        # Convert counts to probabilities
        probs = {token: count / total for token, count in candidates.items()}
        
        # Sort and take top_k
        sorted_probs = sorted(probs.items(), key=lambda x: x[1], reverse=True)[:top_k]
        return dict(sorted_probs)

    def generate(
        self, 
        seed_text: str, 
        max_words: int = 40, 
        stop_tokens: Optional[List[str]] = None,
        temperature: float = 1.0
    ) -> str:
        """Generate a response word-by-word with Stupid Backoff."""
        if not self._fitted:
            return seed_text

        tokens = self.tokenize(seed_text)
        if not tokens:
            return ""
            
        generated = []
        stop_tokens = stop_tokens or [".", "!", "?", "\n"]
        
        for _ in range(max_words):
            candidates = self._get_candidates(tokens)
            
            if not candidates:
                break
                
            # Sample with temperature
            next_word = self._sample(candidates, temperature)
            tokens.append(next_word)
            generated.append(next_word)
            
            if next_word in stop_tokens:
                break
                
        # Reconstruct string
        result = " ".join(generated)
        # Cleanup spaces before punctuation
        result = re.sub(r'\s+([.,!?])', r'\1', result)
        return result

    def _sample(self, counts: Dict[str, int], temperature: float) -> str:
        """Weighted sampling from token counts with temperature."""
        words = list(counts.keys())
        # Apply temperature: p_i = count_i ^ (1/temp) / sum(count_j ^ (1/temp))
        weights = [float(count) ** (1.0 / max(temperature, 0.01)) for count in counts.values()]
        return random.choices(words, weights=weights, k=1)[0]

