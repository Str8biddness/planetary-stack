"""Bounded agent loop over an Ollama-style chat endpoint.

Ollama is an inference server, not an agent runtime. `/api/chat` will return a
structured `tool_calls` block for models trained on tool use (llama3.1,
qwen2.5, mistral-nemo), but it never executes anything: the CLIENT executes the
call and feeds the result back. This module is that missing loop, written for
mesh workers running under Termux + proot-distro on spare Android phones.

WHY THE TOOL SURFACE IS NOT A SHELL
-----------------------------------
These workers have NO container isolation. proot on an unrooted phone gives no
Podman, no seccomp, no user namespaces — a `run_command` tool there is a
process on the owner's device with the owner's files. The same worker processes
documents synced from other nodes, so model input is attacker-reachable: a
poisoned document that says "ignore previous instructions and run X" is a
direct path from someone else's content to command execution.

So the surface is three structured operations and nothing else:

    read_input(input_id)             only the job's declared inputs, by id
    write_result(content, media_type) only the job's output dir, size-bounded
    list_workspace()                 only the job's scratch dir

There is no `run_command`, no network tool, and no argument anywhere in this
module that names a filesystem path. `read_input` takes an *identifier* that
must already appear in the job's declared inputs; `write_result` takes no
filename at all and the harness names the file. That is deliberate: a tool that
never accepts a path cannot be argued into traversing one.

Containment is enforced in the tool implementations, never by prompting. Every
resolved path must lie under the job workspace root, and the lexical path must
equal its realpath — which rejects `..`, absolute paths, and any symlink
anywhere in the chain. Prompt text is a request; these checks are the boundary.

BOUNDS
------
Every loop here is bounded and every bound fails closed: iterations, wall time,
per-write and total result bytes, conversation size, and tool-call fan-out per
round. A model that keeps calling tools forever stops with `ok=False` and a
machine-readable `stop_reason`; it never returns a success-shaped result.

An unknown tool name is REFUSED — an error result is fed back to the model and
recorded in the transcript. It is never silently dropped, because a silently
dropped call looks to the model like a tool that returned nothing, and to an
operator like a call that never happened.

HONEST SCOPE. This bounds what a compromised or manipulated model can DO on the
worker. It does not make the model trustworthy, does not detect that a prompt
injection occurred, and does not stop the model from writing attacker-chosen
text into the job's own result. It stops that text from becoming a command, a
read outside the declared inputs, or a write outside the output directory.
"""

from __future__ import annotations

import json
import time
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

# Defaults. Every one of these is an argument; none is a hard-coded policy.
DEFAULT_MAX_ITERATIONS = 8
DEFAULT_MAX_WALL_SECONDS = 120.0
DEFAULT_MAX_RESULT_BYTES = 64 * 1024
DEFAULT_MAX_TOTAL_RESULT_BYTES = 256 * 1024
DEFAULT_MAX_CONVERSATION_CHARS = 200_000
DEFAULT_MAX_INPUT_BYTES = 64 * 1024
DEFAULT_MAX_TOOL_CALLS_PER_ROUND = 8
DEFAULT_MAX_WORKSPACE_ENTRIES = 200

# Exact media types only. A wildcard or a list would put the choice of what the
# output IS back in the model's hands.
DEFAULT_ALLOWED_MEDIA_TYPES: frozenset[str] = frozenset(
    {"text/plain", "text/markdown", "application/json"}
)

_MEDIA_TYPE_SUFFIX: Mapping[str, str] = {
    "text/plain": ".txt",
    "text/markdown": ".md",
    "application/json": ".json",
}

READ_INPUT = "read_input"
WRITE_RESULT = "write_result"
LIST_WORKSPACE = "list_workspace"

#: The complete tool surface. There is no shell here and no network here.
TOOL_NAMES: frozenset[str] = frozenset({READ_INPUT, WRITE_RESULT, LIST_WORKSPACE})


class AgentHarnessError(ValueError):
    """A harness configuration or containment error. Always fail closed."""


