"""Strict-validation tests for the remote-worker configuration loader.

These exercise the fail-closed contract of
``services.remote_worker_config.load_remote_worker_config``: a valid
environment loads a frozen config; an absent primary variable disables the
remote worker (returns ``None``); and every individual invalid or
placeholder-looking field raises ``RemoteWorkerConfigError`` rather than
yielding a usable object.
"""

from __future__ import annotations

import hashlib

import pytest

from services.private_mesh.ssh_smoke import NodeTarget
from services.remote_worker_config import (
    RemoteWorkerConfig,
    RemoteWorkerConfigError,
    load_remote_worker_config,
)

# A real-looking, non-placeholder image digest (sha256 of arbitrary bytes,
# not an all-identical hex run).
_HEX = hashlib.sha256(b"planetary-stack-remote-worker-image").hexdigest()
_DIGEST = f"sha256:{_HEX}"
_IMAGE_REF = f"registry.internal/aivm-text-classify@{_DIGEST}"

# A syntactically valid pinned SSH host fingerprint: 43 base64 characters.
_FINGERPRINT = "SHA256:" + "A" * 43

# NODE_ID|SSH_ALIAS|HOST_FINGERPRINT|PYTHON|REPO|STATE_DIR
_NODE = (
    "worker-node-01|smoke-worker|"
    + _FINGERPRINT
    + "|/usr/bin/python3|/opt/planetary|/var/lib/planetary"
)


def _base_env(tmp_path) -> dict[str, str]:
    known_hosts = tmp_path / "known_hosts"
    known_hosts.write_text("worker ssh-ed25519 AAAA\n")
    identity = tmp_path / "id_ed25519"
    identity.write_text("-----BEGIN OPENSSH PRIVATE KEY-----\n")
    return {
        "SYNTHESUS_WORKER_NODE": _NODE,
        "SYNTHESUS_WORKER_IMAGE_REF": _IMAGE_REF,
        "SYNTHESUS_WORKER_IMAGE_DIGEST": _DIGEST,
        "SYNTHESUS_ACCOUNT_ID": "account:owner:mesh-prod",
        "SYNTHESUS_SUBJECT_ID": "node-agent:mesh-prod",
        "SYNTHESUS_KNOWN_HOSTS": str(known_hosts),
        "SYNTHESUS_SSH_IDENTITY": str(identity),
    }


def test_valid_config_loads(tmp_path):
    env = _base_env(tmp_path)
    config = load_remote_worker_config(env)

    assert isinstance(config, RemoteWorkerConfig)
    assert isinstance(config.target, NodeTarget)
    assert config.target.node_id == "worker-node-01"
    assert config.account_id == "account:owner:mesh-prod"
    assert config.subject_id == "node-agent:mesh-prod"
    assert config.image_ref == _IMAGE_REF
    assert config.image_digest == _DIGEST
    assert config.known_hosts.is_file()
    assert config.ssh_identity.is_file()
    assert config.profile == "text-classification.v1"


def test_config_is_frozen(tmp_path):
    config = load_remote_worker_config(_base_env(tmp_path))
    assert config is not None
    with pytest.raises((AttributeError, TypeError)):
        config.account_id = "account:other"  # type: ignore[misc]


def test_to_backend_kwargs_shape(tmp_path):
    config = load_remote_worker_config(_base_env(tmp_path))
    assert config is not None
    kwargs = config.to_backend_kwargs()

    # Exactly the config-derived kwargs the backend needs; no signing keys,
    # carrier, or inventory (those belong to the reviewed wiring).
    assert set(kwargs) == {
        "target",
        "account_id",
        "image_ref",
        "image_digest",
        "profile",
    }
    assert kwargs["target"] is config.target
    assert kwargs["account_id"] == config.account_id
    assert kwargs["image_ref"] == _IMAGE_REF
    assert kwargs["image_digest"] == _DIGEST
    assert kwargs["profile"] == "text-classification.v1"
    assert "keys" not in kwargs
    assert "carrier" not in kwargs
    assert "inventory" not in kwargs


def test_absent_worker_node_returns_none(tmp_path):
    env = _base_env(tmp_path)
    del env["SYNTHESUS_WORKER_NODE"]
    assert load_remote_worker_config(env) is None


def test_empty_worker_node_returns_none(tmp_path):
    env = _base_env(tmp_path)
    env["SYNTHESUS_WORKER_NODE"] = "   "
    assert load_remote_worker_config(env) is None


def test_empty_env_returns_none():
    assert load_remote_worker_config({}) is None


def test_bad_node_target_raises(tmp_path):
    env = _base_env(tmp_path)
    # Only five pipe-separated fields instead of six.
    env["SYNTHESUS_WORKER_NODE"] = (
        "worker-node-01|smoke-worker|" + _FINGERPRINT + "|/usr/bin/python3|/opt/planetary"
    )
    with pytest.raises(RemoteWorkerConfigError):
        load_remote_worker_config(env)


