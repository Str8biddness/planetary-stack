#!/usr/bin/env python3
"""
Geometric Streamer — Synthesus 5 Phase 5
High-concurrency refinery that processes data in-memory (Streaming).
Bypasses intermediate storage to scale toward 100TB ingestion.
"""

import asyncio
import aiohttp
import json
import time
import sys
import os
from pathlib import Path
from bs4 import BeautifulSoup

# Ensure tools directory is in path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), 'tools')))
from geometric_refinery import GeometricEngineFallback

class GeometricStreamer:
    def __init__(self, category="general"):
        self.category = category
        self.engine = GeometricEngineFallback()
        self.shard_dir = Path("/home/dakin/dev/Synthesus_4.0/data/geometric_shards")
        self.shard_dir.mkdir(parents=True, exist_ok=True)
        self.vectors = {}
        self.total_processed_bytes = 0
        self.start_time = time.time()
        print(f"📡 Streaming Refinery initialized for [{category}]")

    async def fetch_and_refine(self, session, url):
        """Fetches a URL and crystallizes it directly to memory."""
        try:
            async with session.get(url, timeout=10) as response:
                if response.status == 200:
                    text = await response.text()
                    self.total_processed_bytes += len(text.encode('utf-8'))
                    
                    # Direct Projection (Tokenize & Map)
                    soup = BeautifulSoup(text, 'html.parser')
                    clean_text = soup.get_text()
                    
                    tokens = clean_text.lower().split()
                    for token in tokens:
                        if len(token) > 2 and token not in self.vectors:
                            # Crystallize!
                            self.vectors[token] = self.engine.word_to_vector(token)
                    
                    return True
        except Exception as e:
            # print(f"⚠️ Stream error on {url}: {e}")
            pass
        return False

    async def run_stream_cycle(self, urls):
        print(f"🚀 Starting stream cycle for {len(urls)} targets...")
        async with aiohttp.ClientSession(headers={'User-Agent': 'SynthesusStreamer/1.0'}) as session:
            tasks = [self.fetch_and_refine(session, url) for url in urls]
            await asyncio.gather(*tasks)
        
        self.save_shard()

    def save_shard(self):
        output_path = self.shard_dir / f"{self.category}_streamed.kn"
        duration = time.time() - self.start_time
        rate = (self.total_processed_bytes / 1024 / 1024) / duration if duration > 0 else 0
        
        kn_data = {
            "metadata": {
                "type": "streamed_crystallization",
                "timestamp": time.time(),
                "processed_raw_mb": self.total_processed_bytes / 1024 / 1024,
                "ingestion_rate_mb_s": rate
            },
            "vectors": self.vectors
        }

        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(kn_data, f, indent=2, ensure_ascii=False)
        
        print(f"💾 Shard [{self.category}_streamed.kn] saved.")
        print(f"📊 Stats: {len(self.vectors)} concepts | {self.total_processed_bytes/1024:.2f} KB refined | {rate:.2f} MB/s rate")

if __name__ == "__main__":
    # Example: Streaming the 'Technical' pillar via target documentation sites
    targets = [
        "https://docs.python.org/3/library/index.html",
        "https://docs.python.org/3/library/stdtypes.html",
        "https://docs.python.org/3/library/functions.html",
        "https://en.cppreference.com/w/cpp/header",
        "https://doc.rust-lang.org/std/index.html"
    ]
    
    streamer = GeometricStreamer(category="technical")
    asyncio.run(streamer.run_stream_cycle(targets))
