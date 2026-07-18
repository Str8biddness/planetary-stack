import os
import sys
import threading
import time
import json
import subprocess
import shlex
import uuid
import atexit
import secrets
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
        self.kernel_status = "Sub-1GB Reasoning Engine: LOCAL FALLBACK"
        self.quadbrain = None
        try:
            from core.quadbrain_master import QuadbrainMaster
            self.quadbrain = QuadbrainMaster()
            self.kernel_status = "Synthesus QuadBrain Master: ONLINE & INTEGRATED"
        except Exception as e:
            # The in-process Quadbrain is only the DEGRADED fallback brain (used if the
            # CHAL runtime on :5010 is unreachable). In the normal path the runtime is the
            # brain, so this not loading is expected noise — not an error.
            print(f"[info] In-process fallback brain not loaded ({e}); using the CHAL runtime as the primary brain (expected).")

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
SHELL_PORT = int(os.environ.get("SYNTHESUS_SHELL_PORT", "8081"))
CONTROLLER_PORT = int(os.environ.get("SYNTHESUS_CONTROLLER_PORT", "5011"))
CONTROLLER_ORIGINS = (
    f"http://127.0.0.1:{SHELL_PORT}",
    f"http://localhost:{SHELL_PORT}",
)
_KNOWN_DEFAULT_API_KEYS = frozenset({"dev-key-change-me"})


def _runtime_api_key():
    """Return the installer-generated controller key or refuse startup."""
    key = (os.environ.get("SYNTHESUS_API_KEY") or "").strip()
    if key in _KNOWN_DEFAULT_API_KEYS or len(key.encode("utf-8")) < 24:
        raise RuntimeError(
            "Synthesus requires a unique per-install API key; run install.sh or "
            "set SYNTHESUS_API_KEY."
        )
    return key


CORS(
    app,
    resources={r"/api/*": {"origins": list(CONTROLLER_ORIGINS)}},
    supports_credentials=False,
)

# Fail before opening a listener if either local trust secret is missing, public,
# or too short. The browser never receives these values.
_runtime_api_key()
accounts.require_secure_configuration()
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

SYNTHESUS_RUNTIME_UPSTREAM_URL = (
    os.environ.get("SYNTHESUS_RUNTIME_UPSTREAM_URL")
    or os.environ.get("SYNTHESUS_RUNTIME_URL")
    or "http://127.0.0.1:5010"
).rstrip("/")
SYNTHESUS_CONTROLLER_URL = os.environ.get(
    "SYNTHESUS_CONTROLLER_URL",
    f"http://127.0.0.1:{CONTROLLER_PORT}",
).rstrip("/")
SYNTHESUS_RUNTIME_URL = f"{SYNTHESUS_CONTROLLER_URL}/runtime"
SYNTHESUS_TERMINAL_SOCKET = os.path.expanduser(
    os.environ.get(
        "SYNTHESUS_TERMINAL_SOCKET",
        "~/.synthesus/ipc/terminal.sock",
    )
)
SYNTHESUS_TERMINAL_TOKEN = os.environ.get(
    "SYNTHESUS_TERMINAL_TOKEN",
) or secrets.token_urlsafe(32)
SYNTHESUS_CONTROLLER_SESSION_ID = secrets.token_hex(16)
_CHILD_PROCESSES: list[subprocess.Popen] = []

# Pending chat answers keyed by answer_id — used so 👍 confirm can stage + upgrade
# a specific assistant message. Server-side only; not exposed as a dump endpoint.
_pending_chat_answers: dict = {}


def _track_child(process: subprocess.Popen) -> subprocess.Popen:
    _CHILD_PROCESSES.append(process)
    return process


def _stop_child_processes() -> None:
    for process in reversed(_CHILD_PROCESSES):
        if process.poll() is not None:
            continue
        process.terminate()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=2)
    try:
        os.unlink(SYNTHESUS_TERMINAL_SOCKET)
    except FileNotFoundError:
        pass
    except OSError as exc:
        print(f"[terminal] could not remove socket during shutdown: {exc}")


atexit.register(_stop_child_processes)


def _runtime_api_headers(*, include_human_session: bool = False) -> dict:
    """Headers for runtime calls. Human session secret is NEVER sent to the browser."""
    headers = {
        "X-API-Key": _runtime_api_key(),
        "Content-Type": "application/json",
    }
    if include_human_session:
        secret = os.environ.get("SYNTHESUS_HUMAN_SESSION_SECRET", "").strip()
        if secret:
            # Injected only on the shell→runtime hop. Frontend never sees this value.
            headers["X-Synthesus-Human-Session"] = secret
    return headers


@app.route('/api/ipc/session', methods=['GET'])
def ipc_session():
    """Return only the short-lived browser capability for terminal IPC."""
    identity = _human_identity_from_request()
    if not identity:
        return jsonify({"error": "authenticated_user_required"}), 401
    return jsonify({
        "controller_port": CONTROLLER_PORT,
        "terminal_token": SYNTHESUS_TERMINAL_TOKEN,
        "terminal_http_path": "/terminal",
        "terminal_ws_path": "/ws/terminal",
        "transport": "authenticated_loopback_to_unix_socket",
        "user": identity,
    })


def _human_identity_from_request():
    """Resolve the logged-in user's real identity via accounts.py (JWT).

    Prefer Authorization: Bearer <token>; fall back to X-Synthesus-Token.
    Returns email string or None. Never invents a human from API-key alone.
    """
    token = None
    auth = request.headers.get("Authorization") or ""
    if auth.lower().startswith("bearer "):
        token = auth.split(" ", 1)[1].strip()
    if not token:
        token = (request.headers.get("X-Synthesus-Token") or "").strip() or None
    if not token:
        body = request.get_json(silent=True) or {}
        token = (body.get("token") or "").strip() or None
    if not token:
        return None
    payload = accounts.verify_token(token)
    if not payload:
        return None
    email = (payload.get("email") or "").strip()
    return email or None


