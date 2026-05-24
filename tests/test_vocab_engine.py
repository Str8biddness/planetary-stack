# tests/test_vocab_engine.py
import unittest
from core.generation.vocab_engine import VocabEngine

class TestVocabEngine(unittest.TestCase):
    def setUp(self):
        self.engine = VocabEngine()

    def test_tokenize(self):
        text = "Hello, world! 123."
        tokens = self.engine.tokenize(text)
        # Expected: ['hello', ',', 'world', '!', '123', '.']
        self.assertEqual(tokens, ['hello', ',', 'world', '!', '123', '.'])

    def test_build_frequency_tables(self):
        texts = ["the quick brown fox", "the quick dog"]
        tables = self.engine.build_frequency_tables(texts)
        
        self.assertEqual(tables["unigrams"]["the"], 2)
        self.assertEqual(tables["unigrams"]["quick"], 2)
        self.assertEqual(tables["bigrams"]["the quick"], 2)
        self.assertEqual(tables["bigrams"]["quick brown"], 1)
        self.assertEqual(tables["trigrams"]["the quick brown"], 1)

    def test_extract_strings(self):
        data = {"a": "hello", "b": ["world", {"c": "test"}]}
        strings = self.engine._extract_strings(data)
        self.assertIn("hello", strings)
        self.assertIn("world", strings)
        self.assertIn("test", strings)

if __name__ == '__main__':
    unittest.main()
