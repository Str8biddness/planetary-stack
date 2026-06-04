# AIVM — Amplification Intelligence Virtual Machine

> Synthesus 3.0 — Self-Improving Learning Layer

## Overview

AIVM (Amplification Intelligence Virtual Machine) is Synthesus's self-improvement and amplification layer. It provides sandboxed model execution, multi-pass inference coordination, error recovery with circuit breakers, and hot-swap model loading.

## Architecture

```
Input Query
    │
    ▼
ExecutionEngine (orchestrator.py) ──► InstructionDispatcher (worker pool)
    │
    ├──────► SandboxManager ──────► ModelSandbox (isolated execution)
    │
    ├──────► ResourceAllocator (CPU/memory budgets per model)
    │
    ├──────► InferenceScheduler (multi-pass reasoning)
    │
    ├──────► ExecutionContextManager (conversation memory)
    │
    ├──────► HotSwapModelLoader (zero-downtime model hot-swapping)
    │
    └──────► ErrorRecoveryManager (circuit breakers + backoff)
              │
              ▼
         Amplified Response
```

## Key Files

| File/Directory | Purpose |
|---------------|---------|
| `aivm/orchestrator.py` | AIVMOrchestrator — top-level coordinator |
| `aivm/execution_engine.py` | ExecutionEngine — wires dispatcher, resource pool, and model loader |
| `aivm/isolation_layer.py` | ModelIsolationLayer — sandboxed model execution with resource limits |
| `aivm/hotswap_loader.py` | HotSwapModelLoader — zero-downtime model hot-swapping |
| `aivm/error_recovery.py` | ErrorRecoveryManager — circuit breakers + backoff |
| `aivm/model_loader.py` | ModelLoader — Management of ONNX/safetensors models with thread-safe registry |
| Subdirectories | dispatcher, sandbox, resource_manager, inference_scheduler, context_manager |

## ModelLoader & Registry

The `ModelLoader` manages the lifecycle of ONNX models, providing thread-safe registration and session management.

```python
from aivm.model_loader import ModelLoader, ModelState

loader = ModelLoader(models_dir="data/models")
loader.load_model("my_model", "./models/model.onnx")

info = loader.get_model_info("my_model")
print(f"Model state: {info.state}")

# Run inference through the sandbox
result = loader.infer("my_model", input_data=[1.0, 2.0, 3.0])
if result.success:
    print(f"Result: {result.output_data}")
```

## SandboxExecutor

The `SandboxExecutor` provides an isolated context for running potentially heavy or unsafe model inference operations. It uses `signal.SIGALRM` to enforce strict timeout limits.

| Feature | Implementation |
|---------|----------------|
| Timeout Enforcement | `signal.SIGALRM` with `ITIMER_REAL` |
| Concurrency Control | Thread-safe active execution counting |
| Error Handling | Categorized Timeout and Runtime error reporting |

## ExecutionEngine

The `ExecutionEngine` is the core heartbeat of AIVM, managing the flow of instructions through the system with built-in resource tracking and error recovery.

```python
from aivm.execution_engine import ExecutionEngine, VMInstruction, InstructionType

engine = ExecutionEngine(max_memory_mb=1024, max_threads=8)
engine.start()

# Execute a health check
instr = VMInstruction(instruction_id="h1", instruction_type=InstructionType.HEALTH_CHECK)
result = engine.execute(instr)
print(result.result)

engine.stop()
```

## AIVMOrchestrator

Main entry point. Manages complete lifecycle of concurrent Synthesus models with error recovery, hot-swap, and circuit breaker protection.

```python
from aivm import AIVMOrchestrator

orch = AIVMOrchestrator(config={
    "dispatcher_workers": 4,
    "sandbox_memory_mb": 512,
    "sandbox_timeout_s": 30.0,
    "max_concurrent_inference": 4,
    "max_contexts": 64,
    "max_sessions_per_model": 4,
    "models_dir": "./models",
})

if orch.initialize():
    orch.load_model("synth", "./models/synth.onnx")
    success, output, error = orch.run_inference("synth", {"query": "Hello"})
    orch.shutdown()
```

## Circuit Breaker Protection

All critical AIVM components are protected by circuit breakers:

| Component | Failure Threshold | Recovery Timeout |
|-----------|------------------|-----------------|
| dispatcher | 5 | 30s |
| sandbox | 5 | 30s |
| resource_allocator | 5 | 30s |
| inference_scheduler | 5 | 30s |
| context_manager | 5 | 30s |
| model_loader | 5 | 30s |
| isolation_layer | 5 | 30s |

## Error Recovery

```python
from aivm.error_recovery import ErrorRecoveryManager, retry_with_backoff, ErrorSeverity

erm = ErrorRecoveryManager()

# Manual error recording
erm.record_error("my_component", "error_type", "Something went wrong", ErrorSeverity.ERROR)

# Retry with exponential backoff
result = retry_with_backoff(
    fn=lambda: risky_operation(),
    max_retries=3,
    base_delay=1.0,
    max_delay=30.0,
)
```

## Hot-Swap Model Loading

Load new model versions without stopping inference:

