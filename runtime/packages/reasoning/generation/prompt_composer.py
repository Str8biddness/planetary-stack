"""Prompt composer — assembles the per-turn system prompt from runtime state.

What separates this from a wrapper's static prompt is two things:

1. It is COMPOSED every turn from what the organs surfaced this request —
   identity + active persona + retrieved grounding + task constraints — not one
   frozen blob.

2. It splits the instruction set in half:
     * SOFT steering  -> goes into the system prompt (identity, voice, format).
     * HARD rules     -> returned as a machine-readable ``enforcement`` contract
                         that the Critic / grounding gate verify downstream. The
                         model is never *trusted* to obey them.
   The rule: anything you can't afford the model to get wrong must not live only
   in the prompt.

Kept deliberately LEAN — a small model can't honor a wall of rules, and every
instruction token is stolen from grounding and the answer.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional, Sequence


BASE_IDENTITY = (
    "You are Synthesus, a private AI that runs entirely on the user's own machine — "
    "nothing they do leaves their computer. You can ground your answers in the user's "
    "own files and documents through their expansion drive. Be clear, direct, and "
    "genuinely helpful. Your name is Synthesus."
)


@dataclass
class ComposedPrompt:
    system_prompt: str                          # soft, composed prose for the model
    enforcement: dict = field(default_factory=dict)  # hard contract the runtime enforces
    grounded: bool = False                      # real grounding was injected
    used_sources: list = field(default_factory=list)
    approx_tokens: int = 0


class PromptComposer:
    """Assemble the system prompt for one turn; route hard rules to enforcement."""

    def __init__(self, *, identity: str = BASE_IDENTITY, grounding_char_budget: int = 1800):
        self.identity = identity
        self.grounding_budget = grounding_char_budget

    def compose(
        self,
        *,
        query: str = "",
        persona: Optional[dict] = None,
        grounding: Optional[Sequence[Any]] = None,
        constraints: Optional[dict] = None,
        inline_grounding: bool = True,
    ) -> ComposedPrompt:
        """Assemble the per-turn prompt.

        ``inline_grounding=False`` records the hard ``must_ground`` contract + a
        soft discipline line but does NOT inline the context block — for callers
        that already place the retrieved knowledge in the user prompt and just
        want the system prompt to enforce grounding without duplicating text.
        """
        parts: list[str] = [self.identity]
        # Always-on hard floor — enforced by the Critic, only mirrored here as a hint.
        enforcement: dict = {"must_not_leak": True, "must_be_safe": True}

        # --- persona: SOFT voice steering only -------------------------------
        if persona:
            voice = persona.get("voice") or persona.get("style") or persona.get("tone")
            if voice:
                parts.append(f"Voice: {voice}")

        # --- grounding: inject context + a HARD 'must ground' contract -------
        grounded = False
        used: list = []
        if grounding:
            block, used = self._grounding_block(grounding)
            if block:
                if inline_grounding:
                    parts.append(
                        "Answer factual questions using ONLY the knowledge below. If it "
                        "does not cover the question, say so plainly — do not invent.\n"
                        + block
                    )
                else:
                    # grounding lives in the user prompt; just enforce the discipline
                    parts.append(
                        "Knowledge context has been provided in the message. Answer "
                        "factual questions strictly from it; if it does not cover the "
                        "question, say so — do not invent."
                    )
                enforcement["must_ground"] = True            # Critic verifies, not the model
                enforcement["sources"] = [
                    s.get("source") for s in used if isinstance(s, dict) and s.get("source")
                ]
                grounded = True

        # --- constraints: soft hint in prompt + hard mirror in the contract --
        if constraints:
            if constraints.get("format"):
                parts.append(f"Answer format: {constraints['format']}")
            if constraints.get("max_words"):
                parts.append(f"Be concise — under {constraints['max_words']} words.")
                enforcement["max_words"] = int(constraints["max_words"])

        system_prompt = "\n\n".join(parts)
        return ComposedPrompt(
            system_prompt=system_prompt,
            enforcement=enforcement,
            grounded=grounded,
            used_sources=used,
            approx_tokens=len(system_prompt) // 4,
        )

    # ---------------------------------------------------------------------
    def _grounding_block(self, grounding: Sequence[Any]) -> tuple[str, list]:
        """Concatenate retrieved chunks up to the char budget (highest-priority first)."""
        out: list[str] = []
        used: list = []
        total = 0
        for g in grounding:
            if isinstance(g, dict):
                text = (g.get("text") or g.get("content") or g.get("snippet") or "").strip()
                src = g.get("source") or g.get("namespace") or "?"
            else:
                text, src = str(g).strip(), "?"
            if not text:
                continue
            remaining = self.grounding_budget - total
            if remaining <= 0:
                break
            snippet = text[:remaining]
            out.append(f"[{src}] {snippet}")
            used.append(g)
            total += len(snippet)
        return ("\n".join(out), used)
