# AIVM Planetary OS

**The AIVM Planetary OS** is the ultimate manifestation of the Synthesus 5 Bounded Synthetic Intelligence Runtime. It is a fully independent operating system where intelligence is not an application, but the hardware itself.

## Architecture

This repository contains the physical implementation of the Planetary OS:

### 1. Synthesus Kernel (`Synthesus_Kernel/`)
The bare-metal C++ kernel that replaces Linux. It runs the underlying hardware virtualization, implements a native 1024x768 graphical engine, handles hardware interrupts (like the PS/2 mouse), and acts as the lowest-level routing layer.

### 2. The Planetary Desktop Environment (`Desktop_Environment/`)
The **CGPU (Cognitive GPU) Narrative Simulation Layer**. This is the native, offline visual interface for the OS. It is built using Glassmorphism web technologies but is compiled into a borderless, full-screen native Python application (`synthesus_native_shell.py`) that bypasses traditional browser sandboxes.
- It features an **IDE File Explorer** natively hooked into the global 3-Way Abstraction Drive.
- It features a **Chat UI** hooked natively into the C++ Kernel IPC for Abstractive Conversion.
- It visualizes the **Digital Twin (HTC)** biological telemetrics natively on the dashboard.

### 3. The Installation Automation (`install_planetary_os_kiosk.sh`)
The automation script to turn any physical Linux machine into a silent bootloader. It annihilates the standard GUI and replaces it instantly with the Synthesus OS Shell via `systemd` and `grub`.

## Quick Start (VM / Bare Metal)

**To boot the C++ Kernel natively via QEMU:**
```bash
cd Synthesus_Kernel
make clean && make
qemu-system-i386 -cdrom synthesus.iso -m 2048 -enable-kvm
```

**To boot the Native Offline OS Shell (The Desktop Environment):**
```bash
cd Desktop_Environment
python3 synthesus_native_shell.py
```
*(This will forcefully bypass PEP-668 package protections to install the required UI frameworks natively into your OS environment).*
