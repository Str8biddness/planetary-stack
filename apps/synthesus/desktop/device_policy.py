"""Per-device permission policy for the private mesh.

The model is deliberately the one people already understand from phones: a row
per device, capability toggles inside the row. There is no capability that
applies globally to "any device" — permission is always granted to a *named*
device, because the whole product claim is that you know which machines are
yours.

Two device roles, and the distinction is load-bearing rather than cosmetic:

  peer    an enrolled mesh node holding a certificate; may be trusted with
          work and with results.
  source  a device that provides data and NOTHING else — a camera, a TV, a
          sensor. It never holds a mesh certificate and is never a peer.

Consumer cameras and smart TVs are among the most-compromised device classes on
any home network. Enrolling one as a peer would put a hostile device inside the
mutual-TLS trust boundary. So `source` devices are structurally incapable of
holding execution or result capabilities: `set_capabilities` refuses, rather
than relying on the UI never to offer it. See the trust-zone discussion in
docs/design/ and `contracts/chal_vsource/v1/models.py` (`trust_zone` currently
admits only `personal_cell` — there is no tier below it yet, which is exactly
why this boundary is enforced here).

Unknown devices are denied by default. An absent policy file means "nothing is
permitted", never "everything is permitted".
"""

from __future__ import annotations

import json
import os
import re
import stat
import tempfile
from pathlib import Path
from typing import Any

POLICY_SCHEMA = "planetary.synthesus.device_policy.v1"
MAX_POLICY_BYTES = 256 * 1024
MAX_DEVICES = 128

# Capabilities are named for what they let a device DO to the owner's data, and
# each one has a real enforcement point. Adding one here without an enforcement
# point would be a lie told in a settings screen.
PEER_CAPABILITIES = (
    "run_inference",  # may execute the owner's workloads
    "return_results",  # may send result bytes back to this desktop
)
SOURCE_CAPABILITIES = ("provide_input",)  # may supply input data, nothing else
ALL_CAPABILITIES = PEER_CAPABILITIES + SOURCE_CAPABILITIES

ROLES = ("peer", "source")

_DEVICE_ID_RE = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9._:-]{2,127}$")
_DEVICE_FIELDS = frozenset({"device_id", "display_name", "role", "capabilities"})


class DevicePolicyError(ValueError):
    """Policy could not be read, or a requested change is not permitted."""


def _capabilities_for(role: str) -> tuple[str, ...]:
    return PEER_CAPABILITIES if role == "peer" else SOURCE_CAPABILITIES


def _validate_device_id(device_id: Any) -> str:
    if not isinstance(device_id, str) or not _DEVICE_ID_RE.match(device_id):
        raise DevicePolicyError("device_id is not a valid identifier")
    return device_id


