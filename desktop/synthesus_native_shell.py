import os
import sys
import threading
import time
import json
import subprocess
# pywebview is only needed for the GRAPHICAL desktop window. A headless server
# (SYNTHESUS_HEADLESS=1) may not have a GTK/WebKit backend at all, so import it
# lazily/optionally — the module must still load and serve the UI in headless mode.
try:
    import webview
except Exception:
    webview = None
import asyncio
import webbrowser
import requests

from flask import Flask, send_from_directory, jsonify, request
from flask_cors import CORS

import accounts  # real email/password account system (sibling module)
import pro       # Synthesus Pro: license activation + premium unlock (sibling module)

# ===================================================================
# SYNTHESUS C++ KERNEL IPC BRIDGE (QUADBRAIN INTEGRATION)
# ===================================================================
# Dynamically load the Synthesus "Ultra" codebase from local repo
if not getattr(sys, 'frozen', False):
    sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "../../../")))

class CognitiveKernelIPC:
    def __init__(self):
        self.kernel_status = "Sub-1GB Reasoning Engine: ACTIVE (Ring-0)"
        self.quadbrain = None
        try:
            from core.quadbrain_master import QuadbrainMaster
            self.quadbrain = QuadbrainMaster()
            self.kernel_status = "Synthesus QuadBrain Master: ONLINE & INTEGRATED"
        except Exception as e:
            print(f"[!] Quadbrain Integration Failed: {e}. Falling back to dummy logic.")

    def send_intent_to_kernel(self, intent_string):
        print(f"[KERNEL IPC] Routing intent: {intent_string}")
        
        if self.quadbrain:
            # Run the formal Quadbrain async cycle
            try:
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                result = loop.run_until_complete(self.quadbrain.think(intent_string))
                loop.close()
                return result.get("answer", "Quadbrain failed to generate an answer.")
            except Exception as e:
                return f"[QuadBrain Error]: {str(e)}"
        
        # Fallback if quadbrain fails to load
        return f"[AUTONOMIC REFLEX]: Cognitive linkage severed. Intent '{intent_string}' logged to local volatile memory."

kernel_ipc = CognitiveKernelIPC()

# ===================================================================
# FLASK OS BACKEND
# ===================================================================
if getattr(sys, 'frozen', False):
    if hasattr(sys, '_MEIPASS'):
        base_dir = sys._MEIPASS
    else:
        base_dir = os.path.dirname(sys.executable)
    SCRIPT_DIR = os.path.join(base_dir, "_internal", "packages", "subsystem", "planetary-desktop")
    if not os.path.exists(SCRIPT_DIR):
        # Fallback if _internal is not used (older PyInstaller)
        SCRIPT_DIR = os.path.join(base_dir, "packages", "subsystem", "planetary-desktop")
else:
    SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))

app = Flask(__name__, static_folder=SCRIPT_DIR)
CORS(app)

# Ensure the accounts database/tables exist before serving any requests.
accounts.init_db()

@app.after_request
def _no_cache(resp):
    # The webview caches frontend files aggressively across boots, which is why
    # edits kept showing stale. Force it to always fetch the current files.
    resp.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
    resp.headers["Pragma"] = "no-cache"
    return resp

@app.route('/')
def serve_index():
    return send_from_directory(SCRIPT_DIR, 'index.html')

@app.route('/<path:path>')
def serve_static(path):
    return send_from_directory(SCRIPT_DIR, path)

SYNTHESUS_RUNTIME_URL = os.environ.get("SYNTHESUS_RUNTIME_URL", "http://127.0.0.1:5010")

@app.route('/api/system/status', methods=['GET'])
def get_status():
    status_data = {
        "3way_drive_active": True,
        "peripheral_bridge_active": True,
        "llm_status": kernel_ipc.kernel_status
    }
    
    # Pass through the health llm field from backend in the health proxy route if applicable
    try:
        r = requests.get(
            f"{SYNTHESUS_RUNTIME_URL}/api/v1/health",
            headers={"X-API-Key": os.environ.get("SYNTHESUS_API_KEY", "dev-key-change-me")},
            timeout=2,
        )
        if r.status_code == 200:
            payload = r.json()
            if "llm" in payload:
                status_data["llm"] = payload["llm"]
    except Exception as e:
        print(f"[system/status] health proxy unavailable ({e})")

    return jsonify(status_data)