_CONTROLLER_URL = f"http://127.0.0.1:{CONTROLLER_PORT}"


def _proxy_controller_jobs(method, path, payload=None):
    """Authenticated shell→controller hop for the private-mesh job API.

    The per-install key is attached only on this server-side hop; the
    browser never sees it, and job actions additionally require a
    logged-in human identity.
    """

    try:
        r = requests.request(
            method,
            f"{_CONTROLLER_URL}{path}",
            headers={"X-API-Key": _runtime_api_key()},
            json=payload,
            timeout=650,
        )
    except Exception as e:
        return jsonify({"error": "controller_unavailable", "message": str(e)}), 503
    content_type = r.headers.get("Content-Type", "application/json")
    return (r.content, r.status_code, {"Content-Type": content_type})


@app.route('/api/jobs', methods=['POST'])
def jobs_submit():
    if not _human_identity_from_request():
        return jsonify({"error": "authenticated_user_required"}), 401
    body = request.get_json(silent=True) or {}
    payload = {
        "bundle_base64": body.get("bundle_base64"),
        "workload_kind": body.get("workload_kind", "inference"),
    }
    return _proxy_controller_jobs("POST", "/api/jobs", payload)


@app.route('/api/jobs/<job_id>', methods=['GET'])
def jobs_status(job_id):
    if not _human_identity_from_request():
        return jsonify({"error": "authenticated_user_required"}), 401
    return _proxy_controller_jobs("GET", f"/api/jobs/{job_id}")


@app.route('/api/jobs/<job_id>/cancel', methods=['POST'])
def jobs_cancel(job_id):
    if not _human_identity_from_request():
        return jsonify({"error": "authenticated_user_required"}), 401
    return _proxy_controller_jobs("POST", f"/api/jobs/{job_id}/cancel")


@app.route('/api/jobs/<job_id>/results/<output_sha256>', methods=['GET'])
def jobs_result(job_id, output_sha256):
    if not _human_identity_from_request():
        return jsonify({"error": "authenticated_user_required"}), 401
    return _proxy_controller_jobs(
        "GET", f"/api/jobs/{job_id}/results/{output_sha256}"
    )