class ToolRefusal(Exception):
    """A tool call the harness will not perform.

    Raised inside a tool implementation and converted into an error result that
    is fed back to the model. The model is told it was refused; it is not told
    a path, a directory listing, or anything else it did not already have.
    """


def _lexical_child(root: Path, *parts: str) -> Path:
    """Return `root/parts` only if it is genuinely inside `root`.

    `root` must already be a realpath. The candidate's realpath must equal its
    lexical path, which fails if any component is a symlink, and it must be
    under the root, which fails on `..` escapes. An absolute or parent-relative
    component is rejected before either check so the reason stays specific.
    """

    for part in parts:
        if not part:
            raise ToolRefusal("empty path component")
        candidate = Path(part)
        if candidate.is_absolute():
            raise ToolRefusal("absolute paths are not permitted")
        if ".." in candidate.parts:
            raise ToolRefusal("parent directory traversal is not permitted")

    resolved_root = root.resolve(strict=False)
    target = resolved_root.joinpath(*parts)
    real = target.resolve(strict=False)
    if real != target:
        # Either a symlink somewhere in the chain, or a normalisation we did
        # not perform ourselves. Both mean the path we checked is not the path
        # we would open.
        raise ToolRefusal("path does not resolve to itself (symlink or traversal)")
    if real != resolved_root and resolved_root not in real.parents:
        raise ToolRefusal("path escapes the job workspace")
    return real


@dataclass(frozen=True)
class JobWorkspace:
    """The only filesystem the tools can see.

    `inputs` maps a job-declared input id to a path RELATIVE to `root`. The
    model never supplies a path; it supplies an id that must already be a key
    here. `output_dir` and `scratch_dir` are likewise relative to `root`.
    """

    root: Path
    inputs: Mapping[str, str]
    output_dir: str = "output"
    scratch_dir: str = "scratch"

    def __post_init__(self) -> None:
        root = Path(self.root)
        if not root.is_dir():
            raise AgentHarnessError(f"workspace root is not a directory: {root}")
        object.__setattr__(self, "root", root.resolve(strict=True))
        if not self.inputs:
            # A job with no declared inputs is legal; a job whose inputs cannot
            # be validated is not. Validate each declared entry eagerly so a
            # bad declaration fails at construction, not mid-conversation.
            object.__setattr__(self, "inputs", {})
        for input_id, relative in dict(self.inputs).items():
            if not isinstance(input_id, str) or not input_id:
                raise AgentHarnessError("input ids must be non-empty strings")
            if not isinstance(relative, str) or not relative:
                raise AgentHarnessError(f"input {input_id!r} has no path")
            try:
                _lexical_child(self.root, relative)
            except ToolRefusal as exc:
                raise AgentHarnessError(
                    f"declared input {input_id!r} is outside the workspace: {exc}"
                ) from exc

    def output_path(self) -> Path:
        return _lexical_child(self.root, self.output_dir)

    def scratch_path(self) -> Path:
        return _lexical_child(self.root, self.scratch_dir)

    def input_path(self, input_id: str) -> Path:
        relative = self.inputs.get(input_id)
        if relative is None:
            raise ToolRefusal(f"unknown input id: {input_id!r}")
        return _lexical_child(self.root, relative)