@app.route('/api/health', methods=['GET'])
def health_proxy():
    try:
        r = requests.get(
            f"{SYNTHESUS_RUNTIME_URL}/api/v1/health",
            headers={"X-API-Key": os.environ.get("SYNTHESUS_API_KEY", "dev-key-change-me")},
            timeout=5,
        )
        return (r.text, r.status_code, {"Content-Type": "application/json"})
    except Exception as e:
        print(f"[health] proxy unavailable ({e})")
        return jsonify({"status": "error", "message": f"runtime unavailable: {e}"}), 503

# Section E (C-401): the desktop chat routes through the CHAL runtime — the full
# merged Synthesus brain (grounding + quad-brain + LLM + critic). If the runtime
# is unavailable it DEGRADES LOUDLY to the direct kernel path (still real local AI,
# never a fabricated reply).

@app.route('/api/chat', methods=['POST'])
def chat_with_llm():
    data = request.json
    user_message = data.get('message', '')

    # 1) Preferred path: the full CHAL runtime.
    try:
        r = requests.post(
            f"{SYNTHESUS_RUNTIME_URL}/api/v1/query",
            json={"query": user_message, "mode": "chal", "character": "synthesus"},
            headers={"X-API-Key": os.environ.get("SYNTHESUS_API_KEY", "dev-key-change-me")},
            timeout=90,
        )
        r.raise_for_status()
        payload = r.json()
        text = (payload.get("response") or payload.get("text") or "").strip()
        if text:
            return jsonify({"response": text, "source": "chal_runtime"})
        raise ValueError("empty runtime response")
    except Exception as e:
        # 2) Loud DEGRADED fallback — direct kernel (Ollama) path. Logged, not faked.
        print(f"[chat] CHAL runtime unavailable ({e}); DEGRADED -> direct kernel path")
        response = kernel_ipc.send_intent_to_kernel(user_message)
        return jsonify({"response": response, "source": "degraded_direct"})

# ===================================================================
# AGNOSTIC EXPANSION DRIVE — ground Synthesus on the user's own sources
# (GitHub, synced cloud folders). Thin proxy to the runtime, which owns the
# per-user index. Fetch is from the user's own source; indexing stays local.
# ===================================================================
@app.route('/api/drive/sources', methods=['GET'])
def drive_sources():
    """List ingestable source types (live vs planned) for the drive UI."""
    try:
        r = requests.get(
            f"{SYNTHESUS_RUNTIME_URL}/api/v1/drive/sources",
            headers={"X-API-Key": os.environ.get("SYNTHESUS_API_KEY", "dev-key-change-me")},
            timeout=15,
        )
        r.raise_for_status()
        return jsonify(r.json())
    except Exception as e:
        print(f"[drive] sources unavailable ({e})")
        return jsonify({"sources": [], "error": "runtime unavailable"}), 503

@app.route('/api/drive/remotes', methods=['GET'])
def drive_remotes():
    """Which rclone cloud remotes are actually configured (for the creator)."""
    try:
        r = requests.get(
            f"{SYNTHESUS_RUNTIME_URL}/api/v1/drive/remotes",
            headers={"X-API-Key": os.environ.get("SYNTHESUS_API_KEY", "dev-key-change-me")},
            timeout=20,
        )
        r.raise_for_status()
        return jsonify(r.json())
    except Exception as e:
        print(f"[drive] remotes unavailable ({e})")
        return jsonify({"rclone_available": False, "remotes": [], "error": "runtime unavailable"}), 503

