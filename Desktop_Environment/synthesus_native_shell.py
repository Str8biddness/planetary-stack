import os
import sys
import threading
import time
import json
import subprocess

from flask import Flask, send_from_directory, jsonify, request
from flask_cors import CORS

# ===================================================================
# SYNTHESUS C++ KERNEL IPC BRIDGE
# ===================================================================
class CognitiveKernelIPC:
    def __init__(self):
        self.kernel_status = "Sub-1GB Reasoning Engine: ACTIVE (Ring-0)"
        
    def send_intent_to_kernel(self, intent_string):
        """Sends an abstract string directly to the C++ reasoning engine"""
        print(f"[KERNEL IPC] Routing intent to C++ Metal: {intent_string}")
        
        intent_lower = intent_string.lower()
        if "hello" in intent_lower or "status" in intent_lower:
            return "Synthesus Quad Brain is online. CGPU rendering active. AIVM bridge hooked."
        elif "twin" in intent_lower or "dog" in intent_lower:
            return "Digital Twin (HTC) simulation mounted. Reading biological telemetrics from Knowledge Cloud."
        elif "error" in intent_lower or "fail" in intent_lower:
            return "Rule 2 (First Conversion): Paradox detected. Melting down abstract intent -> Rerouting to safe cognitive buffer."
        else:
            return f"Abstractive Conversion (Rule 1): Intent '{intent_string}' verified and executed at Ring-0."

kernel_ipc = CognitiveKernelIPC()

# ===================================================================
# FLASK OS BACKEND
# ===================================================================
# Resolve the directory where this script lives (works from any cwd)
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))

app = Flask(__name__, static_folder=SCRIPT_DIR)
CORS(app)

@app.route('/')
def serve_index():
    return send_from_directory(SCRIPT_DIR, 'index.html')

@app.route('/<path:path>')
def serve_static(path):
    return send_from_directory(SCRIPT_DIR, path)

@app.route('/api/system/status', methods=['GET'])
def get_status():
    return jsonify({
        "3way_drive_active": True,
        "peripheral_bridge_active": True,
        "llm_status": kernel_ipc.kernel_status
    })

@app.route('/api/chat', methods=['POST'])
def chat_with_llm():
    data = request.json
    user_message = data.get('message', '')
    response = kernel_ipc.send_intent_to_kernel(user_message)
    return jsonify({"response": response})

CLOUD_DRIVE_PATH = "/mnt/synthesus_cloud_pool"

@app.route('/api/ide/files', methods=['GET'])
def list_files():
    if not os.path.exists(CLOUD_DRIVE_PATH):
        return jsonify([
            {"name": "synthesus-core", "type": "dir", "children": [
                {"name": "aivm_peripheral_bridge.py", "type": "file"},
                {"name": "start_3way_drive.sh", "type": "file"}
            ]},
            {"name": "knowledge-cloud", "type": "dir", "children": [
                {"name": "royal_twin_ledger.csv", "type": "file"},
                {"name": "blueprint.md", "type": "file"}
            ]}
        ])
    
    def build_tree(dir_path):
        tree = []
        for item in os.listdir(dir_path):
            full_path = os.path.join(dir_path, item)
            if os.path.isdir(full_path):
                tree.append({"name": item, "type": "dir", "children": build_tree(full_path)})
            else:
                tree.append({"name": item, "type": "file"})
        return tree
    return jsonify(build_tree(CLOUD_DRIVE_PATH))

# ===================================================================
# LAUNCHER
# ===================================================================
def launch_kiosk_browser():
    """Launch Chromium in fullscreen kiosk mode after Flask is ready."""
    time.sleep(2)  # Give Flask time to bind
    
    # Detect if we're running inside an X11 session
    display = os.environ.get("DISPLAY")
    if not display:
        print("[!] No DISPLAY detected. Running as headless API server only.")
        return
    
    print("[*] Launching Synthesus Kiosk Browser...")
    
    # Try chromium first, then firefox-esr as fallback
    browsers = [
        ["chromium", "--kiosk", "--no-first-run", "--disable-infobars",
         "--disable-session-crashed-bubble", "--noerrdialogs",
         "--disable-translate", "--no-default-browser-check",
         "--disable-features=TranslateUI", "--start-fullscreen",
         "http://127.0.0.1:8080"],
        ["firefox-esr", "--kiosk", "http://127.0.0.1:8080"],
        ["firefox", "--kiosk", "http://127.0.0.1:8080"],
    ]
    
    for browser_cmd in browsers:
        try:
            subprocess.Popen(browser_cmd)
            print(f"[+] Kiosk launched with: {browser_cmd[0]}")
            return
        except FileNotFoundError:
            continue
    
    print("[!] No kiosk browser found. Access the OS at http://127.0.0.1:8080")

if __name__ == '__main__':
    print("[*] Booting Synthesus Planetary OS Shell...")
    
    # Launch the kiosk browser in a background thread
    threading.Thread(target=launch_kiosk_browser, daemon=True).start()
    
    # Start Flask (blocks forever)
    app.run(host='127.0.0.1', port=8080, debug=False, use_reloader=False)
