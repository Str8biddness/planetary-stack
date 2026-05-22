"""Command line interface for Synthesus Knowledge Cloud."""

from __future__ import annotations

import argparse
import json
import logging
import sys
from dataclasses import asdict
from pathlib import Path

from . import __version__
from .build import run_build, stamp_existing_manifest
from .manifest import (
    DEFAULT_SOURCE_ROOTS,
    build_manifest,
    validate_manifest,
    verify_source_manifest,
    write_manifest,
)
from .mirrors import resolve_mirrors
from .profiles import load_profile, summarize_profile
from .provenance import capture_provenance
from .source_planes import validate_source_planes
from .status import status_report
from .sync import DEFAULT_BASE_URL, SyncReport, sync_bundle


# ---------------------------------------------------------------------------
# commands
# ---------------------------------------------------------------------------


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


def cmd_verify_source_manifest(args: argparse.Namespace) -> int:
    result = verify_source_manifest(args.root, args.manifest)
    for failure in result.failures:
        print(f"FAIL {failure}", file=sys.stderr)
    if result.ok:
        print(f"verified {result.checked} source files against {args.manifest}")
        return 0
    return 1


def _print_sync(report: SyncReport, *, verbose: bool) -> None:
    if verbose:
        for r in report.results:
            mirror = f" via {r.mirror}" if r.mirror else ""
            print(f"{r.status} {r.path}{mirror}")
    else:
        for msg in report.to_messages():
            print(msg)
    for failure in report.failures:
        print(f"FAIL {failure}", file=sys.stderr)


def cmd_sync(args: argparse.Namespace) -> int:
    mirrors = resolve_mirrors(args.base_url, args.mirror or None)
    report = sync_bundle(
        args.dest,
        mirrors=mirrors,
        manifest_name=args.manifest_name,
        force=args.force,
        workers=args.workers,
        retries=args.retries,
        timeout=args.timeout,
    )
    _print_sync(report, verbose=args.verbose)
    return 0 if report.ok else 1


def cmd_status(args: argparse.Namespace) -> int:
    mirrors = resolve_mirrors(args.base_url, args.mirror or None)
    report = status_report(
        args.local,
        mirrors=mirrors,
        manifest_name=args.manifest_name,
        deep=not args.shallow,
    )
    if args.json:
        payload = {
            "local_root": str(report.local_root),
            "mirrors": report.mirrors,
            "remote_mirror": report.remote_mirror,
            "remote_manifest_present": report.remote_manifest_present,
            "remote_generated_at": report.remote_generated_at,
            "remote_revised_at": report.remote_revised_at,
            "artifacts": [asdict(a) for a in report.artifacts],
            "extras": report.extras,
        }
        print(json.dumps(payload, indent=2, ensure_ascii=False))
    else:
        print(report.summary())
        for drift in report.drift:
            print(f"{drift.state}\t{drift.path}")
        for extra in report.extras:
            print(f"extra\t{extra}")
    return 0 if report.remote_manifest_present and not report.drift else (2 if not report.remote_manifest_present else 1)


def cmd_inspect_profile(args: argparse.Namespace) -> int:
    profile = load_profile(args.profile)
    print(summarize_profile(profile))
    if args.json:
        print(json.dumps(profile, indent=2, ensure_ascii=False))
    return 0


def cmd_build(args: argparse.Namespace) -> int:
    report = run_build(
        args.profile,
        repo_root=args.repo_root,
        artifact_root=args.artifact_root,
        execute=args.execute,
    )
    payload = {
        "profile": report.plan.to_dict(),
        "executed": report.executed,
        "exit_code": report.exit_code,
        "manifest_path": str(report.manifest_path) if report.manifest_path else None,
        "artifact_count": report.artifact_count,
        "provenance": report.provenance,
    }
    print(json.dumps(payload, indent=2, ensure_ascii=False))
    if report.stderr_tail:
        print(report.stderr_tail, file=sys.stderr)
    return 0 if report.ok else 1


def cmd_stamp_manifest(args: argparse.Namespace) -> int:
    path, manifest = stamp_existing_manifest(
        repo_root=args.repo_root,
        artifact_root=args.artifact_root,
        profile_path=args.profile,
    )
    print(f"wrote {path} ({len(manifest.get('artifacts', []))} artifacts, profile={manifest.get('build', {}).get('profile')})")
    return 0


def cmd_bootstrap(args: argparse.Namespace) -> int:
    from .bootstrap import bootstrap

    mirrors = resolve_mirrors(args.base_url, args.mirror or None)
    report = bootstrap(
        args.target,
        mirrors=mirrors,
        manifest_name=args.manifest_name,
        workers=args.workers,
        force=args.force,
    )
    _print_sync(report.sync, verbose=args.verbose)
    print(
        f"bootstrap target={report.target} verified={report.verified} "
        f"marker={report.marker_path}"
    )
    return 0 if report.ok else 1


