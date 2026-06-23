#!/bin/bash
# ==============================================================================
# AIVM PLANETARY OS - BARE-METAL BOOT AUTOMATION
# This script transforms the host machine into the AIVM Planetary OS by 
# configuring GRUB and Systemd to boot directly into the Synthesus Desktop Env.
# ==============================================================================

echo "[*] Initializing AIVM Planetary OS Boot Automation..."

# 1. Setup the Synthesus OS Shell Bridge Service
echo "[*] Creating Systemd Service for OS Shell Bridge..."
cat << 'EOF' | sudo tee /etc/systemd/system/synthesus-bridge.service
[Unit]
Description=Synthesus OS Shell Bridge API
After=network.target

[Service]
Type=simple
User=dakin
WorkingDirectory=/home/dakin/Synthesus_Desktop_Env
ExecStart=/usr/bin/python3 os_shell_bridge.py
Restart=always

[Install]
WantedBy=multi-user.target
EOF

# 2. Setup the X11 Kiosk Service (The Desktop Environment)
echo "[*] Creating X11 Kiosk Bootloader for Synthesus Desktop..."
cat << 'EOF' | sudo tee /etc/systemd/system/synthesus-desktop.service
[Unit]
Description=Synthesus Planetary OS Desktop Environment
After=systemd-user-sessions.service network.target sound.target synthesus-bridge.service
Conflicts=getty@tty1.service

[Service]
User=dakin
Type=simple
Environment=DISPLAY=:0
# Start a minimal X server and launch Chromium in full-screen kiosk mode
ExecStart=/usr/bin/xinit /usr/bin/chromium-browser --kiosk --incognito --no-errdialogs --disable-infobars --window-position=0,0 --window-size=1920,1080 http://localhost:8080 -- :0 -s 0 dpms -nocursor
Restart=always
RestartSec=3

[Install]
WantedBy=graphical.target
EOF

# 3. Reload systemd and enable the services to start at boot
sudo systemctl daemon-reload
sudo systemctl enable synthesus-bridge.service
sudo systemctl enable synthesus-desktop.service

# 4. Modify GRUB for a seamless, silent "Planetary OS" boot experience
echo "[*] Injecting AIVM Boot Parameters into GRUB..."
sudo sed -i 's/GRUB_CMDLINE_LINUX_DEFAULT="quiet splash"/GRUB_CMDLINE_LINUX_DEFAULT="quiet splash console=tty3 loglevel=3 rd.systemd.show_status=auto rd.udev.log_level=3 vt.global_cursor_default=0"/g' /etc/default/grub
sudo sed -i 's/#GRUB_HIDDEN_TIMEOUT=0/GRUB_HIDDEN_TIMEOUT=0/g' /etc/default/grub

echo "[*] Updating GRUB..."
sudo update-grub

echo "[======================================================================]"
echo "[ SUCCESS ] AIVM Planetary OS boot sequence automated."
echo "On the next reboot, GRUB will seamlessly transition directly into the"
echo "Synthesus Desktop Environment, fully bypassing the standard Linux GUI."
echo "[======================================================================]"