```python
orch.load_model("synth_v1", "./models/synth_v1.onnx")
# ... run inference ...

# Hot-swap to new version
orch.hotswap_model("synth_v1", "synth_v2", "./models/synth_v2.onnx")
```

## Isolation Modes

```python
from aivm.isolation_layer import ModelIsolationLayer, IsolationMode

layer = ModelIsolationLayer()

# NONE — shared process, no isolation
# PROCESS — isolated subprocess per model
# FULL — maximum isolation with separate memory
```

## CHAL Device Execution Guard

Synthesus 5 hypervisor dispatches can now use `packages/aivm/isolation/guard.py` for bounded virtual-device execution. `AIVMExecutionGuard.run()` accepts a device id, an async or sync operation, a timeout budget, and trace metadata, then returns a `DeviceExecutionResult` with:

| Field | Purpose |
|-------|---------|
| `device_id` | CHAL/AIVM device URI or logical device name |
| `ok` / `status` | `ok`, `timeout`, or `fault` outcome |
| `latency_ms` | measured guarded execution latency |
| `output` | raw device result when successful |
| `error` | timeout/fault detail for degraded routing |
| `metadata` | trace id, route, hemisphere mode, or caller-specific context |

The Cognitive Hypervisor wraps hemisphere bridge dispatch with this guard, so timeout and fault cases produce degraded trace records instead of uncaught failures. Hypervisor telemetry now includes `device_isolation`, `budget_exhausted`, and `degraded` fields.

## Snapshot Integrity And Default Device Fallbacks

The AIVM kernel can now complete the canonical 12-step tick without external Knowledge Cloud or MemoryStore backends mounted. `VQD` returns an empty scoped result set when no knowledge backend is present, and `VMD` uses a local in-memory event buffer that participates in snapshot/restore. This keeps default kernel smoke tests bounded while preserving the mount points for real CHAL hardware backends.

Every spawned NPC also mounts `VCD` and `VWD` as explicit Python-side CHAL partitions:

| Device | Partition | Snapshot role |
|-------|-----------|---------------|
| `VCD` | Volatile cache / hot context | Captures L1/L2-style turn or session cache entries independently from durable memory. |
| `VWD` | Writeback staging | Captures validated trace or memory commits waiting for episodic/crystallized backend admission. |

`SnapshotManager` seals every snapshot payload with a SHA-256 fingerprint over the unsigned payload. Restore now recomputes that fingerprint before spawning devices and rejects tampered blobs with a `ValueError`, giving AIVM snapshotting an explicit integrity gate instead of treating the footer as advisory metadata.

Snapshots also carry a per-device fingerprint manifest. Restore replays each mounted device blob and verifies that the restored `VPD`, `VMD`, `VQD`, `VCD`, `VWD`, generation, reasoning, narrative, and model-selection devices match the captured fingerprints before the NPC is admitted back into the kernel. This guards against validly resealed outer snapshots that contain forged device-state blobs.

`VQD` snapshotting now captures the mounted knowledge scope, retrieval policy, lookup count, last lookup trace, and last backend error. This makes the Virtual Knowledge Device replayable across AIVM snapshot/restore even when the restored kernel has no Knowledge Cloud backend mounted, and it lets the per-device fingerprint manifest reject forged knowledge-scope payloads before NPC admission.

Snapshots now include `replay_trace` metadata for the canonical AIVM tick audit stream. The record uses `aivm.snapshot_replay.v1` and stores the ordered tick steps, compact audit event details, canonical-sequence status, emit hashes, scheduler class, and a SHA-256 `events_hash`. It does not store raw prompt text or raw generated response text. Restore verifies `events_hash` before admitting the snapshot and exposes the sealed record on `NPC.snapshot_replay_trace`, while the restored live audit stream remains limited to the new spawn/restore events.

## VPD Pybind Inspection Surface

The native `_synthesus_kernel.EmulEngine.dump_vpd()` pybind surface exposes the Virtual Parameter Device as an inspectable parameter-hardware partition. The JSON-ready dump includes:

| Field | Purpose |
|-------|---------|
| `parameter_count` | Number of mapped parameter records |
| `data_window_offset` | MMIO data-window offset for selected parameter bytes |
| `selected_parameter.available` | Whether the selected parameter slot is valid |
| `selected_parameter.index` | Selected parameter slot |
| `selected_parameter.key` | Mapped Knowledge/Parameter Cloud key |
| `selected_parameter.version` | Parameter record version |
| `selected_parameter.size` | Full selected-parameter byte length |
| `selected_parameter.data_offset` / `data_length` | Active byte-window controls |
| `selected_parameter.bytes` | Current selected byte window as integer bytes |

This surface is a smoke-testable bridge between Synthesus 5 parameter-disk mounts and the C++ VMM device layer. It is inspection metadata only; it does not claim hardware acceleration unless the native module is built and the pybind smoke passes.

## Amplification Loop

```
Query → Reason → Evaluate → Improve → Reason → ...
              ▲                    │
              └────────────────────┘
                   Feedback Loop
```

The amplification loop enables self-improvement:
1. Generate initial response
2. Self-evaluate quality
3. Identify weaknesses
4. Regenerate with corrections
5. Repeat until satisfied
