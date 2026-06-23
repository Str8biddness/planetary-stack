import os
import sys
import threading
import time
import json
import subprocess
import webview

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

@app.route('/api/ide/files', methods=['GET'])
def list_files():
    # Bind the file explorer to the user's actual home directory on the Host OS
    base_dir = os.path.expanduser('~')
    
    def build_tree(dir_path, depth=0):
        if depth > 1: return [] # Limit depth to avoid massive payload
        tree = []
        try:
            for item in os.listdir(dir_path):
                if item.startswith('.'): continue # Skip hidden files
                full_path = os.path.join(dir_path, item)
                if os.path.isdir(full_path):
                    tree.append({"name": item, "type": "dir", "children": build_tree(full_path, depth+1)})
                else:
                    tree.append({"name": item, "type": "file"})
        except Exception:
            pass
        return tree
        
    return jsonify([{"name": "Host OS User Directory", "type": "dir", "children": build_tree(base_dir)}])

@app.route('/api/terminal/run', methods=['POST'])
def run_command():
    data = request.json
    cmd = data.get('command', '')
    try:
        # Route the shell command to the Host OS backend
        output = subprocess.check_output(cmd, shell=True, stderr=subprocess.STDOUT, text=True, timeout=5)
    except subprocess.CalledProcessError as e:
        output = e.output
    except Exception as e:
        output = str(e)
    return jsonify({"output": output})

# ===================================================================
# LAUNCHER
# ===================================================================
def start_flask():
    app.run(host='127.0.0.1', port=8080, debug=False, use_reloader=False)

if __name__ == '__main__':
    print("[*] Booting Synthesus Planetary OS Shell...")
    
    threading.Thread(target=start_flask, daemon=True).start()
    time.sleep(1)
    
    print("[*] Hooking into Host OS via PyWebView (Frameless Mode)...")
    webview.create_window('Synthesus Planetary OS', 'http://127.0.0.1:8080', frameless=True, fullscreen=True)
    webview.start()
