#!/usr/bin/env python3
"""
test_synthesus.py - Integration tests for Synthesus 2.0
Usage: python scripts/test_synthesus.py
"""

import sys
import os
import json
import time

try:
    import httpx
except ImportError:
    print("ERROR: httpx not installed. Run: pip install httpx")
    sys.exit(1)

BASE_URL = os.getenv("SYNTHESUS_URL", "http://localhost:5000")
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


def check_health():
    r = httpx.get(f"{BASE_URL}/health", timeout=10)
    assert r.status_code == 200, f"Status {r.status_code}"
    data = r.json()
    assert "status" in data, "Missing 'status' field"


def check_query_basic():
    r = httpx.post(
        f"{BASE_URL}/query",
        json={"text": "What is 2 + 2?", "mode": "left"},
        timeout=30
    )
    assert r.status_code == 200, f"Status {r.status_code}"
    data = r.json()
    assert "response" in data or "answer" in data, "No response field"


def check_query_dual():
    r = httpx.post(
        f"{BASE_URL}/query",
        json={"text": "Tell me about reasoning", "mode": "dual"},
        timeout=60
    )
    assert r.status_code == 200, f"Status {r.status_code}"


def check_characters_endpoint():
    r = httpx.get(f"{BASE_URL}/characters", timeout=10)
    assert r.status_code == 200, f"Status {r.status_code}"


def check_character_query():
    r = httpx.post(
        f"{BASE_URL}/query",
        json={"text": "Hello", "mode": "character", "character": "synth"},
        timeout=30
    )
    # 200 or 404 if character not loaded is acceptable
    assert r.status_code in [200, 404], f"Unexpected status {r.status_code}"


def check_metrics():
    r = httpx.get(f"{BASE_URL}/metrics", timeout=10)
    assert r.status_code in [200, 404], f"Status {r.status_code}"


def validate_character_files():
    chars_dir = "characters"
    if not os.path.isdir(chars_dir):
        raise AssertionError(f"Directory '{chars_dir}' not found")
    for char in os.listdir(chars_dir):
        char_path = os.path.join(chars_dir, char)
        if os.path.isdir(char_path):
            bio = os.path.join(char_path, "bio.json")
            patterns = os.path.join(char_path, "patterns.json")
            assert os.path.exists(bio), f"Missing bio.json for {char}"
            assert os.path.exists(patterns), f"Missing patterns.json for {char}"
            with open(bio) as f:
                data = json.load(f)
            assert "id" in data, f"{char}/bio.json missing 'id'"
            assert "name" in data, f"{char}/bio.json missing 'name'"


if __name__ == "__main__":
    print("Synthesus 2.0 Test Suite")
    print("=" * 40)
    print(f"Target: {BASE_URL}")
    print()

    print("[API Tests]")
    test("Health endpoint", check_health)
    test("Basic query (left hemisphere)", check_query_basic)
    test("Dual hemisphere query", check_query_dual)
    test("Characters list endpoint", check_characters_endpoint)
    test("Character-mode query", check_character_query)
    test("Metrics endpoint", check_metrics)

    print()
    print("[File Validation Tests]")
    test("Character file structure", validate_character_files)

    print()
    print("=" * 40)
    total = PASS + FAIL
    print(f"Results: {PASS}/{total} passed, {FAIL} failed")
    if FAIL > 0:
        sys.exit(1)
    else:
        print("All tests passed!")
        sys.exit(0)