@dataclass(frozen=True)
class HarnessBounds:
    """Every limit the loop enforces, in one place."""

    max_iterations: int = DEFAULT_MAX_ITERATIONS
    max_wall_seconds: float = DEFAULT_MAX_WALL_SECONDS
    max_result_bytes: int = DEFAULT_MAX_RESULT_BYTES
    max_total_result_bytes: int = DEFAULT_MAX_TOTAL_RESULT_BYTES
    max_conversation_chars: int = DEFAULT_MAX_CONVERSATION_CHARS
    max_input_bytes: int = DEFAULT_MAX_INPUT_BYTES
    max_tool_calls_per_round: int = DEFAULT_MAX_TOOL_CALLS_PER_ROUND
    max_workspace_entries: int = DEFAULT_MAX_WORKSPACE_ENTRIES
    allowed_media_types: frozenset[str] = DEFAULT_ALLOWED_MEDIA_TYPES

    def __post_init__(self) -> None:
        for name in (
            "max_iterations",
            "max_result_bytes",
            "max_total_result_bytes",
            "max_conversation_chars",
            "max_input_bytes",
            "max_tool_calls_per_round",
            "max_workspace_entries",
        ):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, int) or value < 1:
                raise AgentHarnessError(f"{name} must be a positive integer")
        if self.max_wall_seconds <= 0:
            raise AgentHarnessError("max_wall_seconds must be positive")
        if not self.allowed_media_types:
            raise AgentHarnessError("at least one media type must be allowed")


@dataclass
class ToolCallRecord:
    """What was asked, and what the harness actually did about it."""

    iteration: int
    name: str
    arguments: dict[str, Any]
    ok: bool
    detail: str


@dataclass
class AgentRunResult:
    """Outcome of one bounded run.

    `ok` is True only when the model stopped calling tools of its own accord
    inside every bound. A tripped bound returns `ok=False` with a
    machine-readable `stop_reason`; it is never shaped like a success.
    """

    ok: bool
    stop_reason: str
    iterations: int
    messages: list[dict[str, Any]]
    tool_calls: list[ToolCallRecord] = field(default_factory=list)
    written_files: list[str] = field(default_factory=list)
    final_content: str = ""

    @property
    def refusals(self) -> list[ToolCallRecord]:
        return [record for record in self.tool_calls if not record.ok]