def cmd_info(args: argparse.Namespace) -> int:
    mirrors = resolve_mirrors(args.base_url, args.mirror or None)
    provenance = capture_provenance(
        args.repo_root,
        artifact_root=args.artifact_root,
        profile=None,
        generated_by="synthesus-kc info",
    )
    payload = {
        "package_version": __version__,
        "mirrors": mirrors,
        "repo_root": str(Path(args.repo_root).resolve()),
        "artifact_root": str(Path(args.artifact_root).resolve()) if args.artifact_root else None,
        "provenance": provenance.to_dict(),
    }
    print(json.dumps(payload, indent=2, ensure_ascii=False))
    return 0


def cmd_serve(args: argparse.Namespace) -> int:
    from .serve import serve

    serve(args.root, host=args.host, port=args.port)
    return 0


# ---------------------------------------------------------------------------
# parser
# ---------------------------------------------------------------------------


def _add_mirror_flags(p: argparse.ArgumentParser) -> None:
    p.add_argument("--base-url", default=None, help="Primary mirror base URL")
    p.add_argument("--mirror", action="append", default=[], help="Additional mirror (repeatable)")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="synthesus-kc", description="Synthesus Knowledge Cloud utility CLI")
    parser.add_argument("--version", action="version", version=__version__)
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

    verify_src = sub.add_parser("verify-source-manifest", help="Re-hash every file in the source manifest")
    verify_src.add_argument("--root", default=".")
    verify_src.add_argument("--manifest", default="manifests/source_manifest.json")
    verify_src.set_defaults(func=cmd_verify_source_manifest)

    sync = sub.add_parser("sync", help="Download and verify the runtime bundle")
    sync.add_argument("--dest", default="./data")
    sync.add_argument("--manifest-name", default="manifest.json")
    sync.add_argument("--force", action="store_true")
    sync.add_argument("--workers", type=int, default=4)
    sync.add_argument("--retries", type=int, default=3)
    sync.add_argument("--timeout", type=int, default=120)
    sync.add_argument("--verbose", "-v", action="store_true")
    _add_mirror_flags(sync)
    sync.set_defaults(func=cmd_sync)

    status = sub.add_parser("status", help="Compare a local data root against the remote manifest")
    status.add_argument("--local", default="./data")
    status.add_argument("--manifest-name", default="manifest.json")
    status.add_argument("--shallow", action="store_true", help="Skip sha256 recomputation; size-only check")
    status.add_argument("--json", action="store_true")
    _add_mirror_flags(status)
    status.set_defaults(func=cmd_status)

    inspect_profile = sub.add_parser("inspect-profile", help="Load and summarize a build profile")
    inspect_profile.add_argument("profile")
    inspect_profile.add_argument("--json", action="store_true")
    inspect_profile.set_defaults(func=cmd_inspect_profile)

    build_cmd = sub.add_parser("build", help="Plan or execute a profile-aware rebuild of the artifact bundle")
    build_cmd.add_argument("profile")
    build_cmd.add_argument("--repo-root", default=".")
    build_cmd.add_argument("--artifact-root", default=None)
    build_cmd.add_argument("--execute", action="store_true", help="Actually run the heavy pipeline")
    build_cmd.set_defaults(func=cmd_build)

    stamp_cmd = sub.add_parser("stamp-manifest", help="Rebuild artifacts/manifest.json and stamp provenance without rerunning the pipeline")
    stamp_cmd.add_argument("--repo-root", default=".")
    stamp_cmd.add_argument("--artifact-root", default=None)
    stamp_cmd.add_argument("--profile", default=None)
    stamp_cmd.set_defaults(func=cmd_stamp_manifest)

    bootstrap_cmd = sub.add_parser("bootstrap", help="One-shot install for local Synthesus runtimes")
    bootstrap_cmd.add_argument("--target", default=None, help="Target data root (default: $SYNTHESUS_DATA_DIR or ~/.synthesus/data)")
    bootstrap_cmd.add_argument("--manifest-name", default="manifest.json")
    bootstrap_cmd.add_argument("--workers", type=int, default=4)
    bootstrap_cmd.add_argument("--force", action="store_true")
    bootstrap_cmd.add_argument("--verbose", "-v", action="store_true")
    _add_mirror_flags(bootstrap_cmd)
    bootstrap_cmd.set_defaults(func=cmd_bootstrap)

    info_cmd = sub.add_parser("info", help="Print package, mirror, and provenance diagnostics")
    info_cmd.add_argument("--repo-root", default=".")
    info_cmd.add_argument("--artifact-root", default=None)
    _add_mirror_flags(info_cmd)
    info_cmd.set_defaults(func=cmd_info)

    serve_cmd = sub.add_parser("serve", help="Run a tiny HTTP server over the artifacts directory (dev mirror)")
    serve_cmd.add_argument("--root", default="artifacts")
    serve_cmd.add_argument("--host", default="127.0.0.1")
    serve_cmd.add_argument("--port", type=int, default=8765)
    serve_cmd.set_defaults(func=cmd_serve)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if getattr(args, "verbose", False):
        logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
