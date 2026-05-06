"""
PPBRS Pattern Classifier Module
Probabilistic Pattern-Based Reasoning System - Pattern Classification
"""
import re
import json
from typing import Optional, List, Dict, Any, Tuple
from dataclasses import dataclass, field
from enum import Enum


class ConfidenceLevel(Enum):
    """Confidence level thresholds for classification results.
    
    Attributes:
        LOW: Confidence below 0.3 — minimal match
        MEDIUM: Confidence 0.3-0.6 — moderate match
        HIGH: Confidence 0.6-0.8 — strong match
        VERY_HIGH: Confidence 0.8+ — near-certain match
    """
    LOW = 0.3
    MEDIUM = 0.6
    HIGH = 0.8
    VERY_HIGH = 0.95


@dataclass
class Pattern:
    """A tokenized pattern for classification and response matching.
    
    Attributes:
        id: Unique pattern identifier
        tokens: List of trigger tokens (case-insensitive matching)
        weight: Confidence multiplier (default 1.0)
        response_template: Response text or template
        tags: Classification tags for filtering
        metadata: Additional pattern metadata
        examples: Example inputs that match this pattern
        requires_context: List of required context keys
    """
    id: str
    tokens: List[str]
    weight: float = 1.0
    response_template: str = ""
    tags: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)
    examples: List[str] = field(default_factory=list)
    requires_context: List[str] = field(default_factory=list)


@dataclass
class ClassificationResult:
    """Result of pattern classification against an input string.
    
    Attributes:
        pattern_id: ID of the matched pattern
        confidence: Overall confidence score (0.0 to 1.0)
        matched_tokens: List of tokens that matched the input
        unmatched_tokens: List of tokens not found in input
        tags: Tags from the matched pattern
        reasoning: Human-readable reasoning string
    """
    pattern_id: str
    confidence: float
    matched_tokens: List[str]
    unmatched_tokens: List[str]
    tags: List[str]
    reasoning: str


