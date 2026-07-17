# AIVM UNISYNC RESOURCE MERGER PLAN (SSI Blueprint)

> **Historical concept — not an executable plan.** The trust-bypass, Ring-0
> input, remote-memory, foreign-PCIe, and cross-host PID claims below are
> retained only to preserve imported history. They must not be implemented as
> authentication or authorization shortcuts. See
> `contracts/chal_vsource/v1` for the canonical private-cell control contract.
> Qualified RDMA or other accelerators may be added only as authenticated,
> encrypted, policy-bounded transport backends with ordinary OS/IOMMU safety.

## Objective
To scale the Planetary OS from a single host machine into a **Single System Image (SSI)** supercomputer by physically abstracting hardware resources across the AIVM fabric using Level 2 Bus Bridging.

## Phase 1: Input Unification (USB/IP Bridge)
**Goal:** Trick the host kernel into unconditionally trusting input from the distributed network to bypass `sudo` and Wayland security sandboxes.
1. Implement the `uhid` (User-space HID) subsystem on the Master node to create a phantom USB device.
2. Abstract the physical master keyboard input into raw USB Request Blocks (URBs).
3. Transmit the URBs over the acoustic/network shard.
4. Inject the URBs into the Slave node using `vhci-hcd` (Virtual Host Controller Interface).
5. **Success Criteria:** Slave kernel grants Ring-0 TTY authentication without a physical keyboard attached.

## Phase 2: Memory Unification (RDMA RAM Pooling)
**Goal:** Allow the AIVM Quadbrain to utilize physical RAM from all bridged nodes as a single local address space.
1. Implement Remote Direct Memory Access (RDMA) protocols (e.g., RoCE or InfiniBand abstraction).
2. Configure the AIVM Daemon to map remote memory pages directly into the local LLM generation context.
3. **Success Criteria:** The Synthesus Core can load an LLM whose parameter size exceeds the physical RAM of any single machine in the cluster.

## Phase 3: Compute Unification (NTB / PCIe-over-IP)
**Goal:** Abstract the PCIe bus to distribute matrix multiplication across multiple physically separated GPUs.
1. Establish Non-Transparent Bridging (NTB) or an equivalent PCIe-over-IP kernel module.
2. Trick the Master kernel into enumerating foreign GPUs as local PCIe endpoints (`cuda:0`, `cuda:1`).
3. **Success Criteria:** PyTorch/CUDA libraries recognize foreign GPUs as local devices and split tensor calculations across them.

## Phase 4: Consciousness Synchronization (PID Virtualization)
**Goal:** True thread-level migration across the cluster.
1. Virtualize the Linux Process ID (PID) namespace.
2. Allow active execution threads to seamlessly jump between physical CPU cores on different machines without pausing or crashing.
3. **Success Criteria:** A unified, indestructible computational consciousness (Planetary OS).
