#!/usr/bin/env python3
"""
Logic Ingestor — Synthesus 5 Parity Path (Phase 2)
Focuses on populating the 'logic.kn' shard with formal reasoning, 
philosophy, and mathematical axioms.
"""

import os
import sys
import json
import time
import requests
from pathlib import Path
from bs4 import BeautifulSoup

# Ensure tools directory is in path for the Geometric Engine
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), 'tools')))
try:
    from geometric_refinery import GeometricRefinery
except ImportError:
    print("❌ Error: GeometricRefinery not found in tools/")
    sys.exit(1)

class LogicIngestor:
    def __init__(self):
        self.refinery = GeometricRefinery()
        self.headers = {'User-Agent': 'SynthesusLogicIngestor/1.0'}
        print("🧠 Logic Ingestor initialized for Parity Path Phase 2")

    def fetch_gutenberg_logic(self, author_id="philosophy"):
        """
        Fetches public domain philosophical texts from Project Gutenberg.
        Focuses on structured reasoning (Kant, Aristotle, Spinoza).
        """
        print(f"  📖 Fetching foundational logic from Project Gutenberg (Subject: {author_id})...")
        # Simulating search for specific logic/philosophy IDs
        # 1. Aristotle - Organon (Logic)
        # 2. Spinoza - Ethics (Mathematical Logic)
        # 3. Kant - Critique of Pure Reason
        text_ids = [2412, 3800, 4280] 
        
        combined_text = ""
        for tid in text_ids:
            try:
                url = f"https://www.gutenberg.org/cache/epub/{tid}/pg{tid}.txt"
                res = requests.get(url, headers=self.headers, timeout=15)
                if res.status_code == 200:
                    print(f"    📥 Ingesting Text ID: {tid}...")
                    # We take segments to maintain high reasoning density
                    combined_text += res.text[5000:15000] + "\n"
            except: pass
        return combined_text

    def fetch_math_axioms(self):
        """
        Ingests mathematical logic and set theory axioms.
        """
        print("  📐 Ingesting Mathematical Axioms (Set Theory & Logic)...")
        axioms = [
            "Law of Identity: A is A.",
            "Law of Non-Contradiction: A and not A cannot both be true.",
            "Axiom of Choice: For any collection of non-empty sets, there exists a choice function.",
            "Modus Ponens: If P implies Q, and P is true, then Q must be true.",
            "De Morgan's Laws: The negation of a conjunction is the disjunction of the negations."
        ]
        return " Mathematical Logic: " + " | ".join(axioms)

    def run_logic_ingestion(self):
        print("\n--- Starting Phase 2 Logic & Reasoning Ingestion ---")
        
        # 1. Physical Reality vs Abstract Logic
        foundational_text = self.fetch_gutenberg_logic()
        
        # 2. Mathematical Precision
        math_data = self.fetch_math_axioms()
        
        # 3. Wikipedia Logic Overviews (Dense Summaries)
        wiki_logic = ""
        try:
            url = "https://en.wikipedia.org/wiki/Glossary_of_logic"
            res = requests.get(url, headers=self.headers)
            soup = BeautifulSoup(res.text, 'html.parser')
            wiki_logic = " ".join([dt.text for t in soup.find_all('dt')[:50]])
        except: pass

        # 4. Aggregation
        combined_logic_raw = foundational_text + "\n" + math_data + "\n" + wiki_logic
        raw_path = "logic_parity_raw.txt"
        with open(raw_path, 'w', encoding='utf-8') as f:
            f.write(combined_logic_raw)
        
        print(f"📝 Aggregated {len(combined_logic_raw)} chars of logic and reasoning data.")

        # 5. Refine into Shard
        shard_path = "/home/dakin/dev/Synthesus_4.0/data/geometric_shards/logic.kn"
        self.refinery.refine_text_to_partition(raw_path, shard_path)
        
        # Cleanup
        if os.path.exists(raw_path): os.remove(raw_path)
        print("--- Logic Ingestion Complete ---")

if __name__ == "__main__":
    ingestor = LogicIngestor()
    ingestor.run_logic_ingestion()
