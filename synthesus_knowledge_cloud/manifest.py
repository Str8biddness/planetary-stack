"""Manifest creation and validation utilities for Knowledge Cloud artifacts."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, Sequence

DEFAULT_SOURCE_ROOTS = [
    "sources",
    "pipelines",
    "patterns",
    "synthetic",
    "grounding_corpus",
    "support_models",
]


@dataclass(frozen=True)
class ValidationResult:
    checked: int
    failures: tuple[str, ...]

    @property
    def ok(self) -> bool:
        return not self.failures


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def iter_manifest_files(root: Path, include_roots: Sequence[str], exclude: Iterable[str] = ()) -> Iterable[Path]:
    excluded = {item.replace("\\", "/") for item in exclude}
    for rel_root in include_roots:
        base = root / rel_root
        if not base.exists():
            continue
        for path in sorted(base.rglob("*")):
            if not path.is_file():
                continue
            rel = path.relative_to(root).as_posix()
            if rel in excluded:
                continue
            yield path


def build_manifest(
    root: str | Path,
    include_roots: Sequence[str],
    *,
    kind: str = "synthesus-knowledge-artifacts",
    version: str = "1",
    output_path: str | None = None,
    extra: dict | None = None,
) -> dict:
    root_path = Path(root).resolve()
    exclude = {output_path} if output_path else set()
    artifacts = []
    for path in iter_manifest_files(root_path, include_roots, exclude=exclude):
        artifacts.append(
            {
                "path": path.relative_to(root_path).as_posix(),
                "size": path.stat().st_size,
                "sha256": sha256_file(path),
            }
        )
    manifest = {
        "version": version,
        "kind": kind,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "roots": list(include_roots),
        "artifacts": artifacts,
    }
    if extra:
        manifest.update(extra)
    return manifest


def write_manifest(manifest: dict, output: str | Path) -> Path:
    path = Path(output).resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return path


def load_manifest(path: str | Path) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def validate_manifest(root: str | Path, manifest_name: str = "manifest.json") -> ValidationResult:
    root_path = Path(root).resolve()
    manifest = load_manifest(root_path / manifest_name)
    failures: list[str] = []
    checked = 0
    for item in manifest.get("artifacts", []):
        checked += 1
        rel = item["path"].replace("\\", "/")
        path = root_path / rel
        if not path.exists():
            failures.append(f"missing {rel}")
            continue
        size = path.stat().st_size
        if size != int(item["size"]):
            failures.append(f"size mismatch {rel}: expected {item['size']}, got {size}")
            continue
        digest = sha256_file(path)
        if digest != item["sha256"]:
            failures.append(f"sha256 mismatch {rel}")
    return ValidationResult(checked=checked, failures=tuple(failures))
