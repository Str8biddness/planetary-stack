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

## The boundary is the home, not the machine

An earlier draft of this document treated a smart TV as though it were a third
party. That was wrong. The owner owns the TV. Work sent from the PC to the TV
over the LAN does not leave the house, and "nothing leaves your home" is the
guarantee users actually want and the one this product should make.

The correction that survives is narrower and still matters:

**Ownership is not control.** The risk is not that the owner cannot be trusted
with their own data — it is that vendor firmware does things the owner did not
ask for. Smart TVs are documented to run automatic content recognition, ship
telemetry to the manufacturer, and carry unpatched vulnerabilities for years.
Data placed on such a device can leave the house through a path the owner never
authorised and cannot see.

So the question is not "do we trust the user" — obviously yes, it is their
house and their hardware. It is: *does the device's own firmware honour the
boundary the owner set?* For a phone or tablet the answer is largely yes. For a
smart TV it is not currently knowable.

### What actually mitigates this

* **Send work the firmware cannot use.** Operations on already-embedded
  vectors, opaque re-ranking, image tiles that cannot be reassembled. This is
  not a hedge against the owner; it is a hedge against the vendor's software.
* **Network isolation.** Putting untrusted devices on their own VLAN with
  egress rules is the real control. Note that this lives at the router, not in
  the PC — a firewall on the coordinator can govern what Synthesus *sends*, but
  cannot stop a TV's own firmware from talking to the manufacturer. Any kernel
  firewall module should be scoped to what it can honestly enforce.
* **Informed consent per device.** "This device's manufacturer software may see
  what it processes" stated at the moment of granting, not buried in terms.

### Sequencing, which sidesteps most of this

**Phones and tablets first. TVs later.** Phones give the same unlock — a GPU
reachable only through a browser, on a device the mesh cannot otherwise use —
without the firmware problem: the owner controls the OS, apps are sandboxed,
there is no content recognition running, and most homes have several. TVs are
the harder case and the smaller win; they can follow once either network
isolation or vendor behaviour makes them safe.

The strategic bet — that TV manufacturers adapt once this is normal — is a
reasonable bet. It cannot be a security control today, because a guarantee that
depends on future vendor cooperation is not a guarantee yet. Build for phones,
keep the TV path behind blind work and consent, and relax it when reality does.

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
processing — with nothing leaving the home network. Devices previously excluded from
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
