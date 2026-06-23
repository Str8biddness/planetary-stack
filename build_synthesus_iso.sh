#!/bin/bash
# ===================================================================
# SYNTHESUS PLANETARY OS - ISO BUILDER (v3.0)
# ===================================================================
# Uses Chromium Kiosk Mode (industry standard) instead of pywebview.
# This is the same architecture used by every ATM, digital sign,
# and point-of-sale terminal on Earth.

set -e

if [ "$EUID" -ne 0 ]; then
  echo "[-] Please run as root (sudo ./build_synthesus_iso.sh)"
  exit 1
fi

echo "[*] Installing ISO build dependencies..."
apt-get update
apt-get install -y debootstrap squashfs-tools xorriso grub-pc-bin grub-efi-amd64-bin mtools

BUILD_DIR="/tmp/synthesus_iso_build"
CHROOT_DIR="$BUILD_DIR/chroot"
IMAGE_DIR="$BUILD_DIR/image"

echo "[*] Cleaning old builds..."
rm -rf $BUILD_DIR
mkdir -p $CHROOT_DIR
mkdir -p $IMAGE_DIR/live
mkdir -p $IMAGE_DIR/boot/grub

echo "[*] Bootstrapping Debian Minimal Core..."
debootstrap --arch=amd64 stable $CHROOT_DIR http://deb.debian.org/debian/

echo "[*] Configuring the Chroot environment..."
mount --bind /dev $CHROOT_DIR/dev
mount -t proc none $CHROOT_DIR/proc
mount -t sysfs none $CHROOT_DIR/sys

cat << 'CHROOT_SCRIPT' > $CHROOT_DIR/opt/setup.sh
#!/bin/bash
set -e
export DEBIAN_FRONTEND=noninteractive

# Enable non-free firmware repos
cat > /etc/apt/sources.list << 'APT_EOF'
deb http://deb.debian.org/debian stable main contrib non-free non-free-firmware
deb http://deb.debian.org/debian stable-updates main contrib non-free non-free-firmware
APT_EOF

apt-get update

# =======================================================
# CORE PACKAGES
# =======================================================
# Kernel + Live boot
apt-get install -y --no-install-recommends linux-image-amd64 live-boot initramfs-tools

# System
apt-get install -y --no-install-recommends systemd systemd-sysv dbus dbus-x11 sudo

# X11 + Window Manager (Openbox is invisible scaffolding)
apt-get install -y --no-install-recommends xserver-xorg xserver-xorg-video-all xserver-xorg-input-all xinit openbox

# Chromium Browser (The Kiosk Renderer)
apt-get install -y --no-install-recommends chromium

# Hardware Firmware (WiFi, GPU, SD Cards)
apt-get install -y --no-install-recommends firmware-linux firmware-realtek firmware-iwlwifi firmware-misc-nonfree

# Python (Flask Backend Only — no GTK/WebKit bindings needed)
apt-get install -y --no-install-recommends python3 python3-pip

# Install Flask globally
python3 -m pip install flask flask-cors --break-system-packages

# =======================================================
# FORCE SD CARD + USB DRIVERS INTO INITRAMFS
# =======================================================
cat >> /etc/initramfs-tools/modules << 'MOD_EOF'
mmc_core
mmc_block
sdhci
sdhci_pci
usb_storage
uas
MOD_EOF
update-initramfs -u

# =======================================================
# CREATE AUTO-LOGIN USER
# =======================================================
useradd -m -s /bin/bash synthesus
echo "synthesus ALL=(ALL) NOPASSWD: ALL" > /etc/sudoers.d/synthesus
chmod 0440 /etc/sudoers.d/synthesus

# =======================================================
# KIOSK BOOT SEQUENCE
# =======================================================

# Step 1: TTY1 auto-login as 'synthesus'
mkdir -p /etc/systemd/system/getty@tty1.service.d
cat > /etc/systemd/system/getty@tty1.service.d/override.conf << 'GETTY_EOF'
[Service]
ExecStart=
ExecStart=-/sbin/agetty --autologin synthesus --noclear %I $TERM
GETTY_EOF

