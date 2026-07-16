#!/usr/bin/env python3
"""
Technical Ingestor — Synthesus 5 Parity Path (Phase 1)
Automates the ingestion of high-density code patterns and technical documentation.
Focuses on populating the 'technical.kn' shard to achieve coding reasoning parity.
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

class TechnicalIngestor:
    def __init__(self):
        self.refinery = GeometricRefinery()
        self.headers = {'User-Agent': 'SynthesusTechnicalIngestor/1.0'}
        print("💻 Technical Ingestor initialized for Parity Path Phase 1")

    def fetch_github_patterns(self, language="python", limit=5):
        """
        Fetches high-quality code snippets from GitHub (simulated via Search API).
        Targeting structured patterns rather than whole files for density.
        """
        print(f"  📥 Fetching {language} code patterns from GitHub...")
        url = f"https://api.github.com/search/repositories?q=language:{language}&sort=stars&order=desc"
        try:
            res = requests.get(url, headers=self.headers, timeout=15).json()
            repos = res.get('items', [])[:limit]
            
            combined_patterns = ""
            for repo in repos:
                full_name = repo['full_name']
                desc = repo['description'] or ""
                # We ingest metadata and README snippets as high-density 'intent' tokens
                combined_patterns += f"\nRepo: {full_name}\nIntent: {desc}\n"
                
                # Fetch README content for deeper pattern grounding
                readme_url = f"https://api.github.com/repos/{full_name}/readme"
                r_res = requests.get(readme_url, headers=self.headers, timeout=10).json()
                if 'download_url' in r_res:
                    content = requests.get(r_res['download_url'], timeout=10).text[:2000]
                    combined_patterns += f"Patterns: {content}\n"
            
            return combined_patterns
        except Exception as e:
            print(f"⚠️ GitHub fetch failed: {e}")
        return ""

    def fetch_documentation(self, docs_url):
        """
        Scrapes technical documentation to ground the kernel in API semantics.
        """
        print(f"  📖 Ingesting documentation: {docs_url}...")
        try:
            res = requests.get(docs_url, headers=self.headers, timeout=15)
            soup = BeautifulSoup(res.text, 'html.parser')
            # Extract text from paragraphs and code blocks
            text = " ".join([p.text for p in soup.find_all(['p', 'code'])])
            return text[:5000] # Cap per page for density
        except Exception as e:
            print(f"⚠️ Docs ingestion failed: {e}")
        return ""

    def run_ingestion_cycle(self):
        print("\n--- Starting Phase 1 Technical Ingestion ---")
        
        # 1. Collect Multi-Language Code Patterns
        languages = ["python", "cpp", "rust", "go", "javascript"]
        all_code_data = ""
        for lang in languages:
            all_code_data += self.fetch_github_patterns(lang)

        # 2. Collect API Documentation
        docs_sources = [
            "https://docs.python.org/3/library/functions.html",
            "https://en.cppreference.com/w/cpp/algorithm"
        ]
        all_docs_data = ""
        for url in docs_sources:
            all_docs_data += self.fetch_documentation(url)

        # 3. Aggregation
        combined_technical_raw = all_code_data + "\n" + all_docs_data
        raw_path = "technical_parity_raw.txt"
        with open(raw_path, 'w', encoding='utf-8') as f:
            f.write(combined_technical_raw)
        
        print(f"📝 Aggregated {len(combined_technical_raw)} chars of high-density technical data.")

        # 4. Refine into Shard
        shard_path = "/home/dakin/dev/Synthesus_4.0/data/geometric_shards/technical.kn"
        self.refinery.refine_text_to_partition(raw_path, shard_path)
        
        # Cleanup
        if os.path.exists(raw_path): os.remove(raw_path)
        print("--- Technical Ingestion Complete ---")

if __name__ == "__main__":
    ingestor = TechnicalIngestor()
    ingestor.run_ingestion_cycle()
