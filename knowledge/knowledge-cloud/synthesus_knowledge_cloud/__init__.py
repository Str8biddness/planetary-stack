"""Synthesus Knowledge Cloud packaging and artifact utilities."""

__version__ = "0.3.0"

from .manifest import build_manifest, sha256_file, validate_manifest, write_manifest
from .provenance import (
    Provenance,
    capture_provenance,
    dataset_versions,
    embedder_fingerprint,
    git_info,
    stamp_manifest,
)
from .sync import DEFAULT_BASE_URL, DEFAULT_MIRRORS, sync_bundle, resolve_mirrors

__all__ = [
    "DEFAULT_BASE_URL",
    "DEFAULT_MIRRORS",
    "Provenance",
    "build_manifest",
    "capture_provenance",
    "dataset_versions",
    "embedder_fingerprint",
    "git_info",
    "resolve_mirrors",
    "sha256_file",
    "stamp_manifest",
    "sync_bundle",
    "validate_manifest",
    "write_manifest",
    "__version__",
]
