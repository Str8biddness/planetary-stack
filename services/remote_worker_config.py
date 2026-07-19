"""Strict, fail-closed configuration loader for the remote execution worker.

This module reads and validates the environment configuration the desktop
controller needs to dispatch a signed job to a physical remote worker over the
pinned administrative carrier (see ``services/remote_backend.py`` and
``services/private_mesh/ssh_smoke.py``). It is a *configuration boundary* only:
it never constructs signing keys, a control plane, or a live carrier, and it
never talks to the network. The security-sensitive wiring that turns this
config into a running backend (installer-driven mesh enrollment, a persistent
signed control plane, and lease-bound mTLS result return) is intentionally left
to the reviewed ``synthesusd`` construction path.

Fail-closed contract:

* ``load_remote_worker_config`` returns ``None`` *only* when the primary
  ``SYNTHESUS_WORKER_NODE`` variable is absent, which means "remote worker not
  configured". If that variable is present but any required field is missing,
  malformed, or placeholder-looking, it raises ``RemoteWorkerConfigError``.
  It never returns a partially-valid or silently-disabled object.
* No default silently "works": there are no placeholder keys, fake signatures,
  or fallback identifiers. Every value comes from the environment and is
  validated before the frozen ``RemoteWorkerConfig`` is produced.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from services.private_mesh.ssh_smoke import NodeTarget

# Canonical contract identifier, identical to the private-mesh coordinator's
# ``_IDENTIFIER_RE`` (services/private_mesh/ssh_smoke.py). Kept as a local copy
# so this loader does not depend on a private symbol.
_IDENTIFIER_RE = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9._:-]{2,127}$")

# An immutable image digest is exactly ``sha256:`` followed by 64 lowercase
# hex characters, matching the ``@sha256:...`` form the backend pins against.
_DIGEST_RE = re.compile(r"^sha256:([0-9a-f]{64})$")

# The worker only admits this executor profile (services/private_mesh/
# worker_cli.py rejects anything else); do not let config request an
# unsupported one and fail late on the remote side.
_SUPPORTED_PROFILES = frozenset({"text-classification.v1"})
_DEFAULT_PROFILE = "text-classification.v1"

# Substrings that mark a value as an unfilled template / placeholder. A
# security boundary must refuse these rather than dispatch a job against a
# fake identity or image. Applied to identifiers and image references only,
# never to filesystem paths (a temp/test directory name is not a placeholder
# identity).
_PLACEHOLDER_TOKENS = (
    "changeme",
    "change_me",
    "change-me",
    "placeholder",
    "example",
    "your-",
    "your_",
    "yourorg",
    "todo",
    "fixme",
    "replace-me",
    "replaceme",
    "dummy",
    "fake",
    "notreal",
    "dev_secret",
    "xxxx",
)

# Env var names (namespaced).
ENV_WORKER_NODE = "SYNTHESUS_WORKER_NODE"
ENV_IMAGE_REF = "SYNTHESUS_WORKER_IMAGE_REF"
ENV_IMAGE_DIGEST = "SYNTHESUS_WORKER_IMAGE_DIGEST"
ENV_ACCOUNT_ID = "SYNTHESUS_ACCOUNT_ID"
ENV_SUBJECT_ID = "SYNTHESUS_SUBJECT_ID"
ENV_KNOWN_HOSTS = "SYNTHESUS_KNOWN_HOSTS"
ENV_SSH_IDENTITY = "SYNTHESUS_SSH_IDENTITY"
ENV_PROFILE = "SYNTHESUS_WORKER_PROFILE"


class RemoteWorkerConfigError(ValueError):
    """Fail-closed remote-worker configuration error with a clear message."""


def _looks_like_placeholder(value: str) -> bool:
    lowered = value.lower()
    if any(token in lowered for token in _PLACEHOLDER_TOKENS):
        return True
    # An all-identical hex run (e.g. all zeros or all f's) is a stub digest.
    digest_match = _DIGEST_RE.match(value)
    if digest_match:
        hexpart = digest_match.group(1)
        if len(set(hexpart)) == 1:
            return True
    return False


def _require_present(env: Mapping[str, str], name: str) -> str:
    raw = env.get(name)
    if raw is None or raw.strip() == "":
        raise RemoteWorkerConfigError(
            f"{name} is required when {ENV_WORKER_NODE} is set"
        )
    return raw


def _require_identifier(env: Mapping[str, str], name: str) -> str:
    value = _require_present(env, name)
    if not _IDENTIFIER_RE.fullmatch(value):
        raise RemoteWorkerConfigError(
            f"{name} must be a canonical contract identifier "
            f"matching {_IDENTIFIER_RE.pattern}"
        )
    if _looks_like_placeholder(value):
        raise RemoteWorkerConfigError(f"{name} looks like a placeholder value")
    return value


def _require_regular_file(env: Mapping[str, str], name: str) -> Path:
    raw = _require_present(env, name)
    path = Path(raw).expanduser()
    # A symlink to a regular file resolves through ``is_file``; a directory,
    # missing path, or special file fails closed here.
    if not path.is_file():
        raise RemoteWorkerConfigError(
            f"{name} must name an existing regular file: {raw}"
        )
    return path


def _require_image(env: Mapping[str, str]) -> tuple[str, str]:
    image_ref = _require_present(env, ENV_IMAGE_REF)
    declared_digest = _require_present(env, ENV_IMAGE_DIGEST)

    if not _DIGEST_RE.fullmatch(declared_digest):
        raise RemoteWorkerConfigError(
            f"{ENV_IMAGE_DIGEST} must be 'sha256:' followed by 64 lowercase "
            f"hex characters"
        )
    if _looks_like_placeholder(declared_digest):
        raise RemoteWorkerConfigError(
            f"{ENV_IMAGE_DIGEST} looks like a placeholder digest"
        )
    if "@sha256:" not in image_ref:
        raise RemoteWorkerConfigError(
            f"{ENV_IMAGE_REF} must be immutable and pin an @sha256:<digest>"
        )
    if _looks_like_placeholder(image_ref):
        raise RemoteWorkerConfigError(
            f"{ENV_IMAGE_REF} looks like a placeholder image reference"
        )
    ref_digest = image_ref.rsplit("@", 1)[1]
    if not _DIGEST_RE.fullmatch(ref_digest):
        raise RemoteWorkerConfigError(
            f"{ENV_IMAGE_REF} digest must be 'sha256:' followed by 64 lowercase "
            f"hex characters"
        )
    if ref_digest != declared_digest:
        raise RemoteWorkerConfigError(
            f"{ENV_IMAGE_REF} digest does not equal {ENV_IMAGE_DIGEST}"
        )
    return image_ref, declared_digest


def _require_profile(env: Mapping[str, str]) -> str:
    raw = env.get(ENV_PROFILE)
    if raw is None or raw.strip() == "":
        return _DEFAULT_PROFILE
    if raw not in _SUPPORTED_PROFILES:
        raise RemoteWorkerConfigError(
            f"{ENV_PROFILE}={raw!r} is not a supported executor profile "
            f"(allowed: {sorted(_SUPPORTED_PROFILES)})"
        )
    return raw


@dataclass(frozen=True)
class RemoteWorkerConfig:
    """Validated, immutable configuration for the remote execution worker.

    Every field is produced only after strict validation by
    ``load_remote_worker_config``. Constructing this dataclass directly bypasses
    that validation; callers should always go through the loader.
    """

    target: NodeTarget
    account_id: str
    subject_id: str
    image_ref: str
    image_digest: str
    known_hosts: Path
    ssh_identity: Path
    profile: str = _DEFAULT_PROFILE

    def to_backend_kwargs(self) -> dict[str, Any]:
        """Exactly the config-derived kwargs ``RemoteExecutionBackend`` needs.

        This deliberately omits ``carrier``, ``keys``, and ``inventory``: the
        carrier and the signing/enrollment material are constructed by the
        reviewed controller wiring, not by this configuration loader. It returns
        the immutable, validated values (image ref + digest, executor profile,
        the pinned node target, and the account) so that reviewed wiring cannot
        accidentally re-derive them from unvalidated input.
        """

        return {
            "target": self.target,
            "account_id": self.account_id,
            "image_ref": self.image_ref,
            "image_digest": self.image_digest,
            "profile": self.profile,
        }


def load_remote_worker_config(
    env: Mapping[str, str],
) -> RemoteWorkerConfig | None:
    """Load and strictly validate the remote-worker config from ``env``.

    Returns ``None`` only when ``SYNTHESUS_WORKER_NODE`` is absent (remote
    worker not configured). If it is present, every required field must be
    valid or ``RemoteWorkerConfigError`` is raised — the loader never yields a
    usable object from invalid/missing/placeholder input.
    """

    node_value = env.get(ENV_WORKER_NODE)
    if node_value is None or node_value.strip() == "":
        return None

    try:
        target = NodeTarget.parse(node_value)
    except ValueError as exc:
        raise RemoteWorkerConfigError(
            f"{ENV_WORKER_NODE} is not a valid NodeTarget: {exc}"
        ) from exc
    if _looks_like_placeholder(node_value):
        raise RemoteWorkerConfigError(
            f"{ENV_WORKER_NODE} looks like a placeholder node target"
        )

    account_id = _require_identifier(env, ENV_ACCOUNT_ID)
    subject_id = _require_identifier(env, ENV_SUBJECT_ID)
    image_ref, image_digest = _require_image(env)
    known_hosts = _require_regular_file(env, ENV_KNOWN_HOSTS)
    ssh_identity = _require_regular_file(env, ENV_SSH_IDENTITY)
    profile = _require_profile(env)

    return RemoteWorkerConfig(
        target=target,
        account_id=account_id,
        subject_id=subject_id,
        image_ref=image_ref,
        image_digest=image_digest,
        known_hosts=known_hosts,
        ssh_identity=ssh_identity,
        profile=profile,
    )
