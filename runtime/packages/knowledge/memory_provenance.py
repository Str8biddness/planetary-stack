"""Provenance + verification contract for crystallized memory (Mc).

Frozen contract C-001. Read-only after Phase 0.

Anti-collapse law: an LLM_GENERATION may never crystallize to long-term Mc as a
fact, and may never become VERIFIED without an external event (user confirmation
or grounding against real user sources).
"""

from __future__ import annotations

from enum import Enum
from typing import Any, Mapping, MutableMapping, Optional, Sequence, Union


class Provenance(str, Enum):
    """WHERE a memory item came from."""

    USER_DOCUMENT = "user_document"  # ingested from the user's files (the drive)
    USER_STATED = "user_stated"  # a fact the user typed/asserted
    USER_CONFIRMED = "user_confirmed"  # an answer the user explicitly confirmed
    GROUNDED_CITED = "grounded_cited"  # derived from + citing real user sources
    LLM_GENERATION = "llm_generation"  # raw model output — a DRAFT, not knowledge


class Verification(int, Enum):
    """HOW trustworthy (higher = more trusted)."""

    UNVERIFIED = 0  # llm_generation, no external check
    GROUNDED = 1  # derived from real sources, traceable
    VERIFIED = 2  # externally confirmed (user doc / user stated / user confirmed)


VERIFICATION_WEIGHT: dict[Verification, float] = {
    Verification.VERIFIED: 1.0,
    Verification.GROUNDED: 0.7,
    Verification.UNVERIFIED: 0.3,
}

# Provenance values that are USER_* (externally originated).
_USER_PROVENANCES = frozenset(
    {
        Provenance.USER_DOCUMENT,
        Provenance.USER_STATED,
        Provenance.USER_CONFIRMED,
    }
)


def _coerce_provenance(value: Any) -> Provenance:
    """Parse a provenance value; unknown/missing → LLM_GENERATION (least trusted)."""
    if isinstance(value, Provenance):
        return value
    if value is None:
        return Provenance.LLM_GENERATION
    try:
        return Provenance(str(value))
    except ValueError:
        return Provenance.LLM_GENERATION


def _coerce_verification(value: Any) -> Optional[Verification]:
    if isinstance(value, Verification):
        return value
    if value is None:
        return None
    try:
        return Verification(int(value))
    except (TypeError, ValueError):
        return None


def classify(provenance: Union[Provenance, str]) -> Verification:
    """Map provenance → default verification tier.

    USER_* → VERIFIED
    GROUNDED_CITED → GROUNDED
    LLM_GENERATION → UNVERIFIED
    """
    prov = _coerce_provenance(provenance)
    if prov in _USER_PROVENANCES:
        return Verification.VERIFIED
    if prov is Provenance.GROUNDED_CITED:
        return Verification.GROUNDED
    return Verification.UNVERIFIED


def gate(item: Mapping[str, Any]) -> tuple[bool, Verification]:
    """Crystallization gate. Returns (may_crystallize_to_longterm, tier).

    GATE LAW: LLM_GENERATION may NEVER be crystallized to long-term Mc as a fact
    (returns False). Only VERIFIED and GROUNDED persist. UNVERIFIED is session-only.
    """
    if not isinstance(item, Mapping):
        return False, Verification.UNVERIFIED

    prov = _coerce_provenance(item.get("provenance"))
    tier = _coerce_verification(item.get("verification"))
    if tier is None:
        tier = classify(prov)

    # Anti-collapse: raw model output is never long-term Mc, regardless of any
    # caller-supplied verification tier. Tier is forced to UNVERIFIED.
    if prov is Provenance.LLM_GENERATION:
        return False, Verification.UNVERIFIED

    # Only VERIFIED and GROUNDED may crystallize.
    if tier is Verification.UNVERIFIED:
        return False, tier

    return True, tier