@app.route('/api/system/status', methods=['GET'])
def get_status():
    status_data = {
        # Expansion Drive/RAG ingestion is not an SSI mount. Do not claim a
        # distributed storage plane until a verified namespace is mounted.
        "3way_drive_active": False,
        "3way_drive_reason": "verified_planetary_drive_not_mounted",
        "peripheral_bridge_active": False,
        "peripheral_bridge_reason": "browser_kvm_not_enabled",
        "llm_status": kernel_ipc.kernel_status
    }
    
    # Pass through the health llm field from backend in the health proxy route if applicable
    try:
        r = requests.get(
            f"{SYNTHESUS_RUNTIME_URL}/api/v1/health",
            headers={"X-API-Key": _runtime_api_key()},
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
@app.route('/api/v1/health', methods=['GET'])  # the frontend calls /api/v1/health relative to the shell
def health_proxy():
    try:
        r = requests.get(
            f"{SYNTHESUS_RUNTIME_URL}/api/v1/health",
            headers={"X-API-Key": _runtime_api_key()},
            timeout=5,
        )
        return (r.text, r.status_code, {"Content-Type": "application/json"})
    except Exception as e:
        print(f"[health] proxy unavailable ({e})")
        return jsonify({"status": "error", "message": f"runtime unavailable: {e}"}), 503


@app.route('/api/v1/image', methods=['POST'])
def image_proxy():
    """SI Image Studio → runtime POST /api/v1/image (procedural VSA, not diffusion).

    Forwards knobs including enhance + multi-pass. Never invents a PNG if runtime is down.
    (Was previously a dead-code 500: body built then function returned None before the POST.)
    """
    data = request.get_json(silent=True) or {}
    prompt = (data.get("prompt") or "").strip()
    if not prompt and not data.get("scene_id"):
        return jsonify({"ok": False, "error": "prompt_required", "message": "prompt is required"}), 400
    body = {
        "prompt": prompt,
        "resolution": data.get("resolution", 512),
        "style": data.get("style", "flat"),
        "aspect": data.get("aspect", 1.0),
        "use_cache": data.get("use_cache", True),
        "detail": data.get("detail", "high"),
        "look": data.get("look", "photo"),
        "path_mode": data.get("path_mode", True),
        "preset": data.get("preset"),
        "variations": data.get("variations", 1),
        "views": data.get("views", 1),
        "yaw_span": data.get("yaw_span", 30),
        "frames": data.get("frames", 1),
        "yaw_deg": data.get("yaw_deg", 0),
        "pitch_deg": data.get("pitch_deg", 0),
        "time_of_day": data.get("time_of_day"),
        "as_gif": data.get("as_gif", False),
        "gif_format": data.get("gif_format", "gif"),
        "gif_duration_ms": data.get("gif_duration_ms", 400),
        "return_level": data.get("return_level", False),
        "orbit_day": data.get("orbit_day", False),
        "orbit_frames": data.get("orbit_frames", 6),
        "async_mode": data.get("async_mode", False),
        "compile_plan": data.get("compile_plan", True),
        "return_plan": data.get("return_plan", True),
        "keep_session": data.get("keep_session", True),
        "enhance": data.get("enhance", "none"),
        "enhance_strength": data.get("enhance_strength", 0.55),
        "grade": data.get("grade", "none"),
        "edit_text": data.get("edit_text"),
        "scene_id": data.get("scene_id"),
        "pass_only": data.get("pass_only", False),
    }
    # Optional multi-pass / session knobs (only when present)
    for key in (
        "seed", "scene_id", "edit_text", "grade", "yaw", "pitch",
        "pass_id", "construction", "playlist", "finish", "enhance", "enhance_strength",
    ):
        if key in data and data.get(key) is not None and data.get(key) != "":
            body[key] = data[key]
    if data.get("seed") is not None and str(data.get("seed")).strip() != "":
        try:
            body["seed"] = int(data["seed"])
        except (TypeError, ValueError):
            body.pop("seed", None)
    try:
        r = requests.post(
            f"{SYNTHESUS_RUNTIME_URL}/api/v1/image",
            json=body,
            headers=_runtime_api_headers(),
            timeout=180,
        )
        try:
            payload = r.json()
        except Exception:
            payload = {"ok": False, "error": "bad_runtime_body", "message": (r.text or "")[:400]}
        return (json.dumps(payload), r.status_code, {"Content-Type": "application/json"})
    except Exception as e:
        print(f"[image] runtime unavailable ({e})")
        return jsonify({
            "ok": False,
            "error": "runtime_unavailable",
            "message": f"runtime unavailable: {e}",
        }), 503


@app.route('/api/v1/image/jobs/<job_id>', methods=['GET'])
def image_job_proxy(job_id):
    """Poll async SI image job."""
    try:
        r = requests.get(
            f"{SYNTHESUS_RUNTIME_URL}/api/v1/image/jobs/{job_id}",
            headers=_runtime_api_headers(),
            timeout=30,
        )
        try:
            payload = r.json()
        except Exception:
            payload = {"ok": False, "error": "bad_runtime_body", "message": (r.text or "")[:400]}
        return (json.dumps(payload), r.status_code, {"Content-Type": "application/json"})
    except Exception as e:
        return jsonify({"ok": False, "error": "runtime_unavailable", "message": str(e)}), 503


@app.route('/api/v1/image/level', methods=['POST'])
def image_level_proxy():
    """SI level JSON export → runtime."""
    data = request.get_json(silent=True) or {}
    try:
        r = requests.post(
            f"{SYNTHESUS_RUNTIME_URL}/api/v1/image/level",
            json=data,
            headers=_runtime_api_headers(),
            timeout=60,
        )
        try:
            payload = r.json()
        except Exception:
            payload = {"ok": False, "error": "bad_runtime_body", "message": (r.text or "")[:400]}
        return (json.dumps(payload), r.status_code, {"Content-Type": "application/json"})
    except Exception as e:
        return jsonify({"ok": False, "error": "runtime_unavailable", "message": str(e)}), 503


@app.route('/api/v1/image/intent', methods=['POST'])
def image_intent_proxy():
    """Chat draw-intent classifier → runtime."""
    data = request.get_json(silent=True) or {}
    try:
        r = requests.post(
            f"{SYNTHESUS_RUNTIME_URL}/api/v1/image/intent",
            json=data,
            headers=_runtime_api_headers(),
            timeout=30,
        )
        try:
            payload = r.json()
        except Exception:
            payload = {"ok": False, "error": "bad_runtime_body", "message": (r.text or "")[:400]}
        return (json.dumps(payload), r.status_code, {"Content-Type": "application/json"})
    except Exception as e:
        return jsonify({"ok": False, "error": "runtime_unavailable", "message": str(e)}), 503


@app.route('/api/v1/image/presets', methods=['GET'])
def image_presets_proxy():
    """List cinematic SI scene presets (local catalog)."""
    try:
        import sys
        from pathlib import Path
        try:
            import scene_presets as sp
        except ImportError:
            rt = Path(os.environ.get("SYNTHESUS_HOME", Path.home() / ".local/share/synthesus"))
            sys.path.insert(0, str(rt / "runtime" / "packages" / "reasoning"))
            import scene_presets as sp  # type: ignore
        return jsonify({"ok": True, "presets": sp.list_presets()})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e), "presets": []}), 503

@app.route('/api/v1/voice', methods=['POST'])
def voice_proxy():
    """SI Voice Studio → runtime POST /api/v1/voice (formant larynx, not neural TTS).

    Forwards {text, knobs?, seed?}. Never invents WAV if runtime/engine is down.
    Propagates 503 loudly when the formant engine is missing.
    """
    data = request.get_json(silent=True) or {}
    text = (data.get("text") or data.get("prompt") or "").strip()
    if not text:
        return jsonify({
            "ok": False,
            "error": "text_required",
            "message": "text is required",
            "not_neural_tts": True,
        }), 400
    body = {
        "text": text,
        "knobs": data.get("knobs") if isinstance(data.get("knobs"), dict) else {},
        "backend": (data.get("backend") or data.get("engine") or "formant"),
    }
    if data.get("seed") is not None and str(data.get("seed")).strip() != "":
        try:
            body["seed"] = int(data["seed"])
        except (TypeError, ValueError):
            pass
    try:
        r = requests.post(
            f"{SYNTHESUS_RUNTIME_URL}/api/v1/voice",
            json=body,
            headers=_runtime_api_headers(),
            timeout=60,
        )
        try:
            payload = r.json()
        except Exception:
            payload = {
                "ok": False,
                "error": "bad_runtime_body",
                "message": (r.text or "")[:400],
                "not_neural_tts": True,
            }
        return (json.dumps(payload), r.status_code, {"Content-Type": "application/json"})
    except Exception as e:
        print(f"[voice] runtime unavailable ({e})")
        return jsonify({
            "ok": False,
            "error": "runtime_unavailable",
            "message": f"runtime unavailable: {e}",
            "not_neural_tts": True,
            "note": "SI formant larynx missing or failed — not falling back to neural TTS",
        }), 503


# Section E (C-401): the desktop chat routes through the CHAL runtime — the full
# merged Synthesus brain (grounding + quad-brain + LLM + critic). If the runtime
# is unavailable it DEGRADES LOUDLY to the direct kernel path (still real local AI,
# never a fabricated reply).

