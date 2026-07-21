# Browser GPU workers — spec — 2026-07-21

**Status: SPEC. Not built. Nothing here has been measured.**

## The idea

Devices that cannot be mesh peers can still contribute GPU.

A phone, tablet or TV cannot run the node agent: no rootless Podman on
unrooted Android or locked TV firmware, which is why the permission model
classes them `source` rather than `peer`. But nearly all of them run a browser
with WebGL2, and increasingly WebGPU.

WebGPU is the only GPU API that reaches heterogeneous consumer hardware
uniformly. CUDA, Metal, Vulkan and Adreno are four different worlds; a browser
context is one. This is not a trick to extract GPU from the driver — it is the
only available door, and it is a legitimate one.

## What vSource already provides

No contract change is required. The following already exist:

    WorkloadKind.RENDERING, EMBEDDING, INDEXING, SIMULATION
    ResourceVector.gpu_count / gpu_memory_bytes
    inventory.resources.gpus: dict[Identifier, GpuDescriptor]
    lease.gpu_ids — validated against the inventory's allocatable GPU memory

A browser worker advertises an inventory and receives leases like any other
node. The novelty is the executor, not the model.

## The unsolved problem — read before designing anything else

**A device that computes on data sees that data.**

Sending text to a phone to embed means the phone sees the text. The permission
model governs *whether* a device may run work; it says nothing about what that
device learns by running it. For a product whose claim is that your data stays
on machines you control, handing documents to a smart TV — a device class
already identified here as among the most-compromised on a home network — is a
regression, not a feature.

Three honest options, and the choice determines everything downstream:

1. **Peers only.** GPU work goes only to devices the owner has explicitly
   trusted as peers. Simple, safe, and gives up the phones and TVs — which were
   the whole motivation.
2. **Blind work only.** Dispatch only workloads meaningless without context:
   operations on already-embedded vectors, re-ranking by opaque score, image
   kernels on tiles the worker cannot reassemble. Real but narrow, and the
   boundary is easy to get wrong.
3. **Informed consent per device.** The owner is told plainly — "your TV will
   see the documents it indexes" — and chooses. Honest, but only acceptable if
   the UI states it at the moment of granting, not buried in terms.

This spec assumes **(1) plus (2)**: `peer` devices may take any permitted
workload; `source` devices may take blind work only. Option 3 is a product
decision, not an engineering one.

## What a browser worker reports

    {
      "schema": "planetary.synthesus.browser_worker_inventory.v1",
      "device_id": "device:phone:pixel",
      "adapter": {
        "api": "webgpu" | "webgl2",
        "vendor": "<navigator adapter info, may be empty>",
        "architecture": "<may be empty>"
      },
      "limits": {
        "max_buffer_bytes": <int>,          // from adapter.limits
        "max_workgroup_invocations": <int>,
        "max_storage_buffer_bytes": <int>
      },
      "declared_gpu_memory_bytes": <int|null>,
      "measured": false
    }

Notes that matter:

* Browsers deliberately do **not** expose true VRAM. `declared_gpu_memory_bytes`
  is derived from adapter limits and is an **upper bound the browser permits**,
  not memory the device has. It is reported with `measured: false` and must
  never be presented as a measured figure.
* An inventory whose limits cannot be read reports `null`, never a guess.
* Battery: a worker on battery below a threshold declines work rather than
  draining the owner's phone. Thermal throttling is expected and normal; a
  worker that is throttling reports it rather than silently returning slowly.

## Workload rules

| Shape | Verdict |
|---|---|
| Batch embedding, indexing a corpus | good — coarse, parallel |
| Re-ranking / scoring many candidates | good |
| Independent image ops per tile | good |
| Many small independent inferences | good |
| Speculative decoding (draft on phone, verify on PC) | plausible, unmeasured |
| **Model-parallel single forward pass** | **no** |

The last one is the trap. Splitting one forward pass needs per-layer tensor
exchange; on a home LAN at ~0.3–1 ms RTT that loses decisively to running a
smaller model locally. Coarse-grained independent work wins; fine-grained
sharding loses. Design for the former only.

VRAM is the binding constraint throughout. No scheduling changes what fits.

## The line this must not cross

A shell that disguises the nature of a workload to obtain GPU from a device is,
on hardware whose owner did not consent, exactly cryptojacking. What separates
this from that is not the technology — it is identical — but consent:

* default-deny per device, already enforced by `DevicePolicyStore`;
* the owner grants GPU work explicitly, per device;
* the UI shows what is running, on which device, and stops it in one action;
* a worker on battery or thermally throttled declines rather than persists.

These are not nice-to-haves. They are what make the feature legitimate, and
they must be built with the feature rather than after it.

## What this does and does not unlock

**Does:** idle silicon across a home becomes addressable as one pool for
parallel work — overnight indexing, batch embedding, corpus re-ranking, image
processing — with nothing leaving the house. Devices previously excluded from
the mesh contribute for the first time.

**Does not:** pool VRAM (a 70B model does not become runnable), speed up a
single request via sharding, or make a small model equal a frontier one. The
aggregate FLOPS of a home is real but modest against one good GPU.

The honest headline is not "your home is a datacentre". It is: **your home's
idle silicon becomes one addressable pool for parallel work, privately.**

## Status

- Not built. No worker, no executor, no measurement.
- No benchmark exists showing a browser worker beats doing the work locally.
  That measurement should come before the feature, not after.
- No FINISH_CHECKLIST box is checked by this document.
