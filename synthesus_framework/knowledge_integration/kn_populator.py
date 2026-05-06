"""
KNDatabase Populator — Build Synthesus knowledge index from loaded datasets.

Takes KnowledgeEntry objects from kaggle_loader.py and populates:
1. KNDatabase binary store  (kn_database.cpp via ctypes / subprocess wrapper)
2. FAISS vector index        (for semantic search over questions + answers)
3. A metadata SQLite file    (fast lookup by category / source)

Usage:
    python -m knowledge_integration.kn_populator \
        --cache-dir ./data --kn-db ./data/knowledge.kndb --faiss ./data/knowledge.faiss
"""

from __future__ import annotations

import json
import logging
import os
import sqlite3
import struct
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

logger = logging.getLogger(__name__)


def _ensure_parent_dir(path: str | Path) -> Path:
    resolved = Path(path)
    resolved.parent.mkdir(parents=True, exist_ok=True)
    return resolved

# ---------------------------------------------------------------------------
# KNDatabase binary wrapper (direct read/write — no ctypes dependency)
# ---------------------------------------------------------------------------

class KNBinaryWriter:
    """
    Write-only Python wrapper for kn_database.bin.
    Reads existing .kndb via struct.unpack; appends new KNodes.

    File format (per node, binary, native endian):
      8 bytes   : id       (uint64)
      4 bytes   : weight   (float32)
      8 bytes   : ts       (uint64, ms epoch)
      4 bytes   : klen     (uint32)
      klen bytes: key      (utf-8)
      4 bytes   : vlen     (uint32)
      vlen bytes: value    (utf-8)
      4 bytes   : lcount   (uint32)
      lcount*8   : links    (uint64[])
    """

    HEADER = b"KNDB\x01\n"

    def __init__(self, path: str | Path):
        self.path = _ensure_parent_dir(path)
        self.next_id = 1
        self._load_max_id()

    def _load_max_id(self) -> None:
        if not self.path.exists():
            return
        with open(self.path, "rb") as f:
            f.seek(-8, os.SEEK_END)
            while True:
                f.seek(-8 - 4, os.SEEK_CUR)
                try:
                    klen_bytes = f.read(4)
                    if not klen_bytes:
                        break
                    klen = struct.unpack("<I", klen_bytes)[0]
                    f.seek(-4 - klen, os.SEEK_CUR)
                    self.next_id = max(self.next_id, struct.unpack("<Q", f.read(8))[0] + 1)
                except Exception:
                    break

    def insert(self, key: str, value: str, weight: float = 1.0,
               timestamp_ms: Optional[int] = None, links: Optional[List[int]] = None) -> int:
        """Append a KNode to the binary file. Returns the new node id."""
        if timestamp_ms is None:
            timestamp_ms = int(time.time() * 1000)
        links = links or []
        nid = self.next_id
        self.next_id += 1

        key_bytes  = key.encode("utf-8")
        value_bytes = value.encode("utf-8")
        klen = len(key_bytes)
        vlen = len(value_bytes)
        lcount = len(links)

        with open(self.path, "ab") as f:
            f.write(struct.pack("<Q", nid))
            f.write(struct.pack("<f", weight))
            f.write(struct.pack("<Q", timestamp_ms))
            f.write(struct.pack("<I", klen))
            f.write(key_bytes)
            f.write(struct.pack("<I", vlen))
            f.write(value_bytes)
            f.write(struct.pack("<I", lcount))
            for link in links:
                f.write(struct.pack("<Q", link))

        return nid

    def size(self) -> int:
        """Return total number of nodes."""
        if not self.path.exists():
            return 0
        return int(self.next_id - 1) if self.next_id > 1 else 0


# ---------------------------------------------------------------------------
# Metadata SQLite helper
# ---------------------------------------------------------------------------

