"""
PPBRS Pattern Extraction Module
Advanced pattern extraction algorithms for PPBRS system.
"""
import re
from typing import List, Dict, Any, Optional, Tuple, Callable
from dataclasses import dataclass, field
from collections import Counter
import json


@dataclass
class ExtractionResult:
    """Result of pattern extraction.
    
    Attributes:
        patterns: List of extracted pattern strings
        confidence: Confidence score for extraction quality
        metadata: Additional extraction metadata
    """
    patterns: List[str]
    confidence: float
    metadata: Dict[str, Any] = field(default_factory=dict)


class RegexPatternExtractor:
    """Extract patterns using regex-based techniques."""
    
    DEFAULT_PATTERNS = [
        r'\b[A-Z][a-z]+\b',  # Capitalized words
        r'\b\w+ing\b',       # Gerunds
        r'\b\w+tion\b',      # Words ending in tion
        r'\b\w+ly\b',       # Adverbs
        r'\b\w+ness\b',      # Noun forms
        r'\b\w+able\b',      # Adjectives
        r'\b\w+ful\b',       # Adjectives
        r'\b\w+less\b',      # Adjectives
        r'\b\w+ous\b',       # Adjectives
    ]
    
    def __init__(self, custom_patterns: Optional[List[str]] = None):
        """Initializes the RegexPatternExtractor.

        Args:
            custom_patterns: Optional list of regex strings to use for extraction.
        """
        self.patterns = custom_patterns or self.DEFAULT_PATTERNS
        self._compiled = [re.compile(p) for p in self.patterns]
    
    def extract(self, text: str, min_length: int = 3) -> ExtractionResult:
        """Extracts patterns from the given text using registered regexes.

        Args:
            text: Input string to analyze.
            min_length: Minimum length of a match to be included. Defaults to 3.

        Returns:
            An ExtractionResult containing found patterns and confidence score.
        """
        all_matches = []
        
        for pattern in self._compiled:
            matches = pattern.findall(text)
            all_matches.extend(matches)
        
        filtered = [m for m in all_matches if len(m) >= min_length]
        
        return ExtractionResult(
            patterns=filtered,
            confidence=len(filtered) / max(len(text.split()), 1),
            metadata={'raw_count': len(all_matches), 'filtered_count': len(filtered)}
        )
    
    def extract_with_positions(self, text: str) -> List[Tuple[str, int, int]]:
        """Extracts patterns along with their start and end character positions.

        Args:
            text: Input string to analyze.

        Returns:
            A list of tuples containing (match_text, start_index, end_index).
        """
        results = []
        for pattern in self._compiled:
            for match in pattern.finditer(text):
                results.append((match.group(), match.start(), match.end()))
        return sorted(results, key=lambda x: x[1])


class NGramPatternExtractor:
    """Extract patterns using n-gram analysis."""
    
    def __init__(self, min_n: int = 2, max_n: int = 4, top_k: int = 50):
        """Initializes the NGramPatternExtractor.

        Args:
            min_n: Minimum n-gram size. Defaults to 2.
            max_n: Maximum n-gram size. Defaults to 4.
            top_k: Number of top patterns to return. Defaults to 50.
        """
        self.min_n = min_n
        self.max_n = max_n
        self.top_k = top_k
    
    def extract(self, corpus: List[str], filter_stopwords: bool = True) -> ExtractionResult:
        """Extracts common n-gram patterns from a corpus of documents.

        Args:
            corpus: List of strings to analyze.
            filter_stopwords: Whether to exclude common filler words. Defaults to True.

        Returns:
            An ExtractionResult containing top n-grams and frequency metadata.
        """
        stopwords = {'the', 'a', 'an', 'is', 'are', 'was', 'were', 'be', 'been', 
                     'being', 'have', 'has', 'had', 'do', 'does', 'did', 'will',
                     'would', 'could', 'should', 'may', 'might', 'must', 'shall'}
        
        ngram_counts = Counter()
        
        for text in corpus:
            tokens = re.findall(r'\b\w+\b', text.lower())
            if filter_stopwords:
                tokens = [t for t in tokens if t not in stopwords]
            
            for n in range(self.min_n, self.max_n + 1):
                for i in range(len(tokens) - n + 1):
                    ngram = ' '.join(tokens[i:i+n])
                    ngram_counts[ngram] += 1
        
        top_patterns = [p for p, _ in ngram_counts.most_common(self.top_k)]
        
        return ExtractionResult(
            patterns=top_patterns,
            confidence=min(1.0, len(top_patterns) / self.top_k),
            metadata={'total_ngrams': len(ngram_counts), 'corpus_size': len(corpus)}
        )
    
    def extract_from_text(self, text: str, filter_stopwords: bool = True) -> ExtractionResult:
        """Extracts n-gram patterns from a single string.

        Args:
            text: The string to analyze.
            filter_stopwords: Whether to exclude common filler words. Defaults to True.

        Returns:
            An ExtractionResult containing top n-grams.
        """
        return self.extract([text], filter_stopwords)


