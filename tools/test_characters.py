#!/usr/bin/env python3
"""
test_characters.py - Character-mode integration tests for Synthesus 2.0
Tests that each character responds in-character with pattern matching.
"""

import sys
import os
import json

try:
    import httpx
except ImportError:
    print("ERROR: httpx not installed. Run: pip install httpx")
    sys.exit(1)

BASE_URL = os.getenv("SYNTHESUS_URL", "http://localhost:8001")
PASS = 0
FAIL = 0


def test(name, fn):
    global PASS, FAIL
    try:
        fn()
        print(f"  PASS  {name}")
        PASS += 1
    except Exception as e:
        print(f"  FAIL  {name}: {e}")
        FAIL += 1


# ──────────────────────────────────────────────────
# SYNTH character tests
# ──────────────────────────────────────────────────

def synth_greeting():
    r = httpx.post(f"{BASE_URL}/query",
        json={"text": "Hello", "mode": "character", "character": "synth"}, timeout=10)
    assert r.status_code == 200, f"Status {r.status_code}"
    d = r.json()
    assert d.get("character") == "synth", f"Wrong character: {d.get('character')}"
    assert "synth" in d["response"].lower() or "synthesus" in d["response"].lower(), \
        f"Synth didn't identify itself: {d['response'][:80]}"
    print(f"         → \"{d['response'][:100]}\"")

def synth_about_synthesus():
    r = httpx.post(f"{BASE_URL}/query",
        json={"text": "What is Synthesus?", "mode": "character", "character": "synth"}, timeout=10)
    assert r.status_code == 200
    d = r.json()
    assert d.get("source") == "character_pattern", f"Expected pattern match, got: {d.get('source')}"
    assert "dual-hemisphere" in d["response"].lower() or "ppbrs" in d["response"].lower(), \
        f"Synth didn't explain architecture: {d['response'][:80]}"
    assert d["confidence"] > 0.9, f"Low confidence: {d['confidence']}"
    print(f"         → pattern={d.get('pattern_id')} conf={d['confidence']}")
    print(f"         → \"{d['response'][:120]}\"")

def synth_about_aivm():
    r = httpx.post(f"{BASE_URL}/query",
        json={"text": "What is AIVM?", "mode": "character", "character": "synth"}, timeout=10)
    assert r.status_code == 200
    d = r.json()
    assert "aivm" in d["response"].lower(), f"Synth didn't mention AIVM: {d['response'][:80]}"
    assert d.get("source") == "character_pattern"
    print(f"         → pattern={d.get('pattern_id')} conf={d['confidence']}")
    print(f"         → \"{d['response'][:120]}\"")

def synth_pricing():
    r = httpx.post(f"{BASE_URL}/query",
        json={"text": "How much does it cost?", "mode": "character", "character": "synth"}, timeout=10)
    assert r.status_code == 200
    d = r.json()
    assert "open-source" in d["response"].lower() or "enterprise" in d["response"].lower(), \
        f"Synth didn't discuss pricing: {d['response'][:80]}"
    print(f"         → \"{d['response'][:120]}\"")

def synth_architecture():
    r = httpx.post(f"{BASE_URL}/query",
        json={"text": "How does the architecture work?", "mode": "character", "character": "synth"}, timeout=10)
    assert r.status_code == 200
    d = r.json()
    assert "kernel" in d["response"].lower() or "hemisphere" in d["response"].lower() or \
           "ppbrs" in d["response"].lower(), \
        f"Synth didn't explain architecture: {d['response'][:80]}"
    print(f"         → \"{d['response'][:120]}\"")

def synth_unknown_falls_back():
    r = httpx.post(f"{BASE_URL}/query",
        json={"text": "Tell me about quantum physics", "mode": "character", "character": "synth"}, timeout=10)
    assert r.status_code == 200
    d = r.json()
    # Should get the character fallback, not a generic one
    assert d.get("character") == "synth"
    assert d.get("source") in ["character_fallback", "character_pattern"]
    print(f"         → source={d.get('source')} \"{d['response'][:100]}\"")


# ──────────────────────────────────────────────────
# HAVEN character tests
# ──────────────────────────────────────────────────

def haven_greeting():
    r = httpx.post(f"{BASE_URL}/query",
        json={"text": "Hello", "mode": "character", "character": "haven"}, timeout=10)
    assert r.status_code == 200
    d = r.json()
    assert d.get("character") == "haven"
    assert "haven" in d["response"].lower(), f"Haven didn't identify itself: {d['response'][:80]}"
    print(f"         → \"{d['response'][:100]}\"")

def haven_anxiety():
    r = httpx.post(f"{BASE_URL}/query",
        json={"text": "I feel anxious", "mode": "character", "character": "haven"}, timeout=10)
    assert r.status_code == 200
    d = r.json()
    assert d.get("source") == "character_pattern", f"Expected pattern match, got: {d.get('source')}"
    assert "grounding" in d["response"].lower() or "anxiety" in d["response"].lower() or \
           "not alone" in d["response"].lower(), \
        f"Haven didn't respond to anxiety: {d['response'][:80]}"
    print(f"         → pattern={d.get('pattern_id')} conf={d['confidence']}")
    print(f"         → \"{d['response'][:120]}\"")

def haven_meditation():
    r = httpx.post(f"{BASE_URL}/query",
        json={"text": "Help me meditate", "mode": "character", "character": "haven"}, timeout=10)
    assert r.status_code == 200
    d = r.json()
    assert d.get("source") == "character_pattern"
    assert "breath" in d["response"].lower(), f"Haven didn't guide meditation: {d['response'][:80]}"
    print(f"         → \"{d['response'][:120]}\"")

