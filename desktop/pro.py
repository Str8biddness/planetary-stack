"""Synthesus Pro — license activation + premium unlock.

Open plumbing; the *value* it unlocks (the premium persona genomes) is closed and
delivered only on purchase, so this code being visible costs nothing. Flow:

    buy on Gumroad -> get a license key + the Pro pack -> paste key in the app
    -> we verify the key with Gumroad -> install the pack -> personas light up.

The real gate is *delivery*: you can't install a pack you were never given. The key
check adds purchase-binding and (for the monthly membership) subscription status.

Config via env (filled in once the Gumroad product exists):
    PRO_PRODUCT_ID     Gumroad product id (for license verification)
    PRO_PRODUCT_URL    checkout link (the "Get Pro" button target)
    PRO_PACK_PATH      optional: local path to the Pro pack zip to install on activate
Path overrides (mostly for testing/installs):
    SYNTHESUS_HOME     install home (default ~/.local/share/synthesus)
    PRO_STATE_PATH     where activation state is stored
    PRO_CHARACTERS_DIR where persona dirs get installed
"""
from __future__ import annotations
import os, sys, json, time, zipfile

try:
    import requests
except Exception:  # requests always present in the app venv; keep import soft for tooling
    requests = None

GUMROAD_VERIFY = "https://api.gumroad.com/v2/licenses/verify"

# The live Synthesus Pro product (public values — safe to ship as defaults; env overrides).
DEFAULT_PRODUCT_ID = "W9PRkcebyXm_KftDdlU6vA"
DEFAULT_PRODUCT_URL = "https://dakinelle.gumroad.com/l/xkvtl"


# --- paths ---------------------------------------------------------------
def _home() -> str:
    return os.environ.get("SYNTHESUS_HOME", os.path.expanduser("~/.local/share/synthesus"))

def _state_path() -> str:
    return os.environ.get("PRO_STATE_PATH", os.path.join(_home(), "pro.json"))

def _characters_dir() -> str:
    override = os.environ.get("PRO_CHARACTERS_DIR")
    if override:
        return override
    cand = os.path.join(_home(), "runtime", "packages", "characters")
    if os.path.isdir(cand):
        return cand
    dev = os.path.expanduser("~/synthesus-ultra-c101/packages/characters")
    return dev if os.path.isdir(dev) else cand


# --- state ---------------------------------------------------------------
def _load_state() -> dict:
    try:
        with open(_state_path()) as f:
            return json.load(f)
    except Exception:
        return {}

def _save_state(st: dict) -> None:
    p = _state_path()
    os.makedirs(os.path.dirname(p), exist_ok=True)
    tmp = p + ".tmp"
    with open(tmp, "w") as f:
        json.dump(st, f, indent=2)
    os.replace(tmp, p)
    try:
        os.chmod(p, 0o600)  # holds the license key — keep it private
    except Exception:
        pass


# --- Gumroad license verification ---------------------------------------
def verify_license(key: str, product_id: str | None = None) -> dict:
    """Verify a license key against Gumroad. Returns ok/active + subscription info."""
    key = (key or "").strip()
    if not key:
        return {"ok": False, "reason": "empty", "message": "Enter your license key."}
    product_id = (product_id or os.environ.get("PRO_PRODUCT_ID") or DEFAULT_PRODUCT_ID).strip()
    if not product_id:
        return {"ok": False, "reason": "not_configured",
                "message": "Pro isn't configured yet (no product id set)."}
    if requests is None:
        return {"ok": False, "reason": "no_requests", "message": "HTTP client unavailable."}
    try:
        r = requests.post(GUMROAD_VERIFY, timeout=15, data={
            "product_id": product_id, "license_key": key, "increment_uses_count": "false"})
        data = r.json()
    except Exception as e:
        return {"ok": False, "reason": "network", "message": f"Could not reach Gumroad: {e}"}
    if not data.get("success"):
        return {"ok": False, "reason": "invalid",
                "message": data.get("message", "That license key isn't valid.")}
    p = data.get("purchase", {}) or {}
    if p.get("refunded") or p.get("chargebacked") or p.get("disputed"):
        return {"ok": False, "reason": "refunded", "message": "This purchase was refunded."}
    is_sub = bool(p.get("subscription_id"))
    sub_dead = any(p.get(k) for k in
                   ("subscription_cancelled_at", "subscription_ended_at", "subscription_failed_at"))
    active = (not is_sub) or (not sub_dead)   # one-time = always active; sub = active unless dead
    return {"ok": True, "valid": True, "subscription": is_sub, "active": active,
            "email": p.get("email"), "raw": p}


