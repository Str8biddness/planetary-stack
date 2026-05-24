import os
import sqlite3
import pytest
from ml.pattern_lm import PatternLM

def test_pattern_lm_memory():
    lm = PatternLM(order=3)
    lm.fit(["hello there my friend", "hello there good sir"])
    
    # Check predictions for 2-gram context
    preds = lm.predict_next(["hello", "there"])
    assert "my" in preds
    assert "good" in preds
    
    # Check prediction for 1-gram context (backoff from ["what", "hello"] to ["hello"])
    # Wait, the tokens fed to predict_next are ["what", "hello"]. 
    # Since "what hello" is not in the training data, it should backoff to "hello"?
    # Except "what hello" has length 2. "what" is unknown.
    # The context is ["what", "hello"]. order is 3. 
    # It tries to find n=2, context ("what", "hello"). Fails.
    # It tries to find n=1, context ("hello",). Let's see if fit captured n=1. 
    # Actually, in fit(), we train contexts from length 1 to self.order ending at current token.
    # So "hello" is in the context tuples for the next word "there".
    preds_backoff = lm.predict_next(["what", "hello"])
    assert "there" in preds_backoff

def test_pattern_lm_sqlite(tmp_path):
    db_path = str(tmp_path / "test_pattern_lm.db")
    lm = PatternLM(order=3, db_path=db_path)
    
    lm.fit(["the quick brown fox", "the quick lazy dog"])
    
    # Verify DB has entries
    with sqlite3.connect(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT count(*) FROM ngrams")
        count = cursor.fetchone()[0]
        assert count > 0

    # Test prediction
    preds = lm.predict_next(["the", "quick"])
    assert "brown" in preds
    assert "lazy" in preds

    # Test backoff
    preds_backoff = lm.predict_next(["unknown", "word", "the"])
    assert "quick" in preds_backoff

    # Test generate
    gen_text = lm.generate("the quick")
    assert "brown" in gen_text or "lazy" in gen_text
