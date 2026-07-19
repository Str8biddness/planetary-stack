"""Adversarial tests for the encrypted store and versioned namespace (F-060)."""

from __future__ import annotations

import hashlib
import os
import stat
from pathlib import Path

import pytest

from services.planetary_drive.encrypted_store import (
    DriveStorageError,
    EncryptedObjectStore,
)
from services.planetary_drive.namespace_manager import NamespaceManager

KEY = b"\x11" * 32
OTHER_KEY = b"\x22" * 32
NODE = "node:owner:a"


def _store(tmp_path: Path, key: bytes = KEY) -> EncryptedObjectStore:
    return EncryptedObjectStore(tmp_path / "cas", key=key)


# ---- encrypted object store ----

def test_put_get_roundtrip_and_digests(tmp_path):
    store = _store(tmp_path)
    payload = b"planetary drive secret document"
    ref = store.put(payload)
    assert ref.plaintext_sha256 == hashlib.sha256(payload).hexdigest()
    assert ref.plaintext_size == len(payload)
    assert ref.storage_sha256 != ref.plaintext_sha256
    got = store.get(ref.storage_sha256, expected_plaintext_sha256=ref.plaintext_sha256)
    assert got == payload


def test_stored_bytes_are_encrypted_not_plaintext(tmp_path):
    store = _store(tmp_path)
    payload = b"this must never be stored in the clear"
    ref = store.put(payload)
    # Find the raw object on disk and confirm the plaintext is absent.
    root = tmp_path / "cas" / "objects"
    blobs = [p.read_bytes() for p in root.rglob("*") if p.is_file()]
    assert blobs, "no object written"
    assert all(payload not in blob for blob in blobs)
    assert all(hashlib.sha256(blob).hexdigest() == ref.storage_sha256 for blob in blobs)


def test_convergent_encryption_is_deterministic(tmp_path):
    store = _store(tmp_path)
    a = store.put(b"same content")
    b = store.put(b"same content")
    assert a.storage_sha256 == b.storage_sha256


def test_wrong_key_fails_closed(tmp_path):
    store = _store(tmp_path)
    ref = store.put(b"owner-only bytes")
    other = EncryptedObjectStore(tmp_path / "cas", key=OTHER_KEY)
    with pytest.raises(DriveStorageError, match="authentication"):
        other.get(ref.storage_sha256, expected_plaintext_sha256=ref.plaintext_sha256)


def test_relabelled_digest_fails_closed(tmp_path):
    store = _store(tmp_path)
    ref = store.put(b"content one")
    with pytest.raises(DriveStorageError, match="authentication"):
        store.get(ref.storage_sha256, expected_plaintext_sha256="a" * 64)


def test_absent_object_returns_none_and_bad_input_rejected(tmp_path):
    store = _store(tmp_path)
    assert store.get("b" * 64, expected_plaintext_sha256="c" * 64) is None
    with pytest.raises(DriveStorageError):
        store.get("not-a-digest", expected_plaintext_sha256="c" * 64)
    with pytest.raises(DriveStorageError):
        EncryptedObjectStore(tmp_path / "cas2", key=b"short")


# ---- versioned namespace ----

def _ns(tmp_path: Path) -> NamespaceManager:
    return NamespaceManager(tmp_path / "cas", tmp_path / "meta" / "drive.sqlite3", key=KEY)


def test_namespace_put_get_and_encryption(tmp_path):
    ns = _ns(tmp_path)
    m = ns.put_file("notes/a.txt", b"hello drive", NODE)
    assert m.version == 1 and not m.is_deleted
    got = ns.get_file("notes/a.txt")
    assert got is not None and got[1] == b"hello drive"


def test_namespace_versions_and_restore(tmp_path):
    ns = _ns(tmp_path)
    ns.put_file("f", b"v1", NODE)
    ns.put_file("f", b"v2", NODE)
    ns.put_file("f", b"v3", NODE)
    assert ns.list_versions("f") == [1, 2, 3]
    assert ns.get_file("f")[1] == b"v3"
    restored = ns.restore("f", 1, NODE)
    assert restored.version == 4
    assert ns.get_file("f")[1] == b"v1"
    assert ns.list_versions("f") == [1, 2, 3, 4]


def test_namespace_tombstone_hides_file(tmp_path):
    ns = _ns(tmp_path)
    ns.put_file("f", b"data", NODE)
    tomb = ns.delete_file("f", NODE)
    assert tomb.is_deleted and tomb.version == 2
    assert ns.get_file("f") is None
    assert ns.delete_file("f", NODE) is None  # already deleted
    # A prior version's content is still restorable after tombstoning.
    ns.restore("f", 1, NODE)
    assert ns.get_file("f")[1] == b"data"


def test_namespace_database_is_owner_only(tmp_path):
    ns = _ns(tmp_path)
    ns.put_file("f", b"x", NODE)
    mode = stat.S_IMODE(ns.db_path.stat().st_mode)
    assert mode == 0o600, oct(mode)
    assert stat.S_IMODE((ns.db_path.parent).stat().st_mode) == 0o700


def test_namespace_survives_reopen(tmp_path):
    ns = _ns(tmp_path)
    ns.put_file("keep", b"durable", NODE)
    reopened = _ns(tmp_path)
    got = reopened.get_file("keep")
    assert got is not None and got[1] == b"durable"
