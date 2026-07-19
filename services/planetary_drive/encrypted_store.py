"""Encrypted, owner-only, content-addressed object store for Planetary Drive.

F-060 requires that Planetary Drive keep *encrypted* immutable objects in
node-local Unisync CAS roots. This store layers authenticated encryption
(ChaCha20-Poly1305) over the already-hardened
``services.unisync.storage.ContentAddressedStore`` (owner-only 0700 root,
0600 objects, ``O_NOFOLLOW``, atomic exclusive writes, digest verification,
path-traversal rejection).

Convergent encryption is used deliberately: the nonce is derived
deterministically from the encryption key and the plaintext, so identical
plaintext yields identical ciphertext. That keeps the store content-addressed
and de-duplicating (and keeps object bytes reproducible, matching the rest of
the stack), at the cost of revealing plaintext *equality* within a single
owner's store — acceptable for the same-account private mesh. Cross-account
confidentiality and key wrapping/recovery are separate F-060 concerns and are
not provided here; this store takes an already-derived 32-byte object key.
"""

from __future__ import annotations

import hashlib
import hmac
import re
from dataclasses import dataclass
from pathlib import Path

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import ChaCha20Poly1305

from services.unisync.storage import ContentAddressedStore

_SHA256_RE = re.compile(r"^[a-f0-9]{64}$")
_NONCE_BYTES = 12
_KEY_BYTES = 32
_MAX_OBJECT_BYTES = 64 * 1024 * 1024


class DriveStorageError(ValueError):
    """Fail-closed storage error with a stable message."""


@dataclass(frozen=True)
class ObjectRef:
    """Reference to one stored encrypted object."""

    plaintext_sha256: str
    storage_sha256: str
    plaintext_size: int


class EncryptedObjectStore:
    """Owner-only content-addressed store of authenticated-encrypted objects."""

    def __init__(self, root_dir: str | Path, *, key: bytes) -> None:
        if not isinstance(key, (bytes, bytearray)) or len(key) != _KEY_BYTES:
            raise DriveStorageError("object key must be exactly 32 bytes")
        self._key = bytes(key)
        self._aead = ChaCha20Poly1305(self._key)
        # ContentAddressedStore enforces the owner-only, symlink-safe, atomic
        # storage boundary and rejects any non-hex digest / path traversal.
        self._cas = ContentAddressedStore(Path(root_dir))

    def _nonce(self, plaintext: bytes) -> bytes:
        return hmac.new(self._key, b"planetary-drive-nonce\x00" + plaintext, hashlib.sha256).digest()[:_NONCE_BYTES]

    def put(self, plaintext: bytes) -> ObjectRef:
        """Encrypt and store one object; return its plaintext + storage digests."""

        if not isinstance(plaintext, (bytes, bytearray)):
            raise DriveStorageError("object must be bytes")
        data = bytes(plaintext)
        if len(data) > _MAX_OBJECT_BYTES:
            raise DriveStorageError("object exceeds the bounded size limit")
        plaintext_sha256 = hashlib.sha256(data).hexdigest()
        nonce = self._nonce(data)
        # AAD binds the ciphertext to its plaintext digest, so a blob cannot be
        # silently relabelled to a different plaintext.
        blob = nonce + self._aead.encrypt(nonce, data, plaintext_sha256.encode("ascii"))
        storage_sha256 = self._cas.put_bytes(blob)
        return ObjectRef(
            plaintext_sha256=plaintext_sha256,
            storage_sha256=storage_sha256,
            plaintext_size=len(data),
        )

    def get(self, storage_sha256: str, *, expected_plaintext_sha256: str) -> bytes | None:
        """Decrypt and return the object, or None if absent. Fails closed on tamper.

        The plaintext digest (recorded in the file manifest) is the AEAD's
        additional authenticated data, so decryption fails closed if the object
        was relabelled, tampered, or the wrong key is supplied.
        """

        if not isinstance(storage_sha256, str) or _SHA256_RE.fullmatch(storage_sha256) is None:
            raise DriveStorageError("invalid storage digest")
        if not isinstance(expected_plaintext_sha256, str) or _SHA256_RE.fullmatch(expected_plaintext_sha256) is None:
            raise DriveStorageError("invalid expected plaintext digest")
        if not self._cas.has(storage_sha256):
            return None
        blob = self._cas.read_bytes(storage_sha256)
        if len(blob) < _NONCE_BYTES + 16:
            raise DriveStorageError("stored object is too short to be valid")
        nonce, ciphertext = blob[:_NONCE_BYTES], blob[_NONCE_BYTES:]
        try:
            plaintext = self._aead.decrypt(nonce, ciphertext, expected_plaintext_sha256.encode("ascii"))
        except InvalidTag as exc:
            raise DriveStorageError("object failed authentication (wrong key or tampered)") from exc
        if hashlib.sha256(plaintext).hexdigest() != expected_plaintext_sha256:
            raise DriveStorageError("decrypted object does not match its digest")
        return plaintext

    def has(self, storage_sha256: str) -> bool:
        if not isinstance(storage_sha256, str) or _SHA256_RE.fullmatch(storage_sha256) is None:
            return False
        return self._cas.has(storage_sha256)
