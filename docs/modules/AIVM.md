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
