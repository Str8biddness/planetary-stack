#!/bin/bash
echo "[*] Booting Synthesus Planetary OS in VM..."
qemu-system-x86_64 -cdrom /home/dakin/aivm-planetary-os/synthesus-planetary-desktop.iso -m 2048 -enable-kvm -vga std
