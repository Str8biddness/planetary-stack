#!/usr/bin/env python3
"""Run the focused release-readiness suite for the Synthesus 5 CHAL path."""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PYTHONPATH_ENTRIES = (
    ROOT / "packages",
    ROOT / "packages" / "core",
    ROOT / "packages" / "reasoning",
    ROOT / "packages" / "kernel",
    ROOT / "packages" / "knowledge",
    ROOT / "packages" / "api",
)


@dataclass(frozen=True)
class SuiteStep:
    label: str
    command: tuple[str, ...]


STEPS = (
    SuiteStep(
        label="compile-chal-release-path",
        command=(
            sys.executable,
            "-m",
            "py_compile",
            "tools/synthesus5_chal_smoke.py",
            "tools/chal_conversation_compare.py",
            "tools/synthesus5_focused_suite.py",
            "tools/validate_knowledge_cold_start.py",
            "packages/api/production_server.py",
            "packages/core/chal/hypervisor.py",
            "packages/core/chal/quad_brain.py",
            "packages/reasoning/chal.py",
            "tests/test_chal_hypervisor.py",
            "tests/test_chal_reasoning_firmware.py",
            "tests/e2e/test_chat_e2e.py",
        ),
    ),
    SuiteStep(
        label="api-chal-smoke",
        command=(sys.executable, "tools/synthesus5_chal_smoke.py"),
    ),
    SuiteStep(
        label="hypervisor-and-api-regressions",
        command=(
            sys.executable,
            "-m",
            "pytest",
            "-q",
            "tests/test_chal_hypervisor.py",
            "tests/e2e/test_chat_e2e.py::TestChatE2E::test_chal_mode_routes_through_cognitive_hypervisor",
        ),
    ),
    SuiteStep(
        label="firmware-and-comparison-regressions",
        command=(sys.executable, "-m", "pytest", "-q", "tests/test_chal_reasoning_firmware.py"),
    ),
    SuiteStep(
        label="phase8-latency-regression-guard",
        command=(
            sys.executable,
            "tools/chal_conversation_compare.py",
            "--fail-on-leak",
            "--fail-on-reference",
            "--fail-on-axis-regression",
            "--fail-on-continuity",
            "--fail-on-trace-storage",
            "--max-mean-latency-ms",
            "1000",
            "--max-p95-latency-ms",
            "1500",
            "--min-score-delta",
            "0.1",
            "--scorecard-json",
            "tools/results/synthesus5_phase8_reference_scorecard_latest.json",
            "--axis-scorecard-json",
            "tools/results/synthesus5_phase8_axis_scorecard_latest.json",
            "--continuity-scorecard-json",
            "tools/results/synthesus5_phase8_continuity_scorecard_latest.json",
            "--trace-store-scorecard-json",
            "tools/results/synthesus5_phase8_trace_storage_scorecard_latest.json",
            "--baseline-json",
            "tools/results/synthesus5_phase8_latency_baseline_latest.json",
        ),
    ),
    SuiteStep(
        label="knowledge-cloud-cold-start-integrity",
        command=(sys.executable, "tools/validate_knowledge_cold_start.py"),
    ),
)


def _suite_env() -> dict[str, str]:
    env = os.environ.copy()
    existing = env.get("PYTHONPATH", "")
    entries = [str(path) for path in PYTHONPATH_ENTRIES]
    if existing:
        entries.append(existing)
    env["PYTHONPATH"] = os.pathsep.join(entries)
    env.setdefault("SYNTHESUS_KNOWLEDGE_SYNC_MODE", "off")
    env.setdefault("SYNTHESUS_API_KEY", "synthesus5-focused-suite-local")
    return env


def run_suite(*, verbose: bool = False) -> int:
    env = _suite_env()
    for step in STEPS:
        print(f"==> {step.label}")
        completed = subprocess.run(
            step.command,
            cwd=ROOT,
            env=env,
            text=True,
            stdout=None if verbose else subprocess.PIPE,
            stderr=None if verbose else subprocess.STDOUT,
            check=False,
        )
        if completed.returncode != 0:
            if not verbose and completed.stdout:
                print(completed.stdout, end="" if completed.stdout.endswith("\n") else "\n")
            print(f"FAILED: {step.label} exited {completed.returncode}")
            return completed.returncode
        if not verbose and completed.stdout:
            tail = "\n".join(completed.stdout.strip().splitlines()[-8:])
            if tail:
                print(tail)
        print(f"PASS: {step.label}")
    print("Synthesus 5 focused suite passed.")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run the focused Synthesus 5 CHAL release-readiness checks.",
    )
    parser.add_argument("--verbose", action="store_true", help="Stream full command output.")
    args = parser.parse_args()
    return run_suite(verbose=args.verbose)


if __name__ == "__main__":
    raise SystemExit(main())
