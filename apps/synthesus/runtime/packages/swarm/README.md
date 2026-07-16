# Persona-Clone Expert Swarm

**One resident base model + N cheap deltas.** Never N model copies on a shared GPU.

## Call path

```python
from swarm import (
    Expert,
    ExpertRegistry,
    SwarmRequest,
    SwarmScheduler,
    SwarmRuntime,
    SharedOllamaClient,
)

reg = ExpertRegistry()
reg.register(Expert(
    expert_id="historian",
    persona="Historian",
    system_prompt="You are a careful historian. Prefer dates and causes.",
    namespace="ns_history",
    domain="history",
    adapter_ref=None,  # optional path to adapter DATA (validated, not hot-swapped in v1)
))

client = SharedOllamaClient(base_model="llama3.2:3b")  # single base
runtime = SwarmRuntime(SwarmScheduler(reg, model_client=client))

answer = runtime.answer(SwarmRequest(
    query="What matters most about the Concert of Europe?",
    expert_ids=["historian"],
    budget={"max_tokens": 128},  # FAST_MODE default-on shrinks this further
))
print(answer.response)
print(answer.contributing_experts, answer.degraded_experts)
print(answer.sources)  # C-001 verification tiers when present
```

## v1 honesty

| Mechanism | Status |
|-----------|--------|
| `system_prompt` + `namespace` | **Applied** (behavioral delta) |
| LoRA / `adapter_ref` files | **Validated only** (`adapter_applied=False`, `adapter_status=validated_not_applied`) |
| Missing adapter / expert | **Degraded** (`text=""`, no fabricated persona) |
| Firecracker MicroVM | **BLOCKED** on local single-GPU (`FirecrackerLocalBlockedError`) |

## Modules

| File | Role |
|------|------|
| `registry.py` | Experts + contracts |
| `scheduler.py` | Fan-out through shared client |
| `model_client.py` | One Ollama base model |
| `arbiter.py` | Merge via `QuadBrainOrchestrator` |
| `adapters/` | Adapter DATA validation |
| `envelope_firecracker.py` | HOSTED-only envelope (local BLOCK) |
