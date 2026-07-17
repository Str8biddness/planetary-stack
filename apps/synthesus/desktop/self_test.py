#!/usr/bin/env python3
"""Synthesus new-user-journey self-test (the automated "last check").

Drives the exact HTTP/WS endpoints the desktop UI calls, as a brand-new user
would: register -> login -> ingest a folder -> ask a grounded question ->
ask a general question -> run a terminal command. Asserts real behavior at each
step (e.g. the grounded answer must contain the planted fact), captures a visual,
and prints a PASS/FAIL report. Run it before every release.

    python3 self_test.py

Covers the FUNCTIONAL journey against the running stack (shell :8081,
authenticated synthesusd :5011, private PTY Unix socket, runtime :5010).
Full click-through-the-UI screenshotting is the CDP v2.
"""
from __future__ import annotations
import asyncio, json, os, subprocess, sys, tempfile, time, urllib.request

SHELL = "http://127.0.0.1:8081"
RESULTS = []

def _post(path, body):
    req = urllib.request.Request(SHELL + path, data=json.dumps(body).encode(),
                                 headers={"Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(req, timeout=95) as r:
        return r.status, json.loads(r.read().decode())

def check(name, ok, detail=""):
    RESULTS.append((name, ok, detail))
    print(f"  [{'PASS' if ok else 'FAIL'}] {name}" + (f" — {detail}" if detail else ""))
    return ok

def main():
    print("Synthesus self-test — new-user journey\n")
    auth_token = None

    # 0. stack up?
    try:
        urllib.request.urlopen(SHELL + "/", timeout=5)
        check("shell reachable (:8081)", True)
    except Exception as e:
        check("shell reachable (:8081)", False, str(e)); return _report()

    email = f"selftest_{int(time.time())}@synthesus.local"
    pw = "S3lftest-" + os.urandom(3).hex()

    # 1. register
    try:
        s, d = _post("/api/auth/register", {"email": email, "password": pw})
        check("register a new account", d.get("status") == "success", d.get("message", ""))
    except Exception as e:
        check("register a new account", False, str(e))

    # 2. login
    try:
        s, d = _post("/api/auth/login", {"email": email, "password": pw})
        check("log in", d.get("status") == "success", d.get("message", ""))
        auth_token = d.get("token")
    except Exception as e:
        check("log in", False, str(e))

    # 3. ingest a folder with a planted, unique fact
    corpus = tempfile.mkdtemp(prefix="syn_selftest_")
    with open(os.path.join(corpus, "aurora.md"), "w") as f:
        f.write("Aurora API Notes\nThe Aurora API rate limit is 4200 requests per minute per key.\n")
    try:
        s, d = _post("/api/drive/ingest", {"connector": "folder", "target": corpus, "namespace": "selftest"})
        check("ingest a folder into the drive", d.get("status") == "ok",
              f"{d.get('chunks_added')} chunks from {d.get('files_ingested')} files")
    except Exception as e:
        check("ingest a folder into the drive", False, str(e))

    # 4. grounded chat — the answer MUST contain the planted fact
    try:
        s, d = _post("/api/chat", {"message": "What is the Aurora API rate limit?"})
        ans = (d.get("response") or d.get("reply") or json.dumps(d))[:300]
        check("grounded chat returns the planted fact (4200)", "4200" in ans, ans)
    except Exception as e:
        check("grounded chat returns the planted fact (4200)", False, str(e))

    # 5. general chat — a real, helpful answer (non-empty, no leak/error markers)
    try:
        s, d = _post("/api/chat", {"message": "In one sentence, what are you?"})
        ans = (d.get("response") or d.get("reply") or "").strip()
        leak = any(m in ans.lower() for m in ("[fallback]", "traceback", "response_template", "error:"))
        check("general chat answers helpfully", len(ans) > 20 and not leak, ans[:200])
    except Exception as e:
        check("general chat answers helpfully", False, str(e))

    # 6. terminal PTY round-trip
    try:
        import websockets  # type: ignore
        ipc_request = urllib.request.Request(
            SHELL + "/api/ipc/session",
            headers={"Authorization": f"Bearer {auth_token or ''}"},
        )
        with urllib.request.urlopen(ipc_request, timeout=5) as response:
            ipc = json.loads(response.read().decode())
        controller_host = f"127.0.0.1:{ipc['controller_port']}"
        terminal_uri = f"ws://{controller_host}{ipc['terminal_ws_path']}/selftest"
        async def pty():
            async with websockets.connect(
                terminal_uri,
                origin=SHELL,
                subprotocols=["synthesus-terminal", ipc["terminal_token"]],
            ) as ws:
                await ws.send("echo SELFTEST_PTY_OK\n")
                buf = ""
                for _ in range(8):
                    buf += await asyncio.wait_for(ws.recv(), timeout=2)
                    if "SELFTEST_PTY_OK" in buf: break
                return "SELFTEST_PTY_OK" in buf
        check("terminal PTY runs a real command", asyncio.run(pty()))
    except Exception as e:
        check("terminal PTY runs a real command", False, str(e))

    # 7. visual baseline (login screen)
    shot = os.path.join(tempfile.gettempdir(), "synthesus_selftest_login.png")
    try:
        subprocess.run(["chromium", "--headless=new", "--no-sandbox", "--disable-gpu",
                        "--window-size=1600,900", f"--screenshot={shot}", SHELL + "/"],
                       timeout=30, capture_output=True)
        check("captured a visual (login screen)", os.path.exists(shot) and os.path.getsize(shot) > 5000, shot)
    except Exception as e:
        check("captured a visual", False, str(e))

    return _report()

def _report():
    passed = sum(1 for _, ok, _ in RESULTS if ok)
    total = len(RESULTS)
    print(f"\n{'='*50}\n  {passed}/{total} PASS")
    verdict = "JOURNEY OK" if passed == total else "ISSUES — see FAILs above"
    print(f"  VERDICT: {verdict}\n{'='*50}")
    sys.exit(0 if passed == total else 1)

if __name__ == "__main__":
    main()