# --- pack install --------------------------------------------------------
def install_pack(zip_path: str) -> list[str]:
    """Unzip the premium persona pack into the characters dir. Returns persona names."""
    if not zip_path or not os.path.exists(zip_path):
        raise FileNotFoundError(f"Pro pack not found: {zip_path}")
    cdir = _characters_dir()
    os.makedirs(cdir, exist_ok=True)
    with zipfile.ZipFile(zip_path) as z:
        for m in z.namelist():                      # refuse path traversal
            if m.startswith("/") or ".." in m.replace("\\", "/").split("/"):
                raise ValueError(f"unsafe path in pack: {m}")
        z.extractall(cdir)
        tops = sorted({m.split("/")[0] for m in z.namelist() if "/" in m and m.split("/")[0]})
    return tops


# --- public API used by the shell ---------------------------------------
def status() -> dict:
    st = _load_state()
    key = st.get("key", "")
    masked = (key[:4] + "…" + key[-4:]) if len(key) > 8 else ("set" if key else "")
    return {
        "pro": bool(st.get("pro")),
        "subscription": bool(st.get("subscription")),
        "installed": st.get("installed", []),
        "key_masked": masked,
        "product_url": os.environ.get("PRO_PRODUCT_URL") or DEFAULT_PRODUCT_URL,
        "configured": bool((os.environ.get("PRO_PRODUCT_ID") or DEFAULT_PRODUCT_ID).strip()),
    }

def _find_pack() -> str:
    """Locate the Pro pack zip: an explicit env path, the Gumroad download in the
    usual spots, or the local build location. Returns '' if not found."""
    import glob
    dirs = [os.path.expanduser("~/Downloads"), os.path.expanduser("~"),
            os.path.expanduser("~/synthesus-pro"), os.path.join(_home(), "pro")]
    for d in dirs:
        for pat in ("synthesus-pro*.zip", "*pro*personas*.zip"):
            hits = sorted(glob.glob(os.path.join(d, pat)))
            if hits:
                return hits[-1]
    return ""

def activate(key: str, pack_path: str | None = None) -> dict:
    v = verify_license(key)
    if not v.get("ok"):
        return {"pro": False, "error": v.get("message", "Invalid license."), "reason": v.get("reason")}
    if not v.get("active"):
        return {"pro": False, "error": "This subscription is no longer active.", "reason": "inactive"}
    installed = _load_state().get("installed", [])
    pack = pack_path or os.environ.get("PRO_PACK_PATH", "").strip() or _find_pack()
    if pack and os.path.exists(pack):
        installed = install_pack(pack)
    _save_state({"pro": True, "key": key.strip(), "subscription": v.get("subscription"),
                 "email": v.get("email"), "installed": installed, "activated_at": int(time.time())})
    result = status()
    if not installed:
        result["note"] = ("License valid — but the Pro pack file wasn't found. Download it "
                          "from your Gumroad receipt, then activate again.")
    return result

def deactivate() -> dict:
    _save_state({})
    return status()


# --- CLI (for testing the unlock mechanism) ------------------------------
if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "status"
    if cmd == "status":
        print(json.dumps(status(), indent=2))
    elif cmd == "install" and len(sys.argv) > 2:
        print("installed:", install_pack(sys.argv[2]))
    elif cmd == "activate" and len(sys.argv) > 2:
        print(json.dumps(activate(sys.argv[2], sys.argv[3] if len(sys.argv) > 3 else None), indent=2))
    elif cmd == "verify" and len(sys.argv) > 2:
        print(json.dumps(verify_license(sys.argv[2]), indent=2))
    elif cmd == "deactivate":
        print(json.dumps(deactivate(), indent=2))
    else:
        print("usage: pro.py [status|install <zip>|activate <key> [pack]|verify <key>|deactivate]")
