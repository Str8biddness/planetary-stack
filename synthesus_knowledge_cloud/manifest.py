"""Manifest creation and validation utilities for Knowledge Cloud artifacts."""

from __future__ import annotations

import hashlib
import json
import sys
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
    "corpus",
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
        if rel_root in (".", ""):
            base = root
            for path in sorted(base.rglob("*")):
                if not path.is_file():
                    continue
                rel = path.relative_to(root).as_posix()
                if rel in excluded:
                    continue
                yield path
            continue
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
    # When listing the artifact root flat (".") we never want manifest.json itself.
    if include_roots in (["."], (".",)):
        exclude.add("manifest.json")
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
    failures.extend(_validate_runtime_bundle_semantics(root_path))
    return ValidationResult(checked=checked, failures=tuple(failures))


def validate_runtime_bundle_semantics(root: str | Path) -> ValidationResult:
    """Validate cross-artifact runtime compatibility before publishing/stamping."""
    root_path = Path(root).resolve()
    semantic_paths = [
        root_path / "faiss.index",
        root_path / "faiss_metadata.json",
        root_path / "models" / "swarm_embedder.pkl",
    ]
    checked = sum(1 for path in semantic_paths if path.exists())
    return ValidationResult(checked=checked, failures=tuple(_validate_runtime_bundle_semantics(root_path)))


def _validate_runtime_bundle_semantics(root: Path) -> list[str]:
    """Validate artifact relationships that hashes alone cannot prove."""
    failures: list[str] = []
    faiss_path = root / "faiss.index"
    metadata_path = root / "faiss_metadata.json"
    embedder_path = root / "models" / "swarm_embedder.pkl"

    if faiss_path.exists():
        try:
            import faiss

            index = faiss.read_index(str(faiss_path))
        except Exception as exc:
            return [f"FAISS index unreadable: {exc}"]

        if metadata_path.exists():
            try:
                metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
                metadata_count = len(metadata) if isinstance(metadata, (list, dict)) else -1
            except Exception as exc:
                failures.append(f"faiss_metadata.json unreadable: {exc}")
            else:
                if metadata_count != int(index.ntotal):
                    failures.append(
                        f"FAISS/metadata count mismatch: faiss={int(index.ntotal)}, metadata={metadata_count}"
                    )

        if embedder_path.exists():
            try:
                joblib = sys.modules.get("joblib")
                if joblib is None:
                    import joblib as loaded_joblib

                    joblib = loaded_joblib
                model = joblib.load(embedder_path)
                embedder_dim = int(model.get("dim")) if isinstance(model, dict) and "dim" in model else None
            except Exception as exc:
                failures.append(f"swarm embedder unreadable: {exc}")
            else:
                if embedder_dim is None:
                    failures.append("swarm embedder missing persisted dim")
                elif embedder_dim != int(index.d):
                    failures.append(f"FAISS/embedder dim mismatch: faiss={int(index.d)}, embedder={embedder_dim}")

    return failures


def verify_source_manifest(
    repo_root: str | Path = ".",
    manifest_path: str | Path = "manifests/source_manifest.json",
) -> ValidationResult:
    """Re-hash every file listed in the source manifest and report drift."""
    root_path = Path(repo_root).resolve()
    manifest = load_manifest(root_path / manifest_path)
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
        if sha256_file(path) != item["sha256"]:
            failures.append(f"sha256 mismatch {rel}")
    return ValidationResult(checked=checked, failures=tuple(failures))
