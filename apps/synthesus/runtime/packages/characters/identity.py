"""Identity as an append-only, hash-chained life history.

The consciousness loop already computes C(t) = Psi_f(t) ⊕ M_c(t) ⊕ N_s(t)
(`core/consciousness_integrator.py`), and N_s(t) is already described as the
"Narrative Simulation / Identity State". What was missing is *continuity you
can check*: a character that has been running for six months looked exactly
like a fresh copy of the same genome.

This module makes a character's history the thing that identifies it.

    genesis  = H(genome archive digest || character_id)
    entry_n  = H(entry_{n-1} || C(t) digest || narrative delta)
    identity = head of the chain

Three consequences, and the third is the commercially interesting one:

1. **Rooted in the shipped genome.** Genesis binds to the `.sxc`
   `archive_sha256`, so a chain cannot be transplanted onto a different
   character. Change the genome, and every downstream entry is invalid.
2. **Tamper-evident.** Reordering, editing, or excising an episode breaks
   every subsequent link. History cannot be quietly rewritten.
3. **Not reproducible by copying.** Anyone who buys a character receives the
   genome — that is unavoidable in a local-first product, and no amount of
   obfuscation changes it. But they receive it at genesis. They cannot
   fabricate a chain of 50,000 lived entries without actually running those
   50,000 steps, because each link commits to the one before. Accumulated
   history is the asset that copying does not hand over.

HONEST SCOPE. This is tamper-EVIDENCE and continuity, not authenticity and not
anti-forgery. The owner of the machine can run their own chain forward
perfectly legitimately — that is the product working as intended. What a chain
proves is that *this* history is internally consistent and rooted in *that*
genome; it does not prove who ran it. Binding a chain to an issuer needs a
signature over the head, using the keys the mesh already distributes (see
`services/private_mesh/evidence_signing.py`). That is deliberately not done
here, and a chain must not be described as "verified" in that sense.
"""

from __future__ import annotations

import hashlib
import json
import os
import stat
import tempfile
from pathlib import Path
from typing import Any, Iterable

CHAIN_SCHEMA = "planetary.synthesus.identity_chain.v1"
ENTRY_SCHEMA = "planetary.synthesus.identity_entry.v1"

MAX_ENTRY_BYTES = 64 * 1024
MAX_SUMMARY_CHARS = 2000
MAX_GOALS = 32

_ENTRY_FIELDS = frozenset(
    {"schema", "seq", "prev", "t", "state_sha256", "narrative", "entry_sha256"}
)
_NARRATIVE_FIELDS = frozenset(
    {"identity", "role", "scene", "tone", "goals", "continuity_summary"}
)


class IdentityChainError(ValueError):
    """A chain could not be extended, read, or verified."""


def _canonical(payload: Any) -> bytes:
    return json.dumps(
        payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False
    ).encode("ascii")


def _digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def genesis_digest(*, archive_sha256: str, character_id: str) -> str:
    """Root the chain in the exact genome that shipped."""
    if not isinstance(archive_sha256, str) or len(archive_sha256) != 64:
        raise IdentityChainError("archive_sha256 must be a sha256 hex digest")
    if not isinstance(character_id, str) or not character_id.strip():
        raise IdentityChainError("character_id is required")
    return _digest(_canonical({
        "schema": CHAIN_SCHEMA,
        "archive_sha256": archive_sha256,
        "character_id": character_id.strip(),
    }))


def _normalize_narrative(narrative: Any) -> dict[str, Any]:
    """Reduce a NarrativeState (or plain dict) to the committed fields.

    Only the parts of N_s(t) that constitute identity are committed. Volatile
    scratch state is deliberately excluded, so a chain records what the
    character *became*, not every intermediate flicker.
    """

    if not isinstance(narrative, dict):
        narrative = {
            "identity": getattr(narrative, "identity", None),
            "role": getattr(narrative, "current_role", None),
            "scene": getattr(narrative, "scene_tag", None),
            "tone": getattr(narrative, "emotional_tone", None),
            "goals": getattr(narrative, "goals", None),
            "continuity_summary": getattr(narrative, "continuity_summary", None),
        }
    extra = set(narrative) - _NARRATIVE_FIELDS
    if extra:
        raise IdentityChainError(f"narrative has unexpected fields: {sorted(extra)}")

    identity = narrative.get("identity")
    if not isinstance(identity, str) or not identity.strip():
        raise IdentityChainError("narrative.identity is required")

    summary = narrative.get("continuity_summary") or ""
    if not isinstance(summary, str):
        raise IdentityChainError("continuity_summary must be a string")
    if len(summary) > MAX_SUMMARY_CHARS:
        raise IdentityChainError("continuity_summary exceeds its bound")

    goals_in = narrative.get("goals") or []
    if not isinstance(goals_in, list) or len(goals_in) > MAX_GOALS:
        raise IdentityChainError("goals must be a list within its bound")
    goals: list[dict[str, Any]] = []
    for goal in goals_in:
        if not isinstance(goal, dict) or "id" not in goal:
            raise IdentityChainError("each goal needs an id")
        goals.append({"id": str(goal["id"]), "priority": float(goal.get("priority", 0.0))})

    tone_in = narrative.get("tone") or {}
    if not isinstance(tone_in, dict):
        raise IdentityChainError("tone must be an object")
    tone = {str(k): round(float(v), 6) for k, v in sorted(tone_in.items())}

    return {
        "identity": identity.strip(),
        "role": str(narrative.get("role") or ""),
        "scene": str(narrative.get("scene") or ""),
        "tone": tone,
        "goals": sorted(goals, key=lambda g: g["id"]),
        "continuity_summary": summary,
    }