def test_bad_node_fingerprint_raises(tmp_path):
    env = _base_env(tmp_path)
    env["SYNTHESUS_WORKER_NODE"] = (
        "worker-node-01|smoke-worker|not-a-fingerprint|"
        "/usr/bin/python3|/opt/planetary|/var/lib/planetary"
    )
    with pytest.raises(RemoteWorkerConfigError):
        load_remote_worker_config(env)


def test_non_canonical_account_raises(tmp_path):
    env = _base_env(tmp_path)
    env["SYNTHESUS_ACCOUNT_ID"] = "bad account!"
    with pytest.raises(RemoteWorkerConfigError):
        load_remote_worker_config(env)


def test_non_canonical_subject_raises(tmp_path):
    env = _base_env(tmp_path)
    # Leading '.' is not allowed by the canonical identifier regex.
    env["SYNTHESUS_SUBJECT_ID"] = ".node-agent"
    with pytest.raises(RemoteWorkerConfigError):
        load_remote_worker_config(env)


def test_missing_account_raises(tmp_path):
    env = _base_env(tmp_path)
    del env["SYNTHESUS_ACCOUNT_ID"]
    with pytest.raises(RemoteWorkerConfigError):
        load_remote_worker_config(env)


def test_mutable_image_ref_raises(tmp_path):
    env = _base_env(tmp_path)
    # A tag, not an immutable @sha256 pin.
    env["SYNTHESUS_WORKER_IMAGE_REF"] = "registry.internal/aivm-text-classify:latest"
    with pytest.raises(RemoteWorkerConfigError):
        load_remote_worker_config(env)


def test_image_digest_mismatch_raises(tmp_path):
    env = _base_env(tmp_path)
    other = "sha256:" + hashlib.sha256(b"a-different-image").hexdigest()
    env["SYNTHESUS_WORKER_IMAGE_DIGEST"] = other
    with pytest.raises(RemoteWorkerConfigError):
        load_remote_worker_config(env)


def test_malformed_image_digest_raises(tmp_path):
    env = _base_env(tmp_path)
    env["SYNTHESUS_WORKER_IMAGE_DIGEST"] = "sha256:deadbeef"
    env["SYNTHESUS_WORKER_IMAGE_REF"] = "registry.internal/img@sha256:deadbeef"
    with pytest.raises(RemoteWorkerConfigError):
        load_remote_worker_config(env)


def test_missing_known_hosts_file_raises(tmp_path):
    env = _base_env(tmp_path)
    env["SYNTHESUS_KNOWN_HOSTS"] = str(tmp_path / "does_not_exist")
    with pytest.raises(RemoteWorkerConfigError):
        load_remote_worker_config(env)


def test_known_hosts_directory_raises(tmp_path):
    env = _base_env(tmp_path)
    # A directory is not a regular file.
    env["SYNTHESUS_KNOWN_HOSTS"] = str(tmp_path)
    with pytest.raises(RemoteWorkerConfigError):
        load_remote_worker_config(env)


def test_missing_ssh_identity_file_raises(tmp_path):
    env = _base_env(tmp_path)
    env["SYNTHESUS_SSH_IDENTITY"] = str(tmp_path / "no_identity_here")
    with pytest.raises(RemoteWorkerConfigError):
        load_remote_worker_config(env)


def test_placeholder_account_rejected(tmp_path):
    env = _base_env(tmp_path)
    env["SYNTHESUS_ACCOUNT_ID"] = "account:changeme"
    with pytest.raises(RemoteWorkerConfigError):
        load_remote_worker_config(env)


def test_placeholder_image_ref_rejected(tmp_path):
    env = _base_env(tmp_path)
    env["SYNTHESUS_WORKER_IMAGE_REF"] = f"registry.example.com/img@{_DIGEST}"
    with pytest.raises(RemoteWorkerConfigError):
        load_remote_worker_config(env)


def test_placeholder_all_zero_digest_rejected(tmp_path):
    env = _base_env(tmp_path)
    zero = "sha256:" + "0" * 64
    env["SYNTHESUS_WORKER_IMAGE_DIGEST"] = zero
    env["SYNTHESUS_WORKER_IMAGE_REF"] = f"registry.internal/img@{zero}"
    with pytest.raises(RemoteWorkerConfigError):
        load_remote_worker_config(env)


def test_unsupported_profile_rejected(tmp_path):
    env = _base_env(tmp_path)
    env["SYNTHESUS_WORKER_PROFILE"] = "arbitrary-model.v9"
    with pytest.raises(RemoteWorkerConfigError):
        load_remote_worker_config(env)


def test_explicit_supported_profile_accepted(tmp_path):
    env = _base_env(tmp_path)
    env["SYNTHESUS_WORKER_PROFILE"] = "text-classification.v1"
    config = load_remote_worker_config(env)
    assert config is not None
    assert config.profile == "text-classification.v1"
