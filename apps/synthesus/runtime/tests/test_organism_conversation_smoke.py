"""Smoke: conversation organism (Ultra ability #4 lineage) still imports and runs.

This is the valuable Ultra demo path — intent+sentiment organs → conditioned reply.
Does not require private synthetic dumps; uses the organism's built-in demo corpus.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "packages"))
sys.path.insert(0, str(ROOT / "packages" / "reasoning"))


def test_organism_conversation_module_importable():
    import organism_conversation as oc

    assert hasattr(oc, "ConversationOrganism") or hasattr(oc, "main") or hasattr(oc, "Synthesus")


def test_organism_conversation_main_runs():
    """Run the module's demo entry if present — REAL path, not a mock."""
    import organism_conversation as oc

    if hasattr(oc, "main"):
        # main() may print and return None; must not raise
        oc.main()
        return
    if hasattr(oc, "ConversationOrganism"):
        org = oc.ConversationOrganism()
        # best-effort API shapes
        if hasattr(org, "converse"):
            out = org.converse("hey there!")
            assert out is not None
        elif hasattr(org, "process"):
            out = org.process("hey there!")
            assert out is not None
        else:
            pytest.skip("ConversationOrganism has no converse/process")
    else:
        pytest.skip("no ConversationOrganism class")


def test_organ_smoke_fixtures_present():
    fix = ROOT / "tests" / "fixtures" / "organ_smoke"
    assert (fix / "manifest.json").is_file()
    # at least intent + dialogue smoke slices from Ultra synthetic_data
    assert (fix / "intent_smoke.json").is_file()
    assert (fix / "dialogue_smoke.json").is_file()
