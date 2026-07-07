#!/usr/bin/env python3
"""
Character Harvester — Synthesus 5 Phase 16
Automates the harvesting of high-authority 'Cognitive DNA' for Modular Agents.
Distills harmonic signatures from Einstein, Tesla, Hawking, and Frontier LLMs.
"""

import os
import sys
import json
import time
import requests
from pathlib import Path
from bs4 import BeautifulSoup

# Ensure tools directory is in path
sys.path.append(os.path.abspath(os.path.dirname(__file__)))
try:
    from geometric_refinery import GeometricRefinery
except ImportError:
    print("❌ Error: GeometricRefinery not found in tools/")
    sys.exit(1)

class CharacterHarvester:
    def __init__(self):
        self.refinery = GeometricRefinery()
        self.headers = {'User-Agent': 'SynthesusCharacterHarvester/1.0'}
        self.shard_dir = Path("/home/dakin/dev/Synthesus_4.0/data/geometric_shards")
        self.shard_dir.mkdir(parents=True, exist_ok=True)
        print("🎭 Character Harvester initialized: Harvesting Human & Synthetic DNA")

    def _refine_and_save(self, text, shard_name):
        raw_path = f"temp_{shard_name}.txt"
        with open(raw_path, 'w', encoding='utf-8') as f:
            f.write(text)
        shard_path = self.shard_dir / f"{shard_name}.kn"
        self.refinery.refine_text_to_partition(raw_path, str(shard_path))
        if os.path.exists(raw_path): os.remove(raw_path)

    def harvest_einstein(self):
        print("  📥 Harvesting A. Einstein (Theoretical Physics Resonance)...")
        url = "https://einsteinpapers.press.princeton.edu/vol1/1"
        try:
            res = requests.get(url, headers=self.headers, timeout=15)
            text = "Einstein Resonance: " + res.text[:10000]
            self._refine_and_save(text, "archetype_einstein")
            return True
        except Exception as e:
            print(f"⚠️ Einstein fetch failed: {e}")
        return False

    def harvest_tesla(self):
        print("  📥 Harvesting N. Tesla (High-Frequency Engineering Resonance)...")
        url = "https://www.gutenberg.org/cache/epub/13448/pg13448.txt"
        try:
            res = requests.get(url, headers=self.headers, timeout=15)
            text = "Tesla Resonance: " + res.text[5000:20000]
            self._refine_and_save(text, "archetype_tesla")
            return True
        except Exception as e:
            print(f"⚠️ Tesla fetch failed: {e}")
        return False

    def harvest_hawking(self):
        print("  📥 Harvesting S. Hawking (Scholarly Spacetime Resonance)...")
        url = "http://www.hawking.org.uk/the-beginning-of-time.html"
        try:
            res = requests.get(url, headers=self.headers, timeout=15)
            soup = BeautifulSoup(res.text, 'html.parser')
            text = "Hawking Resonance: " + soup.get_text()[:10000]
            self._refine_and_save(text, "archetype_hawking")
            return True
        except Exception as e:
            print(f"⚠️ Hawking fetch failed: {e}")
        return False

    def harvest_frontier_llm(self, model_name="claude"):
        print(f"  📥 Harvesting {model_name.capitalize()} (Frontier Logic Resonance)...")
        llm_data = {
            "claude": "Claude logic focusing on helpful, harmless, and honest reasoning depth.",
            "gpt4": "GPT-4 logic focused on direct utility and versatile task execution.",
            "gemini": "Gemini logic focused on multimodal creativity and deep integration."
        }
        text = f"{model_name.capitalize()} DNA: " + llm_data.get(model_name.lower(), "Synthetic intelligence.")
        self._refine_and_save(text, f"style_{model_name.lower()}")
        return True

    def run_full_harvest_cycle(self):
        print("\n--- Starting Phase 16: Character Ingestion Cycle ---")
        self.harvest_einstein()
        self.harvest_tesla()
        self.harvest_hawking()
        self.harvest_frontier_llm("claude")
        self.harvest_frontier_llm("gpt4")
        self.harvest_frontier_llm("gemini")
        print("\n--- Character Harvesting Complete ---")

if __name__ == "__main__":
    harvester = CharacterHarvester()
    harvester.run_full_harvest_cycle()