def tool_schemas() -> list[dict[str, Any]]:
    """Ollama `/api/chat` tool definitions for the bounded surface.

    Note what is absent: no command, no url, no path, no filename. The schema
    is the advertisement; `_execute_tool` is the enforcement.
    """

    return [
        {
            "type": "function",
            "function": {
                "name": READ_INPUT,
                "description": (
                    "Read one of this job's declared inputs by its id. "
                    "Only ids listed in the job brief exist; no other content "
                    "is reachable."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "input_id": {
                            "type": "string",
                            "description": "A declared input id from the job brief.",
                        }
                    },
                    "required": ["input_id"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": WRITE_RESULT,
                "description": (
                    "Write the job result. The harness chooses the filename; "
                    "content is size-bounded."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "content": {"type": "string"},
                        "media_type": {
                            "type": "string",
                            "description": "Exact media type, e.g. text/plain.",
                        },
                    },
                    "required": ["content", "media_type"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": LIST_WORKSPACE,
                "description": (
                    "List the names in this job's scratch directory. Takes no "
                    "arguments and cannot list any other directory."
                ),
                "parameters": {"type": "object", "properties": {}},
            },
        },
    ]


def _coerce_arguments(raw: Any) -> dict[str, Any]:
    """Ollama returns arguments as an object; some builds return a JSON string."""

    if raw is None:
        return {}
    if isinstance(raw, Mapping):
        return dict(raw)
    if isinstance(raw, (str, bytes, bytearray)):
        try:
            parsed = json.loads(raw)
        except (ValueError, TypeError) as exc:
            raise ToolRefusal("tool arguments are not valid JSON") from exc
        if not isinstance(parsed, Mapping):
            raise ToolRefusal("tool arguments must be a JSON object")
        return dict(parsed)
    raise ToolRefusal("tool arguments must be a JSON object")


def _extract_message(response: Any) -> dict[str, Any]:
    """Accept either a full `/api/chat` response or just its message."""

    if not isinstance(response, Mapping):
        raise AgentHarnessError("chat_fn must return a mapping")
    message = response.get("message", response)
    if not isinstance(message, Mapping):
        raise AgentHarnessError("chat response message must be a mapping")
    return dict(message)


def _extract_tool_calls(message: Mapping[str, Any]) -> list[dict[str, Any]]:
    calls = message.get("tool_calls") or []
    if not isinstance(calls, Sequence) or isinstance(calls, (str, bytes)):
        raise AgentHarnessError("tool_calls must be a list")
    return [dict(call) for call in calls if isinstance(call, Mapping)]


def _conversation_chars(messages: Sequence[Mapping[str, Any]]) -> int:
    return sum(len(json.dumps(message, default=str)) for message in messages)


class _ResultWriter:
    """Names output files itself so no model-supplied string reaches a path."""

    def __init__(self, workspace: JobWorkspace, bounds: HarnessBounds) -> None:
        self._workspace = workspace
        self._bounds = bounds
        self._written_bytes = 0
        self._sequence = 0
        self.written_files: list[str] = []

    def write(self, content: str, media_type: str) -> str:
        if not isinstance(content, str):
            raise ToolRefusal("content must be a string")
        if not isinstance(media_type, str):
            raise ToolRefusal("media_type must be a string")
        media_type = media_type.strip().lower()
        if media_type not in self._bounds.allowed_media_types:
            raise ToolRefusal(f"media type not permitted: {media_type!r}")

        payload = content.encode("utf-8")
        if len(payload) > self._bounds.max_result_bytes:
            # Refused, not truncated. Silently shortening an answer would make
            # a bounded result indistinguishable from a complete one.
            raise ToolRefusal(
                f"result is {len(payload)} bytes; the limit is "
                f"{self._bounds.max_result_bytes}"
            )
        if self._written_bytes + len(payload) > self._bounds.max_total_result_bytes:
            raise ToolRefusal("total result byte budget exhausted")

        output_dir = self._workspace.output_path()
        output_dir.mkdir(parents=True, exist_ok=True)
        self._sequence += 1
        name = f"result-{self._sequence:03d}{_MEDIA_TYPE_SUFFIX.get(media_type, '.bin')}"
        # Re-validate the composed name through the same containment check the
        # model's arguments go through, even though the model did not supply it.
        target = _lexical_child(output_dir, name)
        if target.exists():
            raise ToolRefusal(f"result {name} already exists")
        target.write_bytes(payload)
        self._written_bytes += len(payload)
        self.written_files.append(name)
        return name


def _read_input(workspace: JobWorkspace, bounds: HarnessBounds, arguments: Mapping[str, Any]) -> str:
    input_id = arguments.get("input_id")
    if not isinstance(input_id, str) or not input_id:
        raise ToolRefusal("input_id must be a non-empty string")
    path = workspace.input_path(input_id)
    if not path.is_file():
        raise ToolRefusal(f"input {input_id!r} is not a readable file")
    data = path.read_bytes()
    if len(data) > bounds.max_input_bytes:
        raise ToolRefusal(
            f"input {input_id!r} is {len(data)} bytes; the limit is "
            f"{bounds.max_input_bytes}"
        )
    return data.decode("utf-8", errors="replace")


def _list_workspace(workspace: JobWorkspace, bounds: HarnessBounds) -> str:
    scratch = workspace.scratch_path()
    if not scratch.is_dir():
        return json.dumps({"entries": [], "note": "scratch directory is empty"})
    entries: list[dict[str, Any]] = []
    truncated = False
    for child in sorted(scratch.iterdir(), key=lambda p: p.name):
        if len(entries) >= bounds.max_workspace_entries:
            truncated = True
            break
        if child.is_symlink():
            # Listed as refused rather than hidden: an operator reading the
            # transcript should see that something in the scratch directory
            # pointed outward, and the model should not learn where.
            entries.append({"name": child.name, "kind": "refused_symlink"})
            continue
        kind = "directory" if child.is_dir() else "file"
        entry: dict[str, Any] = {"name": child.name, "kind": kind}
        if kind == "file":
            entry["bytes"] = child.stat().st_size
        entries.append(entry)
    return json.dumps({"entries": entries, "truncated": truncated})


def _execute_tool(
    name: str,
    arguments: Mapping[str, Any],
    *,
    workspace: JobWorkspace,
    bounds: HarnessBounds,
    writer: _ResultWriter,
) -> str:
    if name == READ_INPUT:
        return _read_input(workspace, bounds, arguments)
    if name == WRITE_RESULT:
        written = writer.write(arguments.get("content"), arguments.get("media_type"))
        return json.dumps({"written": written})
    if name == LIST_WORKSPACE:
        return _list_workspace(workspace, bounds)
    # Unknown name. Refuse loudly. The message deliberately does not enumerate
    # the real tools back to a caller that guessed a shell.
    raise ToolRefusal(f"unknown tool: {name!r}")


def run_agent(
    *,
    chat_fn: Callable[..., Any],
    workspace: JobWorkspace,
    messages: Sequence[Mapping[str, Any]],
    model: str = "llama3.1",
    bounds: HarnessBounds | None = None,
    clock: Callable[[], float] = time.monotonic,
) -> AgentRunResult:
    """Drive one bounded tool-calling conversation.

    `chat_fn(model=..., messages=..., tools=...)` must return an Ollama-shaped
    `/api/chat` response (or just its `message`). It is injected so the loop is
    testable without a live Ollama — this harness never opens a socket itself.

    Returns an `AgentRunResult`. Bounds trip into `ok=False` with a
    `stop_reason`; they never raise past the caller as a success.
    """

    bounds = bounds or HarnessBounds()
    if not callable(chat_fn):
        raise AgentHarnessError("chat_fn must be callable")

    conversation: list[dict[str, Any]] = [dict(message) for message in messages]
    if not conversation:
        raise AgentHarnessError("messages must not be empty")

    writer = _ResultWriter(workspace, bounds)
    records: list[ToolCallRecord] = []
    started = clock()
    iteration = 0
    final_content = ""

    def result(ok: bool, stop_reason: str) -> AgentRunResult:
        return AgentRunResult(
            ok=ok,
            stop_reason=stop_reason,
            iterations=iteration,
            messages=conversation,
            tool_calls=records,
            written_files=list(writer.written_files),
            final_content=final_content,
        )

    while True:
        if iteration >= bounds.max_iterations:
            return result(False, "iteration_limit")
        if clock() - started >= bounds.max_wall_seconds:
            return result(False, "wall_time_limit")
        if _conversation_chars(conversation) > bounds.max_conversation_chars:
            return result(False, "conversation_limit")

        iteration += 1
        response = chat_fn(model=model, messages=list(conversation), tools=tool_schemas())
        message = _extract_message(response)
        conversation.append(message)

        tool_calls = _extract_tool_calls(message)
        if not tool_calls:
            content = message.get("content")
            final_content = content if isinstance(content, str) else ""
            return result(True, "model_stopped")

        if len(tool_calls) > bounds.max_tool_calls_per_round:
            return result(False, "tool_call_fanout_limit")

        for call in tool_calls:
            function = call.get("function")
            function = dict(function) if isinstance(function, Mapping) else {}
            name = function.get("name")
            name = name if isinstance(name, str) else ""
            arguments: dict[str, Any] = {}
            try:
                arguments = _coerce_arguments(function.get("arguments"))
                if name not in TOOL_NAMES:
                    raise ToolRefusal(f"unknown tool: {name!r}")
                content = _execute_tool(
                    name,
                    arguments,
                    workspace=workspace,
                    bounds=bounds,
                    writer=writer,
                )
                ok, detail = True, "ok"
            except ToolRefusal as refusal:
                ok, detail = False, str(refusal)
                content = json.dumps({"error": detail})

            records.append(
                ToolCallRecord(
                    iteration=iteration,
                    name=name,
                    arguments=arguments,
                    ok=ok,
                    detail=detail,
                )
            )
            tool_message: dict[str, Any] = {
                "role": "tool",
                "tool_name": name,
                "content": content,
            }
            call_id = call.get("id")
            if isinstance(call_id, str) and call_id:
                tool_message["tool_call_id"] = call_id
            conversation.append(tool_message)