@app.route('/api/chat', methods=['POST'])
def chat_with_llm():
    data = request.json or {}
    user_message = data.get('message', '')

    # Every assistant reply gets a stable answer_id so 👍 can bind human
    # attestation + feedback to that exact message (subject_key / answer_id).
    answer_id = "ans-" + uuid.uuid4().hex[:16]

    # 1) Preferred path: the full CHAL runtime.
    try:
        r = requests.post(
            f"{SYNTHESUS_RUNTIME_URL}/api/v1/query",
            json={"query": user_message, "mode": "chal", "character": "synthesus"},
            headers=_runtime_api_headers(),
            timeout=180,
        )
        r.raise_for_status()
        payload = r.json()
        text = (payload.get("response") or payload.get("text") or "").strip()
        if text:
            _pending_chat_answers[answer_id] = {
                "query": user_message,
                "response": text,
                "source": "chal_runtime",
                "created_ts": time.time(),
            }
            return jsonify({
                "response": text,
                "source": "chal_runtime",
                "answer_id": answer_id,
                "sources": payload.get("sources"),
            })
        raise ValueError("empty runtime response")
    except Exception as e:
        # 2) Loud DEGRADED fallback — direct kernel (Ollama) path. Logged, not faked.
        print(f"[chat] CHAL runtime unavailable ({e}); DEGRADED -> direct kernel path")
        response = kernel_ipc.send_intent_to_kernel(user_message)
        _pending_chat_answers[answer_id] = {
            "query": user_message,
            "response": response,
            "source": "degraded_direct",
            "created_ts": time.time(),
        }
        return jsonify({
            "response": response,
            "source": "degraded_direct",
            "answer_id": answer_id,
            "degraded": True,
            "reason": f"chal_runtime_unavailable: {e}",
        })


# ===================================================================
# HUMAN ATTESTATION + FEEDBACK (Mc upgrade — anti-collapse boundary)
# ===================================================================
# The browser NEVER holds SYNTHESUS_HUMAN_SESSION_SECRET. The shell injects
# X-Synthesus-Human-Session from its own environment when minting tokens.
# confirmed_by is the logged-in account email from accounts.py (JWT), not a
# client-supplied self-label.
# ===================================================================

@app.route('/api/human/attestation', methods=['POST'])
def human_attestation_proxy():
    """Mint a single-use human attestation for feedback→VERIFIED upgrades.

    Frontend calls this shell route only. The shell injects the human-session
    secret server-side and forwards to runtime POST /api/v1/human/attestation.
    """
    data = request.get_json(silent=True) or {}
    human_id = _human_identity_from_request()
    if not human_id:
        # Allow explicit human_id only when it matches a verified session; otherwise
        # require login. Client-supplied identity without JWT is refused.
        return jsonify({
            "issued": False,
            "reason": "login_required",
            "message": "Log in so confirmed_by is a real accounts.py identity.",
            "status": "DEGRADED",
        }), 401

    secret = os.environ.get("SYNTHESUS_HUMAN_SESSION_SECRET", "").strip()
    if not secret:
        print("[attestation] DEGRADED: SYNTHESUS_HUMAN_SESSION_SECRET not set in shell env")
        return jsonify({
            "issued": False,
            "reason": "human_session_secret_unconfigured",
            "message": "Shell is missing SYNTHESUS_HUMAN_SESSION_SECRET (server-side only).",
            "status": "DEGRADED",
        }), 503

    channel = (data.get("channel") or "human_desktop_ui").strip() or "human_desktop_ui"
    subject_key = data.get("subject_key") or data.get("answer_id") or data.get("memory_id")
    body = {
        "human_id": human_id,
        "channel": channel,
        "subject_key": subject_key,
    }
    try:
        r = requests.post(
            f"{SYNTHESUS_RUNTIME_URL}/api/v1/human/attestation",
            json=body,
            headers=_runtime_api_headers(include_human_session=True),
            timeout=15,
        )
        # Pass runtime status/body through — never fake a successful mint.
        return (r.text, r.status_code, {"Content-Type": "application/json"})
    except Exception as e:
        print(f"[attestation] runtime unavailable ({e})")
        return jsonify({
            "issued": False,
            "reason": "runtime_unavailable",
            "message": f"runtime unavailable: {e}",
            "status": "DEGRADED",
        }), 503


def _stage_chat_draft_as_llm_generation(answer_id: str, query: str, response: str) -> dict:
    """Stage the assistant answer into the runtime RAG so feedback can upgrade it.

    The frozen runtime admin/patterns normalizer does not pass provenance through,
    so we stage with a distinctive source/id in the pattern text and then rely on
    feedback matching by answer_id/response. We also best-effort POST a pattern
    whose response text matches for upgrade_from_feedback's content match.

    Returns a small status dict (never silently fakes success).
    """
    pattern_text = f"[chat_draft:{answer_id}] {query or response[:120]}"
    payload = {
        "patterns": [
            {
                "pattern": pattern_text,
                "response": response,
                "source": f"chat_draft:{answer_id}",
                "domain": "chat_draft",
                # id is used when the runtime preserves extra fields; response match is backup
                "id": answer_id,
                "answer_id": answer_id,
                "provenance": "llm_generation",
                "verification": 0,
            }
        ]
    }
    try:
        r = requests.post(
            f"{SYNTHESUS_RUNTIME_URL}/api/v1/admin/patterns",
            json=payload,
            headers=_runtime_api_headers(),
            timeout=60,
        )
        return {
            "staged": r.status_code < 400,
            "status_code": r.status_code,
            "body": r.json() if r.headers.get("content-type", "").startswith("application/json") else r.text[:300],
        }
    except Exception as e:
        print(f"[feedback] stage draft failed ({e})")
        return {"staged": False, "error": str(e)}