def annotate_metadata(
    meta: MutableMapping[str, Any],
    *,
    provenance: Union[Provenance, str],
    provenance_refs: Optional[Sequence[str]] = None,
    origin_voice: Optional[str] = None,
    created_ts: Optional[float] = None,
    confirmed_ts: Optional[float] = None,
    confirmed_by: Optional[str] = None,
    verification: Optional[Union[Verification, int]] = None,
) -> MutableMapping[str, Any]:
    """Write provenance/verification fields onto a memory metadata dict.

    Does not invent verification for LLM_GENERATION beyond UNVERIFIED.
    """
    import time as _time

    prov = _coerce_provenance(provenance)
    if prov is Provenance.LLM_GENERATION:
        tier = Verification.UNVERIFIED
    elif verification is not None:
        tier = _coerce_verification(verification) or classify(prov)
        # Never allow a non-LLM provenance to be labeled with a higher tier than
        # classify() without an external path; callers that already have
        # USER_CONFIRMED use classify which yields VERIFIED.
        if tier is Verification.VERIFIED and prov not in _USER_PROVENANCES:
            # Grounded items stay grounded unless provenance is a USER_* type.
            tier = classify(prov)
    else:
        tier = classify(prov)

    meta["provenance"] = prov.value
    meta["verification"] = int(tier)
    meta["provenance_refs"] = list(provenance_refs or meta.get("provenance_refs") or [])
    if origin_voice is not None:
        meta["origin_voice"] = origin_voice
    elif "origin_voice" not in meta:
        meta["origin_voice"] = None
    meta["created_ts"] = float(created_ts if created_ts is not None else meta.get("created_ts") or _time.time())
    if confirmed_ts is not None:
        meta["confirmed_ts"] = float(confirmed_ts)
    elif "confirmed_ts" not in meta:
        meta["confirmed_ts"] = None
    if confirmed_by is not None:
        meta["confirmed_by"] = confirmed_by
    elif "confirmed_by" not in meta:
        meta["confirmed_by"] = None
    return meta


def resolve_legacy_metadata(meta: Mapping[str, Any]) -> tuple[Provenance, Verification]:
    """Backward-compatible defaults for pre-provenance metadata.

    - Explicit fields win when present and valid.
    - Ingested user docs (domain/namespace user_docs) → USER_DOCUMENT / VERIFIED.
    - Other legacy items with a source path → GROUNDED_CITED / GROUNDED.
    - Unknown legacy → GROUNDED_CITED / GROUNDED so existing corpora keep loading
      without claiming VERIFIED without an external signal.
    """
    if meta.get("provenance") is not None:
        prov = _coerce_provenance(meta.get("provenance"))
        tier = _coerce_verification(meta.get("verification"))
        if tier is None:
            tier = classify(prov)
        # Enforce anti-collapse even on legacy/corrupt rows.
        if prov is Provenance.LLM_GENERATION:
            return Provenance.LLM_GENERATION, Verification.UNVERIFIED
        return prov, tier

    domain = str(meta.get("domain") or "")
    namespace = str(meta.get("namespace") or "")
    if domain == "user_docs" or namespace == "user_docs" or namespace.startswith("user_docs"):
        return Provenance.USER_DOCUMENT, Verification.VERIFIED

    # Existing index items predate this contract; treat as grounded (not verified).
    return Provenance.GROUNDED_CITED, Verification.GROUNDED


def weight_for(meta_or_tier: Any) -> float:
    """Return retrieval weight for a verification tier or metadata dict."""
    if isinstance(meta_or_tier, Verification):
        return VERIFICATION_WEIGHT[meta_or_tier]
    if isinstance(meta_or_tier, Mapping):
        _, tier = resolve_legacy_metadata(meta_or_tier)
        return VERIFICATION_WEIGHT[tier]
    tier = _coerce_verification(meta_or_tier)
    if tier is None:
        return VERIFICATION_WEIGHT[Verification.UNVERIFIED]
    return VERIFICATION_WEIGHT[tier]


__all__ = [
    "Provenance",
    "Verification",
    "VERIFICATION_WEIGHT",
    "classify",
    "gate",
    "annotate_metadata",
    "resolve_legacy_metadata",
    "weight_for",
]