class MetadataDB:
    """Fast metadata index stored in SQLite alongside the KN binary."""

    def __init__(self, path: str | Path):
        self.path = _ensure_parent_dir(Path(path).with_suffix(".meta.db"))
        self.conn = sqlite3.connect(str(self.path))
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS entries (
                id         INTEGER PRIMARY KEY,
                key        TEXT UNIQUE NOT NULL,
                question   TEXT,
                answer     TEXT,
                category   TEXT,
                value      TEXT,
                source     TEXT,
                row_index  INTEGER
            )
        """)
        self.conn.execute("CREATE INDEX IF NOT EXISTS idx_category ON entries(category)")
        self.conn.execute("CREATE INDEX IF NOT EXISTS idx_source   ON entries(source)")
        self.conn.commit()

    def insert(self, id: int, key: str, question: str, answer: str,
               category: str, value: str, source: str, row_index: int) -> None:
        self.conn.execute("""
            INSERT OR REPLACE INTO entries
                (id,key,question,answer,category,value,source,row_index)
            VALUES (?,?,?,?,?,?,?,?)
        """, (id, key, question, answer, category, value, source, row_index))

    def commit(self) -> None:
        self.conn.commit()

    def query_by_category(self, category: str, limit: int = 100) -> List[Dict[str, Any]]:
        cur = self.conn.execute(
            "SELECT * FROM entries WHERE category=? LIMIT ?", (category, limit)
        )
        cols = [d[0] for d in cur.description]
        return [dict(zip(cols, row)) for row in cur.fetchall()]

    def stats(self) -> Dict[str, Any]:
        cur = self.conn.execute("SELECT COUNT(*), COUNT(DISTINCT category), COUNT(DISTINCT source) FROM entries")
        row = cur.fetchone()
        return {"total": row[0], "categories": row[1], "sources": row[2]}


# ---------------------------------------------------------------------------
# Main populator
# ---------------------------------------------------------------------------

class KNPopulator:
    """
    Populate KNDatabase + FAISS + SQLite metadata from KnowledgeEntry stream.

    Pipeline:
        KnowledgeEntry
          → text_blob = f"{question} | {answer} | {category}"
          → embed via SwarmEmbedder  (TF-IDF + SVD, <1ms)
          → insert into KNDatabase   (binary, keyed by question[:64])
          → add to FAISS index       (flat IP, cosine sim)
          → write metadata to SQLite
    """

    def __init__(
        self,
        kn_path: str | Path,
        faiss_path: str | Path,
        embedder,          # SwarmEmbedder instance
        meta_db: Optional[MetadataDB] = None,
        batch_size: int = 1000,
    ):
        self.kn_path    = _ensure_parent_dir(kn_path)
        self.faiss_path = _ensure_parent_dir(faiss_path)
        self.embedder   = embedder
        self.meta_db    = meta_db or MetadataDB(self.kn_path)
        self.batch_size = batch_size
        self._kn_writer  = KNBinaryWriter(str(kn_path))
        self._buffer_texts: List[str]    = []
        self._buffer_meta:  List[Dict[str, Any]] = []
        self._faiss_index: Any = None

    # ------------------------------------------------------------------
    # FAISS helpers
    # ------------------------------------------------------------------

    def _init_faiss(self, dim: int) -> None:
        """Lazy-import FAISS and create a fresh IndexFlatIP."""
        import faiss
        # L2 index (cosine sim via normalised vectors in SwarmEmbedder)
        self._faiss_index = faiss.IndexFlatIP(dim)
        logger.info(f"Created FAISS IndexFlatIP (dim={dim}), total={self._faiss_index.ntotal}")

    def _ensure_faiss(self, dim: Optional[int] = None) -> None:
        if self._faiss_index is None and dim is not None:
            self._init_faiss(dim)

    def _load_existing_faiss(self) -> bool:
        """Try to load existing FAISS index. Returns True if loaded."""
        if not self.faiss_path.exists():
            return False
        try:
            import faiss
            self._faiss_index = faiss.read_index(str(self.faiss_path))
            logger.info(f"Loaded existing FAISS index: {self._faiss_index.ntotal} vectors")
            return True
        except Exception as e:
            logger.warning(f"Could not load FAISS index: {e}")
            return False

    # ------------------------------------------------------------------
    # Population
    # ------------------------------------------------------------------

    def populate(self, entries, max_entries: Optional[int] = None) -> Dict[str, Any]:
        """
        Populate from an iterable of KnowledgeEntry objects.

        Args:
            entries: Generator[KnowledgeEntry, None, None]
            max_entries: Stop after N entries (for testing).

        Returns:
            dict with stats: total_inserted, kn_size, faiss_size, duration_s
        """
        start = time.time()
        total  = 0
        t0     = start

        self._load_existing_faiss()

        texts_buf: List[str]    = []
        meta_buf:  List[Dict]   = []
        kn_ids:    List[int]    = []

        for entry in entries:
            if max_entries is not None and (total + len(texts_buf)) >= max_entries:
                break
            # Combine question + answer + category into searchable text blob
            blob = f"{entry.question} | {entry.answer} | {entry.category}"
            texts_buf.append(blob)
            meta_buf.append({
                "key":      entry.key,
                "question": entry.question,
                "answer":   entry.answer,
                "category": entry.category,
                "value":    entry.value,
                "source":   entry.source,
                "row_index": entry.row_index,
            })

            if len(texts_buf) >= self.batch_size:
                inserted = self._flush_batch(texts_buf, meta_buf, kn_ids)
                total += inserted
                texts_buf, meta_buf, kn_ids = [], [], []
                elapsed = time.time() - t0
                logger.info(f"  flushed batch ({inserted}), total={total}, {elapsed:.1f}s")
                if max_entries and total >= max_entries:
                    break

        # Flush remainder
        if texts_buf:
            total += self._flush_batch(texts_buf, meta_buf, kn_ids)

        # Persist FAISS index
        if self._faiss_index is not None:
            import faiss
            faiss.write_index(self._faiss_index, str(self.faiss_path))
            logger.info(f"FAISS index saved to {self.faiss_path} ({self._faiss_index.ntotal} vectors)")

        duration = time.time() - start
        kn_size  = self._kn_writer.size()
        faiss_size = self._faiss_index.ntotal if self._faiss_index else 0

        result = {
            "total_inserted": total,
            "kn_size":       kn_size,
            "faiss_size":    faiss_size,
            "duration_s":   round(duration, 2),
            "entries_per_s": round(total / max(duration, 0.001), 1),
        }
        logger.info(f"KNPopulator finished: {result}")
        return result

    def _flush_batch(
        self, texts: List[str], meta: List[Dict], kn_ids: List[int]
    ) -> int:
        """Embed, index, and write a batch."""
        # 1. Embed
        vecs = self.embedder.embed_texts(texts)   # (batch, dim), float32, L2-norm

        # 2. FAISS — create or validate the index after we know the actual vector dim
        if self._faiss_index is None:
            self._init_faiss(vecs.shape[1])
        elif getattr(self._faiss_index, "d", vecs.shape[1]) != vecs.shape[1]:
            raise ValueError(
                f"FAISS dimension mismatch: index dim {self._faiss_index.d} vs embeddings {vecs.shape[1]}. "
                "Delete the stale index or regenerate it with the same embedder model."
            )
        self._faiss_index.add(vecs)

        # 3. Write KN + metadata
        for v, m in zip(vecs, meta):
            # Use truncated key to avoid oversized keys
            key    = m["key"][:128]
            # Value stores answer + metadata for retrieval
            value  = json.dumps({"answer": m["answer"], "category": m["category"],
                                   "value": m["value"], "source": m["source"]}, ensure_ascii=False)
            nid    = self._kn_writer.insert(key, value, weight=1.0)
            kn_ids.append(nid)

            self.meta_db.insert(
                id=nid, key=m["key"], question=m["question"],
                answer=m["answer"], category=m["category"],
                value=m["value"], source=m["source"], row_index=m["row_index"],
            )
        self.meta_db.commit()

        return len(texts)

    # ------------------------------------------------------------------
    # Query (sanity check)
    # ------------------------------------------------------------------

    def search_faiss(self, query: str, top_k: int = 5) -> List[Tuple[Dict, float]]:
        """
        Semantic search over the index. Returns list of (metadata, score).
        """
        if self._faiss_index is None:
            self._load_existing_faiss()
        if self._faiss_index is None:
            return []

        q_vec = self.embedder.embed_texts([query])   # (1, dim)
        
        # Check dimension mismatch
        if getattr(self._faiss_index, "d", q_vec.shape[1]) != q_vec.shape[1]:
            raise ValueError(
                f"FAISS dimension mismatch: index dim {self._faiss_index.d} vs query dim {q_vec.shape[1]}. "
                "The embedder model may have been refitted on a smaller corpus."
            )

        scores, indices = self._faiss_index.search(q_vec.astype(np.float32), top_k)

        results = []
        for score, idx in zip(scores[0], indices[0]):
            if idx < 0:
                continue
            cursor = self.meta_db.conn.execute(
                "SELECT * FROM entries WHERE id=?", (int(idx + 1),)
            )
            row = cursor.fetchone()
            if row:
                cols = [d[0] for d in cursor.description]
                results.append((dict(zip(cols, row)), float(score)))
        return results

    def stats(self) -> Dict[str, Any]:
        meta_stats = self.meta_db.stats()
        kn_size    = self._kn_writer.size()
        faiss_size = self._faiss_index.ntotal if self._faiss_index else 0
        return {
            "kn_size":     kn_size,
            "faiss_size":  faiss_size,
            **meta_stats,
        }


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import argparse, logging, sys
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s",
                        stream=sys.stdout)

    parser = argparse.ArgumentParser(description="Populate Synthesus KN knowledge index")
    parser.add_argument("--cache-dir", default="./data")
    parser.add_argument("--kn-db", default="./data/knowledge.kndb")
    parser.add_argument("--faiss", default="./data/knowledge.faiss")
    parser.add_argument("--max", type=int, default=None, help="Max entries to load")
    parser.add_argument("--sample-jeopardy", type=int, default=None, help="Jeopardy sample size")
    parser.add_argument("--sample-conceptnet", type=int, default=None, help="ConceptNet sample size")
    parser.add_argument("--model-dir", default="./data/embedder")
    args = parser.parse_args()

    sys.path.insert(0, str(Path(__file__).parent.parent))
    from knowledge_integration.kaggle_loader import load_all_datasets
    from ml.swarm_embedder import SwarmEmbedder

    embedder = SwarmEmbedder(model_dir=args.model_dir)
    pop = KNPopulator(
        kn_path=args.kn_db,
        faiss_path=args.faiss,
        embedder=embedder,
    )

    entries = load_all_datasets(
        cache_dir=args.cache_dir,
        sample_jeopardy=args.sample_jeopardy,
        sample_conceptnet=args.sample_conceptnet,
    )

    result = pop.populate(entries, max_entries=args.max)
    print("\n=== Population Result ===")
    print(json.dumps(result, indent=2))