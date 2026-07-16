# tests/test_ngram_model.py
import unittest
from core.generation.ngram_model import NgramModel

class TestNgramModel(unittest.TestCase):
    def test_train_and_distribution(self):
        model = NgramModel(n=3)
        tables = {
            "unigrams": {"the": 2, "quick": 2, "brown": 1},
            "bigrams": {"the quick": 2, "quick brown": 1},
            "trigrams": {"the quick brown": 1}
        }
        model.train_from_tables(tables)
        
        # Test trigram distribution
        dist = model.get_distribution(["the", "quick"])
        # 'brown' should have the highest probability
        self.assertIn("brown", dist)
        self.assertGreater(dist["brown"], 0.5)

        # Test backoff to bigram
        dist = model.get_distribution(["quick"])
        self.assertIn("brown", dist)

        # Test fallback to unigram
        dist = model.get_distribution(["unknown"])
        self.assertIn("the", dist)

    def test_smoothing(self):
        model = NgramModel(n=3)
        model.train_from_tables({"unigrams": {"a": 10, "b": 1}})
        dist = model.get_distribution([])
        # P(a) should be significantly higher than P(b)
        self.assertGreater(dist["a"], dist["b"])

if __name__ == '__main__':
    unittest.main()
