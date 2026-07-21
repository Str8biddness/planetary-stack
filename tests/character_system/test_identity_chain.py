"""Identity chains: continuity you can check.

The tests that matter are the ones proving history cannot be rewritten — an
edited entry, a reordered entry, an excised entry, and a chain grafted onto a
different genome must all fail closed.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

_PACKAGES = Path(__file__).resolve().parents[2] / "apps" / "synthesus" / "runtime" / "packages"
if str(_PACKAGES) not in sys.path:
    sys.path.insert(0, str(_PACKAGES))

from characters.archive import verify_archive  # noqa: E402
from characters.identity import (  # noqa: E402
    IdentityChain,
    IdentityChainError,
    genesis_digest,
    state_digest,
    verify_chain,
)

ARCHIVE = _PACKAGES / "characters" / "synthesus.sxc"
GENOME = "a" * 64


def _narrative(step: int) -> dict:
    return {
        "identity": "synthesus",
        "role": "assistant",
        "scene": f"session_{step}",
        "tone": {"valence": 0.1 * step, "arousal": 0.5},
        "goals": [{"id": "help_owner", "priority": 0.9}],
        "continuity_summary": f"Step {step}: continued working with the owner.",
    }


def _chain(tmp_path: Path, steps: int = 3) -> IdentityChain:
    chain = IdentityChain(
        tmp_path / "identity.jsonl", archive_sha256=GENOME, character_id="synthesus"
    )
    for step in range(1, steps + 1):
        chain.append(
            t=step,
            consciousness_state={"t": step, "confidence": 0.5 + step / 100},
            narrative=_narrative(step),
        )
    return chain


def test_chain_grows_and_head_advances(tmp_path):
    chain = IdentityChain(tmp_path / "id.jsonl", archive_sha256=GENOME, character_id="synthesus")
    assert chain.head == chain.genesis and chain.length == 0

    first = chain.append(t=1, consciousness_state={"t": 1}, narrative=_narrative(1))
    assert chain.head == first["entry_sha256"] != chain.genesis
    second = chain.append(t=2, consciousness_state={"t": 2}, narrative=_narrative(2))
    assert second["prev"] == first["entry_sha256"]
    assert chain.length == 2


def test_chain_survives_reload(tmp_path):
    """Continuity persists across restarts — that is the whole point."""
    chain = _chain(tmp_path, steps=4)
    head, length = chain.head, chain.length
    reopened = IdentityChain(
        tmp_path / "identity.jsonl", archive_sha256=GENOME, character_id="synthesus"
    )
    assert reopened.head == head
    assert reopened.length == length


def test_edited_entry_is_detected(tmp_path):
    chain = _chain(tmp_path)
    entries = chain.entries()
    entries[1]["narrative"]["continuity_summary"] = "Step 2: something that never happened."
    with pytest.raises(IdentityChainError, match="has been modified"):
        verify_chain(entries, genesis=chain.genesis)


def test_reordered_entries_are_detected(tmp_path):
    chain = _chain(tmp_path)
    entries = chain.entries()
    entries[0], entries[1] = entries[1], entries[0]
    with pytest.raises(IdentityChainError, match="out of order"):
        verify_chain(entries, genesis=chain.genesis)


def test_excised_entry_is_detected(tmp_path):
    """History cannot be quietly shortened."""
    chain = _chain(tmp_path, steps=4)
    entries = chain.entries()
    del entries[2]
    with pytest.raises(IdentityChainError, match="out of order|broken link"):
        verify_chain(entries, genesis=chain.genesis)


def test_chain_cannot_be_transplanted_onto_another_genome(tmp_path):
    """A history is bound to the genome it was lived in."""
    chain = _chain(tmp_path)
    other_genesis = genesis_digest(archive_sha256="b" * 64, character_id="synthesus")
    with pytest.raises(IdentityChainError, match="broken link"):
        verify_chain(chain.entries(), genesis=other_genesis)


def test_chain_cannot_be_transplanted_onto_another_character(tmp_path):
    chain = _chain(tmp_path)
    other = genesis_digest(archive_sha256=GENOME, character_id="atlas")
    with pytest.raises(IdentityChainError, match="broken link"):
        verify_chain(chain.entries(), genesis=other)


def test_a_fresh_copy_of_the_genome_has_no_history(tmp_path):
    """The commercial point: copying the genome does not copy the life.

    A buyer receives the character at genesis. Producing a long chain requires
    actually running those steps, because every link commits to the one before.
    """
    lived = _chain(tmp_path / "original", steps=25)
    fresh = IdentityChain(
        tmp_path / "copy" / "identity.jsonl", archive_sha256=GENOME, character_id="synthesus"
    )
    assert fresh.genesis == lived.genesis     # same genome
    assert fresh.head != lived.head           # different life
    assert fresh.length == 0 and lived.length == 25


def test_appending_a_forged_long_history_fails(tmp_path):
    """You cannot fabricate a past by writing entries with plausible numbers."""
    chain = _chain(tmp_path, steps=2)
    entries = chain.entries()
    forged = dict(entries[-1])
    forged["seq"] = 3
    forged["t"] = 999
    entries.append(forged)
    with pytest.raises(IdentityChainError, match="broken link|has been modified"):
        verify_chain(entries, genesis=chain.genesis)


def test_story_reads_as_a_continuous_narrative(tmp_path):
    chain = _chain(tmp_path, steps=5)
    story = chain.story()
    assert [item["seq"] for item in story] == [1, 2, 3, 4, 5]
    assert story[0]["summary"].startswith("Step 1")
    assert story[-1]["scene"] == "session_5"


def test_narrative_rejects_unknown_fields(tmp_path):
    chain = IdentityChain(tmp_path / "id.jsonl", archive_sha256=GENOME, character_id="s")
    bad = _narrative(1)
    bad["exfiltrate"] = "secrets"
    with pytest.raises(IdentityChainError, match="unexpected fields"):
        chain.append(t=1, consciousness_state={}, narrative=bad)


def test_state_digest_accepts_the_loops_dataclass_state():
    """Works with whatever C(t) object the consciousness loop produces."""
    class FakeIntegratedState:
        def __init__(self):
            self.t = 7
            self.confidence = 0.82
            self._scratch = "excluded"

    digest = state_digest(FakeIntegratedState())
    assert len(digest) == 64
    assert digest == state_digest(FakeIntegratedState())  # deterministic


def test_chain_roots_in_the_real_shipped_archive(tmp_path):
    """Genesis binds to the genome that actually ships."""
    manifest = verify_archive(ARCHIVE)
    chain = IdentityChain(
        tmp_path / "id.jsonl",
        archive_sha256=manifest["archive_sha256"],
        character_id=manifest["character_id"],
    )
    assert chain.genesis == genesis_digest(
        archive_sha256=manifest["archive_sha256"], character_id="synthesus"
    )
    chain.append(t=1, consciousness_state={"t": 1}, narrative=_narrative(1))
    assert verify_chain(chain.entries(), genesis=chain.genesis) == chain.head
