#!/usr/bin/env python3
import json
import requests
import sys
import os

# Configuration
API_URL = os.environ.get("SYNTHESUS_API_URL", "http://localhost:8000/api/patterns/ingest")
PATTERNS_FILE = os.path.join(os.path.dirname(__file__), "..", "data", "initial_patterns.json")

def seed_patterns():
    if not os.path.exists(PATTERNS_FILE):
        print(f"Error: Patterns file not found at {PATTERNS_FILE}")
        return

    with open(PATTERNS_FILE, "r") as f:
        patterns = json.load(f)

    print(f"Seeding {len(patterns)} patterns to {API_URL}...")
    
    try:
        response = requests.post(API_URL, json=patterns)
        if response.status_code == 200:
            result = response.json()
            print(f"Success! Added {result.get('added', 0)} patterns. Total: {result.get('total', 0)}")
        else:
            print(f"Failed: {response.status_code} - {response.text}")
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    seed_patterns()