def build_entry(
    *,
    prev: str,
    seq: int,
    t: int,
    state_sha256: str,
    narrative: Any,
) -> dict[str, Any]:
    """One link. `state_sha256` is the digest of the C(t) the loop produced."""
    if not isinstance(prev, str) or len(prev) != 64:
        raise IdentityChainError("prev must be a sha256 hex digest")
    if not isinstance(seq, int) or isinstance(seq, bool) or seq < 1:
        raise IdentityChainError("seq must be a positive integer")
    if not isinstance(t, int) or isinstance(t, bool) or t < 0:
        raise IdentityChainError("t must be a non-negative integer")
    if not isinstance(state_sha256, str) or len(state_sha256) != 64:
        raise IdentityChainError("state_sha256 must be a sha256 hex digest")

    entry: dict[str, Any] = {
        "schema": ENTRY_SCHEMA,
        "seq": seq,
        "prev": prev,
        "t": t,
        "state_sha256": state_sha256,
        "narrative": _normalize_narrative(narrative),
    }
    body = _canonical(entry)
    if len(body) > MAX_ENTRY_BYTES:
        raise IdentityChainError("entry exceeds its size bound")
    entry["entry_sha256"] = _digest(body)
    return entry


def state_digest(consciousness_state: Any) -> str:
    """Digest of a C(t) state, however the loop represents it."""
    if hasattr(consciousness_state, "__dict__") and not isinstance(consciousness_state, dict):
        payload = {
            key: value for key, value in vars(consciousness_state).items()
            if not key.startswith("_")
        }
    else:
        payload = consciousness_state
    try:
        return _digest(_canonical(payload))
    except (TypeError, ValueError) as exc:
        raise IdentityChainError(f"consciousness state is not serialisable: {exc}") from exc


class IdentityChain:
    """Append-only chain for one character, persisted as JSON lines."""

    def __init__(self, path: Path | str, *, archive_sha256: str, character_id: str) -> None:
        self.path = Path(path)
        self.character_id = character_id
        self.archive_sha256 = archive_sha256
        self.genesis = genesis_digest(
            archive_sha256=archive_sha256, character_id=character_id
        )
        self._entries: list[dict[str, Any]] = []
        if self.path.exists():
            self._load()

    # ------------------------------------------------------------- storage

    def _load(self) -> None:
        info = self.path.lstat()
        if not stat.S_ISREG(info.st_mode):
            raise IdentityChainError("identity chain path is not a regular file")
        entries = []
        for line in self.path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                entries.append(json.loads(line))
            except ValueError as exc:
                raise IdentityChainError(f"chain contains invalid JSON: {exc}") from exc
        verify_chain(entries, genesis=self.genesis)
        self._entries = entries

    def _append_line(self, entry: dict[str, Any]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.path, "a", encoding="utf-8") as handle:
            handle.write(json.dumps(entry, sort_keys=True, separators=(",", ":")) + "\n")
            handle.flush()
            os.fsync(handle.fileno())

    # --------------------------------------------------------------- chain

    @property
    def head(self) -> str:
        """The character's identity right now."""
        return self._entries[-1]["entry_sha256"] if self._entries else self.genesis

    @property
    def length(self) -> int:
        return len(self._entries)

    def entries(self) -> list[dict[str, Any]]:
        return list(self._entries)

    def append(self, *, t: int, consciousness_state: Any, narrative: Any) -> dict[str, Any]:
        """Record one step of lived history. Returns the new entry."""
        entry = build_entry(
            prev=self.head,
            seq=self.length + 1,
            t=t,
            state_sha256=state_digest(consciousness_state),
            narrative=narrative,
        )
        self._append_line(entry)
        self._entries.append(entry)
        return entry

    def story(self, limit: int = 20) -> list[dict[str, Any]]:
        """The continuous story, newest last — what the character has become."""
        return [
            {
                "seq": entry["seq"],
                "t": entry["t"],
                "role": entry["narrative"]["role"],
                "scene": entry["narrative"]["scene"],
                "summary": entry["narrative"]["continuity_summary"],
            }
            for entry in self._entries[-limit:]
        ]


def verify_chain(entries: Iterable[dict[str, Any]], *, genesis: str) -> str:
    """Walk a chain and return its head, or fail closed.

    Detects an edited entry, a reordered entry, an excised entry, and an entry
    grafted from another character's chain.
    """

    prev = genesis
    seq = 0
    head = genesis
    for entry in entries:
        seq += 1
        if not isinstance(entry, dict) or set(entry) != _ENTRY_FIELDS:
            raise IdentityChainError(f"entry {seq} has unexpected fields")
        if entry.get("schema") != ENTRY_SCHEMA:
            raise IdentityChainError(f"entry {seq} has an unsupported schema")
        if entry.get("seq") != seq:
            raise IdentityChainError(
                f"entry out of order: expected seq {seq}, found {entry.get('seq')}"
            )
        if entry.get("prev") != prev:
            raise IdentityChainError(
                f"entry {seq} does not follow the previous entry (broken link)"
            )
        body = {key: value for key, value in entry.items() if key != "entry_sha256"}
        if _digest(_canonical(body)) != entry.get("entry_sha256"):
            raise IdentityChainError(f"entry {seq} has been modified")
        prev = head = entry["entry_sha256"]
    return head


def atomic_write_chain(path: Path | str, entries: Iterable[dict[str, Any]]) -> None:
    """Rewrite a chain file atomically (used by export, never by append)."""
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(dir=str(target.parent), prefix=".identity-")
    try:
        os.fchmod(fd, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            for entry in entries:
                handle.write(json.dumps(entry, sort_keys=True, separators=(",", ":")) + "\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, target)
    except BaseException:
        try:
            os.unlink(temporary)
        except OSError:
            pass
        raise
