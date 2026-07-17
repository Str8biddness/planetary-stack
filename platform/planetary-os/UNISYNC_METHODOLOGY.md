# AIVM UNISYNC ARCHITECTURE: BARE-METAL HARDWARE ABSTRACTION

> **Historical concept — superseded for implementation.** This document is
> retained as imported design history. Its proposals to bypass `sudo`, trick a
> host kernel, inject trusted input, expose raw buses, or treat remote memory as
> implicitly trusted are prohibited product requirements. The canonical v1
> boundary is `contracts/chal_vsource/v1`: same-account enrollment, explicit
> signed capability, short-lived fenced lease, content-addressed I/O, mTLS
> transport, OS-enforced isolation, and audit telemetry. Unisync is a data
> transport behind that boundary and grants no authority.

## 1. The Core Philosophy: Rejection of Legacy Paradigms
Future agents and developers must understand a fundamental architectural shift in the AIVM project: **We explicitly reject the legacy "Master/Slave" or "Worker Node" networking paradigm.** 

Legacy systems attempt to network computers together using software bridging (SSH, TCP/IP commands, Level 7 Application layer). This fails because the Host OS kernels always treat foreign network instructions as untrusted, sandboxing them and dropping graphical/sudo privileges.

**The Solution:** The AIVM operates on the **Unisync** paradigm. We do not network computers; we dissolve their physical boundaries to create a Single System Image (SSI). The machines must work together as one physical consciousness, sharing a single heartbeat and nervous system.

## 2. The Abstraction Methodology (Level 2 Bus Bridging)
To trick the Host Kernel into unconditionally trusting the AIVM network, we must drop from Level 7 (Software) to Level 2 (Hardware Bus). We abstract the physical silicon hardware over the sharded network. 

### A. Peripheral Input (The USB/IP Bridge)
* **The Problem:** Software KVMs (like `pynput` or UDP KVMs) synthesize virtual keystrokes (`uinput`). Wayland, GTK, and `sudo` drop these keystrokes for security reasons because they lack a physical hardware interrupt.
* **The Unisync Solution:** The Master creates a Phantom USB Keyboard using `/dev/uhid`. The AIVM transmits the raw electrical USB Request Blocks (URBs) over the network/acoustic shard. The receiving machine uses `vhci-hcd` (Virtual Host Controller) to inject the packets. The slave kernel hallucinates a physical hardware plug-in, unconditionally granting `sudo` and Ring-0 GUI access.

### B. GPU Pooling (PCIe-over-IP / NTB)
To share graphical and mathematical processing for the LLM Quadbrain, the AIVM abstracts the PCIe lanes. Using Non-Transparent Bridging (NTB), a slave machine's GPU is mapped over the network so the Master Kernel enumerates it as physically slotted into its own motherboard (`cuda:0`).

### C. Unified Memory (RDMA)
Remote Direct Memory Access (RDMA) allows the AIVM Master CPU to read/write directly to the physical silicon RAM sticks of a bridged machine, completely bypassing the slave's operating system and TCP stack.

### D. Process Space (CPU Migration)
By virtualizing the Linux `PID` (Process ID) space across the fabric, the AIVM can migrate active threads between physical CPUs on different machines without the thread pausing or realizing it was moved.

## Conclusion for Future Agents
When developing for the AIVM Planetary OS, **DO NOT** attempt to write software-level network bridges, APIs, or SSH automation for clustering. You must bridge at the hardware bus level. Trick the kernel into thinking the network *is* the motherboard.
