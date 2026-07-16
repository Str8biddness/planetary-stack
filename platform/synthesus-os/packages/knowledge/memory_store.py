# core/memory_store.py
# Synthesus 2.0 - Memory Store
# Persistent episodic, semantic, procedural, and working memory for synthetic characters

from __future__ import annotations

import json
import re
import sqlite3
import uuid
from contextlib import contextmanager
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from datetime import datetime, timezone, timedelta

import numpy as np

try:
    from ml.swarm_embedder import SwarmEmbedder
except Exception:
    SwarmEmbedder = None


# ---------------------------------------------------------------------------
# Data Models
# ---------------------------------------------------------------------------

@dataclass
class Memory:
    id: str
    character_id: str
    memory_type: str       # "episodic" | "semantic" | "procedural" | "working"
    content: str
    importance: float = 0.5   # [0.0, 1.0]
    access_count: int = 0
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    last_accessed: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    tags: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Convert Memory instance to a dictionary suitable for database storage."""
        d = asdict(self)
        d["tags"] = json.dumps(self.tags)
        d["metadata"] = json.dumps(self.metadata)
        return d

    @classmethod
    def from_row(cls, row: sqlite3.Row) -> "Memory":
        """Create a Memory instance from a database row."""
        d = dict(row)
        d["tags"] = json.loads(d.get("tags") or "[]")
        d["metadata"] = json.loads(d.get("metadata") or "{}")
        return cls(**d)


# ---------------------------------------------------------------------------
# MemoryStore
# ---------------------------------------------------------------------------

class MemoryStore:
    """SQLite-backed episodic, semantic, procedural, and working memory store for Synthesus characters."""

    SCHEMA = """
    CREATE TABLE IF NOT EXISTS memories (
        id TEXT PRIMARY KEY,
        character_id TEXT NOT NULL,
        memory_type TEXT NOT NULL,
        content TEXT NOT NULL,
        importance REAL DEFAULT 0.5,
        access_count INTEGER DEFAULT 0,
        created_at TEXT NOT NULL,
        last_accessed TEXT NOT NULL,
        tags TEXT DEFAULT '[]',
        metadata TEXT DEFAULT '{}'
    );
    CREATE INDEX IF NOT EXISTS idx_mem_character ON memories(character_id);
    CREATE INDEX IF NOT EXISTS idx_mem_type ON memories(memory_type);
    CREATE INDEX IF NOT EXISTS idx_mem_importance ON memories(importance DESC);
    """

    def __init__(
        self,
        db_path: str | Path | Dict[str, Any] = "data/memory.db",
        working_ttl_seconds: int = 3600,
        working_limit: int = 200,
        semantic_dim: int = 128,
    ):
        """Initialize the MemoryStore.

        Args:
            db_path: Path to SQLite database file, or a config dict with
                'db_path'/'path' key. Default 'data/memory.db'.
            working_ttl_seconds: Time-to-live for working memory entries
                in seconds. Default 3600 (1 hour).
            working_limit: Maximum number of working memory entries
                to retain. Default 200.
            semantic_dim: Target embedding size for semantic retrieval.
        """
        if isinstance(db_path, dict):
            config = db_path
            db_path = config.get("db_path") or config.get("path") or "data/memory.db"
            working_ttl_seconds = int(config.get("working_ttl_seconds", working_ttl_seconds))
            working_limit = int(config.get("working_limit", working_limit))
            semantic_dim = int(config.get("semantic_dim", semantic_dim))
        self.db_path = Path(db_path)
        self.working_ttl_seconds = max(0, int(working_ttl_seconds))
        self.working_limit = max(1, int(working_limit))
        self.semantic_dim = max(1, int(semantic_dim))
        self._semantic_cache: Dict[Tuple[str, str, float], Dict[str, Any]] = {}
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _init_db(self) -> None:
        """Initialize the database schema."""
        with self._get_conn() as conn:
            conn.executescript(self.SCHEMA)

    @contextmanager
    def _get_conn(self):
        """Context manager for database connections."""
        conn = sqlite3.connect(self.db_path, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    @staticmethod
    def _normalize_text(text: str) -> str:
        """Normalize text by converting to lowercase and replacing non-alphanumeric characters with spaces."""
        return re.sub(r"[^a-z0-9]+", " ", text.lower()).strip()

    @staticmethod
    def _parse_iso(value: str) -> Optional[datetime]:
        """Parse ISO 8601 formatted string to datetime, with UTC timezone."""
        if not value:
            return None
        try:
            parsed = datetime.fromisoformat(value)
        except ValueError:
            return None
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed

    def _invalidate_character_cache(self, character_id: str) -> None:
        """Invalidate cached semantic indexes for a character."""
        self._semantic_cache = {
            key: value
            for key, value in self._semantic_cache.items()
            if key[0] != character_id
        }

    def _working_expires_at(self, mem: Memory) -> Optional[datetime]:
        """Calculate the expiration time for a working memory entry."""
        expires_at = mem.metadata.get("expires_at")
        parsed = self._parse_iso(expires_at) if isinstance(expires_at, str) else None
        if parsed is not None:
            return parsed
        created = self._parse_iso(mem.created_at)
        if created is None:
            return None
        if self.working_ttl_seconds <= 0:
            return created
        return created + timedelta(seconds=self.working_ttl_seconds)

    def _is_expired_working(self, mem: Memory, now: Optional[datetime] = None) -> bool:
        """Check if a working memory entry has expired."""
        if mem.memory_type != "working":
            return False
        if self.working_ttl_seconds <= 0:
            return True
        now = now or datetime.now(timezone.utc)
        expires_at = self._working_expires_at(mem)
        return expires_at is not None and expires_at <= now

    def cleanup_working_memory(self, character_id: Optional[str] = None) -> int:
        """Remove expired working memory entries for a character."""
        now = datetime.now(timezone.utc)
        with self._get_conn() as conn:
            if character_id:
                rows = conn.execute(
                    "SELECT * FROM memories WHERE memory_type='working' AND character_id=?",
                    (character_id,),
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM memories WHERE memory_type='working'",
                ).fetchall()

            memories = [Memory.from_row(r) for r in rows]
            expired_ids = [m.id for m in memories if self._is_expired_working(m, now)]
            active = [m for m in memories if m.id not in expired_ids]

            if self.working_limit > 0 and len(active) > self.working_limit:
                active.sort(
                    key=lambda m: (
                        self._parse_iso(m.last_accessed) or self._parse_iso(m.created_at) or now,
                        m.importance,
                        m.access_count,
                    ),
                    reverse=True,
                )
                expired_ids.extend(m.id for m in active[self.working_limit:])

            if expired_ids:
                conn.executemany(
                    "DELETE FROM memories WHERE id=?",
                    [(mid,) for mid in expired_ids],
                )
        if character_id and expired_ids:
            self._invalidate_character_cache(character_id)
        return len(expired_ids)

    def _memory_document(self, mem: Memory) -> str:
        """Build a retrieval document for semantic scoring."""
        parts = [mem.content]
        if mem.tags:
            parts.append("Tags: " + " ".join(mem.tags))
        if mem.metadata:
            metadata_bits = [f"{k} {v}" for k, v in mem.metadata.items() if k != "expires_at"]
            if metadata_bits:
                parts.append("Metadata: " + " ".join(metadata_bits))
        parts.append(f"Type: {mem.memory_type}")
        return "\n".join(parts)

    @staticmethod
    def _semantic_fingerprint(memories: List[Memory]) -> str:
        """Create a stable fingerprint for a semantic candidate set."""
        payload = [
            (m.id, m.last_accessed, m.access_count, m.importance, m.content)
            for m in memories
        ]
        return json.dumps(payload, sort_keys=True, ensure_ascii=False)

    def _semantic_rank(
        self,
        character_id: str,
        query: str,
        memory_type: Optional[str],
        top_k: int,
        min_importance: float,
    ) -> List[Memory]:
        """Semantic retrieval over the requested memory slice with lexical fallback."""
        candidates = self._fetch_all(character_id, memory_type, min_importance)
        if not candidates:
            return []
        if not query.strip():
            return candidates[:top_k]

        if SwarmEmbedder is None or len(candidates) < 2:
            return self._lexical_rank(candidates, query, top_k)

        cache_key = (character_id, memory_type or "all", float(min_importance))
        fingerprint = self._semantic_fingerprint(candidates)
        cached = self._semantic_cache.get(cache_key)
        if not cached or cached.get("fingerprint") != fingerprint:
            corpus = [self._memory_document(m) for m in candidates]
            try:
                embedder = SwarmEmbedder(dim=self.semantic_dim)
                embedder.fit(corpus)
                embeddings = embedder.embed_texts(corpus)
                cached = {
                    "fingerprint": fingerprint,
                    "embedder": embedder,
                    "embeddings": embeddings,
                    "memories": candidates,
                }
                self._semantic_cache[cache_key] = cached
            except Exception:
                return self._lexical_rank(candidates, query, top_k)

        embedder = cached["embedder"]
        embeddings = cached["embeddings"]
        memories = cached["memories"]
        try:
            query_vec = embedder.embed_texts([self._memory_document(Memory(
                id="query",
                character_id=character_id,
                memory_type=memory_type or "semantic",
                content=query,
            ))])[0]
        except Exception:
            return self._lexical_rank(memories, query, top_k)

        scores = np.asarray(embeddings, dtype=np.float32) @ np.asarray(query_vec, dtype=np.float32)
        ranked = sorted(zip(memories, scores), key=lambda item: float(item[1]), reverse=True)
        results = [mem for mem, score in ranked if float(score) > 0][:top_k]
        return results or self._lexical_rank(memories, query, top_k)

    def _touch_memories(self, memory_ids: List[str]) -> None:
        """Update access counters for recalled memories."""
        if not memory_ids:
            return
        now = datetime.now(timezone.utc).isoformat()
        with self._get_conn() as conn:
            for memory_id in memory_ids:
                conn.execute(
                    "UPDATE memories SET access_count = access_count + 1, last_accessed=? WHERE id=?",
                    (now, memory_id),
                )

    def _lexical_rank(self, memories: List[Memory], query: str, top_k: int) -> List[Memory]:
        """Keyword-based fallback ranking."""
        if not query.strip():
            return memories[:top_k]
        tokens = set(self._normalize_text(query).split())
        scored = [(m, self._score(m, tokens)) for m in memories]
        scored.sort(key=lambda item: item[1], reverse=True)
        return [m for m, score in scored if score > 0][:top_k]

    # ------------------------------------------------------------------
    # Write
    # ------------------------------------------------------------------

    def store(
        self,
        character_id: str,
        content: str,
        memory_type: str = "episodic",
        importance: float = 0.5,
        tags: Optional[List[str]] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Memory:
        """Store a new memory entry."""
        now = datetime.now(timezone.utc).isoformat()
        mem = Memory(
            id=str(uuid.uuid4()),
            character_id=character_id,
            memory_type=memory_type,
            content=content,
            importance=max(0.0, min(1.0, importance)),
            created_at=now,
            last_accessed=now,
            tags=tags or [],
            metadata=metadata or {},
        )
        d = mem.to_dict()
        with self._get_conn() as conn:
            conn.execute(
                """
                INSERT INTO memories
                (id, character_id, memory_type, content, importance,
                 access_count, created_at, last_accessed, tags, metadata)
                VALUES (?,?,?,?,?,?,?,?,?,?)
                """,
                (
                    d["id"], d["character_id"], d["memory_type"], d["content"],
                    d["importance"], d["access_count"], d["created_at"],
                    d["last_accessed"], d["tags"], d["metadata"],
                ),
            )
        self._invalidate_character_cache(character_id)
        return mem

    def store_episodic(
        self,
        character_id: str,
        content: str,
        importance: float = 0.5,
        tags: Optional[List[str]] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Memory:
        """Store a new episodic memory entry."""
        return self.store(character_id, content, "episodic", importance, tags, metadata)

    def store_semantic(
        self,
        character_id: str,
        content: str,
        importance: float = 0.7,
        tags: Optional[List[str]] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Memory:
        """Store a new semantic memory entry."""
        return self.store(character_id, content, "semantic", importance, tags, metadata)

    def store_procedural(
        self,
        character_id: str,
        content: str,
        importance: float = 0.7,
        tags: Optional[List[str]] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Memory:
        """Store a new procedural memory entry."""
        return self.store(character_id, content, "procedural", importance, tags, metadata)

    def store_working(
        self,
        character_id: str,
        content: str,
        importance: float = 0.3,
        tags: Optional[List[str]] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Memory:
        """Store a new working memory entry."""
        working_metadata = dict(metadata or {})
        if self.working_ttl_seconds > 0:
            working_metadata.setdefault(
                "expires_at",
                (datetime.now(timezone.utc) + timedelta(seconds=self.working_ttl_seconds)).isoformat(),
            )
        working_metadata.setdefault("memory_scope", "working")
        mem = self.store(character_id, content, "working", importance, tags, working_metadata)
        self.cleanup_working_memory(character_id)
        return mem

    # ------------------------------------------------------------------
    # Read
    # ------------------------------------------------------------------

    def recall(
        self,
        character_id: str,
        query: str,
        memory_type: Optional[str] = None,
        top_k: int = 10,
        min_importance: float = 0.0,
    ) -> List[Memory]:
        """Recall memories using the best available strategy."""
        if memory_type == "working":
            self.cleanup_working_memory(character_id)
        if memory_type == "semantic":
            results = self._semantic_rank(character_id, query, memory_type, top_k, min_importance)
        else:
            all_mems = self._fetch_all(character_id, memory_type, min_importance)
            results = self._lexical_rank(all_mems, query, top_k)
        self._touch_memories([m.id for m in results])
        return results

    def recall_procedural(
        self,
        character_id: str,
        query: str,
        top_k: int = 5,
        min_importance: float = 0.0,
    ) -> List[Memory]:
        """Recall procedural memories."""
        return self.recall(character_id, query, memory_type="procedural", top_k=top_k, min_importance=min_importance)

    def recall_semantic(
        self,
        character_id: str,
        query: str,
        top_k: int = 5,
        min_importance: float = 0.0,
    ) -> List[Memory]:
        """Recall semantic memories using vector similarity with lexical fallback."""
        return self.recall(character_id, query, memory_type="semantic", top_k=top_k, min_importance=min_importance)

    def recall_episodic(
        self,
        character_id: str,
        query: str,
        top_k: int = 5,
        min_importance: float = 0.0,
    ) -> List[Memory]:
        """Recall episodic memories."""
        return self.recall(character_id, query, memory_type="episodic", top_k=top_k, min_importance=min_importance)

    def recall_working(
        self,
        character_id: str,
        query: str,
        top_k: int = 5,
        min_importance: float = 0.0,
    ) -> List[Memory]:
        """Recall working memories."""
        self.cleanup_working_memory(character_id)
        return self.recall(character_id, query, memory_type="working", top_k=top_k, min_importance=min_importance)

    def get(self, memory_id: str) -> Optional[Memory]:
        """Retrieve a memory by ID."""
        with self._get_conn() as conn:
            row = conn.execute(
                "SELECT * FROM memories WHERE id=?", (memory_id,)
            ).fetchone()
        return Memory.from_row(row) if row else None

    def list(
        self,
        character_id: str,
        memory_type: Optional[str] = None,
        limit: int = 50,
    ) -> List[Memory]:
        """List memories for a character."""
        return self._fetch_all(character_id, memory_type, limit=limit)

    # ------------------------------------------------------------------
    # Delete / Consolidate
    # ------------------------------------------------------------------

    def forget(self, memory_id: str) -> bool:
        """Delete a memory by ID."""
        with self._get_conn() as conn:
            row = conn.execute("SELECT character_id FROM memories WHERE id=?", (memory_id,)).fetchone()
            cur = conn.execute("DELETE FROM memories WHERE id=?", (memory_id,))
        if row:
            self._invalidate_character_cache(row["character_id"])
        return cur.rowcount > 0

    def prune(
        self,
        character_id: str,
        keep_top: int = 200,
        min_importance: float = 0.1,
    ) -> int:
        """Remove low-importance memories beyond keep_top threshold."""
        with self._get_conn() as conn:
            rows = conn.execute(
                "SELECT id FROM memories WHERE character_id=? AND importance>=? "
                "ORDER BY importance DESC, access_count DESC",
                (character_id, min_importance),
            ).fetchall()
            keep_ids = {r["id"] for r in rows[:keep_top]}
            all_ids = {r["id"] for r in conn.execute(
                "SELECT id FROM memories WHERE character_id=?", (character_id,)
            ).fetchall()}
            remove_ids = all_ids - keep_ids
            if remove_ids:
                conn.executemany(
                    "DELETE FROM memories WHERE id=?",
                    [(i,) for i in remove_ids],
                )
        if remove_ids:
            self._invalidate_character_cache(character_id)
        return len(remove_ids)

    # ------------------------------------------------------------------
    # Stats
    # ------------------------------------------------------------------

    def stats(self, character_id: str) -> Dict[str, Any]:
        """Get statistics for a character's memories."""
        with self._get_conn() as conn:
            total = conn.execute(
                "SELECT COUNT(*) FROM memories WHERE character_id=?",
                (character_id,),
            ).fetchone()[0]
            by_type = conn.execute(
                "SELECT memory_type, COUNT(*) as cnt FROM memories "
                "WHERE character_id=? GROUP BY memory_type",
                (character_id,),
            ).fetchall()
        return {
            "total": total,
            "by_type": {r["memory_type"]: r["cnt"] for r in by_type},
        }

    # ------------------------------------------------------------------
    # Private utilities
    # ------------------------------------------------------------------

    def _fetch_all(
        self,
        character_id: str,
        memory_type: Optional[str] = None,
        min_importance: float = 0.0,
        limit: int = 1000,
    ) -> List[Memory]:
        """Fetch all memories for a character."""
        with self._get_conn() as conn:
            if memory_type:
                rows = conn.execute(
                    "SELECT * FROM memories WHERE character_id=? AND memory_type=? "
                    "AND importance>=? ORDER BY importance DESC LIMIT ?",
                    (character_id, memory_type, min_importance, limit),
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM memories WHERE character_id=? AND importance>=? "
                    "ORDER BY importance DESC LIMIT ?",
                    (character_id, min_importance, limit),
                ).fetchall()
        return [Memory.from_row(r) for r in rows]

    @staticmethod
    def _score(mem: Memory, tokens: set) -> float:
        """Calculate a score for a memory based on query tokens."""
        content_tokens = set(MemoryStore._normalize_text(mem.content).split())
        tag_tokens = {
            token
            for tag in mem.tags
            for token in MemoryStore._normalize_text(tag).split()
        }
        overlap = len(tokens & content_tokens)
        tag_overlap = len(tokens & tag_tokens)
        recency = 0.0
        last_accessed = MemoryStore._parse_iso(mem.last_accessed)
        if last_accessed is not None:
            age_seconds = max(0.0, (datetime.now(timezone.utc) - last_accessed).total_seconds())
            recency = max(0.0, 1.0 - min(age_seconds, 86400.0) / 86400.0)
        access_bonus = min(mem.access_count, 20) * 0.03
        return overlap * 1.0 + tag_overlap * 0.75 + mem.importance * 0.2 + recency * 0.1 + access_bonus
