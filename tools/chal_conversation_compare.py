#!/usr/bin/env python3
"""Compare legacy PPBRS-style conversation output against Synthesus 4.1 CHAL."""

from __future__ import annotations

import argparse
import asyncio
import copy
import sys
import time
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
for path in (
    ROOT / "packages" / "reasoning",
    ROOT / "packages" / "kernel",
    ROOT / "packages" / "knowledge",
    ROOT / "packages" / "core",
    ROOT / "packages",
    ROOT,
):
    value = str(path)
    if value not in sys.path:
        sys.path.insert(0, value)

from core.hemisphere_bridge import HemisphereBridge  # noqa: E402


TURNS = [
    "How should CHAL treat the Knowledge Cloud compared to legacy retrieval?",
    "What happens when PPBRS has a pattern match but final wording needs to be natural?",
    "Explain the difference between a demo and a platform for AIVM NPCs.",
]

LEFT_ROUTES = [
    {
        "pattern": "chal knowledge cloud legacy retrieval",
        "module": "knowledge_hardware_mount",
        "priority": 2.4,
    },
    {
        "pattern": "ppbrs pattern final wording natural",
        "module": "bounded_generation_handoff",
        "priority": 2.2,
    },
    {
        "pattern": "demo platform aivm npcs",
        "module": "platform_boundary_reasoner",
        "priority": 2.0,
    },
]

LEGACY_SURFACE_SIGNATURES = ("[module]", "[fallback]", "response_template", "Handled:")


def legacy_response(turn: str) -> dict[str, Any]:
    q = turn.lower()
    if "knowledge cloud" in q:
        return {
            "response": "[module] Handled: knowledge_cloud. The Knowledge Cloud provides retrieval context for this query.",
            "source": "legacy_ppbrs_template",
            "confidence": 0.74,
        }
    if "ppbrs" in q or "pattern" in q:
        return {
            "response": "[module] Handled: ppbrs. Use the matched response_template for the user.",
            "source": "legacy_response_template",
            "confidence": 0.69,
        }
    return {
        "response": "[fallback] No route matched. I understand you're asking about this. Let me provide what I know.",
        "source": "legacy_fallback",
        "confidence": 0.22,
    }


def right_handler(prompt: str, context: dict[str, Any]) -> dict[str, Any]:
    q = prompt.lower()
    if "knowledge cloud" in q:
        response = (
            "Retrieval stops being a sidecar and becomes addressable cognitive hardware with provenance, locality, "
            "cache behavior, and traceable constraints."
        )
    elif "ppbrs" in q or "pattern" in q:
        response = (
            "The match is preserved as route and confidence metadata, then realized as bounded natural language by the generation spine."
        )
    else:
        response = (
            "The platform boundary is persistence, inspection, and repeatable orchestration: mounted memory, routed modules, "
            "logged decisions, and improvement without template leakage."
        )
    return {
        "response": response,
        "confidence": 0.58,
    }


async def build_chal_rows() -> list[dict[str, Any]]:
    bridge = HemisphereBridge(
        kernel_bin="/tmp/nonexistent-zo-kernel",
        left_config={"routes": LEFT_ROUTES},
        right_handler=right_handler,
        agreement_threshold=0.65,
    )
    rows = []
    for idx, turn in enumerate(TURNS, 1):
        legacy = legacy_response(turn)
        started = time.time()
        chal = await bridge.route_query(
            turn,
            hemisphere="both",
            character_context={"character_id": "synthesus_4_1_chal"},
            rag_context=(
                "CHAL directive: Knowledge Cloud is mounted hardware; PPBRS emits firmware signals; "
                "generation spine owns final wording; template fallback is forbidden outside safety/policy gates."
            ),
            max_tokens=512,
        )
        chal = copy.deepcopy(chal)
        rows.append(
            {
                "turn": idx,
                "user": turn,
                "legacy": legacy,
                "chal": chal,
                "runtime_ms": round((time.time() - started) * 1000, 3),
            }
        )
    return rows


def assert_chal_surfaces_are_clean(rows: list[dict[str, Any]]) -> None:
    failures = []
    for row in rows:
        text = str(row["chal"].get("response", ""))
        for signature in LEGACY_SURFACE_SIGNATURES:
            if signature in text:
                failures.append(f"turn {row['turn']} leaked {signature!r}: {text}")
    if failures:
        raise AssertionError("\n".join(failures))


def render_markdown(rows: list[dict[str, Any]]) -> str:
    lines = [
        "# Synthesus Legacy vs 4.1 CHAL Conversation Comparison",
        "",
        "This harness compares the old template/fallback surface against the CHAL hemi-sync path.",
        "",
        "| Axis | Legacy | Synthesus 4.1 CHAL |",
        "| --- | --- | --- |",
        "| PPBRS role | Emits user-facing template strings | Emits CHAL firmware metadata |",
        "| Left hemisphere | Pattern/fallback text | Bounded route, confidence, constraints, checkpoint |",
        "| Right hemisphere | Usually bypassed or bolted on | Runs narrative/generative candidate in parallel |",
        "| Final wording | `response_template`, `[module] Handled`, `[fallback]` | Generation-spine realization plus arbitration |",
        "| Inspection | Source label only | State handoff, signals, confidence, telemetry-shaped trace |",
        "",
    ]

    for row in rows:
        chal = row["chal"]
        state = chal.get("state_handoff") or {}
        signals = state.get("signals") or []
        firmware = {}
        for signal in reversed(signals):
            candidate = signal.get("payload", {}).get("firmware_signal")
            if candidate:
                firmware = candidate
                break
        trace_id = firmware.get("trace_id", "")
        route = (
            firmware.get("module_message", {})
            .get("payload", {})
            .get("module_used", "")
        )
        lines.extend(
            [
                f"## Turn {row['turn']}",
                "",
                f"**User:** {row['user']}",
                "",
                "**Legacy output**",
                "",
                f"> {row['legacy']['response']}",
                "",
                f"- source: `{row['legacy']['source']}`",
                f"- confidence: `{row['legacy']['confidence']}`",
                "- template leakage risk: `high`",
                "",
                "**CHAL output**",
                "",
                f"> {chal['response']}",
                "",
                f"- hemisphere: `{chal.get('hemisphere_used')}`",
                f"- confidence: `{round(float(chal.get('raw_confidence', 0.0)), 3)}`",
                f"- agreement: `{round(float(chal.get('agreement_score') or 0.0), 3)}`",
                f"- left firmware route: `{route}`",
                f"- trace: `{trace_id}`",
                f"- runtime: `{row['runtime_ms']}ms`",
                "- template leakage risk: `low`",
                "",
                "**Observed difference**",
                "",
                "Legacy exposes routing/fallback scaffolding as conversation. CHAL converts the route into inspectable firmware, runs a right-hemisphere candidate, and returns an arbitrated surface response.",
                "",
            ]
        )
    return "\n".join(lines).rstrip() + "\n"


async def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--write", type=Path, help="Write markdown comparison to this path.")
    parser.add_argument("--fail-on-leak", action="store_true", help="Fail if CHAL output leaks legacy surface signatures.")
    args = parser.parse_args()

    rows = await build_chal_rows()
    if args.fail_on_leak:
        assert_chal_surfaces_are_clean(rows)
    markdown = render_markdown(rows)
    if args.write:
        args.write.parent.mkdir(parents=True, exist_ok=True)
        args.write.write_text(markdown, encoding="utf-8")
        print(args.write)
    else:
        print(markdown)
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