class DevicePolicyStore:
    """Owner-only JSON policy file with atomic writes and default-deny reads."""

    def __init__(self, path: Path | str) -> None:
        self.path = Path(path).expanduser()
        self._ensure_parent()

    # ------------------------------------------------------------------ io

    def _ensure_parent(self) -> None:
        parent = self.path.parent
        parent.mkdir(parents=True, mode=0o700, exist_ok=True)
        info = parent.lstat()
        if not stat.S_ISDIR(info.st_mode) or info.st_uid != os.geteuid():
            raise DevicePolicyError("policy directory must be an owned directory")

    def _default(self) -> dict[str, Any]:
        return {
            "schema": POLICY_SCHEMA,
            # Enforcement of result provenance. Signing and verification always
            # run regardless; this decides whether an unverified result is
            # REFUSED or merely flagged. Default on.
            "require_verified_evidence": True,
            "devices": {},
        }

    def load(self) -> dict[str, Any]:
        try:
            info = self.path.lstat()
        except FileNotFoundError:
            return self._default()
        if not stat.S_ISREG(info.st_mode):
            raise DevicePolicyError("policy path is not a regular file")
        if info.st_uid != os.geteuid():
            raise DevicePolicyError("policy file is not owned by this user")
        if info.st_size > MAX_POLICY_BYTES:
            raise DevicePolicyError("policy file exceeds its size bound")
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
        except (ValueError, UnicodeDecodeError) as exc:
            raise DevicePolicyError(f"policy file is not valid JSON: {exc}") from exc
        return self._validate(payload)

    def _validate(self, payload: Any) -> dict[str, Any]:
        if not isinstance(payload, dict) or payload.get("schema") != POLICY_SCHEMA:
            raise DevicePolicyError("policy schema is unsupported")
        enforce = payload.get("require_verified_evidence")
        if not isinstance(enforce, bool):
            raise DevicePolicyError("require_verified_evidence must be a boolean")
        raw_devices = payload.get("devices")
        if not isinstance(raw_devices, dict):
            raise DevicePolicyError("devices must be an object")
        if len(raw_devices) > MAX_DEVICES:
            raise DevicePolicyError("policy declares too many devices")
        devices: dict[str, Any] = {}
        for device_id, device in raw_devices.items():
            _validate_device_id(device_id)
            if not isinstance(device, dict) or set(device) != _DEVICE_FIELDS:
                raise DevicePolicyError("device row has unexpected fields")
            if device["device_id"] != device_id:
                raise DevicePolicyError("device row id does not match its key")
            role = device["role"]
            if role not in ROLES:
                raise DevicePolicyError("device role is unsupported")
            name = device["display_name"]
            if not isinstance(name, str) or not name or len(name) > 128:
                raise DevicePolicyError("device display_name is invalid")
            capabilities = device["capabilities"]
            if not isinstance(capabilities, dict):
                raise DevicePolicyError("device capabilities must be an object")
            allowed = _capabilities_for(role)
            if set(capabilities) != set(allowed):
                raise DevicePolicyError(
                    "device capabilities do not match the capabilities of its role"
                )
            if not all(isinstance(value, bool) for value in capabilities.values()):
                raise DevicePolicyError("device capability values must be booleans")
            devices[device_id] = {
                "device_id": device_id,
                "display_name": name,
                "role": role,
                "capabilities": {key: bool(capabilities[key]) for key in allowed},
            }
        return {
            "schema": POLICY_SCHEMA,
            "require_verified_evidence": enforce,
            "devices": devices,
        }

    def _save(self, policy: dict[str, Any]) -> None:
        policy = self._validate(policy)
        payload = json.dumps(policy, sort_keys=True, indent=2).encode("utf-8")
        descriptor, temporary = tempfile.mkstemp(
            dir=str(self.path.parent), prefix=".device-policy-"
        )
        try:
            os.fchmod(descriptor, 0o600)
            with os.fdopen(descriptor, "wb") as handle:
                handle.write(payload)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, self.path)
        except BaseException:
            try:
                os.unlink(temporary)
            except OSError:
                pass
            raise

    # -------------------------------------------------------------- queries

    def is_allowed(self, device_id: str, capability: str) -> bool:
        """Default-deny. Unknown device or unknown capability -> False."""
        if capability not in ALL_CAPABILITIES:
            return False
        try:
            policy = self.load()
        except DevicePolicyError:
            # A policy we cannot read is not a policy that grants anything.
            return False
        device = policy["devices"].get(device_id)
        if device is None:
            return False
        return bool(device["capabilities"].get(capability, False))

    def require_verified_evidence(self) -> bool:
        try:
            return bool(self.load()["require_verified_evidence"])
        except DevicePolicyError:
            return True  # unreadable policy fails safe: enforce

    def devices(self) -> list[dict[str, Any]]:
        """Device rows, stable order, for rendering as a permissions list."""
        policy = self.load()
        return [policy["devices"][key] for key in sorted(policy["devices"])]

    # --------------------------------------------------------------- writes

    def set_require_verified_evidence(self, enabled: bool) -> dict[str, Any]:
        if not isinstance(enabled, bool):
            raise DevicePolicyError("require_verified_evidence must be a boolean")
        policy = self.load()
        policy["require_verified_evidence"] = enabled
        self._save(policy)
        return policy

    def add_device(
        self, *, device_id: str, display_name: str, role: str
    ) -> dict[str, Any]:
        """Add a device with every capability OFF. Consent is never implied."""
        device_id = _validate_device_id(device_id)
        if role not in ROLES:
            raise DevicePolicyError("device role is unsupported")
        if not isinstance(display_name, str) or not display_name.strip():
            raise DevicePolicyError("device display_name is required")
        policy = self.load()
        if device_id in policy["devices"]:
            raise DevicePolicyError("device is already present")
        if len(policy["devices"]) >= MAX_DEVICES:
            raise DevicePolicyError("policy declares too many devices")
        policy["devices"][device_id] = {
            "device_id": device_id,
            "display_name": display_name.strip()[:128],
            "role": role,
            "capabilities": {name: False for name in _capabilities_for(role)},
        }
        self._save(policy)
        return policy["devices"][device_id]

    def remove_device(self, device_id: str) -> None:
        policy = self.load()
        if policy["devices"].pop(device_id, None) is None:
            raise DevicePolicyError("device is not present")
        self._save(policy)

    def set_capabilities(
        self, device_id: str, capabilities: dict[str, bool]
    ) -> dict[str, Any]:
        """Set toggles on one device row.

        A `source` device can never be granted an execution or result
        capability: the refusal lives here, not in the UI, so it holds no
        matter who calls it.
        """
        policy = self.load()
        device = policy["devices"].get(device_id)
        if device is None:
            raise DevicePolicyError("device is not present")
        if not isinstance(capabilities, dict) or not capabilities:
            raise DevicePolicyError("capabilities must be a non-empty object")
        allowed = _capabilities_for(device["role"])
        for name, value in capabilities.items():
            if name not in ALL_CAPABILITIES:
                raise DevicePolicyError(f"unknown capability: {name}")
            if name not in allowed:
                raise DevicePolicyError(
                    f"a {device['role']} device cannot be granted {name}"
                )
            if not isinstance(value, bool):
                raise DevicePolicyError("capability values must be booleans")
            device["capabilities"][name] = value
        self._save(policy)
        return device