@app.route('/api/feedback', methods=['POST'])
def feedback_proxy():
    """Human confirm/correction feedback → runtime Mc upgrade path.

    Requires a prior mint via /api/human/attestation. The shell:
      1) resolves confirmed_by from the logged-in accounts.py identity
      2) stages the chat draft into the runtime index (so upgrade can find it)
      3) forwards feedback with actor_kind/channel/human_attestation to runtime
    """
    data = request.get_json(silent=True) or {}
    human_id = _human_identity_from_request()
    if not human_id:
        return jsonify({
            "status": "error",
            "message": "Login required — confirmed_by must be a real accounts.py identity.",
            "verification_upgrade": {"upgraded": False, "reason": "login_required"},
        }), 401

    answer_id = data.get("answer_id") or data.get("memory_id") or data.get("subject_key")
    pending = _pending_chat_answers.get(answer_id) if answer_id else None
    query = data.get("query") or (pending or {}).get("query") or ""
    response_text = data.get("response") or (pending or {}).get("response") or ""
    human_attestation = data.get("human_attestation") or data.get("attestation")
    action = (data.get("action") or "confirm").strip().lower() or "confirm"
    channel = (data.get("channel") or "human_desktop_ui").strip() or "human_desktop_ui"
    rating = data.get("rating")
    if rating is None:
        rating = 5 if action in {"confirm", "confirmed", "thumbs_up", "accept"} else 3

    if not human_attestation:
        return jsonify({
            "status": "error",
            "message": "human_attestation required — mint via POST /api/human/attestation first.",
            "verification_upgrade": {"upgraded": False, "reason": "missing_human_attestation"},
        }), 400

    # Stage draft so runtime feedback has an item to upgrade (match by response / id).
    stage_info = None
    if answer_id and response_text:
        stage_info = _stage_chat_draft_as_llm_generation(answer_id, query, response_text)

    # Force human proof fields from server-side identity — client cannot spoof
    # confirmed_by to someone else's account when a valid session is present.
    body = {
        "session_id": data.get("session_id") or human_id,
        "query": query or "(chat confirm)",
        "response": response_text or "(empty)",
        "rating": int(rating),
        "comments": data.get("comments"),
        "action": action,
        "actor_kind": "human",
        "channel": channel,
        "confirmed_by": human_id,
        "human_attestation": human_attestation,
        "memory_id": answer_id,
        "answer_id": answer_id,
    }
    if data.get("corrected_text"):
        body["action"] = "correct"
        # Runtime reads CORRECT: prefix on comments for correction text
        body["comments"] = f"CORRECT: {data.get('corrected_text')}"

    try:
        r = requests.post(
            f"{SYNTHESUS_RUNTIME_URL}/api/v1/feedback",
            json=body,
            headers=_runtime_api_headers(),
            timeout=30,
        )
        try:
            payload = r.json()
        except Exception:
            payload = {"status": "error", "message": r.text[:500]}
        if isinstance(payload, dict) and stage_info is not None:
            payload["draft_stage"] = stage_info
        return (json.dumps(payload), r.status_code, {"Content-Type": "application/json"})
    except Exception as e:
        print(f"[feedback] runtime unavailable ({e})")
        return jsonify({
            "status": "error",
            "message": f"runtime unavailable: {e}",
            "verification_upgrade": {"upgraded": False, "reason": "runtime_unavailable"},
            "draft_stage": stage_info,
            "status_flag": "DEGRADED",
        }), 503


# ===================================================================
# AGNOSTIC EXPANSION DRIVE — ground Synthesus on the user's own sources
# (GitHub, synced cloud folders). Thin proxy to the runtime, which owns the
# per-user index. Fetch is from the user's own source; indexing stays local.
# ===================================================================
# Dual-mount /api/drive/* and /api/v1/drive/* — desktop JS uses both paths.
@app.route('/api/drive/sources', methods=['GET'])
@app.route('/api/v1/drive/sources', methods=['GET'])
def drive_sources():
    """List ingestable source types (live vs planned) for the drive UI."""
    try:
        r = requests.get(
            f"{SYNTHESUS_RUNTIME_URL}/api/v1/drive/sources",
            headers={"X-API-Key": _runtime_api_key()},
            timeout=15,
        )
        r.raise_for_status()
        return jsonify(r.json())
    except Exception as e:
        print(f"[drive] sources unavailable ({e})")
        return jsonify({"sources": [], "error": "runtime unavailable"}), 503

@app.route('/api/drive/remotes', methods=['GET'])
@app.route('/api/v1/drive/remotes', methods=['GET'])
def drive_remotes():
    """Which rclone cloud remotes are actually configured (for the creator)."""
    try:
        r = requests.get(
            f"{SYNTHESUS_RUNTIME_URL}/api/v1/drive/remotes",
            headers={"X-API-Key": _runtime_api_key()},
            timeout=20,
        )
        r.raise_for_status()
        return jsonify(r.json())
    except Exception as e:
        print(f"[drive] remotes unavailable ({e})")
        return jsonify({"rclone_available": False, "remotes": [], "error": "runtime unavailable"}), 503

@app.route('/api/drive/ingest', methods=['POST'])
@app.route('/api/v1/drive/ingest', methods=['POST'])
def drive_ingest():
    """Ingest a user source into their grounding index (via the runtime)."""
    data = request.get_json(silent=True) or {}
    try:
        r = requests.post(
            f"{SYNTHESUS_RUNTIME_URL}/api/v1/drive/ingest",
            json=data,
            headers={"X-API-Key": _runtime_api_key()},
            timeout=600,
        )
        # Pass the runtime's status + body straight through — loud on errors,
        # never fake a success.
        return (r.text, r.status_code, {"Content-Type": "application/json"})
    except Exception as e:
        print(f"[drive] ingest failed ({e})")
        return jsonify({"status": "error", "message": f"runtime unavailable: {e}"}), 503

