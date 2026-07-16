import os
import subprocess
import threading
import time
import json
from flask import Flask, send_from_directory, jsonify, request
from flask_cors import CORS

app = Flask(__name__, static_folder='.')
CORS(app)

# OS State
os_state = {
    "3way_drive_active": False,
    "peripheral_bridge_active": False,
    "llm_status": "Idle",
    "twin_status": "Standby"
}

# Real-time mock or actual integration points for the Digital Twin
twin_data = {
    "pt": 12,
    "pcv": 45,
    "toxin": 0,
    "pain": 0
}

@app.route('/')
def serve_index():
    return send_from_directory('.', 'index.html')

@app.route('/<path:path>')
def serve_static(path):
    return send_from_directory('.', path)

@app.route('/api/system/status', methods=['GET'])
def get_status():
    return jsonify(os_state)

@app.route('/api/system/3way_drive', methods=['POST'])
def toggle_drive():
    action = request.json.get('action', 'start')
    if action == 'start':
        os_state['3way_drive_active'] = True
        # In reality, this invokes the start_3way_drive.sh we created
        # subprocess.Popen(["bash", "/home/dakin/synthesus_os/start_3way_drive.sh"])
        return jsonify({"status": "3-Way Drive Initiated. Abstracting latency..."})
    else:
        os_state['3way_drive_active'] = False
        return jsonify({"status": "3-Way Drive Disconnected."})

@app.route('/api/system/peripheral_bridge', methods=['POST'])
def toggle_bridge():
    action = request.json.get('action', 'start')
    if action == 'start':
        os_state['peripheral_bridge_active'] = True
        return jsonify({"status": "AIVM Peripheral Bridge Hooked."})
    else:
        os_state['peripheral_bridge_active'] = False
        return jsonify({"status": "AIVM Peripheral Bridge Unhooked."})

# -----------------------------------------------------
# IDE PLANETARY DRIVE ENDPOINTS
# -----------------------------------------------------
CLOUD_DRIVE_PATH = "/mnt/synthesus_cloud_pool"

@app.route('/api/ide/files', methods=['GET'])
def list_files():
    # If the physical mount doesn't exist yet, return a mock tree
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
    
    # Otherwise, read the actual 3-way Rclone FUSE mount
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

@app.route('/api/twin/data', methods=['GET'])
def get_twin_data():
    # Here we would read from the actual royal_twin_ledger.csv or memory space
    return jsonify(twin_data)

def background_twin_updater():
    """Simulates or reads actual Twin data from the OS kernel memory."""
    import random
    while True:
        if os_state["twin_status"] == "Active":
            twin_data["pt"] = 20 + random.randint(0, 10)
            twin_data["pcv"] = 25 + random.randint(0, 10)
            twin_data["toxin"] = 60 + random.randint(0, 20)
            twin_data["pain"] = 5 + random.randint(0, 3)
        time.sleep(2)

if __name__ == '__main__':
    print("[*] Synthesus Desktop Environment Core Server Booting...")
    threading.Thread(target=background_twin_updater, daemon=True).start()
    app.run(host='0.0.0.0', port=8080)