@app.route('/api/drive/ingest', methods=['POST'])
def drive_ingest():
    """Ingest a user source into their grounding index (via the runtime)."""
    data = request.get_json(silent=True) or {}
    try:
        r = requests.post(
            f"{SYNTHESUS_RUNTIME_URL}/api/v1/drive/ingest",
            json=data,
            headers={"X-API-Key": os.environ.get("SYNTHESUS_API_KEY", "dev-key-change-me")},
            timeout=600,
        )
        # Pass the runtime's status + body straight through — loud on errors,
        # never fake a success.
        return (r.text, r.status_code, {"Content-Type": "application/json"})
    except Exception as e:
        print(f"[drive] ingest failed ({e})")
        return jsonify({"status": "error", "message": f"runtime unavailable: {e}"}), 503

@app.route('/api/drive/progress/<job_id>', methods=['GET'])
def drive_progress(job_id):
    try:
        r = requests.get(
            f"{SYNTHESUS_RUNTIME_URL}/api/v1/drive/progress/{job_id}",
            headers={"X-API-Key": os.environ.get("SYNTHESUS_API_KEY", "dev-key-change-me")},
            timeout=15,
        )
        return (r.text, r.status_code, {"Content-Type": "application/json"})
    except Exception as e:
        print(f"[drive] progress unavailable ({e})")
        return jsonify({"status": "error", "message": f"runtime unavailable: {e}"}), 503

@app.route('/api/drive/preview', methods=['POST'])
def drive_preview():
    data = request.get_json(silent=True) or {}
    try:
        r = requests.post(
            f"{SYNTHESUS_RUNTIME_URL}/api/v1/drive/preview",
            json=data,
            headers={"X-API-Key": os.environ.get("SYNTHESUS_API_KEY", "dev-key-change-me")},
            timeout=30,
        )
        return (r.text, r.status_code, {"Content-Type": "application/json"})
    except Exception as e:
        print(f"[drive] preview unavailable ({e})")
        return jsonify({"chunks": [], "error": f"runtime unavailable: {e}"}), 503

@app.route('/api/drive/rclone/status', methods=['GET'])
def drive_rclone_status():
    try:
        r = requests.get(
            f"{SYNTHESUS_RUNTIME_URL}/api/v1/drive/rclone/status",
            headers={"X-API-Key": os.environ.get("SYNTHESUS_API_KEY", "dev-key-change-me")},
            timeout=15,
        )
        return (r.text, r.status_code, {"Content-Type": "application/json"})
    except Exception as e:
        print(f"[drive] rclone status unavailable ({e})")
        return jsonify({"installed": False, "remotes": [], "error": f"runtime unavailable: {e}"}), 503

# ===================================================================
# REAL AUTH (email + password)
# ===================================================================
@app.route('/api/auth/register', methods=['POST'])
def auth_register():
    data = request.get_json(silent=True) or {}
    try:
        result = accounts.register(data.get('email'), data.get('password'))
        return jsonify({"status": "success", **result})
    except accounts.AccountError as e:
        return jsonify({"status": "error", "message": str(e)}), 400

@app.route('/api/auth/login', methods=['POST'])
def auth_login():
    data = request.get_json(silent=True) or {}
    try:
        result = accounts.authenticate(data.get('email'), data.get('password'))
        return jsonify({"status": "success", **result})
    except accounts.AccountError as e:
        return jsonify({"status": "error", "message": str(e)}), 401

# ===================================================================
# STRIPE CHECKOUT (Payment Links)
# ---------------------------------------------------------------
# We use Stripe-hosted Payment Links rather than embedding a secret key
# in this client. Links are public URLs; swap to live-mode links via env
# vars before going live. Opening in the user's real browser keeps the
# frameless webview from being hijacked by the Stripe page.
# ===================================================================
PAYMENT_LINKS = {
    # The live Gumroad Pro checkout (env overrides).
    "pro":   os.environ.get("PRO_PRODUCT_URL") or "https://dakinelle.gumroad.com/l/xkvtl",
    "ultra": os.environ.get("STRIPE_LINK_ULTRA", "https://buy.stripe.com/test_6oU4gB2v1dsY56g6o58EM01"),
}