@app.route('/api/drive/progress/<job_id>', methods=['GET'])
@app.route('/api/v1/drive/progress/<job_id>', methods=['GET'])
def drive_progress(job_id):
    try:
        r = requests.get(
            f"{SYNTHESUS_RUNTIME_URL}/api/v1/drive/progress/{job_id}",
            headers={"X-API-Key": _runtime_api_key()},
            timeout=15,
        )
        return (r.text, r.status_code, {"Content-Type": "application/json"})
    except Exception as e:
        print(f"[drive] progress unavailable ({e})")
        return jsonify({"status": "error", "message": f"runtime unavailable: {e}"}), 503

@app.route('/api/drive/preview', methods=['POST'])
@app.route('/api/v1/drive/preview', methods=['POST'])
def drive_preview():
    data = request.get_json(silent=True) or {}
    try:
        r = requests.post(
            f"{SYNTHESUS_RUNTIME_URL}/api/v1/drive/preview",
            json=data,
            headers={"X-API-Key": _runtime_api_key()},
            timeout=30,
        )
        return (r.text, r.status_code, {"Content-Type": "application/json"})
    except Exception as e:
        print(f"[drive] preview unavailable ({e})")
        return jsonify({"chunks": [], "error": f"runtime unavailable: {e}"}), 503

@app.route('/api/drive/rclone/status', methods=['GET'])
@app.route('/api/v1/drive/rclone/status', methods=['GET'])
def drive_rclone_status():
    try:
        r = requests.get(
            f"{SYNTHESUS_RUNTIME_URL}/api/v1/drive/rclone/status",
            headers={"X-API-Key": _runtime_api_key()},
            timeout=15,
        )
        return (r.text, r.status_code, {"Content-Type": "application/json"})
    except Exception as e:
        print(f"[drive] rclone status unavailable ({e})")
        return jsonify({"installed": False, "remotes": [], "error": f"runtime unavailable: {e}"}), 503


@app.route('/api/drive/paste', methods=['POST'])
@app.route('/api/v1/drive/paste', methods=['POST'])
def drive_paste_local():
    """Write pasted text to a local folder and ingest it (no cloud).

    Body: {text, name?}. Saves under ~/.synthesus/local_paste/ then folder-ingests.
    """
    data = request.get_json(silent=True) or {}
    text = (data.get("text") or "").strip()
    if not text:
        return jsonify({"ok": False, "error": "text_required", "message": "text is required"}), 400
    if len(text) > 200_000:
        return jsonify({"ok": False, "error": "too_long", "message": "max 200k chars"}), 400
    name = (data.get("name") or data.get("namespace") or "local-paste").strip() or "local-paste"
    paste_root = os.path.join(os.path.expanduser("~"), ".synthesus", "local_paste")
    try:
        os.makedirs(paste_root, exist_ok=True)
        fname = os.path.join(paste_root, f"paste_{int(time.time())}.txt")
        with open(fname, "w", encoding="utf-8") as fh:
            fh.write(text)
    except Exception as e:
        return jsonify({"ok": False, "error": "write_failed", "message": str(e)}), 500
    # Forward as folder ingest to runtime
    try:
        r = requests.post(
            f"{SYNTHESUS_RUNTIME_URL}/api/v1/drive/ingest",
            json={
                "connector": "folder",
                "target": paste_root,
                "namespace": name,
                "async": False,
            },
            headers={"X-API-Key": _runtime_api_key()},
            timeout=120,
        )
        try:
            payload = r.json()
        except Exception:
            payload = {"ok": False, "error": "bad_runtime_body", "message": (r.text or "")[:400]}
        if isinstance(payload, dict):
            payload.setdefault("local_file", fname)
            payload.setdefault("namespace", name)
        return (json.dumps(payload), r.status_code, {"Content-Type": "application/json"})
    except Exception as e:
        return jsonify({
            "ok": False,
            "error": "runtime_unavailable",
            "message": str(e),
            "local_file": fname,
            "note": "Text saved locally; runtime ingest failed",
        }), 503

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

@app.route('/api/settings/llm', methods=['GET'])
def get_llm_settings():
    try:
        r = requests.get(
            f"{SYNTHESUS_RUNTIME_URL}/api/v1/settings/llm",
            headers={"X-API-Key": _runtime_api_key()},
            timeout=5,
        )
        return (r.text, r.status_code, {"Content-Type": "application/json"})
    except Exception as e:
        return jsonify({"provider": "ollama", "model": "", "key_set": False, "error": str(e)}), 503

@app.route('/api/settings/llm', methods=['POST'])
def post_llm_settings():
    # Pro gate applies ONLY to cloud backends. Local backends (Ollama, LM Studio) are
    # free because they use an explicitly configured local inference endpoint.
    data = request.json or {}
    provider = data.get("provider", "ollama")
    LOCAL_BACKENDS = ("ollama", "lmstudio")
    if provider not in LOCAL_BACKENDS and not pro.is_pro():
        return jsonify({"status": "error", "message": "Cloud LLM backends require Synthesus Pro. Local backends (Ollama, LM Studio) are free."}), 403
        
    try:
        r = requests.post(
            f"{SYNTHESUS_RUNTIME_URL}/api/v1/settings/llm",
            json=data,
            headers={"X-API-Key": _runtime_api_key()},
            timeout=5,
        )
        return (r.text, r.status_code, {"Content-Type": "application/json"})
    except Exception as e:
        return jsonify({"status": "error", "message": f"runtime unavailable: {e}"}), 503

@app.route('/api/conversations/<sid>/export', methods=['GET'])
def export_conversation(sid):
    fmt = request.args.get("format", "md")
    try:
        r = requests.get(
            f"{SYNTHESUS_RUNTIME_URL}/api/v1/conversations/{sid}/export?format={fmt}",
            headers={"X-API-Key": _runtime_api_key()},
            timeout=5,
        )
        return (r.text, r.status_code, {"Content-Type": r.headers.get("Content-Type", "text/markdown")})
    except Exception as e:
        return f"export unavailable: {e}", 503