class TFIDFPatternExtractor:
    """Extract patterns using TF-IDF style scoring."""
    
    def __init__(self, min_df: int = 1, max_df: float = 0.95, top_k: int = 30):
        """Initializes the TFIDFPatternExtractor.

        Args:
            min_df: Minimum document frequency for a term. Defaults to 1.
            max_df: Maximum document frequency as a fraction. Defaults to 0.95.
            top_k: Number of top terms to return. Defaults to 30.
        """
        self.min_df = min_df
        self.max_df = max_df
        self.top_k = top_k
        self._doc_freq: Dict[str, int] = {}
        self._num_docs = 0
    
    def fit(self, corpus: List[str]) -> 'TFIDFPatternExtractor':
        """Calculates document frequencies from a corpus.

        Args:
            corpus: List of strings to learn from.

        Returns:
            The instance itself (builder pattern).
        """
        self._num_docs = len(corpus)
        self._doc_freq = Counter()
        
        for text in corpus:
            tokens = set(re.findall(r'\b\w+\b', text.lower()))
            for token in tokens:
                self._doc_freq[token] += 1
        
        return self
    
    def extract(self, document: str) -> ExtractionResult:
        """Extracts important terms from a single document based on fitted IDF values.

        Args:
            document: The string to analyze.

        Returns:
            An ExtractionResult containing top weighted terms.
        """
        tokens = re.findall(r'\b\w+\b', document.lower())
        token_counts = Counter(tokens)
        
        idf_scores = {}
        for token, count in token_counts.items():
            df = self._doc_freq.get(token, 0)
            if df >= self.min_df and df / max(self._num_docs, 1) <= self.max_df:
                idf = max(0, (self._num_docs - df + 0.5) / (df + 0.5))
                tfidf = count * idf
                idf_scores[token] = tfidf
        
        top_terms = sorted(idf_scores.items(), key=lambda x: x[1], reverse=True)[:self.top_k]
        
        return ExtractionResult(
            patterns=[t for t, _ in top_terms],
            confidence=idf_scores.get(top_terms[0][0], 0) if top_terms else 0,
            metadata={'num_terms': len(idf_scores), 'doc_length': len(tokens)}
        )


class ContextualPatternExtractor:
    """Extract patterns with contextual awareness."""
    
    def __init__(self, window_size: int = 3):
        """Initializes the ContextualPatternExtractor.

        Args:
            window_size: Number of tokens to consider on each side of an anchor. Defaults to 3.
        """
        self.window_size = window_size
        self._contexts: Dict[str, List[str]] = {}
    
    def extract(self, text: str, anchor: str) -> ExtractionResult:
        """Extracts patterns found in the immediate context of an anchor word.

        Args:
            text: The input string to analyze.
            anchor: The word around which to extract context.

        Returns:
            An ExtractionResult containing contextual patterns.
        """
        text_lower = text.lower()
        anchor_lower = anchor.lower()
        
        if anchor_lower not in text_lower:
            return ExtractionResult(patterns=[], confidence=0.0)
        
        tokens = re.findall(r'\b\w+\b', text)
        anchor_idx = next(i for i, t in enumerate(tokens) if t.lower() == anchor_lower)
        
        start = max(0, anchor_idx - self.window_size)
        end = min(len(tokens), anchor_idx + self.window_size + 1)
        
        context_tokens = tokens[start:end]
        
        patterns = []
        for n in range(1, self.window_size * 2 + 1):
            for i in range(len(context_tokens) - n + 1):
                if anchor_lower in ' '.join(context_tokens[i:i+n]).lower():
                    patterns.append(' '.join(context_tokens[i:i+n]))
        
        return ExtractionResult(
            patterns=patterns,
            confidence=0.8 if patterns else 0.0,
            metadata={'anchor': anchor, 'position': anchor_idx}
        )
    
    def extract_with_tags(self, text: str) -> List[Dict[str, Any]]:
        """Analyzes text and returns a list of tokens with their surrounding contexts.

        Args:
            text: The string to analyze.

        Returns:
            A list of dictionaries containing token, context, and position info.
        """
        tokens = re.findall(r'\b\w+\b', text)
        
        results = []
        for i, token in enumerate(tokens):
            start = max(0, i - self.window_size)
            end = min(len(tokens), i + self.window_size + 1)
            context = tokens[start:end]
            
            results.append({
                'token': token,
                'context': context,
                'position': i,
                'is_contextual': len(context) > 1
            })
        
        return results


