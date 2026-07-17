# Planetary Stack architecture

## Product boundary

Planetary OS is the product experience and node operating environment.
Synthesus is the local cognitive controller. CHAL defines devices and
capabilities. vSource owns discovery, inventory, leases, and placement.
Unisync moves workload and artifact data through topology-appropriate
backends. AIVM isolates execution. Knowledge Cloud supplies
manifest-verified knowledge and model artifacts.

The term "single system image" means one coherent resource and control view.
It does not mean that arbitrary Internet-connected machines share one kernel,
one memory-consistency domain, or one trusted security boundary.

## Control and data paths

```text
User
  |
  v
Planetary Desktop ── localhost WebSocket/HTTP ── synthesusd
                                                   |
                                                   v
                                           Cognitive Hypervisor
                                                   |
                                                   v
                                                  CHAL
                                                   |
                      +----------------------------+------------------+
                      |                                               |
                      v                                               v
           vSource scheduler/registry                    Knowledge Cloud client
                      |                                               |
                      v                                               v
            placement + signed lease                    manifest + artifact hash
                      |
                      v
               Unisync transport
                      |
                      v
             node agent → AIVM sandbox
```

## Trust zones

1. Desktop UI: unprivileged presentation client.
2. Local controller: account policy, orchestration, and user intent.
3. Personal/private cell: authenticated machines under one owner or
   organization.
4. Public fabric: untrusted providers and tenants with zero implicit trust.
5. Artifact plane: signed manifests, content hashes, immutable releases, and
   provenance.

Crossing a zone requires explicit identity, authorization, encryption,
resource limits, and audit records.

## Versioned CHAL/vSource contract

The canonical distributed control-plane contract is
[`contracts/chal_vsource/v1`](../contracts/chal_vsource/v1/README.md). Its
strict Pydantic models and nine committed Draft 2020-12 JSON Schemas freeze:

- CHAL request, response, structured error, capability, and telemetry frames;
- vSource inventory, placement, fenced lease, and lifecycle frames.

Version 1 schedules only inside a same-account private cell. Workload and data
fields cross the boundary as signed descriptors with RFC 8785 request and
inventory digests or as content-addressed artifact references. Bounded TTLs,
I-JSON-safe numbers, canonical arrays, fenced leases, and metadata enums are
wire invariants. Allocation admission applies componentwise capability,
request, inventory, transport, and GPU-ID joins; results and lifecycle events
bind the exact active lease digest and fencing token. Raw bytecode, `marshal`,
pickle, `eval`, arbitrary shell
commands, raw prompt/output telemetry, implicit delegation, and public-fabric
placement are not part of the protocol. Unisync will implement transport
beneath this boundary; it cannot grant authority or weaken validation.

The schemas define messages, not a claim of runtime completion. Signature
verification, enrollment/revocation, the inventory registry, allocator,
lease-state persistence, node agent, transport, and AIVM sandbox remain gated
implementation work.

## Local controller boundary

The desktop now reaches private services through `synthesusd`, bound only to
loopback. Runtime HTTP requires the per-install API key already used on the
server-to-server hop. Browser terminal HTTP/WebSocket traffic uses a separate
random capability generated for each desktop launch and an allowlisted local
UI origin. The desktop shell releases that capability only to a valid logged-in
user session.

The PTY backend has no TCP listener. `synthesusd` reaches it through a Unix
socket inside a mode-0700 user directory, with the socket node restricted to
mode 0600. The browser never receives the runtime API key or human-attestation
secret.

## Workload classes

### Suitable across the public Internet

- Embeddings and indexing.
- Evaluation and simulation batches.
- Rendering and media transforms.
- Independent inference requests.
- Checkpointable fine-tuning shards.
- Replicated model-serving endpoints.

### Restricted to qualified cells

- Tensor- or pipeline-parallel training.
- Workloads requiring tightly synchronized GPU collectives.
- Shared-memory assumptions.
- Latency-sensitive databases.

## First release

The first commercial release is a private personal mesh. It pools machines
owned by one subscriber and deliberately excludes public third-party
workloads. That release proves the interface, scheduler, workload protocol,
failure recovery, resource controls, and customer value before adding a
marketplace and adversarial nodes.
