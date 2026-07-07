import webview
import time
import requests
import sys

print("[*] Contacting AIVM Root Daemon...")
# Wait for daemon
for i in range(5):
    try:
        requests.get("http://127.0.0.1:8080/")
        break
    except:
        time.sleep(1)

print("[*] Launching Synthesus Desktop (User Mode)...")
webview.create_window('Synthesus Planetary OS', 'http://127.0.0.1:8080', frameless=True, fullscreen=True, text_select=True)
webview.start()