class CompositePatternExtractor:
    """Combine multiple extractors for comprehensive pattern extraction."""
    
    def __init__(self):
        """Initializes the CompositePatternExtractor by instantiating sub-extractors."""
        self.regex_extractor = RegexPatternExtractor()
        self.ngram_extractor = NGramPatternExtractor()
        self.tfidf_extractor = TFIDFPatternExtractor()
        self.contextual_extractor = ContextualPatternExtractor()
    
    def extract_all(self, corpus: List[str], anchor: Optional[str] = None) -> Dict[str, ExtractionResult]:
        """Runs all available extractors on the provided input.

        Args:
            corpus: List of strings to analyze.
            anchor: Optional anchor word for contextual extraction.

        Returns:
            A dictionary mapping extractor names to their respective ExtractionResults.
        """
        results = {}
        
        if len(corpus) > 1:
            self.tfidf_extractor.fit(corpus)
        
        if len(corpus) == 1:
            results['regex'] = self.regex_extractor.extract(corpus[0])
            results['ngram'] = self.ngram_extractor.extract_from_text(corpus[0])
            results['tfidf'] = self.tfidf_extractor.extract(corpus[0])
            if anchor:
                results['contextual'] = self.contextual_extractor.extract(corpus[0], anchor)
        else:
            results['ngram'] = self.ngram_extractor.extract(corpus)
            results['tfidf'] = self.tfidf_extractor.extract(' '.join(corpus[:10]))
        
        return results
    
    def merge_results(self, results: Dict[str, ExtractionResult], weights: Optional[Dict[str, float]] = None) -> List[Tuple[str, float]]:
        """Combines results from multiple extractors into a single weighted list.

        Args:
            results: Dictionary of ExtractionResults from different extractors.
            weights: Optional dictionary of weights for each extractor.

        Returns:
            A list of (pattern, weighted_score) tuples, sorted descending.
        """
        weights = weights or {k: 1.0 for k in results.keys()}
        
        pattern_scores: Dict[str, float] = Counter()
        
        for extractor_name, result in results.items():
            weight = weights.get(extractor_name, 1.0)
            for pattern in result.patterns:
                pattern_scores[pattern] += weight * result.confidence
        
        return sorted(pattern_scores.items(), key=lambda x: x[1], reverse=True)


def load_patterns_from_file(path: str) -> List[Dict[str, Any]]:
    """Loads pattern definitions from a JSON file.

    Args:
        path: Path to the JSON file.

    Returns:
        A list of pattern dictionaries, or an empty list if loading fails.
    """
    try:
        with open(path, 'r') as f:
            return json.load(f)
    except Exception as e:
        print(f"Error loading patterns: {e}")
        return []


def save_patterns_to_file(path: str, patterns: List[Dict[str, Any]]) -> bool:
    """Saves pattern definitions to a JSON file.

    Args:
        path: Path to the output JSON file.
        patterns: List of pattern dictionaries to save.

    Returns:
        True if the save was successful, False otherwise.
    """
    try:
        with open(path, 'w') as f:
            json.dump(patterns, f, indent=2)
        return True
    except Exception as e:
        print(f"Error saving patterns: {e}")
        return False
