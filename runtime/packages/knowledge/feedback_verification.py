"""C-004: Feedback → verification bridge.

A user confirm/correction upgrades a linked memory item to VERIFIED.
Only a real external event (feedback_event) may trigger the upgrade —
there is no self-promotion path from LLM_GENERATION to VERIFIED.
"""

from __future__ import annotations

import logging
import time
from typing import Any, Callable, Mapping, MutableMapping, Optional, Sequence

try:
    from memory_provenance import (
        Provenance,
        Verification,
        annotate_metadata,
        classify,
        gate,
    )
except ImportError:
    from knowledge.memory_provenance import (  # type: ignore
        Provenance,
        Verification,
        annotate_metadata,
        classify,
        gate,
    )

logger = logging.getLogger(__name__)

# Ratings at or above this are treated as confirmations when no explicit action.
_CONFIRM_RATING_MIN = 4


def _event_is_external_confirm(feedback_event: Mapping[str, Any]) -> bool:
    """True only when the event is a real external confirmation/correction.

    Reject empty events, self-triggered synthetic events, and non-confirm ratings.
    """
    if not isinstance(feedback_event, Mapping) or not feedback_event:
        return False

    # Explicit self-trigger markers are refused (anti-collapse).
    if feedback_event.get("self_triggered") or feedback_event.get("source") == "self":
        return False
    if feedback_event.get("origin") in {"llm", "llm_generation", "model"}:
        return False

    action = str(feedback_event.get("action") or feedback_event.get("type") or "").lower()
    if action in {"confirm", "confirmed", "correction", "correct", "thumbs_up", "accept"}:
        return True

    if feedback_event.get("corrected_text") or feedback_event.get("correction"):
        return True

    rating = feedback_event.get("rating")
    if rating is not None:
        try:
            return int(rating) >= _CONFIRM_RATING_MIN
        except (TypeError, ValueError):
            return False

    # Explicit boolean flag from API adapters
    if feedback_event.get("confirmed") is True:
        return True

    return False


def _is_correction(feedback_event: Mapping[str, Any]) -> bool:
    action = str(feedback_event.get("action") or feedback_event.get("type") or "").lower()
    if action in {"correction", "correct"}:
        return True
    return bool(feedback_event.get("corrected_text") or feedback_event.get("correction"))


def _corrected_text(feedback_event: Mapping[str, Any]) -> Optional[str]:
    text = feedback_event.get("corrected_text") or feedback_event.get("correction")
    if text is None:
        return None
    text = str(text).strip()
    return text or None


def _match_item(item: Mapping[str, Any], feedback_event: Mapping[str, Any]) -> bool:
    """Locate a memory item by answer/trace/memory id or response text."""
    for key in ("memory_id", "item_id", "id"):
        event_id = feedback_event.get(key)
        item_id = item.get(key) or item.get("memory_id") or item.get("id")
        if event_id is not None and item_id is not None and str(event_id) == str(item_id):
            return True

    for key in ("trace_id", "answer_id"):
        event_val = feedback_event.get(key)
        if event_val is None:
            continue
        item_val = item.get(key)
        if item_val is None and isinstance(item.get("metadata"), Mapping):
            item_val = item["metadata"].get(key)
        if item_val is not None and str(item_val) == str(event_val):
            return True
        # tags may carry trace:<id>
        tags = item.get("tags") or []
        if isinstance(tags, list) and f"trace:{event_val}" in tags:
            return True

    response = feedback_event.get("response") or feedback_event.get("answer")
    if response:
        content = item.get("content") or item.get("response") or item.get("pattern") or ""
        if str(response).strip() and str(response).strip() in str(content):
            return True

    return False


def _item_metadata_view(item: MutableMapping[str, Any]) -> MutableMapping[str, Any]:
    """Return the mutable metadata dict for an item (creates if needed)."""
    if "metadata" in item and isinstance(item["metadata"], dict):
        return item["metadata"]
    # Flat metadata style (RAG pattern dicts)
    return item


def _apply_verified_fields(
    item: MutableMapping[str, Any],
    *,
    confirmed_by: Optional[str],
    corrected_text: Optional[str] = None,
) -> MutableMapping[str, Any]:
    """Mutate item to USER_CONFIRMED / VERIFIED. External event required (caller)."""
    meta = _item_metadata_view(item)
    now = time.time()
    annotate_metadata(
        meta,
        provenance=Provenance.USER_CONFIRMED,
        provenance_refs=list(meta.get("provenance_refs") or item.get("provenance_refs") or []),
        origin_voice=meta.get("origin_voice", item.get("origin_voice")),
        created_ts=meta.get("created_ts") or item.get("created_ts") or now,
        confirmed_ts=now,
        confirmed_by=confirmed_by or "user_feedback",
        verification=Verification.VERIFIED,
    )
    # Mirror authoritative fields on the item root for RAG-style dicts.
    item["provenance"] = Provenance.USER_CONFIRMED.value
    item["verification"] = int(Verification.VERIFIED)
    item["confirmed_ts"] = now
    item["confirmed_by"] = confirmed_by or "user_feedback"

    if corrected_text is not None:
        if "content" in item:
            item["content"] = corrected_text
        if "response" in item:
            item["response"] = corrected_text
        meta["corrected_text"] = corrected_text
        meta["content_corrected"] = True

    return item