def haven_self_care():
    r = httpx.post(f"{BASE_URL}/query",
        json={"text": "Give me some self care tips", "mode": "character", "character": "haven"}, timeout=10)
    assert r.status_code == 200
    d = r.json()
    assert d.get("character") == "haven"
    # Should match self-care pattern or at least stay in character
    assert "care" in d["response"].lower() or "grateful" in d["response"].lower() or \
           "haven" in d["response"].lower()
    print(f"         → \"{d['response'][:120]}\"")


# ──────────────────────────────────────────────────
# LEXIS character tests
# ──────────────────────────────────────────────────

def lexis_greeting():
    r = httpx.post(f"{BASE_URL}/query",
        json={"text": "Hello", "mode": "character", "character": "lexis"}, timeout=10)
    assert r.status_code == 200
    d = r.json()
    assert d.get("character") == "lexis"
    assert "lexis" in d["response"].lower(), f"Lexis didn't identify itself: {d['response'][:80]}"
    print(f"         → \"{d['response'][:100]}\"")

def lexis_api_error():
    r = httpx.post(f"{BASE_URL}/query",
        json={"text": "I have an API error", "mode": "character", "character": "lexis"}, timeout=10)
    assert r.status_code == 200
    d = r.json()
    assert d.get("source") == "character_pattern", f"Expected pattern match, got: {d.get('source')}"
    assert "api" in d["response"].lower() or "endpoint" in d["response"].lower(), \
        f"Lexis didn't troubleshoot API: {d['response'][:80]}"
    print(f"         → pattern={d.get('pattern_id')} conf={d['confidence']}")
    print(f"         → \"{d['response'][:120]}\"")

def lexis_docker():
    r = httpx.post(f"{BASE_URL}/query",
        json={"text": "My docker build failed", "mode": "character", "character": "lexis"}, timeout=10)
    assert r.status_code == 200
    d = r.json()
    assert d.get("source") == "character_pattern"
    assert "docker" in d["response"].lower() or "image" in d["response"].lower(), \
        f"Lexis didn't troubleshoot Docker: {d['response'][:80]}"
    print(f"         → \"{d['response'][:120]}\"")

def lexis_python_debug():
    r = httpx.post(f"{BASE_URL}/query",
        json={"text": "I have a Python traceback error", "mode": "character", "character": "lexis"}, timeout=10)
    assert r.status_code == 200
    d = r.json()
    assert d.get("character") == "lexis"
    assert "traceback" in d["response"].lower() or "python" in d["response"].lower() or \
           "error" in d["response"].lower()
    print(f"         → \"{d['response'][:120]}\"")


# ──────────────────────────────────────────────────
# Cross-character isolation test
# ──────────────────────────────────────────────────

def character_isolation():
    """Verify that the same query gets different responses per character."""
    responses = {}
    for char in ["synth", "haven", "lexis"]:
        r = httpx.post(f"{BASE_URL}/query",
            json={"text": "Hello", "mode": "character", "character": char}, timeout=10)
        assert r.status_code == 200
        d = r.json()
        responses[char] = d["response"]
    # All three should be different
    assert responses["synth"] != responses["haven"], "Synth and Haven gave same response"
    assert responses["synth"] != responses["lexis"], "Synth and Lexis gave same response"
    assert responses["haven"] != responses["lexis"], "Haven and Lexis gave same response"
    for char, resp in responses.items():
        print(f"         → {char}: \"{resp[:70]}\"")

def nonexistent_character():
    r = httpx.post(f"{BASE_URL}/query",
        json={"text": "Hello", "mode": "character", "character": "fakeperson"}, timeout=10)
    assert r.status_code == 200
    d = r.json()
    assert "not found" in d["response"].lower(), f"Didn't handle missing character: {d['response'][:80]}"
    print(f"         → \"{d['response'][:80]}\"")


# ──────────────────────────────────────────────────
# Run all tests
# ──────────────────────────────────────────────────

if __name__ == "__main__":
    print("Synthesus 2.0 Character Mode Test Suite")
    print("=" * 50)
    print(f"Target: {BASE_URL}")
    print()

    print("[Synth - AIVM Brand Ambassador]")
    test("Synth greeting", synth_greeting)
    test("Synth explains Synthesus", synth_about_synthesus)
    test("Synth explains AIVM", synth_about_aivm)
    test("Synth discusses pricing", synth_pricing)
    test("Synth explains architecture", synth_architecture)
    test("Synth fallback on unknown topic", synth_unknown_falls_back)

    print()
    print("[Haven - Wellness Companion]")
    test("Haven greeting", haven_greeting)
    test("Haven handles anxiety", haven_anxiety)
    test("Haven guides meditation", haven_meditation)
    test("Haven self-care tips", haven_self_care)

    print()
    print("[Lexis - Technical Assistant]")
    test("Lexis greeting", lexis_greeting)
    test("Lexis troubleshoots API error", lexis_api_error)
    test("Lexis troubleshoots Docker", lexis_docker)
    test("Lexis debugs Python", lexis_python_debug)

    print()
    print("[Cross-Character Tests]")
    test("Character isolation (different responses)", character_isolation)
    test("Nonexistent character handled", nonexistent_character)

    print()
    print("=" * 50)
    total = PASS + FAIL
    print(f"Results: {PASS}/{total} passed, {FAIL} failed")
    if FAIL > 0:
        sys.exit(1)
    else:
        print("All character tests passed!")
        sys.exit(0)