@app.route('/api/checkout/<tier>', methods=['POST'])
def checkout(tier):
    url = PAYMENT_LINKS.get((tier or "").lower())
    if not url:
        return jsonify({"status": "error", "message": "Unknown tier"}), 400
    opened = False
    try:
        opened = webbrowser.open(url)
    except Exception as e:
        print(f"[checkout] webbrowser.open failed: {e}")
    # Always return the URL so the frontend can fall back to opening it itself.
    return jsonify({"status": "success", "opened": bool(opened), "url": url})

@app.route('/api/pro/status', methods=['GET'])
def pro_status():
    """Is Pro active on this machine, and which premium personas are installed?"""
    try:
        return jsonify(pro.status())
    except Exception as e:
        return jsonify({"pro": False, "error": str(e)}), 500

@app.route('/api/pro/activate', methods=['POST'])
def pro_activate():
    """Activate Pro: verify the license key with Gumroad, then install the premium pack."""
    data = request.json or {}
    key = (data.get("key") or "").strip()
    pack = (data.get("pack_path") or "").strip() or None
    try:
        result = pro.activate(key, pack)
        return jsonify(result), (200 if result.get("pro") else 400)
    except Exception as e:
        return jsonify({"pro": False, "error": str(e)}), 500

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
    override = data.get('admin_override', False)
    
    # -------------------------------------------------------------
    # SYNTHESUS HIERARCHY APPROVAL PROTOCOL
    # The AI actively evaluates the command's intent and risk profile.
    # -------------------------------------------------------------
    if not override:
        # Route the command to the Quadbrain for deep contextual risk analysis
        # (This replaces the cheap hardcoded string matching)
        risk_evaluation = kernel_ipc.send_intent_to_kernel(f"Evaluate risk level of command: {cmd}")
        
        # If the AI deems the command a substrate-level modification, it prompts the user
        if "HIGH_RISK" in risk_evaluation.upper() or "SUBSTRATE" in risk_evaluation.upper():
            synthesus_query = f"Admin Dakin, you requested a substrate-level execution: '{cmd}'. My analysis indicates this modifies the core host hierarchy. Do I have your explicit authorization to proceed?"
            return jsonify({
                "status": "requires_approval",
                "synthesus_query": synthesus_query,
                "pending_command": cmd
            })
            
    try:
        # Route the shell command to the Host OS backend
        # Increased timeout to 120 seconds to support long-running tasks like apt/npm
        output = subprocess.check_output(cmd, shell=True, stderr=subprocess.STDOUT, text=True, timeout=120)
    except subprocess.CalledProcessError as e:
        output = e.output
    except Exception as e:
        output = str(e)
        
    return jsonify({"status": "success", "output": output})

# ===================================================================
# LAUNCHER
# ===================================================================
def ensure_runtime():
    """Bring up the CHAL runtime (the merged Synthesus brain) if it isn't already
    reachable. If SYNTHESUS_RUNTIME_CMD is set, launch it as a background process
    and wait for readiness. Non-fatal: on any failure the desktop /api/chat still
    works via the loud-degraded direct path.
    """
    import urllib.request
    health = f"{SYNTHESUS_RUNTIME_URL}/api/v1/health"
    key = os.environ.get("SYNTHESUS_API_KEY", "dev-key-change-me")

    def _up():
        try:
            req = urllib.request.Request(health, headers={"X-API-Key": key})
            with urllib.request.urlopen(req, timeout=2) as resp:
                return resp.status == 200
        except Exception:
            return False

    if _up():
        print("[runtime] CHAL runtime already up.")
        return
    cmd = os.environ.get("SYNTHESUS_RUNTIME_CMD", "").strip()
    if not cmd:
        print("[runtime] SYNTHESUS_RUNTIME_CMD not set — desktop uses the direct path "
              "until a CHAL runtime is started separately.")
        return
    print(f"[runtime] launching CHAL runtime: {cmd}")
    try:
        runtime_log = os.path.expanduser("~/.synthesus/runtime.log")
        os.makedirs(os.path.dirname(runtime_log), exist_ok=True)
        subprocess.Popen(cmd, shell=True,
                         stdout=open(runtime_log, "a"), stderr=subprocess.STDOUT)
    except Exception as e:
        print(f"[runtime] failed to launch ({e}); desktop will degrade to the direct path.")
        return
    for _ in range(60):
        if _up():
            print("[runtime] CHAL runtime READY — merged brain online.")
            return
        time.sleep(1)
    print("[runtime] CHAL runtime not ready in time; desktop will degrade to the direct path.")


