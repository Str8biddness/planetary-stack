#!/bin/bash
echo "[*] Unmounting USB..."
umount /dev/sda1 2>/dev/null
umount /dev/sda2 2>/dev/null

echo "[*] Flashing Synthesus Planetary OS to /dev/sda..."
dd if=/home/dakin/aivm-planetary-os/synthesus-planetary-desktop.iso of=/dev/sda bs=4M status=progress
sync

echo "[+] Flash Complete! You may now remove the USB drive."
