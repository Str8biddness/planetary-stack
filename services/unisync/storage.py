"""Confined content-addressed object storage for Unisync."""

from __future__ import annotations

import hashlib
import errno
import json
import os
import secrets
import stat
from pathlib import Path

from .contracts import HEX_SHA256_RE, TransferContext
from .errors import BackpressureError, DigestMismatchError, InvalidFrameError, StorageSecurityError
from .framing import DEFAULT_LIMITS, FrameLimits


O_NOFOLLOW = getattr(os, "O_NOFOLLOW", 0)
O_DIRECTORY = getattr(os, "O_DIRECTORY", 0)


def _fsync_fd(fd: int) -> None:
    os.fsync(fd)


def _fsync_directory(path: Path) -> None:
    flags = os.O_RDONLY | O_DIRECTORY
    fd = os.open(path, flags)
    try:
        _fsync_fd(fd)
    finally:
        os.close(fd)


def _ensure_confined(root: Path, path: Path) -> None:
    root_resolved = root.resolve(strict=True)
    try:
        path.resolve(strict=False).relative_to(root_resolved)
    except ValueError as exc:
        raise StorageSecurityError("path escapes object store root") from exc


def _reject_symlink(path: Path) -> None:
    if path.is_symlink():
        raise StorageSecurityError(f"symlink is not allowed in object store path: {path}")


def _lstat_existing(path: Path) -> os.stat_result | None:
    try:
        return os.lstat(path)
    except FileNotFoundError:
        return None


def _ensure_regular_lstat(path: Path) -> os.stat_result:
    info = _lstat_existing(path)
    if info is None:
        raise FileNotFoundError(path)
    if stat.S_ISLNK(info.st_mode):
        raise StorageSecurityError(f"symlink is not allowed in object store path: {path}")
    if not stat.S_ISREG(info.st_mode):
        raise StorageSecurityError(f"object store path is not a regular file: {path}")
    return info


def _ensure_safe_directory(path: Path) -> None:
    info = _lstat_existing(path)
    if info is None:
        return
    if stat.S_ISLNK(info.st_mode):
        raise StorageSecurityError(f"symlink is not allowed in object store path: {path}")
    if not stat.S_ISDIR(info.st_mode):
        raise StorageSecurityError(f"object store path is not a directory: {path}")


def _ensure_safe_parent_components(root: Path, path: Path) -> None:
    _ensure_confined(root, path)
    try:
        relative_parent = path.parent.relative_to(root)
    except ValueError as exc:
        raise StorageSecurityError("path escapes object store root") from exc
    current = root
    for part in relative_parent.parts:
        current = current / part
        _ensure_safe_directory(current)


def _ensure_directory(path: Path, root: Path) -> None:
    _ensure_safe_parent_components(root, path)
    path.mkdir(mode=0o700, parents=True, exist_ok=True)
    os.chmod(path, 0o700)
    _ensure_safe_directory(path)


def _open_regular_no_follow(path: Path, flags: int) -> int:
    try:
        fd = os.open(path, flags | O_NOFOLLOW)
    except OSError as exc:
        if exc.errno in {errno.ELOOP, errno.ELOOP if hasattr(errno, "ELOOP") else 40}:
            raise StorageSecurityError(f"symlink is not allowed in object store path: {path}") from exc
        raise
    try:
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode):
            raise StorageSecurityError(f"object store path is not a regular file: {path}")
        return fd
    except Exception:
        os.close(fd)
        raise


def _create_exclusive_regular(path: Path) -> int:
    try:
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | O_NOFOLLOW, 0o600)
    except FileExistsError as exc:
        raise StorageSecurityError(f"temporary object store path already exists: {path}") from exc
    except OSError as exc:
        if exc.errno == errno.ELOOP:
            raise StorageSecurityError(f"symlink is not allowed in object store path: {path}") from exc
        raise
    try:
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode):
            raise StorageSecurityError(f"object store path is not a regular file: {path}")
        return fd
    except Exception:
        os.close(fd)
        raise


def _read_regular_bytes(path: Path) -> bytes:
    fd = _open_regular_no_follow(path, os.O_RDONLY)
    try:
        with os.fdopen(fd, "rb") as handle:
            return handle.read()
    except Exception:
        raise


