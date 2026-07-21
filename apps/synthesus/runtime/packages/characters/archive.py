"""Character archives: one portable, verifiable file per character.

A character is currently a loose directory of JSON — `bio.json`,
`personality.json`, `knowledge.json`, `patterns.json` — and the studio's
"export" hands back a dict plus a sentence telling you to copy files into
place by hand. That is fine for a scratch directory and wrong for something
that ships with the product: nothing records which files belong together,
nothing detects a truncated or edited member, and nothing pins the schema.

An archive fixes that. It is a ZIP with:

    manifest.json          schema, character id, member digests, archive digest
    bio.json               \\
    personality.json        |  the member files, byte-identical to source
    knowledge.json          |
    patterns.json          /

Two properties this format guarantees, both deliberate:

* **Deterministic.** Members are stored sorted, with a fixed timestamp and no
  compression variance, so building the same character twice produces
  byte-identical archives with the same digest. A build that is not
  reproducible cannot be checked against what shipped.
* **Verified on load.** Every member's SHA-256 is recorded in the manifest and
  re-checked on read, and the manifest itself is covered by an archive digest.
  A member that has been edited, truncated, added or removed fails closed.

HONEST SCOPE: this is integrity, NOT authenticity. The digest proves the
archive is intact and self-consistent; it does not prove who produced it. A
signed-archive story would reuse the node contract keys the mesh already
distributes (see `services/private_mesh/evidence_signing.py`) and is not built
here. Do not describe an archive as "trusted" on the strength of this module.
"""

from __future__ import annotations

import hashlib
import io
import json
import zipfile
from pathlib import Path
from typing import Any

ARCHIVE_SCHEMA = "planetary.synthesus.character_archive.v1"
ARCHIVE_SUFFIX = ".sxc"
MANIFEST_NAME = "manifest.json"

# The member set is fixed. `bio.json` is the only required one; a character may
# legitimately ship without learned patterns or a knowledge graph.
REQUIRED_MEMBERS = ("bio.json",)
OPTIONAL_MEMBERS = ("personality.json", "knowledge.json", "patterns.json")
ALL_MEMBERS = REQUIRED_MEMBERS + OPTIONAL_MEMBERS

# Bounds. A character is authored data, not a payload channel.
MAX_MEMBER_BYTES = 8 * 1024 * 1024
MAX_ARCHIVE_BYTES = 32 * 1024 * 1024

# Fixed ZIP timestamp so identical input yields identical bytes.
_FIXED_DATE = (1980, 1, 1, 0, 0, 0)


class CharacterArchiveError(ValueError):
    """An archive could not be built, read, or verified."""


def _canonical_json(payload: Any) -> bytes:
    return json.dumps(
        payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False
    ).encode("ascii")


def _digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _read_member_file(path: Path) -> bytes:
    data = path.read_bytes()
    if len(data) > MAX_MEMBER_BYTES:
        raise CharacterArchiveError(f"{path.name} exceeds the member size bound")
    if not data:
        raise CharacterArchiveError(f"{path.name} is empty")
    try:
        json.loads(data.decode("utf-8"))
    except (ValueError, UnicodeDecodeError) as exc:
        raise CharacterArchiveError(f"{path.name} is not valid JSON: {exc}") from exc
    return data


def _character_id(bio_bytes: bytes) -> str:
    try:
        bio = json.loads(bio_bytes.decode("utf-8"))
    except (ValueError, UnicodeDecodeError) as exc:
        raise CharacterArchiveError(f"bio.json is not valid JSON: {exc}") from exc
    character_id = bio.get("character_id") or bio.get("id")
    if not isinstance(character_id, str) or not character_id.strip():
        raise CharacterArchiveError("bio.json has no character_id")
    return character_id.strip()


def build_archive(
    character_dir: Path | str,
    destination: Path | str | None = None,
) -> Path:
    """Build a deterministic archive from a character directory.

    Returns the archive path. Building twice from unchanged input produces
    byte-identical output.
    """

    source = Path(character_dir)
    if not source.is_dir():
        raise CharacterArchiveError(f"not a character directory: {source}")

    members: dict[str, bytes] = {}
    for name in ALL_MEMBERS:
        path = source / name
        if path.exists():
            members[name] = _read_member_file(path)
        elif name in REQUIRED_MEMBERS:
            raise CharacterArchiveError(f"character directory is missing {name}")

    character_id = _character_id(members["bio.json"])

    manifest: dict[str, Any] = {
        "schema": ARCHIVE_SCHEMA,
        "character_id": character_id,
        "members": {name: _digest(data) for name, data in sorted(members.items())},
        "member_bytes": {name: len(data) for name, data in sorted(members.items())},
    }
    # The archive digest covers the manifest, which covers every member — one
    # value to quote when saying which character shipped.
    manifest["archive_sha256"] = _digest(_canonical_json(manifest))

    out = Path(destination) if destination else source.with_suffix(ARCHIVE_SUFFIX)
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as zf:
        for name, data in [(MANIFEST_NAME, _canonical_json(manifest))] + sorted(members.items()):
            info = zipfile.ZipInfo(name, date_time=_FIXED_DATE)
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o644 << 16
            zf.writestr(info, data)
    payload = buffer.getvalue()
    if len(payload) > MAX_ARCHIVE_BYTES:
        raise CharacterArchiveError("archive exceeds the size bound")
    out.write_bytes(payload)
    return out


