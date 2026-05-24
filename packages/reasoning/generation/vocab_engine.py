# core/generation/vocab_engine.py
import re
import os
import json
from collections import Counter
from typing import List, Dict, Any

class VocabEngine:
    """Engine for building token frequency tables from internal Synthesus corpora."""
    
    def __init__(self):
        # Basic tokenization: words and punctuation
        self.token_pattern = re.compile(r"\w+|[^\w\s]")

    def tokenize(self, text: str) -> List[str]:
        """Convert text into a list of lowercase tokens."""
        return self.token_pattern.findall(text.lower())

    def build_frequency_tables(self, texts: List[str]) -> Dict[str, Dict]:
        """Build unigram, bigram, and trigram frequency tables from a list of texts."""
        unigrams = Counter()
        bigrams = Counter()
        trigrams = Counter()

        for text in texts:
            tokens = self.tokenize(text)
            unigrams.update(tokens)
            
            # Bigrams
            for i in range(len(tokens) - 1):
                bigrams[(tokens[i], tokens[i+1])] += 1
                
            # Trigrams
            for i in range(len(tokens) - 2):
                trigrams[(tokens[i], tokens[i+1], tokens[i+2])] += 1
                
        # Convert tuple keys to strings for JSON/Pickle compatibility
        return {
            "unigrams": dict(unigrams),
            "bigrams": {f"{k[0]} {k[1]}": v for k, v in bigrams.items()},
            "trigrams": {f"{k[0]} {k[1]} {k[2]}": v for k, v in trigrams.items()}
        }

    def ingest_directory(self, directory: str) -> List[str]:
        """Recursively ingest text-based files from a directory."""
        texts = []
        if not os.path.exists(directory):
            return texts

        for root, _, files in os.walk(directory):
            for file in files:
                if file.endswith((".txt", ".md", ".json", ".py")):

                    file_path = os.path.join(root, file)
                    try:
                        with open(file_path, 'r', encoding='utf-8') as f:
                            content = f.read()
                            if file.endswith(".json"):
                                try:
                                    data = json.loads(content)
                                    texts.extend(self._extract_strings(data))
                                except json.JSONDecodeError:
                                    pass
                            else:
                                texts.append(content)
                    except Exception:
                        pass
        return texts

    def _extract_strings(self, obj: Any) -> List[str]:
        """Recursively extract all string values from a JSON-like object."""
        strings = []
        if isinstance(obj, str):
            strings.append(obj)
        elif isinstance(obj, list):
            for item in obj:
                strings.extend(self._extract_strings(item))
        elif isinstance(obj, dict):
            for value in obj.values():
                strings.extend(self._extract_strings(value))
        return strings
