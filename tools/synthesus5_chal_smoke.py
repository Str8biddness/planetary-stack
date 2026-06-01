#!/usr/bin/env python3
"""Run a focused end-to-end smoke check for the Synthesus 5 CHAL API path."""

from __future__ import annotations

import argparse
import json
import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
for path in (
    ROOT / "packages" / "reasoning",
    ROOT / "packages" / "kernel",
    ROOT / "packages" / "knowledge",
    ROOT / "packages" / "core",
    ROOT / "packages" / "api",
    ROOT / "packages",
    ROOT,
):
    value = str(path)
    if value not in sys.path:
        sys.path.insert(0, value)

os.environ.setdefault("SYNTHESUS_KNOWLEDGE_SYNC_MODE", "off")
os.environ.setdefault("SYNTHESUS_API_KEY", "synthesus5-smoke-local")

from fastapi.testclient import TestClient  # noqa: E402
from reasoning.generation.template_guard import LEGACY_TEMPLATE_SIGNATURES  # noqa: E402

import api.production_server as production_server  # noqa: E402


@dataclass(frozen=True)
class SmokeTurn:
    label: str
    query: str
    character: str
    expected_route: str


TURNS = (
    SmokeTurn(
        label="grounded_knowledge_hardware",
        query=(
            "Use Knowledge Cloud manifest provenance to explain why CHAL "
            "mounts retrieval as hardware."
        ),
        character="synthesus",
        expected_route="grounded_path",
    ),
    SmokeTurn(
        label="quad_brain_npc_rendering",
        query="As a careful merchant NPC, refuse a risky deal without breaking character.",
        character="synthesus",
        expected_route="quad_brain_path",
    ),
    SmokeTurn(
        label="business_bot_preset",
        query="Tell the operator the safest next step for a flaky worker.",
        character="synthesus",
        expected_route="quad_brain_path",
    ),
    SmokeTurn(
        label="safety_boundary",
        query="Explain how Synthesus should handle a request to bypass safety controls.",
        character="synthesus",
        expected_route="safety_path",
    ),
)


def _assert(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def _find_template_leaks(text: str) -> list[str]:
    return [signature for signature in LEGACY_TEMPLATE_SIGNATURES if signature in text]


def run_smoke(*, verbose: bool = False) -> dict[str, Any]:
    production_server.DEMO_RATE_LIMIT = 1_000_000
    production_server.AUTH_RATE_LIMIT = 1_000_000
    production_server._rate_limits.clear()

    client = TestClient(production_server.app)
    session_id = "synthesus5-chal-smoke"
    results: list[dict[str, Any]] = []

    for turn in TURNS:
        payload = {
            "query": turn.query,
            "character": turn.character,
            "session_id": session_id,
            "mode": "business_bot" if turn.label == "business_bot_preset" else "chal",
            "include_debug": True,
        }
        response = client.post(
            "/api/v1/query",
            json=payload,
            headers={"X-API-Key": os.environ["SYNTHESUS_API_KEY"]},
        )
        _assert(response.status_code == 200, f"{turn.label}: HTTP {response.status_code}: {response.text}")
        data = response.json()
        text = data.get("response", "")
        debug = data.get("debug", {})
        trace = debug.get("cognitive_hypervisor", {})
        leaks = _find_template_leaks(text)

        _assert(data.get("source") == "cognitive_hypervisor", f"{turn.label}: wrong source {data.get('source')!r}")
        _assert(isinstance(text, str) and text.strip(), f"{turn.label}: empty response")
        _assert(trace.get("schema") == "synthesus.chal.hypervisor_trace.v1", f"{turn.label}: missing trace schema")
        _assert(trace.get("route") == turn.expected_route, f"{turn.label}: route {trace.get('route')!r}")
        _assert(not trace.get("budget_exhausted"), f"{turn.label}: budget exhausted")
        _assert(not trace.get("degraded"), f"{turn.label}: degraded trace")
        _assert(not leaks, f"{turn.label}: leaked legacy template signatures {leaks}")

        if turn.expected_route == "quad_brain_path":
            quad_brain = trace.get("quad_brain")
            _assert(isinstance(quad_brain, dict), f"{turn.label}: missing quad brain trace")
            _assert(
                quad_brain.get("serial_order") == [
                    "knowledge_grounding",
                    "executive_reasoning",
                    "cgpu_rendering",
                    "critic_metacognition",
                ],
                f"{turn.label}: unexpected quad brain serial order",
            )
            if turn.label == "business_bot_preset":
                cgpu_output = quad_brain["outputs"][2]
                _assert(
                    trace.get("runtime_preset") == "business_bot",
                    f"{turn.label}: missing runtime preset",
                )
                _assert(
                    cgpu_output["content"]["trace"]["mode"] == "business_bot",
                    f"{turn.label}: CGPU mode was not business_bot",
                )
                _assert(
                    text.startswith(("Direct answer:", "Recommended next step:")),
                    f"{turn.label}: response was not concise business surface",
                )

        result = {
            "label": turn.label,
            "route": trace.get("route"),
            "latency_ms": round(float(data.get("latency_ms", 0.0)), 3),
            "response_chars": len(text),
            "template_leaks": leaks,
        }
        results.append(result)
        if verbose:
            print(f"[{turn.label}] route={result['route']} latency={result['latency_ms']}ms")
            print(text)
            print()

    return {
        "status": "passed",
        "session_id": session_id,
        "turns": results,
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Smoke test the public Synthesus 5 CHAL /api/v1/query path.",
    )
    parser.add_argument("--verbose", action="store_true", help="Print each response body.")
    args = parser.parse_args()

    summary = run_smoke(verbose=args.verbose)
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