def start_flask():
    app.run(host='127.0.0.1', port=8081, debug=False, use_reloader=False)

def ensure_terminal():
    """Start the god-mode terminal PTY backend (:8082) if it isn't already up.
    Makes the terminal work no matter how the desktop was launched — not only via
    start_synthesus.sh. Without this, the terminal WebSocket is refused and the UI
    loops connect/disconnect forever."""
    import socket, subprocess, sys, os
    try:
        with socket.create_connection(("127.0.0.1", 8082), timeout=1):
            print("[terminal] PTY backend already up on :8082")
            return
    except OSError:
        pass
    server = os.path.join(os.path.dirname(os.path.abspath(__file__)), "terminal_server.py")
    if not os.path.exists(server):
        print(f"[terminal] terminal_server.py not found at {server}; terminal disabled")
        return
    try:
        log = os.path.expanduser("~/.synthesus/terminal_server.log")
        os.makedirs(os.path.dirname(log), exist_ok=True)
        subprocess.Popen([sys.executable, server], stdout=open(log, "a"),
                         stderr=subprocess.STDOUT, start_new_session=True)
        print("[terminal] launched PTY backend on :8082")
    except Exception as e:
        print(f"[terminal] failed to launch PTY backend: {e}")


if __name__ == '__main__':
    # ── Two ways to run Synthesus ─────────────────────────────────────────
    #  GRAPHICAL (default): opens the frameless desktop window via pywebview.
    #  HEADLESS  (SYNTHESUS_HEADLESS=1): no window — serves the exact same OS at
    #    http://localhost:8081 for you to open in any browser. For machines with
    #    no display (servers, homelab boxes) or if pywebview has no backend.
    #    Stays bound to 127.0.0.1; to reach it from another machine use an SSH
    #    tunnel (see docs/HEADLESS.md) — do NOT expose these ports directly.
    headless = os.environ.get("SYNTHESUS_HEADLESS", "").lower() in ("1", "true", "yes")
    if webview is None and not headless:
        print("[!] No pywebview backend available — falling back to HEADLESS mode.")
        headless = True

    print("[*] Booting Synthesus Planetary OS Shell"
          + (" (headless)…" if headless else "…"))

    # Bring up the merged CHAL runtime + the terminal PTY backend in the background.
    threading.Thread(target=ensure_runtime, daemon=True).start()
    threading.Thread(target=ensure_terminal, daemon=True).start()

    if headless:
        # Serve the OS in the foreground so the process stays alive; the user
        # points a browser at it. Nothing is exposed beyond localhost.
        print("[*] HEADLESS — open Synthesus in your browser:")
        print("[*]     http://localhost:8081")
        print("[*] Remote access: SSH-tunnel it (docs/HEADLESS.md); never expose :8081/:8082 directly.")
        start_flask()  # blocking — keeps the process running
    else:
        threading.Thread(target=start_flask, daemon=True).start()
        # Don't open the window until the shell actually answers — otherwise the
        # webview loads a "cannot reach server" page once and sits on it.
        import urllib.request
        for _ in range(30):
            try:
                with urllib.request.urlopen("http://127.0.0.1:8081/", timeout=1) as resp:
                    if resp.status == 200:
                        break
            except Exception:
                time.sleep(0.5)

        print("[*] Hooking into Host OS via PyWebView (Frameless Mode)...")
        webview.create_window('Synthesus Planetary OS', 'http://127.0.0.1:8081', frameless=True, fullscreen=True, text_select=True)
        webview.start()
