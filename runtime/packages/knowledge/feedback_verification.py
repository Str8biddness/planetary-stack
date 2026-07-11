"""C-004: Feedback → verification bridge.

A user confirm/correction upgrades a linked memory item to VERIFIED.

Anti-collapse (auth boundary — Foreman lesson):
  Self-labeling ≠ authentication. Upgrade requires **positive proof of human
  origin**, not the mere absence of a bot marker. Deny-by-default.

  Required human proof (all must hold):
    1. actor_kind == "human"                         (allow-list)
    2. channel ∈ HUMAN_CHANNELS                       (allow-list)
    3. confirmed_by is a non-empty human identity     (not api-key / agent ids)
    4. human_attestation is a **server-issued** single-use token
       (issued only after a human-session secret is verified — agents with
       only an API key cannot mint these)

  Omitting bot markers while sending action=confirm is NOT enough.
"""

from __future__ import annotations

import logging
import os
import secrets
import time
from typing import Any, Callable, Mapping, MutableMapping, Optional, Sequence

try:
    from memory_provenance import (
        Provenance,
        Verification,
        annotate_metadata,
        gate,
    )
except ImportError:
    from knowledge.memory_provenance import (  # type: ignore
        Provenance,
        Verification,
        annotate_metadata,
        gate,
    )

logger = logging.getLogger(__name__)

# Ratings at or above this are treated as confirmation *intent* (not proof).
_CONFIRM_RATING_MIN = 4

# Allow-list: only these channels may promote memory (deny-by-default).
HUMAN_ACTOR_KIND = "human"
HUMAN_CHANNELS = frozenset(
    {
        "human_desktop_ui",
        "desktop_ui",
        "webos_user",
    }
)

# Identities / prefixes that are never accepted as confirmed_by (API key subjects, agents).
_BLOCKED_CONFIRMED_BY = frozenset(
    {
        "llm",
        "model",
        "system",
        "self",
        "agent",
        "api_key",
        "user_feedback",  # generic placeholder — not a human identity
    }
)
_BLOCKED_CONFIRMED_BY_PREFIXES = (
    "auth:",  # production_server get_auth key truncation
    "agent:",
    "api:",
    "ip:",
    "llm:",
    "model:",
)


class HumanAttestationStore:
    """Server-side single-use human attestation tokens (Foreman-style).

    Tokens are unguessable and only issued after the human-session secret is
    verified. An agent that can only self-label (action=confirm) cannot mint them.
    """

    def __init__(self) -> None:
        self._tokens: dict[str, dict[str, Any]] = {}

    def issue(
        self,
        *,
        human_id: str,
        channel: str,
        subject_key: Optional[str] = None,
        ttl_s: float = 600.0,
    ) -> str:
        channel_l = str(channel or "").lower()
        if channel_l not in HUMAN_CHANNELS:
            raise ValueError(f"channel not on human allow-list: {channel!r}")
        human_id = str(human_id or "").strip()
        if not human_id:
            raise ValueError("human_id is required to issue attestation")
        if not _is_acceptable_human_identity(human_id):
            raise ValueError(f"human_id is not an acceptable human identity: {human_id!r}")

        token = secrets.token_urlsafe(32)
        self._tokens[token] = {
            "human_id": human_id,
            "channel": channel_l,
            "subject_key": str(subject_key) if subject_key else None,
            "expires": time.time() + float(ttl_s),
            "issued_at": time.time(),
        }
        return token

    def peek(self, token: str) -> Optional[dict[str, Any]]:
        rec = self._tokens.get(token)
        if rec is None:
            return None
        if float(rec["expires"]) < time.time():
            self._tokens.pop(token, None)
            return None
        return dict(rec)

    def consume(
        self,
        token: str,
        *,
        subject_key: Optional[str] = None,
    ) -> Optional[dict[str, Any]]:
        """Consume a single-use attestation. Returns record or None if invalid."""
        if not token:
            return None
        rec = self._tokens.pop(str(token), None)
        if rec is None:
            return None
        if float(rec["expires"]) < time.time():
            return None
        bound = rec.get("subject_key")
        if bound is not None and subject_key is not None and str(bound) != str(subject_key):
            # Subject mismatch — do not re-insert (fail closed, token burned)
            logger.warning(
                "human attestation subject mismatch: bound=%s got=%s",
                bound,
                subject_key,
            )
            return None
        return rec

    def clear(self) -> None:
        self._tokens.clear()


