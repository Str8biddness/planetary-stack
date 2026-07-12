#!/usr/bin/env python3
"""
Utterance plan compiler for SI formant speech — mirror of image scene_plan.

LLM/rules produce a *recipe* (phones, stress, rate, F0 knobs).
Formant engine executes. No neural TTS, no audio from the LLM.

Plan schema (v1):
  {
    "version": "utterance-plan-v1",
    "source_text": "...",
    "words": [{"orth": "hello", "phones": ["HH","EH","L","OW"], "stress": 1, "dur_scale": 1.0}],
    "f0_base_hz": 150,
    "f0_end_hz": 170,
    "rate": 0.85,
    "f2_stretch": 1.1,
    "rising_final": true,
    "transition_s": 0.04,
    "amp": 0.9,
    "pauses_ms": [0, 180],
    "style": "clear_robotic",
    "source": "rules" | "llm+rules",
    "monologue": "...",
    "outer_voice": "...",
    "not_neural_tts": true
  }
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import urllib.error
import urllib.request
from typing import Any, List, Optional, Sequence

from formant_engine import PHONE_DB, get_phone
from formant_g2p import text_to_phonemes, word_to_phonemes

PLAN_VERSION = "utterance-plan-v1"
ALLOWED_PHONES = frozenset(k for k in PHONE_DB.keys() if k == k.upper() and not k[-1:].isdigit())
# also allow SIL markers
ALLOWED_PHONES = ALLOWED_PHONES | frozenset({"SIL", "SIL_LONG"})

CONTENT_STRESS = frozenset({
    "hello", "world", "quick", "brown", "fox", "speak", "speech", "voice",
    "synthesus", "kernel", "sovereign", "formant", "system", "computer",
})
FUNCTION_WORDS = frozenset({
    "a", "an", "the", "to", "of", "and", "or", "for", "in", "on", "at",
    "is", "are", "was", "were", "be", "am", "do", "does", "did", "not",
    "with", "from", "by", "as", "it", "its", "that", "this", "these", "those",
})


def validate_phone(p: str) -> Optional[str]:
    n = re.sub(r"\d", "", (p or "").upper().strip())
    if n in ALLOWED_PHONES or n in PHONE_DB:
        return n
    return None


def validate_phones(phones: Sequence[str]) -> List[str]:
    out = []
    for p in phones:
        v = validate_phone(p)
        if v:
            out.append(v)
    return out


def _stress_for(orth: str, phones: List[str]) -> int:
    w = orth.lower()
    if w in FUNCTION_WORDS:
        return 0
    if w in CONTENT_STRESS:
        return 1
    # default: stress if has vowel and length > 2
    vowels = {"IY", "IH", "EH", "AE", "AA", "AH", "AO", "UH", "UW", "ER", "AX",
              "EY", "AY", "OW", "AW", "OY"}
    if any(p in vowels for p in phones) and len(w) > 2:
        return 1
    return 0


def _dur_scale_for(stress: int, orth: str) -> float:
    if orth.lower() in FUNCTION_WORDS:
        return 0.78
    if stress >= 1:
        return 1.15
    return 1.0


def compile_utterance_plan_rules(
    text: str,
    *,
    accent: Optional[dict] = None,
    geometric_prosody: Optional[dict] = None,
) -> dict[str, Any]:
    """Deterministic offline plan from G2P + stress heuristics."""
    text = (text or "").strip()
    accent = accent or {}
    geo = geometric_prosody or {}
    steps = ["parse text → words → ARPABET via formant_g2p"]
    words_out: List[dict[str, Any]] = []
    pauses_ms: List[int] = []

    parts = text_to_phonemes(text)
    for orth, ph in parts:
        if orth in (".", ","):
            pauses_ms.append(220 if orth == "." else 120)
            continue
        phones = validate_phones(ph)
        if not phones:
            steps.append(f"drop empty phones for {orth!r}")
            continue
        stress = _stress_for(orth, phones)
        ds = _dur_scale_for(stress, orth)
        words_out.append({
            "orth": orth,
            "phones": phones,
            "stress": stress,
            "dur_scale": round(ds, 3),
            "how": "g2p_rules",
        })
        pauses_ms.append(160 if stress else 110)
        steps.append(f"{orth} → {' '.join(phones)} stress={stress}")

    # trailing pause trim — pauses_ms is after each word; last is inter-word only
    if pauses_ms:
        pauses_ms = [0] + pauses_ms[:-1]

    f0_base = float(geo.get("f0_base") or accent.get("f0_base") or 155.0)
    rising = float(accent.get("rising_inflection") or 1.12)
    f0_end = float(geo.get("f0_end") or f0_base * rising)
    rate = float(geo.get("dur_scale") or accent.get("rate") or 0.82)
    f2 = float(geo.get("f2_stretch") or (1.0 + float(accent.get("wide_vowels") or 0.1)))
    transition = float(geo.get("transition") or (0.025 + 0.04 * float(accent.get("legato_bias") or 0.55)))
    amp = float(geo.get("amp") or 0.9)

    monologue = (
        f"Inner: speak {text!r} via SI formant engine (not neural TTS). "
        f"{len(words_out)} words, rate={rate:.2f}, F0={f0_base:.0f}→{f0_end:.0f} Hz, "
        f"F2_stretch={f2:.2f}."
    )
    outer = (
        "SI formant speech (robotic but intended intelligible). "
        "Not natural TTS; not a neural voice model."
    )

    plan = {
        "version": PLAN_VERSION,
        "source_text": text,
        "words": words_out,
        "f0_base_hz": f0_base,
        "f0_end_hz": f0_end,
        "rate": rate,
        "f2_stretch": f2,
        "rising_final": rising > 1.05,
        "transition_s": transition,
        "amp": amp,
        "pauses_ms": pauses_ms,
        "style": "clear_robotic",
        "source": "rules",
        "compile_steps": steps,
        "monologue": monologue,
        "outer_voice": outer,
        "honesty": "si_formant",
        "not_neural_tts": True,
        "stock": "utterance_plan",
        "llm_status": "skipped",
    }
    return plan


def plan_fingerprint(plan: dict[str, Any]) -> str:
    raw = json.dumps(
        {
            "v": plan.get("version"),
            "t": plan.get("source_text"),
            "w": [
                (w.get("orth"), w.get("phones"), w.get("stress"), w.get("dur_scale"))
                for w in plan.get("words") or []
            ],
            "f0": (plan.get("f0_base_hz"), plan.get("f0_end_hz")),
            "rate": plan.get("rate"),
            "f2": plan.get("f2_stretch"),
            "p": plan.get("pauses_ms"),
        },
        sort_keys=True,
    )
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


def public_plan_view(plan: dict[str, Any]) -> dict[str, Any]:
    return {
        "version": plan.get("version"),
        "source_text": plan.get("source_text"),
        "word_count": len(plan.get("words") or []),
        "words": [
            {
                "orth": w.get("orth"),
                "phones": w.get("phones"),
                "stress": w.get("stress"),
                "dur_scale": w.get("dur_scale"),
            }
            for w in (plan.get("words") or [])
        ],
        "f0_base_hz": plan.get("f0_base_hz"),
        "f0_end_hz": plan.get("f0_end_hz"),
        "rate": plan.get("rate"),
        "f2_stretch": plan.get("f2_stretch"),
        "pauses_ms": plan.get("pauses_ms"),
        "source": plan.get("source"),
        "llm_status": plan.get("llm_status"),
        "outer_voice": plan.get("outer_voice"),
        "monologue": plan.get("monologue"),
        "fingerprint": plan_fingerprint(plan),
        "not_neural_tts": True,
        "stock": "utterance_plan",
    }


def apply_pass_knobs(plan: dict[str, Any], knobs: dict[str, Any]) -> dict[str, Any]:
    """Multi-pass: mutate prosody knobs without re-G2P (unless replan phones)."""
    p = dict(plan)
    p["words"] = [dict(w) for w in (plan.get("words") or [])]
    knobs = knobs or {}
    if knobs.get("rate") is not None:
        p["rate"] = float(np_clip(float(knobs["rate"]), 0.5, 1.6))
    if knobs.get("dur_scale") is not None:
        p["rate"] = float(np_clip(float(knobs["dur_scale"]), 0.5, 1.6))
    if knobs.get("slower"):
        p["rate"] = float(np_clip(float(p.get("rate") or 1.0) * 0.85, 0.5, 1.6))
    if knobs.get("faster"):
        p["rate"] = float(np_clip(float(p.get("rate") or 1.0) * 1.15, 0.5, 1.6))
    if knobs.get("f0_base_hz") is not None:
        p["f0_base_hz"] = float(np_clip(float(knobs["f0_base_hz"]), 80, 280))
    if knobs.get("f0_end_hz") is not None:
        p["f0_end_hz"] = float(np_clip(float(knobs["f0_end_hz"]), 80, 320))
    if knobs.get("higher") or knobs.get("pitch_up"):
        p["f0_base_hz"] = float(p.get("f0_base_hz") or 150) * 1.12
        p["f0_end_hz"] = float(p.get("f0_end_hz") or 160) * 1.12
    if knobs.get("lower") or knobs.get("pitch_down"):
        p["f0_base_hz"] = float(p.get("f0_base_hz") or 150) * 0.9
        p["f0_end_hz"] = float(p.get("f0_end_hz") or 160) * 0.9
    if knobs.get("rising_final") is not None:
        p["rising_final"] = bool(knobs["rising_final"])
        if p["rising_final"]:
            p["f0_end_hz"] = float(p.get("f0_base_hz") or 150) * 1.15
    if knobs.get("f2_stretch") is not None:
        p["f2_stretch"] = float(np_clip(float(knobs["f2_stretch"]), 0.85, 1.4))
    if knobs.get("wide_vowels") is not None:
        p["f2_stretch"] = 1.0 + float(knobs["wide_vowels"])
    if knobs.get("amp") is not None:
        p["amp"] = float(np_clip(float(knobs["amp"]), 0.3, 1.0))
    if knobs.get("emphasize"):
        # boost stress on matching orth
        key = str(knobs["emphasize"]).lower()
        for w in p["words"]:
            if w.get("orth", "").lower() == key:
                w["stress"] = 1
                w["dur_scale"] = float(w.get("dur_scale") or 1.0) * 1.25
    if knobs.get("pause_ms") is not None:
        # stretch all inter-word pauses
        pad = int(knobs["pause_ms"])
        p["pauses_ms"] = [pad if i else 0 for i in range(len(p["words"]))]
    p["pass_knobs"] = knobs
    p["compile_steps"] = list(p.get("compile_steps") or []) + [f"pass_knobs:{list(knobs.keys())}"]
    return p


def np_clip(x: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, x))


def plan_is_sparse(plan: dict[str, Any]) -> bool:
    words = plan.get("words") or []
    if len(words) < 1:
        return True
    # many unknown short rule-G2P words
    weak = sum(1 for w in words if len(w.get("phones") or []) <= 1)
    return weak >= max(1, len(words) // 2)


def _llm_enabled(use_llm: Optional[bool]) -> bool:
    if use_llm is True:
        return True
    if use_llm is False:
        return False
    env = os.environ.get("SYNTHESUS_FORMANT_LLM_PLAN", "").strip().lower()
    return env in ("1", "true", "yes", "on", "auto")


def llm_enrich_plan(plan: dict[str, Any], timeout_s: float = 8.0) -> dict[str, Any]:
    """Optional Ollama enrich: only phone proposals for words; validate strictly."""
    if not _llm_enabled(True):
        return plan
    allowed = sorted(ALLOWED_PHONES)
    payload = {
        "task": "utterance_plan",
        "text": plan.get("source_text"),
        "allowed_phones": allowed[:80],
        "current_words": [
            {"orth": w.get("orth"), "phones": w.get("phones")}
            for w in (plan.get("words") or [])
        ],
        "schema": {
            "words": [{"orth": "str", "phones": ["ARPABET"], "stress": 0}],
            "rate": 0.85,
            "monologue": "str",
        },
    }
    prompt = (
        "You help Synthesus SI formant speech (NOT neural TTS). "
        "Output JSON only. Phones must be from allowed_phones. "
        f"USER:\n{json.dumps(payload)}\n"
    )
    text = _call_ollama(prompt, timeout_s=timeout_s)
    if not text:
        plan = dict(plan)
        plan["llm_status"] = "unavailable"
        return plan
    obj = _extract_json(text)
    if not obj:
        plan = dict(plan)
        plan["llm_status"] = "parse_fail"
        return plan

    plan = dict(plan)
    plan["source"] = "llm+rules"
    plan["llm_status"] = "ok"
    steps = list(plan.get("compile_steps") or [])
    by_orth = {w["orth"].lower(): dict(w) for w in (plan.get("words") or [])}
    for w in obj.get("words") or []:
        if not isinstance(w, dict):
            continue
        orth = str(w.get("orth") or "").lower().strip()
        if not orth or orth not in by_orth:
            continue
        phones = validate_phones(w.get("phones") or [])
        if phones:
            by_orth[orth]["phones"] = phones
            by_orth[orth]["how"] = "llm+validated"
            steps.append(f"llm phones {orth} → {' '.join(phones)}")
        if w.get("stress") is not None:
            by_orth[orth]["stress"] = int(w["stress"])
    # preserve order
    plan["words"] = [
        by_orth[w["orth"].lower()] for w in (plan.get("words") or [])
        if w["orth"].lower() in by_orth
    ]
    if obj.get("rate") is not None:
        try:
            plan["rate"] = float(np_clip(float(obj["rate"]), 0.5, 1.5))
        except (TypeError, ValueError):
            pass
    if obj.get("monologue"):
        plan["monologue"] = (
            f"{plan.get('monologue', '')} LLM: {str(obj['monologue'])[:300]}"
        ).strip()
    plan["compile_steps"] = steps
    return plan


def _extract_json(text: str) -> Optional[dict]:
    text = (text or "").strip()
    m = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.S)
    if m:
        text = m.group(1)
    else:
        a, b = text.find("{"), text.rfind("}")
        if a >= 0 and b > a:
            text = text[a : b + 1]
    try:
        o = json.loads(text)
        return o if isinstance(o, dict) else None
    except json.JSONDecodeError:
        return None


def _call_ollama(prompt: str, timeout_s: float = 8.0) -> Optional[str]:
    model = os.environ.get("SYNTHESUS_MODEL", "llama3.2:3b")
    base = os.environ.get("OLLAMA_API_URL", "http://localhost:11434")
    url = base if base.rstrip("/").endswith("/api/generate") else base.rstrip("/") + "/api/generate"
    body = json.dumps({
        "model": model,
        "prompt": prompt,
        "stream": False,
        "options": {"temperature": 0.1, "num_predict": 400},
    }).encode("utf-8")
    req = urllib.request.Request(url, data=body, headers={"Content-Type": "application/json"}, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=timeout_s) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        return data.get("response")
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, OSError, json.JSONDecodeError):
        return None


def compile_utterance_plan(
    text: str,
    *,
    accent: Optional[dict] = None,
    geometric_prosody: Optional[dict] = None,
    use_llm: Optional[bool] = None,
) -> dict[str, Any]:
    plan = compile_utterance_plan_rules(
        text, accent=accent, geometric_prosody=geometric_prosody,
    )
    do_llm = False
    if use_llm is True:
        do_llm = True
    elif use_llm is False:
        do_llm = False
    elif _llm_enabled(None):
        do_llm = plan_is_sparse(plan)
        plan["llm_policy"] = "auto_sparse" if do_llm else "auto_skip_rich"
    if do_llm:
        try:
            plan = llm_enrich_plan(plan)
        except Exception as exc:
            plan = dict(plan)
            plan["llm_status"] = f"error:{type(exc).__name__}"
    return plan


def plan_to_render_words(plan: dict[str, Any]) -> List[dict[str, Any]]:
    """Flatten plan into renderable word dicts with absolute dur_scale."""
    rate = float(plan.get("rate") or 1.0)
    out = []
    for w in plan.get("words") or []:
        phones = validate_phones(w.get("phones") or [])
        if not phones:
            continue
        ds = float(w.get("dur_scale") or 1.0) * rate
        out.append({
            "orth": w.get("orth") or "",
            "phones": phones,
            "stress": int(w.get("stress") or 0),
            "dur_scale": ds,
        })
    return out


def classify_speech_pass(message: str) -> Optional[dict[str, Any]]:
    """Chat knobs for multi-pass speech (like image pass intent)."""
    t = (message or "").strip().lower()
    if not t:
        return None
    knobs: dict[str, Any] = {}
    if re.search(r"\b(slower|slow\s+down|more\s+slowly)\b", t):
        knobs["slower"] = True
    if re.search(r"\b(faster|quicker|speed\s+up)\b", t):
        knobs["faster"] = True
    if re.search(r"\b(higher|higher\s+pitch|up\s+pitch)\b", t):
        knobs["higher"] = True
    if re.search(r"\b(lower|deeper|down\s+pitch)\b", t):
        knobs["lower"] = True
    if re.search(r"\b(rising|more\s+rising|question)\b", t):
        knobs["rising_final"] = True
    if re.search(r"\b(wide\s+vowels|more\s+australian|aussie)\b", t):
        knobs["f2_stretch"] = 1.2
    if re.search(r"\bemphasize\s+(\w+)", t):
        m = re.search(r"\bemphasize\s+(\w+)", t)
        if m:
            knobs["emphasize"] = m.group(1)
    if knobs:
        return knobs
    return None
