"""Confined content-addressed object storage for Unisync."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

from .contracts import HEX_SHA256_RE, TransferContext
from .errors import BackpressureError, DigestMismatchError, InvalidFrameError, StorageSecurityError
from .framing import DEFAULT_LIMITS, FrameLimits


def _ensure_confined(root: Path, path: Path) -> None:
    root_resolved = root.resolve(strict=True)
    try:
        path.resolve(strict=False).relative_to(root_resolved)
    except ValueError as exc:
        raise StorageSecurityError("path escapes object store root") from exc


def _reject_symlink(path: Path) -> None:
    if path.is_symlink():
        raise StorageSecurityError(f"symlink is not allowed in object store path: {path}")


def _validate_digest(digest: str) -> str:
    if not HEX_SHA256_RE.fullmatch(digest):
        raise StorageSecurityError("object digest must be lowercase SHA-256 hex")
    return digest


class ContentAddressedStore:
    """CAS rooted in a caller-provided directory with restrictive permissions."""

    def __init__(self, root: Path | str) -> None:
        self.root = Path(root)
        if self.root.exists() and self.root.is_symlink():
            raise StorageSecurityError("object store root must not be a symlink")
        self.root.mkdir(mode=0o700, parents=True, exist_ok=True)
        os.chmod(self.root, 0o700)
        self._objects = self.root / "objects"
        self._partials = self.root / ".partials"
        self._tmp = self.root / ".tmp"
        for directory in (self._objects, self._partials, self._tmp):
            _ensure_confined(self.root, directory)
            _reject_symlink(directory)
            directory.mkdir(mode=0o700, parents=True, exist_ok=True)
            os.chmod(directory, 0o700)

    def object_path(self, digest: str) -> Path:
        digest = _validate_digest(digest)
        directory = self._objects / digest[:2]
        _ensure_confined(self.root, directory)
        _reject_symlink(self._objects)
        if directory.exists():
            _reject_symlink(directory)
        return directory / digest

    def has(self, digest: str) -> bool:
        path = self.object_path(digest)
        if path.exists():
            _reject_symlink(path)
            return path.is_file()
        return False

    def stat_size(self, digest: str) -> int:
        path = self.object_path(digest)
        if not path.exists():
            raise FileNotFoundError(digest)
        _reject_symlink(path)
        return path.stat().st_size

    def read_bytes(self, digest: str) -> bytes:
        path = self.object_path(digest)
        _reject_symlink(path)
        data = path.read_bytes()
        if hashlib.sha256(data).hexdigest() != digest:
            raise DigestMismatchError("stored object digest mismatch")
        return data

    def open_read(self, digest: str, *, offset: int = 0):
        path = self.object_path(digest)
        _reject_symlink(path)
        handle = path.open("rb")
        handle.seek(offset)
        return handle

    def put_bytes(self, payload: bytes) -> str:
        digest = hashlib.sha256(payload).hexdigest()
        final_path = self.object_path(digest)
        final_path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        os.chmod(final_path.parent, 0o700)
        if final_path.exists():
            _reject_symlink(final_path)
            if hashlib.sha256(final_path.read_bytes()).hexdigest() != digest:
                raise DigestMismatchError("existing content-addressed object is corrupt")
            return digest
        temp_path = self._tmp / f"{digest}.{os.getpid()}.tmp"
        _ensure_confined(self.root, temp_path)
        fd = os.open(temp_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        try:
            with os.fdopen(fd, "wb") as handle:
                handle.write(payload)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temp_path, final_path)
            os.chmod(final_path, 0o400)
        finally:
            if temp_path.exists():
                temp_path.unlink()
        return digest

    def start_receive(self, context: TransferContext, *, limits: FrameLimits = DEFAULT_LIMITS) -> "ObjectAssembler":
        return ObjectAssembler(self, context, limits=limits)

    def partial_paths_for(self, context: TransferContext) -> tuple[Path, Path]:
        stem = f"{context.object_sha256}.{context.transfer_id}"
        part_path = self._partials / f"{stem}.part"
        meta_path = self._partials / f"{stem}.json"
        _ensure_confined(self.root, part_path)
        _ensure_confined(self.root, meta_path)
        return part_path, meta_path


class ObjectAssembler:
    """Assemble bounded chunks into one verified content-addressed object."""

    def __init__(self, store: ContentAddressedStore, context: TransferContext, *, limits: FrameLimits = DEFAULT_LIMITS) -> None:
        self.store = store
        self.context = context
        self.limits = limits
        self._part_path, self._meta_path = store.partial_paths_for(context)
        for path in (self._part_path, self._meta_path):
            if path.exists():
                _reject_symlink(path)
        self._chunk_hashes: dict[int, str] = {}
        self._pending: dict[int, tuple[bytes, str]] = {}
        self._pending_bytes = 0
        self._offset = 0
        self._load_or_create()

    @property
    def offset(self) -> int:
        return self._offset

    def _load_or_create(self) -> None:
        if self._meta_path.exists() or self._part_path.exists():
            if not self._meta_path.exists() or not self._part_path.exists():
                self.abort()
                raise StorageSecurityError("partial object metadata/data mismatch")
            meta = json.loads(self._meta_path.read_text(encoding="utf-8"))
            if meta.get("context") != self.context.to_wire():
                raise StorageSecurityError("partial object belongs to a different transfer context")
            self._offset = int(meta.get("offset", 0))
            self._chunk_hashes = {int(key): str(value) for key, value in meta.get("chunk_hashes", {}).items()}
            actual_size = self._part_path.stat().st_size
            if actual_size != self._offset:
                self.abort()
                raise StorageSecurityError("partial object size does not match metadata")
            return
        fd = os.open(self._part_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        os.close(fd)
        self._persist_meta()

    def _persist_meta(self) -> None:
        payload = {
            "context": self.context.to_wire(),
            "offset": self._offset,
            "chunk_hashes": {str(key): value for key, value in sorted(self._chunk_hashes.items())},
        }
        temp_path = self._meta_path.with_suffix(".json.tmp")
        fd = os.open(temp_path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                json.dump(payload, handle, sort_keys=True, separators=(",", ":"))
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temp_path, self._meta_path)
            os.chmod(self._meta_path, 0o600)
        finally:
            if temp_path.exists():
                temp_path.unlink()

    def receive_chunk(self, *, offset: int, payload: bytes, chunk_sha256: str) -> bool:
        if offset < 0:
            raise InvalidFrameError("chunk offset must be non-negative")
        if offset + len(payload) > self.context.byte_length:
            raise InvalidFrameError("chunk exceeds declared total length")
        actual = hashlib.sha256(payload).hexdigest()
        if actual != chunk_sha256:
            raise DigestMismatchError("chunk digest mismatch")
        if offset < self._offset:
            known = self._chunk_hashes.get(offset)
            if known == chunk_sha256 and offset + len(payload) <= self._offset:
                return False
            raise InvalidFrameError("conflicting duplicate chunk")
        if offset > self._offset:
            existing = self._pending.get(offset)
            if existing is not None:
                if existing[1] == chunk_sha256:
                    return False
                raise InvalidFrameError("conflicting pending duplicate chunk")
            if self._pending_bytes + len(payload) > self.limits.max_pending_bytes:
                raise BackpressureError("reordered chunk buffer exceeds pending byte cap")
            self._pending[offset] = (payload, chunk_sha256)
            self._pending_bytes += len(payload)
            return False
        self._write_contiguous(offset, payload, chunk_sha256)
        self._flush_pending()
        return True

    def _write_contiguous(self, offset: int, payload: bytes, chunk_sha256: str) -> None:
        if offset != self._offset:
            raise InvalidFrameError("non-contiguous chunk write")
        with self._part_path.open("r+b") as handle:
            handle.seek(offset)
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        self._chunk_hashes[offset] = chunk_sha256
        self._offset += len(payload)
        self._persist_meta()

    def _flush_pending(self) -> None:
        while self._offset in self._pending:
            payload, digest = self._pending.pop(self._offset)
            self._pending_bytes -= len(payload)
            self._write_contiguous(self._offset, payload, digest)

    def finalize(self) -> str:
        if self._offset != self.context.byte_length:
            self.abort()
            raise DigestMismatchError("partial object length does not match transfer context")
        actual = hashlib.sha256(self._part_path.read_bytes()).hexdigest()
        if actual != self.context.object_sha256:
            self.abort()
            raise DigestMismatchError("final object digest mismatch")
        final_path = self.store.object_path(actual)
        final_path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        os.chmod(final_path.parent, 0o700)
        if final_path.exists():
            _reject_symlink(final_path)
            if hashlib.sha256(final_path.read_bytes()).hexdigest() != actual:
                self.abort()
                raise DigestMismatchError("existing final object is corrupt")
            self.abort()
            return actual
        os.replace(self._part_path, final_path)
        os.chmod(final_path, 0o400)
        if self._meta_path.exists():
            self._meta_path.unlink()
        return actual

    def abort(self) -> None:
        for path in (self._part_path, self._meta_path):
            try:
                if path.exists() or path.is_symlink():
                    path.unlink()
            except FileNotFoundError:
                pass