# Process-local default store (C-005 wires the same instance).
_DEFAULT_ATTESTATION_STORE = HumanAttestationStore()


def get_default_attestation_store() -> HumanAttestationStore:
    return _DEFAULT_ATTESTATION_STORE


def human_session_secret_from_env() -> Optional[str]:
    """Shared secret known only to the human desktop UI + server.

    Agents that hold only the API key do not have this. If unconfigured, all
    upgrades fail closed (DEGRADED — no silent forge path).
    """
    val = os.environ.get("SYNTHESUS_HUMAN_SESSION_SECRET", "").strip()
    return val or None


def verify_human_session_secret(
    provided: Optional[str],
    *,
    expected: Optional[str] = None,
) -> bool:
    """Constant-time compare of the human-session secret."""
    exp = expected if expected is not None else human_session_secret_from_env()
    if not exp or not provided:
        return False
    try:
        return secrets.compare_digest(str(provided), str(exp))
    except (TypeError, ValueError):
        return False


def issue_human_attestation(
    *,
    human_id: str,
    channel: str,
    subject_key: Optional[str] = None,
    human_session_proof: Optional[str] = None,
    store: Optional[HumanAttestationStore] = None,
    expected_secret: Optional[str] = None,
    ttl_s: float = 600.0,
) -> dict[str, Any]:
    """Issue a single-use attestation after verifying the human-session secret.

    Returns {issued: bool, reason, human_attestation?}.
    """
    if not verify_human_session_secret(human_session_proof, expected=expected_secret):
        logger.info("attestation issue refused: invalid or missing human session proof")
        return {
            "issued": False,
            "reason": "invalid_human_session_proof",
            "human_attestation": None,
        }
    reg = store or _DEFAULT_ATTESTATION_STORE
    try:
        token = reg.issue(
            human_id=human_id,
            channel=channel,
            subject_key=subject_key,
            ttl_s=ttl_s,
        )
    except ValueError as exc:
        return {
            "issued": False,
            "reason": str(exc),
            "human_attestation": None,
        }
    return {
        "issued": True,
        "reason": "ok",
        "human_attestation": token,
        "channel": str(channel).lower(),
        "human_id": human_id,
        "subject_key": subject_key,
    }


def _is_acceptable_human_identity(value: str) -> bool:
    v = str(value or "").strip()
    if not v:
        return False
    low = v.lower()
    if low in _BLOCKED_CONFIRMED_BY:
        return False
    for prefix in _BLOCKED_CONFIRMED_BY_PREFIXES:
        if low.startswith(prefix):
            return False
    return True


def _is_confirm_intent(feedback_event: Mapping[str, Any]) -> bool:
    """Whether the event *claims* confirm/correct intent. Not human proof."""
    action = str(feedback_event.get("action") or feedback_event.get("type") or "").lower()
    if action in {"confirm", "confirmed", "correction", "correct", "thumbs_up", "accept"}:
        return True
    if feedback_event.get("corrected_text") or feedback_event.get("correction"):
        return True
    rating = feedback_event.get("rating")
    if rating is not None:
        try:
            if int(rating) >= _CONFIRM_RATING_MIN:
                return True
        except (TypeError, ValueError):
            pass
    if feedback_event.get("confirmed") is True:
        return True
    return False


def _subject_key_from_event(feedback_event: Mapping[str, Any]) -> Optional[str]:
    for key in ("memory_id", "answer_id", "item_id", "trace_id", "id"):
        val = feedback_event.get(key)
        if val is not None and str(val).strip():
            return str(val)
    return None