# Step 2: Auto-start X11 on login
cat > /home/synthesus/.bash_profile << 'PROFILE_EOF'
if [[ -z $DISPLAY ]] && [[ $(tty) = /dev/tty1 ]]; then
    exec startx -- -nocursor 2>/dev/null
fi
PROFILE_EOF

# Step 3: X11 launches Openbox
cat > /home/synthesus/.xinitrc << 'XINIT_EOF'
exec openbox-session
XINIT_EOF

# Step 4: Openbox launches Flask + Chromium Kiosk
mkdir -p /home/synthesus/.config/openbox
cat > /home/synthesus/.config/openbox/autostart << 'AUTO_EOF'
# Disable screensaver / power management
xset s off &
xset -dpms &
xset s noblank &

# Start the Synthesus OS Backend
python3 /opt/synthesus/synthesus_native_shell.py &

# Wait for Flask to bind
sleep 3

# Launch Chromium in fullscreen kiosk mode
chromium --kiosk --no-first-run --disable-infobars \
    --disable-session-crashed-bubble --noerrdialogs \
    --disable-translate --no-default-browser-check \
    --disable-features=TranslateUI \
    --user-data-dir=/home/synthesus/.chromium-kiosk \
    http://127.0.0.1:8080 &
AUTO_EOF

# Fix all permissions
chown -R synthesus:synthesus /home/synthesus/

# =======================================================
# CLEANUP
# =======================================================
apt-get clean
rm -rf /var/lib/apt/lists/* /tmp/* /var/tmp/*

CHROOT_SCRIPT

chmod +x $CHROOT_DIR/opt/setup.sh

echo "[*] Injecting the Synthesus Desktop Environment..."
mkdir -p $CHROOT_DIR/opt/synthesus
cp -r /home/dakin/aivm-planetary-os/Desktop_Environment/* $CHROOT_DIR/opt/synthesus/

echo "[*] Running setup inside chroot (this takes a few minutes)..."
chroot $CHROOT_DIR /bin/bash /opt/setup.sh
rm $CHROOT_DIR/opt/setup.sh

echo "[*] Unmounting virtual filesystems..."
umount $CHROOT_DIR/sys 2>/dev/null || true
umount $CHROOT_DIR/proc 2>/dev/null || true
umount $CHROOT_DIR/dev 2>/dev/null || true

echo "[*] Copying Kernel to Boot Image..."
cp $CHROOT_DIR/boot/vmlinuz-* $IMAGE_DIR/live/vmlinuz
cp $CHROOT_DIR/boot/initrd.img-* $IMAGE_DIR/live/initrd.img

echo "[*] Compressing filesystem into SquashFS..."
mksquashfs $CHROOT_DIR $IMAGE_DIR/live/filesystem.squashfs -comp xz -e boot

echo "[*] Generating GRUB config..."
cat > $IMAGE_DIR/boot/grub/grub.cfg << 'GRUB_EOF'
set default=0
set timeout=3

menuentry "Synthesus Planetary OS" {
    linux /live/vmlinuz boot=live quiet splash rootdelay=5
    initrd /live/initrd.img
}

menuentry "Synthesus Planetary OS (Debug)" {
    linux /live/vmlinuz boot=live rootdelay=5
    initrd /live/initrd.img
}
GRUB_EOF

echo "[*] Building final ISO..."
grub-mkrescue -o /home/dakin/aivm-planetary-os/synthesus-planetary-desktop.iso $IMAGE_DIR

echo ""
echo "========================================"
echo "[+] SUCCESS! ISO built successfully."
echo "[+] File: /home/dakin/aivm-planetary-os/synthesus-planetary-desktop.iso"
echo "[+] Size: $(du -h /home/dakin/aivm-planetary-os/synthesus-planetary-desktop.iso | cut -f1)"
echo "========================================"
echo ""
echo "Flash to USB with:"
echo "  sudo bash /home/dakin/aivm-planetary-os/flash_usb.sh"
