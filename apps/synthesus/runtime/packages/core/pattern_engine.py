# core/pattern_engine.py
# Synthesus 2.0 - Pattern Engine
# Discovers, scores, and manages reasoning patterns from interaction history

from __future__ import annotations

import json
import math
import sqlite3
import hashlib
from contextlib import contextmanager
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from datetime import datetime, timezone


PATTERN_TEMPLATE_SURFACE = {
    "surface": "pattern_candidate_storage",
    "boundary": "core_pattern_engine",
    "user_facing": False,
}


# ---------------------------------------------------------------------------
# Data Models
# ---------------------------------------------------------------------------

@dataclass
class Pattern:
    """A learned reasoning or behavioral pattern for a Synthesus character.
    
    Patterns are discovered from interaction history, scored by success rate,
    and used by the left hemisphere to generate fast, contextually appropriate
    responses without full cognitive processing.
    
    Attributes:
        id: Unique identifier (SHA256 hash of character_id:type:trigger, first 16 chars).
        character_id: ID of the character this pattern belongs to.
        pattern_type: Category — "reasoning", "response", "emotional", or "behavioral".
        trigger: Conditions or tokens that activate this pattern.
        response_template: Templated output structure when pattern fires.
        weight: Influence weight [0.0, 1.0] affecting selection priority.
        usage_count: Number of times this pattern has been activated.
        success_rate: Ratio of successful to total activations.
        created_at: ISO-8601 UTC timestamp of creation.
        updated_at: ISO-8601 UTC timestamp of last update.
        metadata: Additional flexible data (context windows, examples, surface labels, etc.).
    """
    id: str
    character_id: str
    pattern_type: str          # "reasoning", "response", "emotional", "behavioral"
    trigger: str               # conditions that activate this pattern
    response_template: str     # templated output structure
    weight: float = 1.0        # influence weight [0.0, 1.0]
    usage_count: int = 0
    success_rate: float = 0.0
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """
        Converts the pattern object to a dictionary.

        Returns:
            Dict[str, Any]: A dictionary representation of the pattern.
        """
        return asdict(self)

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "Pattern":
        """
        Creates a Pattern object from a dictionary.

        Args:
            d (Dict[str, Any]): The dictionary containing pattern data.

        Returns:
            Pattern: A new Pattern instance.
        """
        return cls(**{k: v for k, v in d.items() if k in cls.__dataclass_fields__})


@dataclass
class PatternMatch:
    """Result of matching a query against the pattern database.
    
    Attributes:
        pattern: The matched Pattern object.
        score: Overall match score [0.0, 1.0] combining overlap, success rate, weight, recency.
        context_overlap: Fraction of trigger tokens found in query context (Jaccard).
        recency_boost: Exponential decay factor for pattern age (~1.0 for new, ~0.0 for old).
    """
    pattern: Pattern
    score: float
    context_overlap: float
    recency_boost: float


# ---------------------------------------------------------------------------
# PatternEngine
# ---------------------------------------------------------------------------