def verify_human_confirm_proof(
    feedback_event: Mapping[str, Any],
    *,
    store: Optional[HumanAttestationStore] = None,
    consume: bool = False,
) -> tuple[bool, str, Optional[dict[str, Any]]]:
    """Deny-by-default human proof check (positive allow-list + server token).

    Returns (ok, reason, attestation_record_or_none).

    When consume=True and proof is valid, the attestation token is burned
    (single-use). Callers that only probe should pass consume=False.
    """
    if not isinstance(feedback_event, Mapping) or not feedback_event:
        return False, "empty_event", None

    # Explicit bot / self markers still hard-fail (belt + suspenders).
    if feedback_event.get("self_triggered") or feedback_event.get("source") == "self":
        return False, "self_triggered_refused", None
    if feedback_event.get("origin") in {"llm", "llm_generation", "model", "agent"}:
        return False, "model_origin_refused", None

    # --- Positive allow-list (invert polarity) ---
    actor_kind = str(feedback_event.get("actor_kind") or "").lower()
    if actor_kind != HUMAN_ACTOR_KIND:
        return False, "missing_human_actor_kind", None

    channel = str(feedback_event.get("channel") or feedback_event.get("ui_channel") or "").lower()
    if channel not in HUMAN_CHANNELS:
        return False, "channel_not_human_allowlisted", None

    confirmed_by = str(
        feedback_event.get("confirmed_by")
        or feedback_event.get("human_id")
        or ""
    ).strip()
    if not _is_acceptable_human_identity(confirmed_by):
        return False, "missing_or_invalid_confirmed_by", None

    if not _is_confirm_intent(feedback_event):
        return False, "not_confirm_intent", None

    # Server-issued single-use attestation — not a self-label.
    token = feedback_event.get("human_attestation") or feedback_event.get("attestation")
    if not token:
        return False, "missing_human_attestation", None

    reg = store or _DEFAULT_ATTESTATION_STORE
    subject = _subject_key_from_event(feedback_event)
    if consume:
        rec = reg.consume(str(token), subject_key=subject)
    else:
        rec = reg.peek(str(token))
        if rec is not None and rec.get("subject_key") is not None and subject is not None:
            if str(rec["subject_key"]) != str(subject):
                rec = None

    if rec is None:
        return False, "invalid_or_consumed_human_attestation", None

    # Attestation channel / human_id must match the event claims.
    if rec.get("channel") != channel:
        return False, "attestation_channel_mismatch", None
    if str(rec.get("human_id") or "") != confirmed_by:
        return False, "attestation_human_mismatch", None

    return True, "human_confirmed", rec


# Back-compat name used in older call sites / docs — now deny-by-default.
def _event_is_external_confirm(
    feedback_event: Mapping[str, Any],
    *,
    store: Optional[HumanAttestationStore] = None,
) -> bool:
    ok, _reason, _rec = verify_human_confirm_proof(
        feedback_event, store=store, consume=False
    )
    return ok


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
    if "metadata" in item and isinstance(item["metadata"], dict):
        return item["metadata"]
    return item


