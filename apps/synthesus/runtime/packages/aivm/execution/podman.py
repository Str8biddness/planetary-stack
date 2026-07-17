"""A narrow, production rootless-Podman CPU execution boundary.

This module deliberately does not verify signatures or allocate leases.  It
accepts only the structured result of those earlier gates, binds that result
to a fixed local image and entrypoint, and executes without an in-process
fallback.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import secrets
import selectors
import signal
import stat
import subprocess
import time
from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass, field
from enum import StrEnum
from pathlib import Path, PurePosixPath
from types import MappingProxyType
from typing import Any, Protocol

from contracts.aivm.v1 import AIVMWorkloadManifest, document_sha256

from ..admission import AdmissionDecision, AdmissionStatus


_IDENTIFIER = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{2,127}$")
_SHA256 = re.compile(r"^[a-f0-9]{64}$")
_IMAGE_DIGEST = re.compile(r"^sha256:[a-f0-9]{64}$")
_IMMUTABLE_IMAGE = re.compile(
    r"^[a-z0-9][a-z0-9._/:~-]{1,255}@sha256:[a-f0-9]{64}$"
)
_CONTAINER_NAME = re.compile(r"^aivm-[a-f0-9]{16}-[a-f0-9]{8}$")
_MAX_SAFE_INTEGER = 9_007_199_254_740_991
_READ_CHUNK = 65_536


class ExecutionStatus(StrEnum):
    SUCCEEDED = "succeeded"
    REJECTED = "rejected"
    FAILED = "failed"
    UNAVAILABLE = "unavailable"


class ExecutionBoundaryError(RuntimeError):
    """Internal fail-closed error whose public message is a stable code."""


class InvalidExecutionRequest(ExecutionBoundaryError):
    pass


class HostUnavailable(ExecutionBoundaryError):
    pass


class ReplayRejected(ExecutionBoundaryError):
    pass


class OutputViolation(ExecutionBoundaryError):
    pass


class RunnerUnavailable(ExecutionBoundaryError):
    pass


def _require_identifier(name: str, value: object) -> str:
    if not isinstance(value, str) or _IDENTIFIER.fullmatch(value) is None:
        raise InvalidExecutionRequest(f"invalid_{name}")
    return value


def _require_sha256(name: str, value: object) -> str:
    if not isinstance(value, str) or _SHA256.fullmatch(value) is None:
        raise InvalidExecutionRequest(f"invalid_{name}")
    return value


def _canonical_bytes(value: object) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        allow_nan=False,
    ).encode("ascii")


def _sha256_json(value: object) -> str:
    return hashlib.sha256(_canonical_bytes(value)).hexdigest()


def _write_all(fd: int, payload: bytes) -> None:
    view = memoryview(payload)
    while view:
        written = os.write(fd, view)
        if written <= 0:
            raise OSError("short write")
        view = view[written:]


def _fsync_directory(path: Path) -> None:
    flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0)
    fd = os.open(path, flags)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def _private_directory(path: Path, *, create: bool) -> Path:
    path = path.expanduser()
    if not path.is_absolute():
        raise InvalidExecutionRequest("directory_must_be_absolute")
    if any(character in str(path) for character in ("\x00", "\n", "\r", ":")):
        raise InvalidExecutionRequest("invalid_directory_path")
    if create:
        path.mkdir(mode=0o700, parents=True, exist_ok=True)
    try:
        info = path.lstat()
    except FileNotFoundError as exc:
        raise InvalidExecutionRequest("directory_unavailable") from exc
    if stat.S_ISLNK(info.st_mode) or not stat.S_ISDIR(info.st_mode):
        raise InvalidExecutionRequest("directory_not_real")
    if info.st_uid != os.geteuid() or stat.S_IMODE(info.st_mode) != 0o700:
        raise InvalidExecutionRequest("directory_not_owner_only")
    return path.resolve(strict=True)


def _safe_relative_output(value: str) -> str:
    if not isinstance(value, str) or not value or len(value) > 240:
        raise ValueError("output path must be a bounded relative path")
    path = PurePosixPath(value)
    if path.is_absolute() or any(part in {"", ".", ".."} for part in path.parts):
        raise ValueError("output path must be normalized and relative")
    if any(character in value for character in ("\x00", "\n", "\r", ":", "\\")):
        raise ValueError("output path contains an unsupported character")
    return value


@dataclass(frozen=True)
class LeaseAuthority:
    """Exact active lease revision already verified by the caller."""

    account_id: str
    workload_id: str
    node_id: str
    lease_id: str
    lease_sha256: str
    fencing_token: int

    def __post_init__(self) -> None:
        for name in ("account_id", "workload_id", "node_id", "lease_id"):
            _require_identifier(name, getattr(self, name))
        _require_sha256("lease_sha256", self.lease_sha256)
        if (
            isinstance(self.fencing_token, bool)
            or not isinstance(self.fencing_token, int)
            or not 1 <= self.fencing_token <= _MAX_SAFE_INTEGER
        ):
            raise InvalidExecutionRequest("invalid_fencing_token")

    def to_record(self) -> dict[str, object]:
        return asdict(self)


@dataclass(frozen=True)
class AdmittedExecutionRequest:
    """Manifest and lease authority that have passed earlier trust gates.

    The executor intentionally requires an :class:`AdmissionDecision` rather
    than accepting a raw workload manifest.  It rechecks all identity and
    policy bindings but does not claim to repeat signature verification.
    """

    manifest: AIVMWorkloadManifest
    admission: AdmissionDecision
    lease: LeaseAuthority
    manifest_sha256: str = field(init=False)

    def __post_init__(self) -> None:
        if type(self.manifest) is not AIVMWorkloadManifest:
            raise InvalidExecutionRequest("manifest_not_strict_model")
        if (
            self.admission.status is not AdmissionStatus.ADMITTED
            or not self.admission.admitted
        ):
            raise InvalidExecutionRequest("manifest_not_admitted")
        expected_identity = (
            self.manifest.manifest_id,
            self.manifest.workload_id,
            self.manifest.account_id,
        )
        admitted_identity = (
            self.admission.manifest_id,
            self.admission.workload_id,
            self.admission.account_id,
        )
        if admitted_identity != expected_identity:
            raise InvalidExecutionRequest("admission_identity_mismatch")
        image_identity = (
            f"{self.manifest.runtime_image.image_id}@"
            f"{self.manifest.runtime_image.digest}"
        )
        if self.admission.evidence.get("runtime_image") != image_identity:
            raise InvalidExecutionRequest("admission_image_mismatch")
        if self.admission.evidence.get("entrypoint_id") != self.manifest.entrypoint_id:
            raise InvalidExecutionRequest("admission_entrypoint_mismatch")
        if self.lease.account_id != self.manifest.account_id:
            raise InvalidExecutionRequest("lease_account_mismatch")
        if self.lease.workload_id != self.manifest.workload_id:
            raise InvalidExecutionRequest("lease_workload_mismatch")
        if self.manifest.network.mode != "deny" or self.manifest.network.allowlist:
            raise InvalidExecutionRequest("cpu_executor_requires_network_deny")
        if self.manifest.runtime_image.devices:
            raise InvalidExecutionRequest("cpu_executor_rejects_devices")
        if self.manifest.resources.gpu_count or self.manifest.resources.gpu_memory_bytes:
            raise InvalidExecutionRequest("cpu_executor_rejects_gpu")
        if self.manifest.filesystem.rootfs != "readonly" or self.manifest.filesystem.host_mounts:
            raise InvalidExecutionRequest("cpu_executor_requires_readonly_rootfs")
        object.__setattr__(self, "manifest_sha256", document_sha256(self.manifest))


@dataclass(frozen=True)
class TrustedEntrypoint:
    """Operator-owned fixed executable; no manifest text becomes argv."""

    entrypoint_id: str
    executable: str
    arguments: tuple[str, ...]
    output_mount: str
    outputs: tuple[tuple[str, str], ...]

    def __post_init__(self) -> None:
        _require_identifier("entrypoint_id", self.entrypoint_id)
        executable = PurePosixPath(self.executable)
        if (
            not executable.is_absolute()
            or ".." in executable.parts
            or any(character in self.executable for character in ("\x00", "\n", "\r"))
        ):
            raise ValueError("trusted executable must be a normalized absolute path")
        if len(self.arguments) > 64:
            raise ValueError("trusted entrypoint has too many arguments")
        for argument in self.arguments:
            if not isinstance(argument, str) or len(argument) > 4096 or "\x00" in argument:
                raise ValueError("trusted entrypoint argument is invalid")
        mount = PurePosixPath(self.output_mount)
        if not mount.is_absolute() or ".." in mount.parts or self.output_mount == "/":
            raise ValueError("output mount must be a normalized absolute path")
        output_ids = [output_id for output_id, _ in self.outputs]
        if output_ids != sorted(set(output_ids)) or not output_ids:
            raise ValueError("trusted outputs must be non-empty, unique, and sorted")
        relative_paths: list[str] = []
        for output_id, relative_path in self.outputs:
            _require_identifier("output_id", output_id)
            relative_paths.append(_safe_relative_output(relative_path))
        if len(relative_paths) != len(set(relative_paths)):
            raise ValueError("trusted output paths must be unique")

    def policy_record(self) -> dict[str, object]:
        return {
            "entrypoint_id": self.entrypoint_id,
            "executable": self.executable,
            "arguments": list(self.arguments),
            "output_mount": self.output_mount,
            "outputs": [list(item) for item in self.outputs],
        }


@dataclass(frozen=True)
class ExecutorPolicy:
    """Local policy and owner-only roots for one executor instance."""

    state_dir: Path
    artifact_dir: Path
    output_dir: Path
    trusted_images: Mapping[str, str]
    trusted_entrypoints: Mapping[str, TrustedEntrypoint]
    podman_binary: str = "podman"
    stdout_limit_bytes: int = 65_536
    stderr_limit_bytes: int = 65_536
    max_output_files: int = 32
    max_output_file_bytes: int = 64 * 1024 * 1024

    def __post_init__(self) -> None:
        if not isinstance(self.podman_binary, str) or not self.podman_binary:
            raise ValueError("podman binary is required")
        if any(character in self.podman_binary for character in ("\x00", "\n", "\r")):
            raise ValueError("podman binary is invalid")
        for name in (
            "stdout_limit_bytes",
            "stderr_limit_bytes",
            "max_output_files",
            "max_output_file_bytes",
        ):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
                raise ValueError(f"{name} must be positive")
        images = dict(self.trusted_images)
        if not images:
            raise ValueError("at least one trusted image is required")
        for logical_identity, immutable_ref in images.items():
            if "@" not in logical_identity:
                raise ValueError("trusted image identity must include a digest")
            digest = logical_identity.rsplit("@", 1)[1]
            if _IMAGE_DIGEST.fullmatch(digest) is None:
                raise ValueError("trusted image identity has an invalid digest")
            if not isinstance(immutable_ref, str) or _IMMUTABLE_IMAGE.fullmatch(immutable_ref) is None:
                raise ValueError("trusted image reference must be immutable")
            if immutable_ref.rsplit("@", 1)[1] != digest:
                raise ValueError("trusted image reference digest does not match manifest identity")
        entrypoints = dict(self.trusted_entrypoints)
        if not entrypoints:
            raise ValueError("at least one trusted entrypoint is required")
        for key, entrypoint in entrypoints.items():
            if key != entrypoint.entrypoint_id:
                raise ValueError("trusted entrypoint map key mismatch")
        object.__setattr__(self, "trusted_images", MappingProxyType(images))
        object.__setattr__(self, "trusted_entrypoints", MappingProxyType(entrypoints))


@dataclass(frozen=True)
class CommandResult:
    argv: tuple[str, ...]
    exit_code: int
    stdout: bytes = b""
    stderr: bytes = b""
    timed_out: bool = False
    stdout_truncated: bool = False
    stderr_truncated: bool = False


class CommandRunner(Protocol):
    def run(
        self,
        argv: Sequence[str],
        *,
        timeout_seconds: float,
        stdout_limit: int,
        stderr_limit: int,
    ) -> CommandResult:
        """Run argv without a shell and retain at most the requested bytes."""


class SubprocessCommandRunner:
    """Bounded subprocess runner that never uses ``communicate()``."""

    def run(
        self,
        argv: Sequence[str],
        *,
        timeout_seconds: float,
        stdout_limit: int,
        stderr_limit: int,
    ) -> CommandResult:
        command = tuple(argv)
        if (
            not command
            or timeout_seconds <= 0
            or stdout_limit <= 0
            or stderr_limit <= 0
            or any(not isinstance(item, str) or not item or "\x00" in item for item in command)
        ):
            raise RunnerUnavailable("invalid_command")
        try:
            process = subprocess.Popen(
                command,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                shell=False,
                close_fds=True,
                start_new_session=True,
            )
        except (FileNotFoundError, PermissionError, OSError) as exc:
            raise RunnerUnavailable("runner_start_failed") from exc
        assert process.stdout is not None
        assert process.stderr is not None
        os.set_blocking(process.stdout.fileno(), False)
        os.set_blocking(process.stderr.fileno(), False)
        selector = selectors.DefaultSelector()
        selector.register(process.stdout, selectors.EVENT_READ, ("stdout", stdout_limit))
        selector.register(process.stderr, selectors.EVENT_READ, ("stderr", stderr_limit))
        buffers = {"stdout": bytearray(), "stderr": bytearray()}
        truncated = {"stdout": False, "stderr": False}
        deadline = time.monotonic() + timeout_seconds
        timed_out = False
        killed_at: float | None = None
        try:
            while selector.get_map():
                now = time.monotonic()
                if now >= deadline and not timed_out:
                    timed_out = True
                    killed_at = now
                    try:
                        os.killpg(process.pid, signal.SIGKILL)
                    except ProcessLookupError:
                        pass
                if timed_out and killed_at is not None and now - killed_at > 2.0:
                    for key in list(selector.get_map().values()):
                        selector.unregister(key.fileobj)
                    break
                events = selector.select(timeout=0.05)
                if not events and process.poll() is not None:
                    events = [
                        (key, selectors.EVENT_READ)
                        for key in list(selector.get_map().values())
                    ]
                for key, _ in events:
                    stream_name, limit = key.data
                    try:
                        chunk = os.read(key.fileobj.fileno(), _READ_CHUNK)
                    except BlockingIOError:
                        continue
                    if not chunk:
                        selector.unregister(key.fileobj)
                        continue
                    remaining = limit - len(buffers[stream_name])
                    if remaining > 0:
                        buffers[stream_name].extend(chunk[:remaining])
                    if len(chunk) > max(remaining, 0):
                        truncated[stream_name] = True
            try:
                exit_code = process.wait(timeout=2.0)
            except subprocess.TimeoutExpired:
                try:
                    os.killpg(process.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
                exit_code = process.wait(timeout=2.0)
        finally:
            selector.close()
            process.stdout.close()
            process.stderr.close()
        return CommandResult(
            argv=command,
            exit_code=exit_code,
            stdout=bytes(buffers["stdout"]),
            stderr=bytes(buffers["stderr"]),
            timed_out=timed_out,
            stdout_truncated=truncated["stdout"],
            stderr_truncated=truncated["stderr"],
        )


@dataclass(frozen=True)
class HostCapabilityEvidence:
    podman_version: str
    cgroup_version: str
    cgroup_controllers: tuple[str, ...]
    seccomp_enabled: bool
    rootless: bool
    image_id: str
    image_digest: str

    def to_record(self) -> dict[str, object]:
        return asdict(self)


def _mapping_value(mapping: Mapping[str, Any], *names: str) -> Any:
    folded = {str(key).casefold(): value for key, value in mapping.items()}
    for name in names:
        if name.casefold() in folded:
            return folded[name.casefold()]
    return None


class PodmanHostProbe:
    def __init__(
        self,
        runner: CommandRunner,
        *,
        podman_binary: str,
        controllers_path: Path = Path("/sys/fs/cgroup/cgroup.controllers"),
    ) -> None:
        self._runner = runner
        self._podman = podman_binary
        self._controllers_path = controllers_path

    def _query(self, argv: Sequence[str]) -> object:
        result = self._runner.run(
            argv,
            timeout_seconds=10.0,
            stdout_limit=1_048_576,
            stderr_limit=16_384,
        )
        if result.timed_out or result.exit_code != 0 or result.stdout_truncated:
            raise HostUnavailable("podman_probe_failed")
        try:
            return json.loads(result.stdout.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise HostUnavailable("podman_probe_invalid") from exc

    def probe(self, immutable_ref: str, expected_digest: str) -> HostCapabilityEvidence:
        info = self._query((self._podman, "info", "--format", "json"))
        if not isinstance(info, Mapping):
            raise HostUnavailable("podman_info_invalid")
        host = _mapping_value(info, "host")
        version_record = _mapping_value(info, "version")
        if not isinstance(host, Mapping):
            raise HostUnavailable("podman_host_info_missing")
        security = _mapping_value(host, "security")
        if not isinstance(security, Mapping):
            raise HostUnavailable("podman_security_info_missing")
        rootless = _mapping_value(security, "rootless")
        seccomp = _mapping_value(security, "seccompEnabled", "seccomp_enabled")
        cgroup_version = str(_mapping_value(host, "cgroupVersion", "cgroup_version") or "").lower()
        if rootless is not True:
            raise HostUnavailable("podman_not_rootless")
        if seccomp is not True:
            raise HostUnavailable("podman_seccomp_unavailable")
        if cgroup_version not in {"v2", "2"}:
            raise HostUnavailable("cgroup_v2_unavailable")
        controllers_value = _mapping_value(host, "cgroupControllers", "cgroup_controllers")
        if isinstance(controllers_value, list):
            controllers = {str(item) for item in controllers_value}
        else:
            try:
                controllers = set(self._controllers_path.read_text(encoding="ascii").split())
            except (OSError, UnicodeError) as exc:
                raise HostUnavailable("cgroup_controllers_unavailable") from exc
        if not {"cpu", "memory", "pids"}.issubset(controllers):
            raise HostUnavailable("required_cgroup_controllers_unavailable")

        inspected = self._query(
            (self._podman, "image", "inspect", immutable_ref, "--format", "json")
        )
        if not isinstance(inspected, list) or len(inspected) != 1 or not isinstance(inspected[0], Mapping):
            raise HostUnavailable("image_inspect_invalid")
        image = inspected[0]
        image_id = str(_mapping_value(image, "Id", "ID") or "")
        digest = str(_mapping_value(image, "Digest") or "")
        repo_digests = _mapping_value(image, "RepoDigests")
        digest_candidates = {digest}
        if isinstance(repo_digests, list):
            digest_candidates.update(
                str(item).rsplit("@", 1)[-1]
                for item in repo_digests
                if isinstance(item, str) and "@" in item
            )
        if expected_digest not in digest_candidates:
            raise HostUnavailable("cached_image_digest_mismatch")
        if _SHA256.fullmatch(image_id) is not None:
            image_id = f"sha256:{image_id}"
        if _IMAGE_DIGEST.fullmatch(image_id) is None:
            raise HostUnavailable("cached_image_id_invalid")
        podman_version = ""
        if isinstance(version_record, Mapping):
            podman_version = str(_mapping_value(version_record, "Version") or "")
        return HostCapabilityEvidence(
            podman_version=podman_version,
            cgroup_version="v2",
            cgroup_controllers=tuple(sorted(controllers)),
            seccomp_enabled=True,
            rootless=True,
            image_id=image_id,
            image_digest=expected_digest,
        )


class ReplayStore:
    """Owner-only durable claims; one full authority tuple executes once."""

    def __init__(self, state_dir: Path) -> None:
        self.state_dir = _private_directory(state_dir, create=True)

    @staticmethod
    def authority_key(authority: Mapping[str, object]) -> str:
        return _sha256_json(authority)

    def _create_exclusive(self, path: Path, payload: bytes) -> None:
        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
        try:
            fd = os.open(path, flags, 0o600)
        except FileExistsError as exc:
            raise ReplayRejected("authority_already_consumed") from exc
        try:
            _write_all(fd, payload)
            os.fsync(fd)
        finally:
            os.close(fd)
        _fsync_directory(self.state_dir)

    def claim(
        self,
        authority: Mapping[str, object],
        *,
        lease_scope: Mapping[str, object] | None = None,
    ) -> tuple[str, Path]:
        key = self.authority_key(authority)
        if lease_scope is not None:
            lease_key = self.authority_key(lease_scope)
            lease_path = self.state_dir / f"{lease_key}.lease.json"
            self._create_exclusive(
                lease_path,
                _canonical_bytes(
                    {
                        "authority_sha256": key,
                        "lease_scope": dict(lease_scope),
                        "state": "consumed",
                    }
                )
                + b"\n",
            )
        path = self.state_dir / f"{key}.claim.json"
        self._create_exclusive(
            path,
            _canonical_bytes(
                {
                    "authority": dict(authority),
                    "authority_sha256": key,
                    "state": "claimed",
                }
            )
            + b"\n",
        )
        return key, path

    def finalize(self, key: str, record: Mapping[str, object]) -> Path:
        _require_sha256("authority_sha256", key)
        target = self.state_dir / f"{key}.result.json"
        temporary = self.state_dir / f".{key}.{secrets.token_hex(8)}.tmp"
        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
        payload = _canonical_bytes(dict(record)) + b"\n"
        fd = os.open(temporary, flags, 0o600)
        try:
            _write_all(fd, payload)
            os.fsync(fd)
        finally:
            os.close(fd)
        os.replace(temporary, target)
        _fsync_directory(self.state_dir)
        return target


@dataclass(frozen=True)
class ExecutionEvidence:
    authority_sha256: str
    policy_sha256: str
    account_id: str
    workload_id: str
    manifest_id: str
    manifest_sha256: str
    lease_id: str
    lease_sha256: str
    fencing_token: int
    node_id: str
    runtime_image: str
    immutable_image_ref: str
    cached_image_id: str
    entrypoint_id: str
    input_set_sha256: str
    output_set_sha256: str
    outputs: tuple[Mapping[str, object], ...]
    exit_code: int
    stdout_bytes: int
    stderr_bytes: int
    stdout_sha256: str
    stderr_sha256: str
    host: HostCapabilityEvidence

    def to_record(self) -> dict[str, object]:
        return {
            "authority_sha256": self.authority_sha256,
            "policy_sha256": self.policy_sha256,
            "account_id": self.account_id,
            "workload_id": self.workload_id,
            "manifest_id": self.manifest_id,
            "manifest_sha256": self.manifest_sha256,
            "lease_id": self.lease_id,
            "lease_sha256": self.lease_sha256,
            "fencing_token": self.fencing_token,
            "node_id": self.node_id,
            "runtime_image": self.runtime_image,
            "immutable_image_ref": self.immutable_image_ref,
            "cached_image_id": self.cached_image_id,
            "entrypoint_id": self.entrypoint_id,
            "input_set_sha256": self.input_set_sha256,
            "output_set_sha256": self.output_set_sha256,
            "outputs": [dict(item) for item in self.outputs],
            "exit_code": self.exit_code,
            "stdout_bytes": self.stdout_bytes,
            "stderr_bytes": self.stderr_bytes,
            "stdout_sha256": self.stdout_sha256,
            "stderr_sha256": self.stderr_sha256,
            "host": self.host.to_record(),
        }


@dataclass(frozen=True)
class ExecutionResult:
    status: ExecutionStatus
    reason: str
    evidence: ExecutionEvidence | None = None

    @property
    def ok(self) -> bool:
        return self.status is ExecutionStatus.SUCCEEDED


class PodmanExecutor:
    """Execute one admitted CPU workload under a fixed rootless Podman policy."""

    def __init__(
        self,
        policy: ExecutorPolicy,
        *,
        runner: CommandRunner | None = None,
        controllers_path: Path = Path("/sys/fs/cgroup/cgroup.controllers"),
    ) -> None:
        self._policy = policy
        self._runner = runner or SubprocessCommandRunner()
        self._state_dir = _private_directory(policy.state_dir, create=True)
        self._artifact_dir = _private_directory(policy.artifact_dir, create=True)
        self._output_dir = _private_directory(policy.output_dir, create=True)
        if len({self._state_dir, self._artifact_dir, self._output_dir}) != 3:
            raise InvalidExecutionRequest("executor_roots_must_be_distinct")
        self._store = ReplayStore(self._state_dir)
        self._probe = PodmanHostProbe(
            self._runner,
            podman_binary=policy.podman_binary,
            controllers_path=controllers_path,
        )
        self._uid = os.geteuid()
        self._gid = os.getegid()
        if self._uid == 0:
            raise InvalidExecutionRequest("root_executor_is_forbidden")

    def _select_policy(
        self, request: AdmittedExecutionRequest
    ) -> tuple[str, str, TrustedEntrypoint, str]:
        manifest = request.manifest
        logical_image = f"{manifest.runtime_image.image_id}@{manifest.runtime_image.digest}"
        immutable_ref = self._policy.trusted_images.get(logical_image)
        if immutable_ref is None:
            raise InvalidExecutionRequest("runtime_image_not_trusted")
        entrypoint = self._policy.trusted_entrypoints.get(manifest.entrypoint_id)
        if entrypoint is None:
            raise InvalidExecutionRequest("entrypoint_not_trusted")
        if tuple(manifest.outputs) != tuple(output_id for output_id, _ in entrypoint.outputs):
            raise InvalidExecutionRequest("manifest_outputs_do_not_match_entrypoint")
        if manifest.filesystem.writable_paths != [entrypoint.output_mount]:
            raise InvalidExecutionRequest("manifest_writable_paths_exceed_executor_surface")
        if manifest.resources.scratch_bytes != 0:
            raise InvalidExecutionRequest("scratch_is_not_supported_by_cpu_slice")
        if manifest.resources.output_bytes <= 0:
            raise InvalidExecutionRequest("output_budget_required")
        if manifest.resources.open_file_limit < 16:
            raise InvalidExecutionRequest("open_file_limit_too_small")
        policy_record = {
            "version": "planetary.aivm.podman-cpu-policy.v1",
            "image": {"logical": logical_image, "immutable_ref": immutable_ref},
            "entrypoint": entrypoint.policy_record(),
            "isolation": {
                "rootless": True,
                "network": "none",
                "rootfs": "readonly",
                "capabilities": "none",
                "no_new_privileges": True,
                "userns": "keep-id",
                "uid": self._uid,
                "gid": self._gid,
                "pull": "never",
            },
            "resources": manifest.resources.model_dump(mode="json"),
            "output_limits": {
                "files": self._policy.max_output_files,
                "per_file_bytes": self._policy.max_output_file_bytes,
                "stdout_bytes": self._policy.stdout_limit_bytes,
                "stderr_bytes": self._policy.stderr_limit_bytes,
            },
        }
        return logical_image, immutable_ref, entrypoint, _sha256_json(policy_record)

    def _verify_inputs(self, request: AdmittedExecutionRequest, entrypoint: TrustedEntrypoint) -> str:
        manifest = request.manifest
        descriptors = {item.artifact_id: item for item in manifest.artifacts}
        records: list[dict[str, object]] = []
        output_prefix = entrypoint.output_mount.rstrip("/") + "/"
        for artifact_id in manifest.inputs:
            descriptor = descriptors[artifact_id]
            if descriptor.mount_path == entrypoint.output_mount or descriptor.mount_path.startswith(output_prefix):
                raise InvalidExecutionRequest("input_overlaps_output_mount")
            path = self._artifact_dir / descriptor.sha256
            try:
                before = path.lstat()
            except FileNotFoundError as exc:
                raise InvalidExecutionRequest("input_artifact_unavailable") from exc
            if (
                not stat.S_ISREG(before.st_mode)
                or before.st_uid != self._uid
                or before.st_nlink != 1
                or stat.S_IMODE(before.st_mode) & 0o022
                or before.st_size != descriptor.size_bytes
            ):
                raise InvalidExecutionRequest("input_artifact_not_confined")
            flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
            fd = os.open(path, flags)
            digest = hashlib.sha256()
            try:
                opened = os.fstat(fd)
                if (opened.st_dev, opened.st_ino) != (before.st_dev, before.st_ino):
                    raise InvalidExecutionRequest("input_artifact_changed")
                while True:
                    chunk = os.read(fd, _READ_CHUNK)
                    if not chunk:
                        break
                    digest.update(chunk)
            finally:
                os.close(fd)
            if digest.hexdigest() != descriptor.sha256:
                raise InvalidExecutionRequest("input_artifact_digest_mismatch")
            records.append(
                {
                    "artifact_id": artifact_id,
                    "mount_path": descriptor.mount_path,
                    "sha256": descriptor.sha256,
                    "size_bytes": descriptor.size_bytes,
                }
            )
        return _sha256_json(records)

    def _authority_record(
        self,
        request: AdmittedExecutionRequest,
        *,
        logical_image: str,
        immutable_ref: str,
        policy_sha256: str,
        input_set_sha256: str,
    ) -> dict[str, object]:
        return {
            "account_id": request.manifest.account_id,
            "workload_id": request.manifest.workload_id,
            "manifest_id": request.manifest.manifest_id,
            "manifest_sha256": request.manifest_sha256,
            "runtime_image": logical_image,
            "immutable_image_ref": immutable_ref,
            "entrypoint_id": request.manifest.entrypoint_id,
            "input_set_sha256": input_set_sha256,
            "lease": request.lease.to_record(),
            "policy_sha256": policy_sha256,
        }

    def _build_command(
        self,
        request: AdmittedExecutionRequest,
        *,
        immutable_ref: str,
        entrypoint: TrustedEntrypoint,
        output_path: Path,
        name: str,
        cidfile: Path,
    ) -> tuple[str, ...]:
        if _CONTAINER_NAME.fullmatch(name) is None:
            raise InvalidExecutionRequest("invalid_container_name")
        resources = request.manifest.resources
        cpus = f"{resources.cpu_millicores / 1000:.3f}"
        argv: list[str] = [
            self._policy.podman_binary,
            "run",
            "--pull=never",
            "--name",
            name,
            "--cidfile",
            str(cidfile),
            "--network=none",
            "--read-only",
            "--cap-drop=all",
            "--security-opt=no-new-privileges",
            "--userns=keep-id",
            "--user",
            f"{self._uid}:{self._gid}",
            "--ipc=private",
            "--pid=private",
            "--uts=private",
            "--log-driver=none",
            "--cpus",
            cpus,
            "--memory",
            str(resources.memory_bytes),
            "--memory-swap",
            str(resources.memory_bytes),
            "--pids-limit",
            str(resources.process_limit),
            "--ulimit",
            f"nofile={resources.open_file_limit}:{resources.open_file_limit}",
            "--workdir",
            "/work",
        ]
        descriptors = {item.artifact_id: item for item in request.manifest.artifacts}
        for artifact_id in request.manifest.inputs:
            descriptor = descriptors[artifact_id]
            source = self._artifact_dir / descriptor.sha256
            argv.extend(
                (
                    "--volume",
                    f"{source}:{descriptor.mount_path}:ro,nosuid,nodev,noexec",
                )
            )
        argv.extend(
            (
                "--volume",
                f"{output_path}:{entrypoint.output_mount}:rw,nosuid,nodev,noexec",
                "--entrypoint",
                entrypoint.executable,
                immutable_ref,
                *entrypoint.arguments,
            )
        )
        return tuple(argv)

    def _control(self, *arguments: str) -> bool:
        try:
            result = self._runner.run(
                (self._policy.podman_binary, *arguments),
                timeout_seconds=5.0,
                stdout_limit=4096,
                stderr_limit=4096,
            )
        except RunnerUnavailable:
            return False
        return not result.timed_out and result.exit_code == 0

    def _cleanup(self, name: str, *, timed_out: bool) -> bool:
        ok = True
        if timed_out:
            ok = self._control("stop", "--time", "1", "--ignore", name) and ok
            ok = self._control("kill", "--signal", "KILL", "--ignore", name) and ok
        ok = self._control("rm", "--force", "--ignore", name) and ok
        return ok

    def _scan_outputs(
        self,
        output_path: Path,
        entrypoint: TrustedEntrypoint,
        byte_budget: int,
    ) -> tuple[tuple[Mapping[str, object], ...], str]:
        expected = {relative: output_id for output_id, relative in entrypoint.outputs}
        allowed_directories = {""}
        for relative in expected:
            parent = PurePosixPath(relative).parent
            while str(parent) != ".":
                allowed_directories.add(str(parent))
                parent = parent.parent
        seen: set[str] = set()
        records: list[Mapping[str, object]] = []
        total = 0
        for root, directories, files in os.walk(output_path, topdown=True, followlinks=False):
            root_path = Path(root)
            relative_root = root_path.relative_to(output_path).as_posix()
            if relative_root == ".":
                relative_root = ""
            for directory in list(directories):
                path = root_path / directory
                relative = f"{relative_root}/{directory}".strip("/")
                info = path.lstat()
                if (
                    relative not in allowed_directories
                    or stat.S_ISLNK(info.st_mode)
                    or not stat.S_ISDIR(info.st_mode)
                    or info.st_uid != self._uid
                ):
                    raise OutputViolation("unsafe_output_directory")
            for filename in files:
                path = root_path / filename
                relative = f"{relative_root}/{filename}".strip("/")
                if relative not in expected or relative in seen:
                    raise OutputViolation("unexpected_output")
                if len(seen) >= self._policy.max_output_files:
                    raise OutputViolation("output_file_count_exceeded")
                before = path.lstat()
                if (
                    not stat.S_ISREG(before.st_mode)
                    or before.st_uid != self._uid
                    or before.st_nlink != 1
                    or stat.S_IMODE(before.st_mode) & 0o022
                ):
                    raise OutputViolation("unsafe_output_file")
                if before.st_size > self._policy.max_output_file_bytes:
                    raise OutputViolation("output_file_too_large")
                total += before.st_size
                if total > byte_budget:
                    raise OutputViolation("output_budget_exceeded")
                flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
                fd = os.open(path, flags)
                digest = hashlib.sha256()
                measured = 0
                try:
                    opened = os.fstat(fd)
                    if (opened.st_dev, opened.st_ino) != (before.st_dev, before.st_ino):
                        raise OutputViolation("output_changed_during_validation")
                    while True:
                        chunk = os.read(fd, _READ_CHUNK)
                        if not chunk:
                            break
                        measured += len(chunk)
                        if measured > self._policy.max_output_file_bytes or measured > byte_budget:
                            raise OutputViolation("output_file_too_large")
                        digest.update(chunk)
                    after = os.fstat(fd)
                    if (
                        (after.st_dev, after.st_ino) != (before.st_dev, before.st_ino)
                        or after.st_size != before.st_size
                        or after.st_nlink != 1
                        or not stat.S_ISREG(after.st_mode)
                    ):
                        raise OutputViolation("output_changed_during_validation")
                finally:
                    os.close(fd)
                records.append(
                    {
                        "output_id": expected[relative],
                        "path": relative,
                        "sha256": digest.hexdigest(),
                        "size_bytes": measured,
                    }
                )
                seen.add(relative)
        if len(seen) > self._policy.max_output_files:
            raise OutputViolation("output_file_count_exceeded")
        if seen != set(expected):
            raise OutputViolation("required_output_missing")
        records.sort(key=lambda item: str(item["output_id"]))
        immutable_records = tuple(MappingProxyType(dict(item)) for item in records)
        return immutable_records, _sha256_json(records)

    def _finalize_failure(self, authority_key: str, status: ExecutionStatus, reason: str) -> None:
        try:
            self._store.finalize(
                authority_key,
                {
                    "authority_sha256": authority_key,
                    "reason": reason,
                    "status": status.value,
                },
            )
        except OSError:
            pass

    def execute(self, request: AdmittedExecutionRequest) -> ExecutionResult:
        if type(request) is not AdmittedExecutionRequest:
            return ExecutionResult(ExecutionStatus.REJECTED, "validated_request_required")
        authority_key = ""
        name = ""
        cidfile: Path | None = None
        try:
            logical_image, immutable_ref, entrypoint, policy_sha256 = self._select_policy(request)
            input_set_sha256 = self._verify_inputs(request, entrypoint)
            host = self._probe.probe(immutable_ref, request.manifest.runtime_image.digest)
            authority = self._authority_record(
                request,
                logical_image=logical_image,
                immutable_ref=immutable_ref,
                policy_sha256=policy_sha256,
                input_set_sha256=input_set_sha256,
            )
            authority_key, _ = self._store.claim(
                authority,
                lease_scope={
                    "account_id": request.lease.account_id,
                    "node_id": request.lease.node_id,
                    "lease_id": request.lease.lease_id,
                },
            )
            output_path = self._output_dir / authority_key
            output_path.mkdir(mode=0o700, exist_ok=False)
            if stat.S_IMODE(output_path.lstat().st_mode) != 0o700:
                raise OutputViolation("output_directory_not_owner_only")
            name = f"aivm-{authority_key[:16]}-{secrets.token_hex(4)}"
            cidfile = self._state_dir / f"{name}.cid"
            argv = self._build_command(
                request,
                immutable_ref=immutable_ref,
                entrypoint=entrypoint,
                output_path=output_path,
                name=name,
                cidfile=cidfile,
            )
            result = self._runner.run(
                argv,
                timeout_seconds=float(request.manifest.resources.time_limit_seconds),
                stdout_limit=self._policy.stdout_limit_bytes,
                stderr_limit=self._policy.stderr_limit_bytes,
            )
            cleanup_ok = self._cleanup(name, timed_out=result.timed_out)
            if cidfile is not None:
                try:
                    cidfile.unlink()
                except FileNotFoundError:
                    pass
                except OSError:
                    cleanup_ok = False
            if not cleanup_ok:
                reason = "container_cleanup_failed"
                self._finalize_failure(authority_key, ExecutionStatus.UNAVAILABLE, reason)
                return ExecutionResult(ExecutionStatus.UNAVAILABLE, reason)
            if result.timed_out:
                reason = "execution_timeout"
                self._finalize_failure(authority_key, ExecutionStatus.FAILED, reason)
                return ExecutionResult(ExecutionStatus.FAILED, reason)
            if result.stdout_truncated or result.stderr_truncated:
                reason = "process_output_limit_exceeded"
                self._finalize_failure(authority_key, ExecutionStatus.FAILED, reason)
                return ExecutionResult(ExecutionStatus.FAILED, reason)
            if result.exit_code != 0:
                reason = "container_exit_nonzero"
                self._finalize_failure(authority_key, ExecutionStatus.FAILED, reason)
                return ExecutionResult(ExecutionStatus.FAILED, reason)
            outputs, output_set_sha256 = self._scan_outputs(
                output_path,
                entrypoint,
                min(
                    request.manifest.resources.output_bytes,
                    self._policy.max_output_files * self._policy.max_output_file_bytes,
                ),
            )
            evidence = ExecutionEvidence(
                authority_sha256=authority_key,
                policy_sha256=policy_sha256,
                account_id=request.manifest.account_id,
                workload_id=request.manifest.workload_id,
                manifest_id=request.manifest.manifest_id,
                manifest_sha256=request.manifest_sha256,
                lease_id=request.lease.lease_id,
                lease_sha256=request.lease.lease_sha256,
                fencing_token=request.lease.fencing_token,
                node_id=request.lease.node_id,
                runtime_image=logical_image,
                immutable_image_ref=immutable_ref,
                cached_image_id=host.image_id,
                entrypoint_id=entrypoint.entrypoint_id,
                input_set_sha256=input_set_sha256,
                output_set_sha256=output_set_sha256,
                outputs=outputs,
                exit_code=result.exit_code,
                stdout_bytes=len(result.stdout),
                stderr_bytes=len(result.stderr),
                stdout_sha256=hashlib.sha256(result.stdout).hexdigest(),
                stderr_sha256=hashlib.sha256(result.stderr).hexdigest(),
                host=host,
            )
            self._store.finalize(
                authority_key,
                {
                    "authority_sha256": authority_key,
                    "evidence": evidence.to_record(),
                    "status": ExecutionStatus.SUCCEEDED.value,
                },
            )
            return ExecutionResult(ExecutionStatus.SUCCEEDED, "execution_verified", evidence)
        except ReplayRejected:
            return ExecutionResult(ExecutionStatus.REJECTED, "authority_already_consumed")
        except InvalidExecutionRequest as exc:
            return ExecutionResult(ExecutionStatus.REJECTED, str(exc))
        except HostUnavailable as exc:
            return ExecutionResult(ExecutionStatus.UNAVAILABLE, str(exc))
        except OutputViolation as exc:
            if authority_key:
                self._finalize_failure(authority_key, ExecutionStatus.FAILED, str(exc))
            return ExecutionResult(ExecutionStatus.FAILED, str(exc))
        except RunnerUnavailable:
            if name:
                self._cleanup(name, timed_out=True)
            if authority_key:
                self._finalize_failure(authority_key, ExecutionStatus.UNAVAILABLE, "podman_unavailable")
            return ExecutionResult(ExecutionStatus.UNAVAILABLE, "podman_unavailable")
        except (OSError, ValueError, TypeError):
            if name:
                self._cleanup(name, timed_out=True)
            if authority_key:
                self._finalize_failure(authority_key, ExecutionStatus.UNAVAILABLE, "execution_boundary_error")
            return ExecutionResult(ExecutionStatus.UNAVAILABLE, "execution_boundary_error")
