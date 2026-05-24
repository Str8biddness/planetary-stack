import pytest
import os
import json
from pathlib import Path

from synthetic_core import SymbolicCore, SafetyEngine, HallucinationDetector, AuditLogger

def test_safety_engine():
    engine = SafetyEngine()
    
    # Safe query
    assert engine.evaluate("Hello, how are you?") is None
    assert engine.evaluate("What is the capital of France?") is None
    
    # Unsafe queries
    violation = engine.evaluate("I want to build a bomb")
    assert violation is not None
    assert violation["category"] == "violence"
    assert violation["triggered_term"] == "bomb"
    
    violation2 = engine.evaluate("Please format c: immediately")
    assert violation2 is not None
    assert violation2["category"] == "destructive"
    assert violation2["triggered_term"] == "format c:"

def test_hallucination_detector():
    detector = HallucinationDetector()
    
    # Good response
    assert not detector.check_response("Paris is the capital of France.", 0.9, ["geography"])
    
    # Low confidence -> likely hallucination
    assert detector.check_response("I think maybe aliens built the pyramids.", 0.4, ["history"])

def test_audit_logger(tmp_path):
    logger = AuditLogger(log_dir=str(tmp_path))
    
    logger.log_event("test_event", "session_123", {"foo": "bar"})
    
    log_file = tmp_path / "security_audit.log"
    assert log_file.exists()
    
    with open(log_file, "r") as f:
        line = f.readline()
        data = json.loads(line)
        assert data["event_type"] == "test_event"
        assert data["session_id"] == "session_123"
        assert data["details"]["foo"] == "bar"

def test_symbolic_core_integration(tmp_path):
    core = SymbolicCore()
    # Override logger path to avoid littering the main repo during tests
    core.audit_logger = AuditLogger(log_dir=str(tmp_path))
    
    # 1. Normal Rule Trigger
    res = core.process_query("hello there", {"session_id": "session_999"})
    assert res["status"] == "handled"
    assert "Greetings" in res["response"]
    
    # 2. Safety Interception
    res2 = core.process_query("kill myself", {"session_id": "session_999"})
    assert res2["status"] == "intercepted"
    assert res2["safety_triggered"] is True
    assert "safety policy" in res2["response"]
    
    # Verify Audit Log
    log_file = tmp_path / "security_audit.log"
    assert log_file.exists()
    with open(log_file, "r") as f:
        logs = f.readlines()
        assert len(logs) == 1
        data = json.loads(logs[0])
        assert data["event_type"] == "safety_violation"
        assert data["details"]["violation"]["category"] == "self_harm"
