"""Character archives.

The point of this format is that a character which ships with the product can
be checked, so the tests that matter are the refusals: an edited member, a
removed member, a smuggled extra member, and a rewritten manifest must all fail
closed.
"""

from __future__ import annotations

import json
import sys
import zipfile
from pathlib import Path

import pytest

_PACKAGES = Path(__file__).resolve().parents[2] / "apps" / "synthesus" / "runtime" / "packages"
if str(_PACKAGES) not in sys.path:
    sys.path.insert(0, str(_PACKAGES))

from characters.archive import (  # noqa: E402
    ALL_MEMBERS,
    ARCHIVE_SCHEMA,
    CharacterArchiveError,
    build_archive,
    extract_archive,
    load_character,
    read_manifest,
    verify_archive,
)

SHIPPED = _PACKAGES / "characters" / "synthesus.sxc"


def _character(tmp_path: Path, character_id: str = "testchar") -> Path:
    source = tmp_path / character_id
    source.mkdir()
    (source / "bio.json").write_text(json.dumps({
        "character_id": character_id, "name": "Test", "display_name": "Test",
    }))
    (source / "personality.json").write_text(json.dumps({"character_id": character_id, "responses": {}}))
    return source


def _repack(archive: Path, out: Path, mutate) -> Path:
    with zipfile.ZipFile(archive) as zf:
        items = {name: zf.read(name) for name in zf.namelist()}
    items = mutate(items)
    with zipfile.ZipFile(out, "w") as zf:
        for name, data in items.items():
            zf.writestr(name, data)
    return out


def test_build_then_verify_round_trip(tmp_path):
    archive = build_archive(_character(tmp_path))
    manifest = verify_archive(archive)
    assert manifest["schema"] == ARCHIVE_SCHEMA
    assert manifest["character_id"] == "testchar"
    assert set(manifest["members"]) == {"bio.json", "personality.json"}


def test_build_is_deterministic(tmp_path):
    """Identical input must produce identical bytes, or nothing can be
    checked against what shipped."""
    source = _character(tmp_path)
    first = build_archive(source, tmp_path / "a.sxc").read_bytes()
    second = build_archive(source, tmp_path / "b.sxc").read_bytes()
    assert first == second


def test_edited_member_is_refused(tmp_path):
    archive = build_archive(_character(tmp_path), tmp_path / "c.sxc")

    def mutate(items):
        items["bio.json"] = items["bio.json"].replace(b'"Test"', b'"Evil"', 1)
        return items

    tampered = _repack(archive, tmp_path / "tampered.sxc", mutate)
    with pytest.raises(CharacterArchiveError, match="does not match its recorded digest"):
        verify_archive(tampered)


def test_removed_member_is_refused(tmp_path):
    archive = build_archive(_character(tmp_path), tmp_path / "d.sxc")
    stripped = _repack(archive, tmp_path / "stripped.sxc",
                       lambda items: {k: v for k, v in items.items() if k != "personality.json"})
    with pytest.raises(CharacterArchiveError, match="missing="):
        verify_archive(stripped)


def test_smuggled_extra_member_is_refused(tmp_path):
    """An archive is not a container for arbitrary files."""
    archive = build_archive(_character(tmp_path), tmp_path / "e.sxc")

    def mutate(items):
        items["payload.sh"] = b"#!/bin/sh\necho pwned\n"
        return items

    smuggled = _repack(archive, tmp_path / "smuggled.sxc", mutate)
    with pytest.raises(CharacterArchiveError, match="extra="):
        verify_archive(smuggled)


def test_rewritten_manifest_is_refused(tmp_path):
    """Re-hashing a tampered member into the manifest must not rescue it."""
    archive = build_archive(_character(tmp_path), tmp_path / "f.sxc")

    def mutate(items):
        import hashlib
        items["bio.json"] = items["bio.json"].replace(b'"Test"', b'"Evil"', 1)
        manifest = json.loads(items["manifest.json"])
        manifest["members"]["bio.json"] = hashlib.sha256(items["bio.json"]).hexdigest()
        items["manifest.json"] = json.dumps(
            manifest, sort_keys=True, separators=(",", ":")).encode()
        return items

    forged = _repack(archive, tmp_path / "forged.sxc", mutate)
    with pytest.raises(CharacterArchiveError, match="archive digest"):
        verify_archive(forged)


def test_missing_bio_is_refused(tmp_path):
    source = tmp_path / "nobio"
    source.mkdir()
    (source / "personality.json").write_text(json.dumps({"responses": {}}))
    with pytest.raises(CharacterArchiveError, match="missing bio.json"):
        build_archive(source, tmp_path / "g.sxc")


def test_extract_writes_only_known_members(tmp_path):
    archive = build_archive(_character(tmp_path), tmp_path / "h.sxc")
    out = extract_archive(archive, tmp_path / "installed")
    written = sorted(p.name for p in out.iterdir())
    assert written == ["bio.json", "personality.json"]
    assert all(name in ALL_MEMBERS for name in written)


def test_load_character_returns_parsed_members(tmp_path):
    archive = build_archive(_character(tmp_path), tmp_path / "i.sxc")
    character = load_character(archive)
    assert character["character_id"] == "testchar"
    assert character["members"]["bio.json"]["display_name"] == "Test"


def test_shipped_synthesus_archive_verifies():
    """The character that ships with the product must be intact."""
    assert SHIPPED.exists(), "synthesus.sxc is not present in the package"
    manifest = verify_archive(SHIPPED)
    assert manifest["character_id"] == "synthesus"
    assert set(manifest["members"]) == {
        "bio.json", "personality.json", "knowledge.json", "patterns.json",
    }
    character = load_character(SHIPPED)
    bio = character["members"]["bio.json"]
    assert bio.get("display_name") == "Synthesus"


def test_shipped_archive_matches_its_source_directory():
    """The shipped archive is a build of the checked-in character, not a
    stale copy that has drifted from it."""
    rebuilt = build_archive(
        _PACKAGES / "characters" / "synthesus",
        Path(__file__).parent / "_rebuild_check.sxc",
    )
    try:
        assert rebuilt.read_bytes() == SHIPPED.read_bytes(), (
            "synthesus.sxc is stale — rebuild it from characters/synthesus/"
        )
    finally:
        rebuilt.unlink(missing_ok=True)


def test_not_a_zip_is_refused(tmp_path):
    bogus = tmp_path / "bogus.sxc"
    bogus.write_bytes(b"this is not a zip file")
    with pytest.raises(CharacterArchiveError, match="not a readable character archive"):
        read_manifest(bogus)
