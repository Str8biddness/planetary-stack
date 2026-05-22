"""Command line interface for Synthesus Knowledge Cloud."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .manifest import DEFAULT_SOURCE_ROOTS, build_manifest, validate_manifest, write_manifest
from .profiles import load_profile, summarize_profile
from .source_planes import validate_source_planes
from .sync import DEFAULT_BASE_URL, sync_bundle


def cmd_validate(args: argparse.Namespace) -> int:
    result = validate_manifest(args.root, args.manifest_name)
    for failure in result.failures:
        print(f"FAIL {failure}", file=sys.stderr)
    if result.ok:
        print(f"validated {result.checked} artifacts under {Path(args.root).resolve()}")
        return 0
    return 1


def cmd_source_manifest(args: argparse.Namespace) -> int:
    manifest = build_manifest(
        args.root,
        args.include_root or DEFAULT_SOURCE_ROOTS,
        kind="synthesus-knowledge-source-plane",
        output_path=args.output,
    )
    out = write_manifest(manifest, Path(args.root).resolve() / args.output)
    print(f"wrote {out} ({len(manifest['artifacts'])} files)")
    return 0


def cmd_validate_sources(args: argparse.Namespace) -> int:
    result = validate_source_planes(args.root)
    for error in result.errors:
        print(f"ERROR: {error}", file=sys.stderr)
    if result.ok:
        print(
            f"source planes ok: {result.required_paths} required paths, "
            f"{result.character_pattern_banks} character pattern banks"
        )
        return 0
    return 1


def cmd_sync(args: argparse.Namespace) -> int:
    for message in sync_bundle(args.dest, base_url=args.base_url, manifest_name=args.manifest_name, force=args.force):
        print(message)
    return 0


def cmd_inspect_profile(args: argparse.Namespace) -> int:
    profile = load_profile(args.profile)
    print(summarize_profile(profile))
    if args.json:
        print(json.dumps(profile, indent=2, ensure_ascii=False))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="synthesus-kc", description="Synthesus Knowledge Cloud utility CLI")
    sub = parser.add_subparsers(dest="command", required=True)

    validate = sub.add_parser("validate", help="Validate runtime artifacts against manifest.json")
    validate.add_argument("--root", default="artifacts")
    validate.add_argument("--manifest-name", default="manifest.json")
    validate.set_defaults(func=cmd_validate)

    source_manifest = sub.add_parser("build-source-manifest", help="Build source-plane manifest")
    source_manifest.add_argument("--root", default=".")
    source_manifest.add_argument("--output", default="manifests/source_manifest.json")
    source_manifest.add_argument("--include-root", action="append")
    source_manifest.set_defaults(func=cmd_source_manifest)

    validate_sources = sub.add_parser("validate-sources", help="Validate source/pipeline/pattern planes")
    validate_sources.add_argument("--root", default=".")
    validate_sources.set_defaults(func=cmd_validate_sources)

    sync = sub.add_parser("sync", help="Download and verify the runtime bundle")
    sync.add_argument("--dest", default="./data")
    sync.add_argument("--base-url", default=DEFAULT_BASE_URL)
    sync.add_argument("--manifest-name", default="manifest.json")
    sync.add_argument("--force", action="store_true")
    sync.set_defaults(func=cmd_sync)

    inspect_profile = sub.add_parser("inspect-profile", help="Load and summarize a build profile")
    inspect_profile.add_argument("profile")
    inspect_profile.add_argument("--json", action="store_true")
    inspect_profile.set_defaults(func=cmd_inspect_profile)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