def _stat_regular_size(path: Path) -> int:
    fd = _open_regular_no_follow(path, os.O_RDONLY)
    try:
        return os.fstat(fd).st_size
    finally:
        os.close(fd)


def _regular_file_exists(path: Path) -> bool:
    info = _lstat_existing(path)
    if info is None:
        return False
    if stat.S_ISLNK(info.st_mode):
        raise StorageSecurityError(f"symlink is not allowed in object store path: {path}")
    if not stat.S_ISREG(info.st_mode):
        raise StorageSecurityError(f"object store path is not a regular file: {path}")
    return True


def _unlink_if_exists(path: Path) -> None:
    try:
        os.unlink(path)
    except FileNotFoundError:
        pass


def _random_tmp_path(directory: Path, stem: str) -> Path:
    return directory / f"{stem}.{secrets.token_hex(16)}.tmp"


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
        self.root = self.root.resolve(strict=True)
        self._objects = self.root / "objects"
        self._partials = self.root / ".partials"
        self._tmp = self.root / ".tmp"
        for directory in (self._objects, self._partials, self._tmp):
            _ensure_confined(self.root, directory)
            _reject_symlink(directory)
            _ensure_directory(directory, self.root)

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
        return _regular_file_exists(path)

    def stat_size(self, digest: str) -> int:
        path = self.object_path(digest)
        return _stat_regular_size(path)

    def read_bytes(self, digest: str) -> bytes:
        path = self.object_path(digest)
        data = _read_regular_bytes(path)
        if hashlib.sha256(data).hexdigest() != digest:
            raise DigestMismatchError("stored object digest mismatch")
        return data

    def open_read(self, digest: str, *, offset: int = 0):
        path = self.object_path(digest)
        fd = _open_regular_no_follow(path, os.O_RDONLY)
        size = os.fstat(fd).st_size
        if offset < 0 or offset > size:
            os.close(fd)
            raise InvalidFrameError("resume offset is outside the stored object")
        handle = os.fdopen(fd, "rb")
        handle.seek(offset)
        return handle

    def put_bytes(self, payload: bytes) -> str:
        digest = hashlib.sha256(payload).hexdigest()
        final_path = self.object_path(digest)
        _ensure_directory(final_path.parent, self.root)
        if _regular_file_exists(final_path):
            if hashlib.sha256(_read_regular_bytes(final_path)).hexdigest() != digest:
                raise DigestMismatchError("existing content-addressed object is corrupt")
            return digest
        temp_path = _random_tmp_path(self._tmp, digest)
        _ensure_confined(self.root, temp_path)
        _ensure_safe_parent_components(self.root, temp_path)
        fd = _create_exclusive_regular(temp_path)
        try:
            with os.fdopen(fd, "wb") as handle:
                handle.write(payload)
                handle.flush()
                _fsync_fd(handle.fileno())
            os.replace(temp_path, final_path)
            os.chmod(final_path, 0o400)
            try:
                published = _read_regular_bytes(final_path)
            except Exception:
                _unlink_if_exists(final_path)
                _fsync_directory(final_path.parent)
                raise
            if hashlib.sha256(published).hexdigest() != digest:
                _unlink_if_exists(final_path)
                _fsync_directory(final_path.parent)
                raise DigestMismatchError("published content-addressed object is corrupt")
            _fsync_directory(final_path.parent)
            _fsync_directory(self._tmp)
        finally:
            _unlink_if_exists(temp_path)
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
        meta_exists = _regular_file_exists(self._meta_path)
        part_exists = _regular_file_exists(self._part_path)
        if meta_exists or part_exists:
            if not meta_exists or not part_exists:
                self.abort()
                raise StorageSecurityError("partial object metadata/data mismatch")
            meta = json.loads(_read_regular_bytes(self._meta_path).decode("utf-8"))
            if meta.get("context") != self.context.to_wire():
                raise StorageSecurityError("partial object belongs to a different transfer context")
            self._offset = int(meta.get("offset", 0))
            if self._offset < 0 or self._offset > self.context.byte_length:
                self.abort()
                raise StorageSecurityError("partial object resume offset is outside the transfer length")
            self._chunk_hashes = {int(key): str(value) for key, value in meta.get("chunk_hashes", {}).items()}
            actual_size = _stat_regular_size(self._part_path)
            if actual_size != self._offset:
                self.abort()
                raise StorageSecurityError("partial object size does not match metadata")
            return
        _ensure_safe_parent_components(self.store.root, self._part_path)
        fd = _create_exclusive_regular(self._part_path)
        os.close(fd)
        self._persist_meta()

    def _persist_meta(self) -> None:
        payload = {
            "context": self.context.to_wire(),
            "offset": self._offset,
            "chunk_hashes": {str(key): value for key, value in sorted(self._chunk_hashes.items())},
        }
        temp_path = _random_tmp_path(self.store._partials, self._meta_path.name)
        _ensure_confined(self.store.root, temp_path)
        _ensure_safe_parent_components(self.store.root, temp_path)
        fd = _create_exclusive_regular(temp_path)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                json.dump(payload, handle, sort_keys=True, separators=(",", ":"))
                handle.flush()
                _fsync_fd(handle.fileno())
            os.replace(temp_path, self._meta_path)
            os.chmod(self._meta_path, 0o600)
            _fsync_directory(self.store._partials)
        finally:
            _unlink_if_exists(temp_path)

    def receive_chunk(self, *, offset: int, payload: bytes, chunk_sha256: str) -> bool:
        if offset < 0:
            raise InvalidFrameError("chunk offset must be non-negative")
        if not payload:
            raise InvalidFrameError("chunk payload must be nonempty")
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
                if existing[0] == payload and existing[1] == chunk_sha256:
                    return False
                raise InvalidFrameError("conflicting pending duplicate chunk")
            end = offset + len(payload)
            for pending_offset, (pending_payload, _) in self._pending.items():
                pending_end = pending_offset + len(pending_payload)
                if offset < pending_end and pending_offset < end:
                    raise InvalidFrameError("pending chunk overlaps an existing pending span")
            if len(self._pending) >= self.limits.max_pending_chunks:
                raise BackpressureError("reordered chunk buffer exceeds pending entry cap")
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
        fd = _open_regular_no_follow(self._part_path, os.O_RDWR)
        with os.fdopen(fd, "r+b") as handle:
            handle.seek(offset)
            handle.write(payload)
            handle.flush()
            _fsync_fd(handle.fileno())
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
        if self._pending:
            self.abort()
            raise InvalidFrameError("cannot finalize with pending non-contiguous chunks")
        part_stat = _ensure_regular_lstat(self._part_path)
        part_data = _read_regular_bytes(self._part_path)
        actual = hashlib.sha256(part_data).hexdigest()
        if actual != self.context.object_sha256:
            self.abort()
            raise DigestMismatchError("final object digest mismatch")
        final_path = self.store.object_path(actual)
        _ensure_directory(final_path.parent, self.store.root)
        if _regular_file_exists(final_path):
            if hashlib.sha256(_read_regular_bytes(final_path)).hexdigest() != actual:
                self.abort()
                raise DigestMismatchError("existing final object is corrupt")
            self.abort()
            return actual
        current_part = _ensure_regular_lstat(self._part_path)
        if (current_part.st_dev, current_part.st_ino, current_part.st_size) != (
            part_stat.st_dev,
            part_stat.st_ino,
            part_stat.st_size,
        ):
            self.abort()
            raise StorageSecurityError("partial object changed during final publication")
        os.replace(self._part_path, final_path)
        os.chmod(final_path, 0o400)
        try:
            published = _read_regular_bytes(final_path)
        except Exception:
            _unlink_if_exists(final_path)
            _fsync_directory(final_path.parent)
            self.abort()
            raise
        if hashlib.sha256(published).hexdigest() != actual:
            _unlink_if_exists(final_path)
            _fsync_directory(final_path.parent)
            self.abort()
            raise DigestMismatchError("published final object digest mismatch")
        _unlink_if_exists(self._meta_path)
        _fsync_directory(final_path.parent)
        _fsync_directory(self.store._partials)
        return actual

    def abort(self) -> None:
        for path in (self._part_path, self._meta_path):
            _unlink_if_exists(path)
        try:
            _fsync_directory(self.store._partials)
        except FileNotFoundError:
            pass