@app.route('/api/pro/packs', methods=['GET'])
def pro_packs():
    try:
        r = requests.get(
            f"{SYNTHESUS_RUNTIME_URL}/api/v1/pro/packs",
            headers={"X-API-Key": _runtime_api_key()},
            timeout=5,
        )
        return (r.text, r.status_code, {"Content-Type": "application/json"})
    except Exception as e:
        return jsonify({"available": [], "installed": [], "error": str(e)}), 503

@app.route('/api/pro/packs/install', methods=['POST'])
def install_pro_pack():
    if not pro.is_pro():
        return jsonify({"status": "error", "message": "Requires Synthesus Pro."}), 403
    data = request.json or {}
    try:
        r = requests.post(
            f"{SYNTHESUS_RUNTIME_URL}/api/v1/pro/packs/install",
            json=data,
            headers={"X-API-Key": _runtime_api_key()},
            timeout=60,
        )
        return (r.text, r.status_code, {"Content-Type": "application/json"})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 503

@app.route('/api/foreman/queue', methods=['GET'])
def get_foreman_queue():
    try:
        r = requests.get(
            f"{SYNTHESUS_RUNTIME_URL}/api/v1/foreman/queue",
            headers={"X-API-Key": _runtime_api_key()},
            timeout=5,
        )
        return (r.text, r.status_code, {"Content-Type": "application/json"})
    except Exception as e:
        return jsonify({"queue": [], "error": str(e)}), 503

@app.route('/api/foreman/approve', methods=['POST'])
def approve_foreman_step():
    try:
        r = requests.post(
            f"{SYNTHESUS_RUNTIME_URL}/api/v1/foreman/approve",
            json=request.json or {},
            headers={"X-API-Key": _runtime_api_key()},
            timeout=5,
        )
        return (r.text, r.status_code, {"Content-Type": "application/json"})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 503

@app.route('/api/foreman/deny', methods=['POST'])
def deny_foreman_step():
    try:
        r = requests.post(
            f"{SYNTHESUS_RUNTIME_URL}/api/v1/foreman/deny",
            json=request.json or {},
            headers={"X-API-Key": _runtime_api_key()},
            timeout=5,
        )
        return (r.text, r.status_code, {"Content-Type": "application/json"})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 503

@app.route('/api/ide/files', methods=['GET'])
def list_files():
    """List files under the user's home directory (depth-limited, no hidden).

    Each node carries a `path` relative to home so the UI can open real content
    via GET /api/ide/read?path=...
    """
    base_dir = os.path.expanduser('~')

    def build_tree(dir_path, depth=0):
        if depth > 2:
            return []
        tree = []
        try:
            entries = sorted(os.listdir(dir_path), key=lambda s: s.lower())
        except Exception:
            return []
        for item in entries:
            if item.startswith('.'):
                continue
            full_path = os.path.join(dir_path, item)
            rel = os.path.relpath(full_path, base_dir)
            try:
                if os.path.isdir(full_path):
                    tree.append({
                        "name": item,
                        "type": "dir",
                        "path": rel,
                        "children": build_tree(full_path, depth + 1),
                    })
                else:
                    tree.append({"name": item, "type": "file", "path": rel})
            except Exception:
                continue
        return tree

    return jsonify([{
        "name": "Home",
        "type": "dir",
        "path": "",
        "children": build_tree(base_dir),
    }])


@app.route('/api/ide/read', methods=['GET'])
def read_ide_file():
    """Read a text file under the user's home (path-safe). Never escapes home."""
    rel = (request.args.get("path") or "").strip().lstrip("/")
    if not rel or ".." in rel.split(os.sep):
        return jsonify({"ok": False, "error": "path_required"}), 400
    base = os.path.realpath(os.path.expanduser("~"))
    target = os.path.realpath(os.path.join(base, rel))
    # Containment: must stay inside home
    if target != base and not (target.startswith(base + os.sep)):
        return jsonify({"ok": False, "error": "path_escape"}), 403
    if not os.path.isfile(target):
        return jsonify({"ok": False, "error": "not_found", "path": rel}), 404
    try:
        size = os.path.getsize(target)
    except OSError as e:
        return jsonify({"ok": False, "error": str(e)}), 500
    if size > 512_000:
        return jsonify({
            "ok": False,
            "error": "too_large",
            "bytes": size,
            "message": "File > 512KB — open in an external editor",
        }), 413
    # Binary sniff — refuse obvious non-text
    try:
        with open(target, "rb") as fh:
            head = fh.read(512)
        if b"\x00" in head:
            return jsonify({
                "ok": False,
                "error": "binary",
                "message": "Binary file — preview not available",
                "bytes": size,
            }), 415
        text = open(target, "r", encoding="utf-8", errors="replace").read()
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500
    return jsonify({
        "ok": True,
        "path": rel,
        "name": os.path.basename(target),
        "bytes": size,
        "content": text,
    })

@app.route('/api/terminal/run', methods=['POST'])
def run_command():
    """Reject the removed legacy shell-command transport.

    Interactive terminal work is available only through the authenticated
    synthesusd capability and its owner-only Unix-socket PTY backend. Keeping a
    loud tombstone prevents old clients from silently falling back to a less
    trusted path.
    """
    return jsonify({
        "status": "disabled",
        "error": "legacy_terminal_transport_removed",
        "message": "Use the authenticated terminal WebSocket session.",
    }), 410

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
    health = f"{SYNTHESUS_RUNTIME_UPSTREAM_URL}/api/v1/health"
    key = _runtime_api_key()

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
        argv = shlex.split(cmd)
        if not argv:
            raise ValueError("SYNTHESUS_RUNTIME_CMD is empty")
        _track_child(
            subprocess.Popen(
                argv,
                stdout=open(runtime_log, "a"),
                stderr=subprocess.STDOUT,
            )
        )
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
    app.run(host='127.0.0.1', port=SHELL_PORT, debug=False, use_reloader=False)

