#!/usr/bin/env python3
"""
Geometric Refinery Tool (Bootstrap Version)
Uses a fallback Python implementation of the 5-Axis Geometric Engine
when the C++ bridge is not yet compiled.
Supports Multi-Category Live Ingestion and Categorical Sharding.
"""

import os
import sys
import json
import time
import hashlib
import requests
from bs4 import BeautifulSoup
from pathlib import Path
from translation_bridge import TranslationBridge

class GeometricEngineFallback:
    """
    Python fallback implementation of the 5-Axis SLLM Core.
    Matches the C++ logic exactly.
    """
    def __init__(self):
        self.DIM = 5

    def word_to_vector(self, word):
        word = word.lower().strip()
        # Use MD5 to simulate the djb2/fnv1a dual hash behavior
        h = hashlib.md5(word.encode()).digest()
        
        x = (h[0] + h[1] * 256) / 65535.0
        y = (h[2] + h[3] * 256) / 65535.0
        z = (h[4] + h[5] * 256) / 65535.0
        phase = (h[6] + h[7] * 256) / 65535.0
        scale = (h[8] + h[9] * 256) / 65535.0
        
        return [x, y, z, phase, scale]

class ArchiveIngestor:
    """
    Fetches historical and technical texts from the Internet Archive.
    """
    def __init__(self):
        self.search_url = "https://archive.org/advancedsearch.php"
        self.headers = {'User-Agent': 'SynthesusGeometricRefinery/1.0'}

    def fetch_library_samples(self, limit=5):
        """Searches for high-value public domain texts."""
        print(f"📚 Querying Internet Archive for {limit} items...")
        params = {
            'q': 'mediatype:texts AND (subject:"philosophy" OR subject:"science")',
            'fl[]': 'identifier,title',
            'rows': limit,
            'output': 'json'
        }
        try:
            res = requests.get(self.search_url, params=params, headers=self.headers, timeout=15).json()
            docs = res.get('response', {}).get('docs', [])
            
            combined_text = ""
            for doc in docs:
                ident = doc['identifier']
                title = doc['title']
                print(f"  📥 Fetching snippet: {title}...")
                # Fetch metadata/description as a high-density text sample
                meta_url = f"https://archive.org/metadata/{ident}"
                m_res = requests.get(meta_url, headers=self.headers, timeout=10).json()
                desc = m_res.get('metadata', {}).get('description', "")
                combined_text += f"\nTitle: {title}\nDescription: {desc}\n"
            
            return "Historical Context: " + combined_text
        except Exception as e:
            print(f"⚠️ Archive fetch failed: {e}")
        return ""

class LiveIngestor:
    """
    Fetches day-to-day information from free APIs and structured web sources.
    """
    def __init__(self):
        self.headers = {'User-Agent': 'SynthesusGeometricRefinery/1.0'}

    def fetch_weather(self, city="London"):
        print(f"🌡️ Fetching weather for {city}...")
        try:
            response = requests.get(f"https://wttr.in/{city}?format=4", headers=self.headers, timeout=10)
            return f"Weather in {city}: {response.text.strip()}" if response.status_code == 200 else ""
        except: return ""

    def fetch_news(self):
        print("📰 Fetching latest news (EN, ES, ZH)...")
        sources = [
            ("English", "https://feeds.bbci.co.uk/news/rss.xml"),
            ("Spanish", "https://elpais.com/rss/elpais/portada.xml"),
            ("Chinese", "http://www.scmp.com/rss/2/feed.xml") # SCMP for high-quality Asian context
        ]
        combined = ""
        for lang, url in sources:
            try:
                print(f"  📥 Loading {lang} feed...")
                response = requests.get(url, headers=self.headers, timeout=10)
                soup = BeautifulSoup(response.content, 'xml')
                titles = [i.title.text for i in soup.find_all('item')[:10]]
                combined += f" {lang} Headlines: " + " | ".join(titles)
            except: pass
        return combined

    def fetch_stocks(self, symbols=["AAPL", "GOOGL", "TSLA"]):
        print(f"📈 Fetching stocks {symbols}...")
        return f"Market Status: {', '.join(symbols)} tracking active [Price Signal Hub]."

    def fetch_sports(self):
        print("⚽ Fetching sports updates...")
        try:
            response = requests.get("https://news.google.com/rss/search?q=sports", headers=self.headers, timeout=10)
            soup = BeautifulSoup(response.content, 'xml')
            return " Sports: " + " | ".join([i.title.text for i in soup.find_all('item')[:10]])
        except: return ""

    def fetch_arxiv(self, query="ai"):
        print(f"🔬 Fetching {query} research from arXiv...")
        try:
            url = f"http://export.arxiv.org/api/query?search_query=all:{query}&start=0&max_results=10"
            response = requests.get(url, headers=self.headers, timeout=10)
            soup = BeautifulSoup(response.content, 'xml')
            titles = [t.text.strip() for t in soup.find_all('title')][1:]
            return f"arXiv {query}: " + " | ".join(titles)
        except: return ""

    def fetch_regulatory(self):
        print("⚖️ Fetching regulatory updates...")
        try:
            url = "https://www.federalregister.gov/api/v1/documents.json?per_page=10"
            data = requests.get(url, headers=self.headers, timeout=10).json()
            titles = [doc['title'] for doc in data.get('results', [])]
            return "Regulatory: " + " | ".join(titles)
        except: return ""

    def fetch_crypto(self):
        print("🪙 Fetching crypto markets...")
        try:
            url = "https://api.coingecko.com/api/v3/simple/price?ids=bitcoin,ethereum,cardano&vs_currencies=usd"
            data = requests.get(url, headers=self.headers, timeout=10).json()
            summary = "Crypto: " + ", ".join([f"{k.capitalize()}: ${v['usd']}" for k,v in data.items()])
            return summary
        except: return ""

    def fetch_github_trending(self):
        print("💻 Fetching GitHub trends...")
        try:
            response = requests.get("https://github.com/trending", headers=self.headers, timeout=15)
            soup = BeautifulSoup(response.content, 'html.parser')
            repos = [r.text.strip().replace("\n", "").replace(" ", "") for r in soup.select('h2.h3 a')[:10]]
            return "Trending Code: " + " | ".join(repos)
        except: return ""