def read_manifest(archive_path: Path | str) -> dict[str, Any]:
    """Return the manifest without extracting anything."""
    path = Path(archive_path)
    if path.stat().st_size > MAX_ARCHIVE_BYTES:
        raise CharacterArchiveError("archive exceeds the size bound")
    try:
        with zipfile.ZipFile(path) as zf:
            raw = zf.read(MANIFEST_NAME)
    except (KeyError, zipfile.BadZipFile) as exc:
        raise CharacterArchiveError(f"not a readable character archive: {exc}") from exc
    try:
        manifest = json.loads(raw.decode("utf-8"))
    except (ValueError, UnicodeDecodeError) as exc:
        raise CharacterArchiveError(f"manifest is not valid JSON: {exc}") from exc
    if not isinstance(manifest, dict) or manifest.get("schema") != ARCHIVE_SCHEMA:
        raise CharacterArchiveError("archive schema is unsupported")
    return manifest


def verify_archive(archive_path: Path | str) -> dict[str, Any]:
    """Fail closed unless every member matches the manifest.

    Returns the verified manifest. Raises `CharacterArchiveError` on any
    mismatch, missing member, or unexpected extra member.
    """

    path = Path(archive_path)
    manifest = read_manifest(path)

    recorded = manifest.get("members")
    if not isinstance(recorded, dict) or not recorded:
        raise CharacterArchiveError("manifest records no members")

    # The archive digest must cover exactly this manifest.
    stated = manifest.get("archive_sha256")
    checkable = {key: value for key, value in manifest.items() if key != "archive_sha256"}
    if not isinstance(stated, str) or stated != _digest(_canonical_json(checkable)):
        raise CharacterArchiveError("archive digest does not match its manifest")

    with zipfile.ZipFile(path) as zf:
        present = {name for name in zf.namelist() if name != MANIFEST_NAME}
        expected = set(recorded)
        if present != expected:
            missing = sorted(expected - present)
            extra = sorted(present - expected)
            raise CharacterArchiveError(
                f"archive members differ from the manifest; missing={missing} extra={extra}"
            )
        for name in sorted(expected):
            if name not in ALL_MEMBERS:
                raise CharacterArchiveError(f"unexpected member: {name}")
            info = zf.getinfo(name)
            if info.file_size > MAX_MEMBER_BYTES:
                raise CharacterArchiveError(f"{name} exceeds the member size bound")
            data = zf.read(name)
            if _digest(data) != recorded[name]:
                raise CharacterArchiveError(f"{name} does not match its recorded digest")
    for name in REQUIRED_MEMBERS:
        if name not in recorded:
            raise CharacterArchiveError(f"archive is missing required member {name}")
    return manifest


def extract_archive(archive_path: Path | str, destination: Path | str) -> Path:
    """Verify, then extract into `destination/<character_id>/`."""
    manifest = verify_archive(archive_path)
    target = Path(destination) / manifest["character_id"]
    target.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(Path(archive_path)) as zf:
        for name in sorted(manifest["members"]):
            # Names are validated against ALL_MEMBERS above, so there is no
            # path traversal surface here; write by explicit name regardless.
            (target / Path(name).name).write_bytes(zf.read(name))
    return target


def load_character(archive_path: Path | str) -> dict[str, Any]:
    """Verify and return the character's parsed members, without touching disk."""
    manifest = verify_archive(archive_path)
    character: dict[str, Any] = {"character_id": manifest["character_id"], "members": {}}
    with zipfile.ZipFile(Path(archive_path)) as zf:
        for name in sorted(manifest["members"]):
            character["members"][name] = json.loads(zf.read(name).decode("utf-8"))
    return character


def _main(argv: list[str]) -> int:
    import argparse

    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = parser.add_subparsers(dest="command", required=True)
    build = sub.add_parser("build", help="build an archive from a character directory")
    build.add_argument("directory")
    build.add_argument("--out", default=None)
    verify = sub.add_parser("verify", help="verify an archive")
    verify.add_argument("archive")
    args = parser.parse_args(argv)

    if args.command == "build":
        out = build_archive(args.directory, args.out)
        manifest = verify_archive(out)
        print(json.dumps({
            "built": str(out),
            "character_id": manifest["character_id"],
            "archive_sha256": manifest["archive_sha256"],
            "members": manifest["members"],
        }, indent=2, sort_keys=True))
        return 0

    manifest = verify_archive(args.archive)
    print(json.dumps({"verified": True, **manifest}, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    import sys

    raise SystemExit(_main(sys.argv[1:]))