class PatternClassifier:
    """
    Production-ready pattern classifier with confidence scoring
    and multi-criteria matching.
    """
    
    def __init__(self, threshold: float = 0.3, use_fuzzy: bool = True):
        """Initializes the PatternClassifier.

        Args:
            threshold: Minimum confidence score for a match to be considered. Defaults to 0.3.
            use_fuzzy: Whether to enable fuzzy token matching. Defaults to True.
        """
        self.patterns: Dict[str, Pattern] = {}
        self.threshold = threshold
        self.use_fuzzy = use_fuzzy
        self._token_cache: Dict[str, set] = {}
        self._inverted_index: Dict[str, set] = {}
        
    def add_pattern(self, pattern: Pattern) -> None:
        """Registers a new pattern for classification.

        Args:
            pattern: The Pattern object to add.
        """
        self.patterns[pattern.id] = pattern
        normalized = self._normalize_tokens(pattern.tokens)
        self._token_cache[pattern.id] = normalized
        
        # Update inverted index
        for token in normalized:
            if token not in self._inverted_index:
                self._inverted_index[token] = set()
            self._inverted_index[token].add(pattern.id)
        
    def _normalize_tokens(self, tokens: List[str]) -> set:
        """Preprocesses and normalizes a list of tokens for optimized matching.

        Args:
            tokens: List of raw trigger tokens.

        Returns:
            A set of normalized and cleaned token strings.
        """
        normalized = set()
        for tok in tokens:
            normalized.add(tok.lower().strip())
            normalized.add(re.sub(r'[^\w\s]', '', tok.lower().strip()))
        return normalized
    
    def _fuzzy_match(self, token: str, input_tokens: set) -> bool:
        """Checks if a token matches any input tokens using fuzzy similarity logic.

        Args:
            token: The pattern token to check.
            input_tokens: Set of tokens from the user input.

        Returns:
            True if a fuzzy match is found, False otherwise.
        """
        if token.lower() in input_tokens:
            return True
        if self.use_fuzzy:
            for inp_tok in input_tokens:
                if self._levenshtein_similarity(token.lower(), inp_tok) > 0.8:
                    return True
                if token.lower() in inp_tok or inp_tok in token.lower():
                    return True
        return False
    
    def _levenshtein_similarity(self, s1: str, s2: str) -> float:
        """Calculates the normalized Levenshtein similarity ratio between two strings.

        Args:
            s1: The first string.
            s2: The second string.

        Returns:
            Similarity ratio between 0.0 and 1.0.
        """
        if len(s1) == 0 and len(s2) == 0:
            return 1.0
        len1, len2 = len(s1), len(s2)
        min_len = min(len1, len2)
        if min_len == 0:
            return 0.0
        distance = self._levenshtein_distance(s1, s2)
        return 1.0 - (distance / max(len1, len2))
    
    def _levenshtein_distance(self, s1: str, s2: str) -> int:
        """Computes the Levenshtein edit distance between two strings.

        Args:
            s1: The first string.
            s2: The second string.

        Returns:
            The integer edit distance.
        """
        if len(s1) > len(s2):
            s1, s2 = s2, s1
        distances = range(len(s1) + 1)
        for i2, c2 in enumerate(s2):
            distances_ = [i2 + 1]
            for i1, c1 in enumerate(s1):
                if c1 == c2:
                    distances_.append(distances[i1])
                else:
                    distances_.append(1 + min((distances[i1], distances[i1 + 1], distances_[-1])))
            distances = distances_
        return distances[-1]
    
    def _tokenize_input(self, input_str: str) -> set:
        """Cleans and tokenizes an input string into a set of lowercased words.

        Args:
            input_str: The raw input string.

        Returns:
            A set of tokens found in the input.
        """
        tokens = re.findall(r'\b\w+\b', input_str.lower())
        return set(tokens)
    
    def score_pattern(self, pattern: Pattern, input_str: str, 
                     input_tokens: Optional[set] = None) -> Tuple[float, List[str], List[str]]:
        """Evaluates a pattern against an input string and calculates confidence.

        Args:
            pattern: The Pattern instance to score.
            input_str: The input string to check against.
            input_tokens: Optional pre-tokenized input set.

        Returns:
            A tuple containing (confidence_score, list_of_matched_tokens, list_of_unmatched_tokens).
        """
        if input_tokens is None:
            input_tokens = self._tokenize_input(input_str)
        pattern_normalized = self._token_cache.get(pattern.id, set())
        
        matched = []
        unmatched = []
        
        for tok in pattern.tokens:
            tok_normalized = tok.lower().strip()
            tok_clean = re.sub(r'[^\w\s]', '', tok_normalized)
            
            found = False
            for inp_tok in input_tokens:
                if tok_normalized == inp_tok or tok_clean == inp_tok:
                    matched.append(tok)
                    found = True
                    break
                if self.use_fuzzy and self._levenshtein_similarity(tok_normalized, inp_tok) > 0.8:
                    matched.append(tok)
                    found = True
                    break
            
            if not found:
                unmatched.append(tok)
        
        if not pattern.tokens:
            return 0.0, [], []
        
        token_score = len(matched) / len(pattern.tokens)
        confidence = token_score * pattern.weight
        
        return confidence, matched, unmatched
    
    def _get_candidates(self, input_tokens: set) -> List[Pattern]:
        """Retrieves a reduced set of candidate patterns based on token overlap.
        
        Args:
            input_tokens: Set of normalized input tokens.
            
        Returns:
            List of Pattern objects that share at least one token with the input.
        """
        candidate_ids = set()
        for token in input_tokens:
            if token in self._inverted_index:
                candidate_ids.update(self._inverted_index[token])
        
        return [self.patterns[pid] for pid in candidate_ids if pid in self.patterns]

    def classify(self, input_str: str, top_k: int = 1) -> List[ClassificationResult]:
        """Classifies the input string against all registered patterns.

        Args:
            input_str: The input text to classify.
            top_k: Number of top results to return. Defaults to 1.

        Returns:
            A list of ClassificationResult objects sorted by confidence.
        """
        input_tokens = self._tokenize_input(input_str)
        candidates = self._get_candidates(input_tokens)
        
        # If no candidates found through inverted index, 
        # only fall back to full scan if fuzzy matching is enabled 
        # (fuzzy can match tokens that aren't exact hits)
        # However, for performance, we usually prefer fuzzy-aware indexing.
        # For Phase 1, we stick to direct token overlap.
        
        results = []
        for pattern in candidates:
            confidence, matched, unmatched = self.score_pattern(pattern, input_str, input_tokens)
            
            if confidence >= self.threshold:
                reasoning = self._build_reasoning(pattern, matched, unmatched, confidence)
                results.append(ClassificationResult(
                    pattern_id=pattern.id,
                    confidence=confidence,
                    matched_tokens=matched,
                    unmatched_tokens=unmatched,
                    tags=pattern.tags,
                    reasoning=reasoning
                ))
        
        results.sort(key=lambda x: x.confidence, reverse=True)
        return results[:top_k]
    
    def _build_reasoning(self, pattern: Pattern, matched: List[str], unmatched: List[str], confidence: float) -> str:
        """Generates a human-readable explanation of why a pattern matched or didn't.

        Args:
            pattern: The Pattern that was evaluated.
            matched: List of matched tokens.
            unmatched: List of unmatched tokens.
            confidence: The final confidence score.

        Returns:
            A formatted reasoning string.
        """
        parts = []
        if matched:
            parts.append(f"Matched tokens: {', '.join(matched)}")
        if unmatched:
            parts.append(f"Missing tokens: {', '.join(unmatched)}")
        parts.append(f"Weight: {pattern.weight:.2f}")
        parts.append(f"Confidence: {confidence:.3f}")
        return " | ".join(parts)
    
    def get_best_match(self, input_str: str) -> Optional[ClassificationResult]:
        """Retrieves the single best matching pattern for the given input.

        Args:
            input_str: The input text to evaluate.

        Returns:
            The highest scoring ClassificationResult, or None if no matches exceed the threshold.
        """
        results = self.classify(input_str, top_k=1)
        return results[0] if results else None
    
    def load_patterns(self, patterns: List[Dict]) -> int:
        """Loads pattern definitions from a list of raw dictionaries.

        Args:
            patterns: List of dictionaries representing patterns.

        Returns:
            The number of successfully loaded patterns.
        """
        count = 0
        for p_data in patterns:
            try:
                pattern = Pattern(
                    id=p_data.get('id', f'pattern_{count}'),
                    tokens=p_data.get('tokens', []),
                    weight=p_data.get('weight', 1.0),
                    response_template=p_data.get('response_template', ''),
                    tags=p_data.get('tags', []),
                    metadata=p_data.get('metadata', {}),
                    examples=p_data.get('examples', []),
                    requires_context=p_data.get('requires_context', [])
                )
                self.add_pattern(pattern)
                count += 1
            except Exception as e:
                print(f"Error loading pattern {p_data.get('id', 'unknown')}: {e}")
        return count
    
    def save_patterns(self, path: str) -> bool:
        """Exports all registered patterns to a JSON file.

        Args:
            path: Target file path.

        Returns:
            True if export succeeded, False otherwise.
        """
        try:
            data = []
            for p in self.patterns.values():
                data.append({
                    'id': p.id,
                    'tokens': p.tokens,
                    'weight': p.weight,
                    'response_template': p.response_template,
                    'tags': p.tags,
                    'metadata': p.metadata,
                    'examples': p.examples,
                    'requires_context': p.requires_context
                })
            with open(path, 'w') as f:
                json.dump(data, f, indent=2)
            return True
        except Exception as e:
            print(f"Error saving patterns: {e}")
            return False
    
    def get_confidence_level(self, confidence: float) -> ConfidenceLevel:
        """Maps a numeric confidence score to a ConfidenceLevel enum category.

        Args:
            confidence: Float confidence score (0.0 to 1.0).

        Returns:
            The corresponding ConfidenceLevel.
        """
        if confidence >= ConfidenceLevel.VERY_HIGH.value:
            return ConfidenceLevel.VERY_HIGH
        elif confidence >= ConfidenceLevel.HIGH.value:
            return ConfidenceLevel.HIGH
        elif confidence >= ConfidenceLevel.MEDIUM.value:
            return ConfidenceLevel.MEDIUM
        return ConfidenceLevel.LOW