def ensure_terminal():
    """Start the private PTY backend on its user-only Unix socket."""
    import httpx

    try:
        transport = httpx.HTTPTransport(uds=SYNTHESUS_TERMINAL_SOCKET)
        with httpx.Client(
            transport=transport,
            base_url="http://synthesus-terminal",
            timeout=1,
        ) as client:
            if client.get("/api/terminal/health").status_code == 200:
                print(f"[terminal] PTY backend already up on {SYNTHESUS_TERMINAL_SOCKET}")
                return
    except Exception:
        pass
    server = os.path.join(os.path.dirname(os.path.abspath(__file__)), "terminal_server.py")
    if not os.path.exists(server):
        print(f"[terminal] terminal_server.py not found at {server}; terminal disabled")
        return
    try:
        log = os.path.expanduser("~/.synthesus/terminal_server.log")
        os.makedirs(os.path.dirname(log), exist_ok=True)
        env = os.environ.copy()
        env["SYNTHESUS_TERMINAL_SOCKET"] = SYNTHESUS_TERMINAL_SOCKET
        _track_child(
            subprocess.Popen(
                [sys.executable, server],
                stdout=open(log, "a"),
                stderr=subprocess.STDOUT,
                env=env,
            )
        )
        print(f"[terminal] launched PTY backend on {SYNTHESUS_TERMINAL_SOCKET}")
    except Exception as e:
        print(f"[terminal] failed to launch PTY backend: {e}")


def ensure_controller():
    """Start authenticated synthesusd and wait for its loopback readiness endpoint."""
    import urllib.error
    import urllib.request

    health = f"{SYNTHESUS_CONTROLLER_URL}/ready"
    key = _runtime_api_key()

    def _up():
        try:
            req = urllib.request.Request(health, headers={"X-API-Key": key})
            with urllib.request.urlopen(req, timeout=2) as resp:
                if resp.status != 200:
                    return False
                payload = json.loads(resp.read().decode("utf-8"))
                return payload.get("session_id") == SYNTHESUS_CONTROLLER_SESSION_ID
        except (OSError, urllib.error.URLError):
            return False

    if _up():
        print(f"[controller] synthesusd already up on 127.0.0.1:{CONTROLLER_PORT}")
        return True

    daemon = os.path.join(os.path.dirname(os.path.abspath(__file__)), "synthesusd.py")
    if not os.path.exists(daemon):
        print(f"[controller] synthesusd.py not found at {daemon}; desktop cannot start")
        return False

    controller_log = os.path.expanduser("~/.synthesus/synthesusd.log")
    os.makedirs(os.path.dirname(controller_log), exist_ok=True)
    env = os.environ.copy()
    env.update({
        "SYNTHESUS_CONTROLLER_PORT": str(CONTROLLER_PORT),
        "SYNTHESUS_CONTROLLER_PARENT_PID": str(os.getpid()),
        "SYNTHESUS_CONTROLLER_SESSION_ID": SYNTHESUS_CONTROLLER_SESSION_ID,
        "SYNTHESUS_RUNTIME_UPSTREAM_URL": SYNTHESUS_RUNTIME_UPSTREAM_URL,
        "SYNTHESUS_TERMINAL_SOCKET": SYNTHESUS_TERMINAL_SOCKET,
        "SYNTHESUS_TERMINAL_TOKEN": SYNTHESUS_TERMINAL_TOKEN,
        "SYNTHESUS_SHELL_PORT": str(SHELL_PORT),
        "SYNTHESUS_CONTROLLER_ALLOWED_ORIGINS": ",".join(CONTROLLER_ORIGINS),
    })
    try:
        _track_child(
            subprocess.Popen(
                [sys.executable, daemon],
                stdout=open(controller_log, "a"),
                stderr=subprocess.STDOUT,
                env=env,
            )
        )
    except Exception as e:
        print(f"[controller] failed to launch synthesusd: {e}")
        return False

    for _ in range(60):
        if _up():
            print(
                f"[controller] synthesusd READY on 127.0.0.1:{CONTROLLER_PORT}; "
                "runtime and terminal traffic are authenticated"
            )
            return True
        time.sleep(0.25)
    print("[controller] synthesusd failed its authenticated startup check")
    return False


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

    # Bring up private services, then place authenticated synthesusd in front of them.
    threading.Thread(target=ensure_runtime, daemon=True).start()
    threading.Thread(target=ensure_terminal, daemon=True).start()
    if not ensure_controller():
        raise SystemExit("Synthesus refuses to start without authenticated synthesusd")

    if headless:
        # Serve the OS in the foreground so the process stays alive; the user
        # points a browser at it. Nothing is exposed beyond localhost.
        print("[*] HEADLESS — open Synthesus in your browser:")
        print(f"[*]     http://localhost:{SHELL_PORT}")
        print(
            "[*] Remote access: SSH-tunnel the documented shell/controller ports; "
            "the PTY itself has no TCP listener."
        )
        start_flask()  # blocking — keeps the process running
    else:
        threading.Thread(target=start_flask, daemon=True).start()
        # Don't open the window until the shell actually answers — otherwise the
        # webview loads a "cannot reach server" page once and sits on it.
        import urllib.request
        for _ in range(30):
            try:
                with urllib.request.urlopen(
                    f"http://127.0.0.1:{SHELL_PORT}/",
                    timeout=1,
                ) as resp:
                    if resp.status == 200:
                        break
            except Exception:
                time.sleep(0.5)

        print("[*] Hooking into Host OS via PyWebView (Frameless Mode)...")
        webview.create_window(
            'Synthesus Planetary OS',
            f'http://127.0.0.1:{SHELL_PORT}',
            frameless=True,
            fullscreen=True,
            text_select=True,
        )
        webview.start()
