#!/usr/bin/env python3
"""
Geometric Refinery Tool (Bootstrap Version)
Uses a fallback Python implementation of the 5-Axis Geometric Engine
when the C++ bridge is not yet compiled.
Supports Multi-Category Live Ingestion and Categorical Sharding.
"""

import os
import sys
import re
import html
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

    MASK64 = 0xFFFFFFFFFFFFFFFF

    def word_to_vector(self, word):
        # Canonical hash: bit-for-bit identical to the C++ kernel
        # (geometric_engine.cpp::generate_vector_from_hash) so shards built in
        # Python remain valid when the SSE kernel is loaded. djb2 + fnv1a over
        # UTF-8 bytes with signed-char semantics to match g++ on x86.
        word = word.lower().strip()
        h1 = 5381
        h2 = 0x811c9dc5
        for b in word.encode('utf-8'):
            c = b - 256 if b > 127 else b          # emulate signed char
            h1 = (((h1 << 5) + h1) + c) & self.MASK64          # djb2
            h2 = ((h2 ^ (c & self.MASK64)) * 0x01000193) & self.MASK64  # fnv1a
        x = (h1 & 0xFFFF) / 65535.0
        y = ((h1 >> 16) & 0xFFFF) / 65535.0
        z = ((h1 >> 32) & 0xFFFF) / 65535.0
        phase = ((h1 >> 48) & 0xFFFF) / 65535.0
        scale = (h2 & 0xFFFF) / 65535.0
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

    # Tokens that are markup/code/noise rather than concepts.
    _CJK = lambda self, ch: '\u4e00' <= ch <= '\u9fff'

    # Markers + phrases that signal corpus boilerplate (Project Gutenberg
    # headers/footers and license text) rather than real content. Left
    # unstripped these dominate the low-frequency spectral modes.
    _BOILERPLATE = re.compile(
        r'project gutenberg|gutenberg\.org|gutenberg-tm|public domain|'
        r'distributed proofread|ebook|copyright|trademark|donation|'
        r'redistribut|paragraph 1\.|section [0-9]|terms of (this|the) agreement',
        re.IGNORECASE)

    def _strip_boilerplate(self, text):
        # Extract every body between START / END markers (handles a corpus of
        # several concatenated Gutenberg books, not just one).
        bodies = re.findall(
            r'\*\*\*\s*start of th[ei]s? project gutenberg.*?\*\*\*'
            r'(.*?)'
            r'\*\*\*\s*end of th[ei]s? project gutenberg',
            text, re.IGNORECASE | re.DOTALL)
        if bodies:
            text = "\n".join(bodies)
        # Drop any residual admin/license lines that survived.
        return "\n".join(ln for ln in text.splitlines()
                         if not self._BOILERPLATE.search(ln))

    def clean_and_tokenize(self, text):
        """Turn raw scraped text into concept tokens.

        Strips HTML tags + entities, drops URLs / LaTeX / code residue, keeps
        alphabetic words (len>=2) and individual CJK pictographs. This is the
        gate that keeps `nasa</h2>`, `rel="noopener">mexico`, `$\\textit{jwst}$`
        and `arxiv:2603.17835` out of the knowledge cloud.
        """
        text = self._strip_boilerplate(text)                         # kill license/admin text
        text = html.unescape(re.sub(r'<[^>]+>', ' ', text))          # kill HTML tags + entities
        text = re.sub(r'https?://\S+|www\.\S+', ' ', text)            # kill URLs
        text = re.sub(r'\$[^$]*\$|\\[a-zA-Z]+', ' ', text)            # kill inline LaTeX / commands

        tokens = []
        for raw in text.lower().split():
            # CJK: every pictograph is its own concept
            if any(self._CJK(ch) for ch in raw):
                tokens.extend(ch for ch in raw if self._CJK(ch))
                continue
            # Strip surrounding punctuation, keep internal hyphen/apostrophe
            w = raw.strip(".,;:!?\"'()[]{}<>=*|/\\`~#%&+")
            # Drop code/byte-string prefixes like b'ee, r'x, u'y, f'z
            if "'" in w and len(w.split("'", 1)[0]) < 2:
                continue
            # Concept = purely alphabetic (allowing - and ') and at least 2 chars
            if len(w) >= 2 and re.fullmatch(r"[a-z][a-z'\-]*[a-z]", w):
                tokens.append(w)
        return tokens

    def refine_text_to_partition(self, input_path, output_path):
        if not os.path.exists(input_path): return
        with open(input_path, 'r', encoding='utf-8') as f: text = f.read()

        words = self.clean_and_tokenize(text)
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