def upgrade_from_feedback(
    feedback_event: Mapping[str, Any],
    *,
    items: Optional[Sequence[MutableMapping[str, Any]]] = None,
    find_item: Optional[Callable[[Mapping[str, Any]], Optional[MutableMapping[str, Any]]]] = None,
    confirmed_by: Optional[str] = None,
) -> dict[str, Any]:
    """Upgrade a linked memory item to VERIFIED from a real feedback event.

    Parameters
    ----------
    feedback_event:
        External user feedback. Must be a confirm/correction (rating>=4, action,
        or corrected_text). Self-triggered / model-origin events are rejected.
    items:
        Optional sequence of mutable memory/pattern dicts to search.
    find_item:
        Optional locator callback; used when items is not provided or as a
        priority lookup (e.g. MemoryStore.get).
    confirmed_by:
        Optional actor id (API auth subject).

    Returns
    -------
    dict with upgraded, reason, item_id, provenance, verification, ...
    """
    if not _event_is_external_confirm(feedback_event):
        logger.info(
            "feedback_verification refused: not an external confirm/correction event"
        )
        return {
            "upgraded": False,
            "reason": "not_external_confirm_event",
            "item_id": None,
            "provenance": None,
            "verification": None,
        }

    target: Optional[MutableMapping[str, Any]] = None
    if find_item is not None:
        try:
            target = find_item(feedback_event)
        except Exception as exc:
            logger.warning("feedback find_item failed: %s", exc)
            target = None

    if target is None and items is not None:
        for item in items:
            if isinstance(item, MutableMapping) and _match_item(item, feedback_event):
                target = item
                break

    if target is None:
        return {
            "upgraded": False,
            "reason": "item_not_found",
            "item_id": feedback_event.get("memory_id") or feedback_event.get("trace_id"),
            "provenance": None,
            "verification": None,
        }

    # Anti-collapse double-check: never allow a path that sets VERIFIED without
    # going through USER_CONFIRMED provenance (this function is that path, and
    # it requires an external event — already checked above).
    correction = _corrected_text(feedback_event) if _is_correction(feedback_event) else None
    actor = confirmed_by or feedback_event.get("confirmed_by") or feedback_event.get("auth")
    _apply_verified_fields(target, confirmed_by=str(actor) if actor else "user_feedback", corrected_text=correction)

    # Optional persistence hook on store-like objects attached to the item.
    persist = getattr(target, "save", None)
    if callable(persist):
        persist()

    item_id = (
        target.get("id")
        or target.get("memory_id")
        or target.get("item_id")
        or feedback_event.get("memory_id")
        or feedback_event.get("trace_id")
    )

    # Prove the gate now admits this item as long-term (USER_CONFIRMED → VERIFIED).
    may, tier = gate(target if "provenance" in target else _item_metadata_view(target))
    assert may is True and tier is Verification.VERIFIED  # invariant of this path

    return {
        "upgraded": True,
        "reason": "user_confirmed" if correction is None else "user_corrected",
        "item_id": item_id,
        "provenance": Provenance.USER_CONFIRMED.value,
        "verification": int(Verification.VERIFIED),
        "corrected": correction is not None,
        "confirmed_by": str(actor) if actor else "user_feedback",
        "confirmed_ts": target.get("confirmed_ts") or _item_metadata_view(target).get("confirmed_ts"),
    }


def assert_no_self_promotion(item: Mapping[str, Any]) -> bool:
    """Return True if item is still not VERIFIED under LLM_GENERATION provenance.

    Helper for adversarial tests: a raw generation must not appear verified.
    """
    prov = str(item.get("provenance") or "")
    if isinstance(item.get("metadata"), Mapping):
        prov = prov or str(item["metadata"].get("provenance") or "")
    ver = item.get("verification")
    if ver is None and isinstance(item.get("metadata"), Mapping):
        ver = item["metadata"].get("verification")
    if prov == Provenance.LLM_GENERATION.value:
        return int(ver or 0) == int(Verification.UNVERIFIED)
    return True


__all__ = [
    "upgrade_from_feedback",
    "assert_no_self_promotion",
]