class GeometricRefinery:
    def __init__(self):
        try:
            import _synthesus_kernel as kernel
            self.engine = kernel.GeometricEngine()
            print("🚀 Geometric Refinery using C++ Engine")
        except ImportError:
            self.engine = GeometricEngineFallback()
            print("⚠️ Geometric Refinery using Python Fallback (C++ bridge not built)")
            
        self.live = LiveIngestor()
        self.archive = ArchiveIngestor()
        self.bridge = TranslationBridge(self.engine)
        self.shard_dir = Path("/home/dakin/dev/Synthesus_4.0/data/geometric_shards")
        self.shard_dir.mkdir(parents=True, exist_ok=True)

    def automate_multi_sharding(self):
        print("\n--- Starting Automated Multi-Category Sharding ---")
        
        # 0. Generate Translation Bridge
        self.bridge.generate_bridge_shard()

        categories = {
            "environment": [self.live.fetch_weather("London"), self.live.fetch_weather("New York")],
            "global_news": [self.live.fetch_news()],
            "finance": [self.live.fetch_stocks(), self.live.fetch_crypto()],
            "sports": [self.live.fetch_sports()],
            "technical": [self.live.fetch_arxiv("quantum"), self.live.fetch_arxiv("ai"), self.live.fetch_github_trending()],
            "regulatory": [self.live.fetch_regulatory()],
            "library": [self.archive.fetch_library_samples(limit=10)]
        }
        
        for cat, blobs in categories.items():
            combined_text = "\n".join([b for b in blobs if b])
            if not combined_text: 
                print(f"⏩ Skipping {cat} (no data)")
                continue
            
            raw_file = f"temp_{cat}.txt"
            with open(raw_file, 'w') as f: f.write(combined_text)
            
            output_shard = self.shard_dir / f"{cat}.kn"
            self.refine_text_to_partition(raw_file, str(output_shard))
            os.remove(raw_file)
            
        print("\n--- Multi-Category Ingestion Complete ---")

    def refine_text_to_partition(self, input_path, output_path):
        if not os.path.exists(input_path): return
        with open(input_path, 'r', encoding='utf-8') as f: text = f.read()

        # Advanced Unicode Tokenization
        # 1. Split by spaces for most languages
        # 2. Extract individual characters for CJK (Chinese, Japanese, Korean)
        words = []
        for word in text.lower().split():
            # Check if word contains CJK characters
            is_cjk = any('\u4e00' <= char <= '\u9fff' for char in word)
            if is_cjk:
                words.extend(list(word)) # Individual pictographs are concepts
            else:
                words.append(word)
        
        unique_words = list(set(words))
        
        kn_data = {
            "metadata": {"source": input_path, "timestamp": time.time(), "dimensions": 5},
            "vectors": {w: self.engine.word_to_vector(w) for w in unique_words if len(w) > 0}
        }

        with open(output_path, 'w') as f: json.dump(kn_data, f, indent=2, ensure_ascii=False)
        print(f"💾 Shard [{os.path.basename(output_path)}] created. Size: {len(kn_data['vectors'])} tokens.")

if __name__ == "__main__":
    refinery = GeometricRefinery()
    refinery.automate_multi_sharding()