class PatternEngine:
    """Discovers, scores, and retrieves reasoning patterns for Synthesus characters."""

    SCHEMA = """
    CREATE TABLE IF NOT EXISTS patterns (
        id TEXT PRIMARY KEY,
        character_id TEXT NOT NULL,
        pattern_type TEXT NOT NULL,
        trigger TEXT NOT NULL,
        response_template TEXT NOT NULL,
        weight REAL DEFAULT 1.0,
        usage_count INTEGER DEFAULT 0,
        success_rate REAL DEFAULT 0.0,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL,
        metadata TEXT DEFAULT '{}'
    );
    CREATE INDEX IF NOT EXISTS idx_patterns_character ON patterns(character_id);
    CREATE INDEX IF NOT EXISTS idx_patterns_type ON patterns(pattern_type);
    """

    def __init__(self, db_path: str = "data/patterns.db"):
        """
        Initializes the PatternEngine with a database path.

        Args:
            db_path (str): The path to the SQLite database.
        """
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _init_db(self) -> None:
        """Initializes the pattern database schema."""
        with self._get_conn() as conn:
            conn.executescript(self.SCHEMA)

    @contextmanager
    def _get_conn(self):
        """
        Context manager for database connections.

        Yields:
            sqlite3.Connection: A database connection object.
        """
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
    def _make_id(character_id: str, trigger: str, pattern_type: str) -> str:
        """
        Generates a unique ID for a pattern.

        Args:
            character_id (str): The character ID.
            trigger (str): The pattern trigger text.
            pattern_type (str): The type of pattern.

        Returns:
            str: A 16-character hex string ID.
        """
        raw = f"{character_id}:{pattern_type}:{trigger}"
        return hashlib.sha256(raw.encode()).hexdigest()[:16]

    # ------------------------------------------------------------------
    # CRUD
    # ------------------------------------------------------------------

    def add_pattern(
        self,
        character_id: str,
        pattern_type: str,
        trigger: str,
        response_template: str,
        weight: float = 1.0,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Pattern:
        """
        Adds or replaces a pattern in the database.

        Args:
            character_id (str): The character ID.
            pattern_type (str): The type of pattern.
            trigger (str): The trigger text.
            response_template (str): The response template.
            weight (float): The initial weight (default: 1.0).
            metadata (dict, optional): Additional metadata.

        Returns:
            Pattern: The created Pattern object.
        """
        pid = self._make_id(character_id, trigger, pattern_type)
        now = datetime.now(timezone.utc).isoformat()
        pattern_metadata = self._with_template_surface(metadata or {})
        pattern = Pattern(
            id=pid,
            character_id=character_id,
            pattern_type=pattern_type,
            trigger=trigger,
            response_template=response_template,
            weight=weight,
            created_at=now,
            updated_at=now,
            metadata=pattern_metadata,
        )
        with self._get_conn() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO patterns
                (id, character_id, pattern_type, trigger, response_template,
                 weight, usage_count, success_rate, created_at, updated_at, metadata)
                VALUES (?,?,?,?,?,?,?,?,?,?,?)
                """,
                (
                    pattern.id, pattern.character_id, pattern.pattern_type,
                    pattern.trigger, pattern.response_template, pattern.weight,
                    pattern.usage_count, pattern.success_rate,
                    pattern.created_at, pattern.updated_at,
                    json.dumps(pattern.metadata),
                ),
            )
        return pattern

    def get_pattern(self, pattern_id: str) -> Optional[Pattern]:
        """
        Retrieves a pattern by its ID.

        Args:
            pattern_id (str): The pattern ID.

        Returns:
            Optional[Pattern]: The Pattern object if found, else None.
        """
        with self._get_conn() as conn:
            row = conn.execute(
                "SELECT * FROM patterns WHERE id=?", (pattern_id,)
            ).fetchone()
        if row is None:
            return None
        return self._row_to_pattern(row)

    def list_patterns(
        self,
        character_id: str,
        pattern_type: Optional[str] = None,
        limit: int = 100,
    ) -> List[Pattern]:
        """
        Lists patterns for a specific character.

        Args:
            character_id (str): The character ID.
            pattern_type (str, optional): Filter by pattern type.
            limit (int): The maximum number of patterns to return.

        Returns:
            List[Pattern]: A list of Pattern objects.
        """
        with self._get_conn() as conn:
            if pattern_type:
                rows = conn.execute(
                    "SELECT * FROM patterns WHERE character_id=? AND pattern_type=? LIMIT ?",
                    (character_id, pattern_type, limit),
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM patterns WHERE character_id=? LIMIT ?",
                    (character_id, limit),
                ).fetchall()
        return [self._row_to_pattern(r) for r in rows]

    def delete_pattern(self, pattern_id: str) -> bool:
        """
        Deletes a pattern from the database.

        Args:
            pattern_id (str): The pattern ID.

        Returns:
            bool: True if the pattern was deleted, False otherwise.
        """
        with self._get_conn() as conn:
            cur = conn.execute("DELETE FROM patterns WHERE id=?", (pattern_id,))
        return cur.rowcount > 0

    # ------------------------------------------------------------------
    # Scoring & Retrieval
    # ------------------------------------------------------------------

    def match(
        self,
        character_id: str,
        context: str,
        pattern_type: Optional[str] = None,
        top_k: int = 5,
    ) -> List[PatternMatch]:
        """Score patterns against context and return top-k matches."""
        candidates = self.list_patterns(character_id, pattern_type, limit=500)
        if not candidates:
            return []

        scored: List[PatternMatch] = []
        ctx_tokens = set(context.lower().split())

        for p in candidates:
            overlap = self._token_overlap(ctx_tokens, p.trigger)
            recency = self._recency_boost(p.updated_at)
            score = (
                overlap * 0.5
                + p.success_rate * 0.3
                + p.weight * 0.1
                + recency * 0.1
            )
            scored.append(PatternMatch(
                pattern=p,
                score=score,
                context_overlap=overlap,
                recency_boost=recency,
            ))

        scored.sort(key=lambda m: m.score, reverse=True)
        return scored[:top_k]

    # ------------------------------------------------------------------
    # Learning
    # ------------------------------------------------------------------

    def record_usage(self, pattern_id: str, success: bool) -> None:
        """Update usage stats after a pattern fires."""
        with self._get_conn() as conn:
            row = conn.execute(
                "SELECT usage_count, success_rate FROM patterns WHERE id=?",
                (pattern_id,),
            ).fetchone()
            if row is None:
                return
            n = row["usage_count"] + 1
            sr = (row["success_rate"] * row["usage_count"] + (1.0 if success else 0.0)) / n
            conn.execute(
                "UPDATE patterns SET usage_count=?, success_rate=?, updated_at=? WHERE id=?",
                (n, round(sr, 4), datetime.now(timezone.utc).isoformat(), pattern_id),
            )

    def decay_weights(self, character_id: str, factor: float = 0.99) -> int:
        """Apply exponential decay to all pattern weights for a character."""
        with self._get_conn() as conn:
            cur = conn.execute(
                "UPDATE patterns SET weight = weight * ? WHERE character_id=?",
                (factor, character_id),
            )
        return cur.rowcount

    # ------------------------------------------------------------------
    # Discovery (from raw interaction text)
    # ------------------------------------------------------------------

    def discover(
        self,
        character_id: str,
        interaction_text: str,
        outcome_success: bool,
    ) -> Optional[Pattern]:
        """
        Heuristically extract a pattern from a successful interaction.
        Returns the new Pattern if one was created, else None.
        """
        if not outcome_success:
            return None

        words = interaction_text.lower().split()
        if len(words) < 4:
            return None

        # Simple trigger: first 6 significant words
        stop = {"the", "a", "an", "is", "it", "of", "in", "to", "and", "or"}
        sig = [w for w in words if w not in stop][:6]
        trigger = " ".join(sig)

        # Avoid near-duplicate triggers
        existing = self.list_patterns(character_id, limit=500)
        for p in existing:
            if self._token_overlap(set(sig), p.trigger) > 0.8:
                # Reinforce instead
                self.record_usage(p.id, success=True)
                return None

        template = interaction_text[:200].strip()
        return self.add_pattern(
            character_id=character_id,
            pattern_type="reasoning",
            trigger=trigger,
            response_template=template,
            weight=0.5,
        )

    # ------------------------------------------------------------------
    # Stats
    # ------------------------------------------------------------------

    def stats(self, character_id: str) -> Dict[str, Any]:
        """
        Retrieves pattern statistics for a character.

        Args:
            character_id (str): The character ID.

        Returns:
            Dict[str, Any]: A dictionary containing total patterns and counts by type.
        """
        with self._get_conn() as conn:
            total = conn.execute(
                "SELECT COUNT(*) FROM patterns WHERE character_id=?",
                (character_id,),
            ).fetchone()[0]
            by_type = conn.execute(
                "SELECT pattern_type, COUNT(*) as cnt FROM patterns "
                "WHERE character_id=? GROUP BY pattern_type",
                (character_id,),
            ).fetchall()
        return {
            "total_patterns": total,
            "by_type": {r["pattern_type"]: r["cnt"] for r in by_type},
        }

    # ------------------------------------------------------------------
    # Private utilities
    # ------------------------------------------------------------------

    @staticmethod
    def _row_to_pattern(row: sqlite3.Row) -> Pattern:
        """
        Converts a database row to a Pattern object.

        Args:
            row (sqlite3.Row): The database row.

        Returns:
            Pattern: The converted Pattern object.
        """
        d = dict(row)
        d["metadata"] = json.loads(d.get("metadata") or "{}")
        d["metadata"] = PatternEngine._with_template_surface(d["metadata"])
        return Pattern(**d)

    @staticmethod
    def _with_template_surface(metadata: Dict[str, Any]) -> Dict[str, Any]:
        enriched = dict(metadata)
        existing_surface = enriched.get("template_surface")
        if not isinstance(existing_surface, dict):
            enriched["template_surface"] = dict(PATTERN_TEMPLATE_SURFACE)
            return enriched

        merged_surface = dict(PATTERN_TEMPLATE_SURFACE)
        merged_surface.update(existing_surface)
        merged_surface["user_facing"] = False
        enriched["template_surface"] = merged_surface
        return enriched

    @staticmethod
    def _token_overlap(ctx_tokens: set, trigger: str) -> float:
        """
        Calculates the Jaccard-like overlap between context tokens and trigger.

        Args:
            ctx_tokens (set): A set of tokens from the context.
            trigger (str): The trigger text.

        Returns:
            float: The overlap score [0.0, 1.0].
        """
        trig_tokens = set(trigger.lower().split())
        if not trig_tokens:
            return 0.0
        return len(ctx_tokens & trig_tokens) / len(trig_tokens)

    @staticmethod
    def _recency_boost(updated_at: str) -> float:
        """
        Calculates a recency boost based on the last update time.

        Args:
            updated_at (str): ISO formatted timestamp.

        Returns:
            float: The recency boost factor [0.0, 1.0].
        """
        try:
            dt = datetime.fromisoformat(updated_at)
            delta_days = (datetime.now(timezone.utc) - dt).days
            return math.exp(-delta_days / 30.0)
        except Exception:
            return 0.0