def _apply_verified_fields(
    item: MutableMapping[str, Any],
    *,
    confirmed_by: str,
    corrected_text: Optional[str] = None,
    channel: Optional[str] = None,
) -> MutableMapping[str, Any]:
    """Mutate item to USER_CONFIRMED / VERIFIED. Human proof required (caller)."""
    meta = _item_metadata_view(item)
    now = time.time()
    annotate_metadata(
        meta,
        provenance=Provenance.USER_CONFIRMED,
        provenance_refs=list(meta.get("provenance_refs") or item.get("provenance_refs") or []),
        origin_voice=meta.get("origin_voice", item.get("origin_voice")),
        created_ts=meta.get("created_ts") or item.get("created_ts") or now,
        confirmed_ts=now,
        confirmed_by=confirmed_by,
        verification=Verification.VERIFIED,
    )
    item["provenance"] = Provenance.USER_CONFIRMED.value
    item["verification"] = int(Verification.VERIFIED)
    item["confirmed_ts"] = now
    item["confirmed_by"] = confirmed_by
    if channel:
        meta["confirm_channel"] = channel
        item["confirm_channel"] = channel

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
    attestation_store: Optional[HumanAttestationStore] = None,
) -> dict[str, Any]:
    """Upgrade a linked memory item to VERIFIED from a human-proven feedback event.

    Deny-by-default: requires human actor_kind, allow-listed channel, human
    confirmed_by identity, and a server-issued single-use human_attestation.
    Mere action=confirm / high rating / API-key auth is NOT sufficient.
    """
    store = attestation_store or _DEFAULT_ATTESTATION_STORE

    # Probe first (don't consume yet) so we can fail before burning a token on
    # item-not-found — actually for security we should consume on any attempt
    # that presents a token to prevent replay after probing. Consume only after
    # intent+labels pass but regardless of item find, to stop token farming.
    ok, reason, _preview = verify_human_confirm_proof(
        feedback_event, store=store, consume=False
    )
    if not ok:
        logger.info("feedback_verification refused: %s", reason)
        return {
            "upgraded": False,
            "reason": reason,
            "item_id": None,
            "provenance": None,
            "verification": None,
        }

    # Consume the single-use attestation now (replay-proof).
    ok2, reason2, att_rec = verify_human_confirm_proof(
        feedback_event, store=store, consume=True
    )
    if not ok2 or att_rec is None:
        logger.info("feedback_verification refused on consume: %s", reason2)
        return {
            "upgraded": False,
            "reason": reason2,
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
            "item_id": feedback_event.get("memory_id")
            or feedback_event.get("answer_id")
            or feedback_event.get("trace_id"),
            "provenance": None,
            "verification": None,
        }

    # Prefer identity bound in the server-issued attestation over caller args.
    actor = (
        str(att_rec.get("human_id") or "").strip()
        or str(feedback_event.get("confirmed_by") or "").strip()
        or (str(confirmed_by).strip() if confirmed_by else "")
    )
    if not _is_acceptable_human_identity(actor):
        return {
            "upgraded": False,
            "reason": "missing_or_invalid_confirmed_by",
            "item_id": target.get("id"),
            "provenance": None,
            "verification": None,
        }

    correction = _corrected_text(feedback_event) if _is_correction(feedback_event) else None
    channel = str(att_rec.get("channel") or feedback_event.get("channel") or "")
    _apply_verified_fields(
        target,
        confirmed_by=actor,
        corrected_text=correction,
        channel=channel or None,
    )

    persist = getattr(target, "save", None)
    if callable(persist):
        persist()

    item_id = (
        target.get("id")
        or target.get("memory_id")
        or target.get("item_id")
        or feedback_event.get("memory_id")
        or feedback_event.get("answer_id")
        or feedback_event.get("trace_id")
    )

    may, tier = gate(target if "provenance" in target else _item_metadata_view(target))
    if not (may is True and tier is Verification.VERIFIED):
        # Should be unreachable if annotate set USER_CONFIRMED; fail closed.
        logger.error("post-upgrade gate invariant failed may=%s tier=%s", may, tier)
        return {
            "upgraded": False,
            "reason": "post_upgrade_gate_failed",
            "item_id": item_id,
            "provenance": target.get("provenance"),
            "verification": target.get("verification"),
        }

    return {
        "upgraded": True,
        "reason": "user_confirmed" if correction is None else "user_corrected",
        "item_id": item_id,
        "provenance": Provenance.USER_CONFIRMED.value,
        "verification": int(Verification.VERIFIED),
        "corrected": correction is not None,
        "confirmed_by": actor,
        "channel": channel or None,
        "confirmed_ts": target.get("confirmed_ts")
        or _item_metadata_view(target).get("confirmed_ts"),
    }


def assert_no_self_promotion(item: Mapping[str, Any]) -> bool:
    """Return True if item is still not VERIFIED under LLM_GENERATION provenance."""
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
    "HUMAN_ACTOR_KIND",
    "HUMAN_CHANNELS",
    "HumanAttestationStore",
    "get_default_attestation_store",
    "human_session_secret_from_env",
    "verify_human_session_secret",
    "issue_human_attestation",
    "verify_human_confirm_proof",
    "upgrade_from_feedback",
    "assert_no_self_promotion",
]
