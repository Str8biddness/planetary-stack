#!/usr/bin/env python3
"""
Synthesus GOD-MODE TERMINAL BACKEND
===================================

A REAL localhost-only PTY server. Not a mock, not an echo shim: every session
forks a genuine login `bash` on a Unix pseudo-terminal (stdlib `pty`/`os.openpty`)
and streams it byte-for-byte over a WebSocket to the xterm.js frontend.

Protocol (matched exactly to script.js in the planetary-desktop frontend):
  * WS   ws://127.0.0.1:8082/ws/pty/user/{session_id}
         - text/bytes from client  -> written to the pty stdin (keystrokes)
         - bytes from the pty       -> sent to the client as TEXT frames
           (the frontend calls term.write(e.data) with no binaryType set, so
            binary frames would arrive as Blobs it can't render -> we send text)
  * POST http://127.0.0.1:8082/api/terminal/resize
         - JSON {session_id, cols, rows} -> TIOCSWINSZ on that session's pty

Bind: 127.0.0.1 ONLY. This is a real root-capable shell; it must never be
exposed on 0.0.0.0.

Law: DEGRADE LOUDLY. Failures are logged to stderr and surfaced to the client,
never silently swallowed.
"""

import asyncio
import fcntl
import json
import os
import pty
import signal
import struct
import sys
import termios
import logging
from pathlib import Path

import uvicorn
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import JSONResponse
from pydantic import BaseModel

logging.basicConfig(
    level=logging.INFO,
    format="[terminal_server] %(asctime)s %(levelname)s %(message)s",
    stream=sys.stderr,
)
log = logging.getLogger("terminal_server")

HOST = "127.0.0.1"   # NEVER 0.0.0.0 — this is a real shell.
PORT = 8082

app = FastAPI(title="Synthesus God-Mode Terminal Backend")


def terminal_root() -> Path:
    """Return the validated working directory for every new terminal."""
    configured = os.environ.get("SYNTHESUS_TERMINAL_ROOT")
    if configured:
        root = Path(configured).expanduser().resolve()
    else:
        source_path = Path(__file__).resolve()
        root = next(
            (parent for parent in source_path.parents if (parent / ".git").exists()),
            Path(os.environ.get("SYNTHESUS_HOME", Path.home())).expanduser().resolve(),
        )

    if not root.is_dir():
        raise RuntimeError(f"terminal root is not a directory: {root}")
    return root


class PtySession:
    """One real bash on one real pty."""

    def __init__(self, session_id: str):
        self.session_id = session_id
        self.master_fd: int | None = None
        self.pid: int | None = None
        self.cols = 80
        self.rows = 24
        self.cwd: Path | None = None

    def spawn(self):
        working_directory = terminal_root()
        # pty.fork() gives us a controlling terminal in the child and a master
        # fd in the parent — a genuine pseudo-terminal, not a pipe.
        pid, master_fd = pty.fork()
        if pid == 0:
            # ---- CHILD ----
            env = os.environ.copy()
            env["TERM"] = "xterm-256color"
            env["SYNTHESUS_PTY"] = "1"
            env["PWD"] = str(working_directory)
            shell = os.environ.get("SHELL", "/bin/bash")
            try:
                os.chdir(working_directory)
                # Login + interactive shell so profiles/prompt load like a real terminal.
                os.execvpe(shell, [shell, "-l", "-i"], env)
            except Exception:
                os.execvpe("/bin/sh", ["/bin/sh", "-i"], env)
            os._exit(127)  # unreachable
        # ---- PARENT ----
        self.pid = pid
        self.master_fd = master_fd
        self.cwd = working_directory
        # Non-blocking so the asyncio reader never stalls the event loop.
        flags = fcntl.fcntl(master_fd, fcntl.F_GETFL)
        fcntl.fcntl(master_fd, fcntl.F_SETFL, flags | os.O_NONBLOCK)
        self.set_winsize(self.rows, self.cols)
        log.info(
            "session %s: spawned %s pid=%d fd=%d cwd=%s",
            self.session_id,
            os.environ.get("SHELL", "/bin/bash"),
            pid,
            master_fd,
            working_directory,
        )

    def set_winsize(self, rows: int, cols: int):
        if self.master_fd is None:
            return
        self.rows, self.cols = rows, cols
        winsize = struct.pack("HHHH", rows, cols, 0, 0)
        fcntl.ioctl(self.master_fd, termios.TIOCSWINSZ, winsize)

    def close(self):
        if self.pid is not None:
            try:
                os.kill(self.pid, signal.SIGKILL)
                os.waitpid(self.pid, 0)
            except Exception:
                pass
        if self.master_fd is not None:
            try:
                os.close(self.master_fd)
            except Exception:
                pass
        log.info("session %s: closed pid=%s", self.session_id, self.pid)
        self.master_fd = None
        self.pid = None


# session_id -> PtySession (so /resize can find the live pty for a socket)
SESSIONS: dict[str, PtySession] = {}


@app.websocket("/ws/pty/user/{session_id}")
async def pty_ws(websocket: WebSocket, session_id: str):
    await websocket.accept()
    loop = asyncio.get_running_loop()

    # A fresh bash per connection; keyed by session_id for resize lookups.
    session = PtySession(session_id)
    try:
        session.spawn()
    except Exception as exc:  # DEGRADE LOUDLY
        log.exception("session %s: spawn failed", session_id)
        try:
            await websocket.send_text(f"\r\n[terminal_server] FAILED to spawn shell: {exc}\r\n")
        finally:
            await websocket.close()
        return

    SESSIONS[session_id] = session
    master_fd = session.master_fd

    # ---- pty stdout -> websocket, driven by the event loop's fd reader ----
    def on_readable():
        try:
            data = os.read(master_fd, 65536)
        except (BlockingIOError, InterruptedError):
            return
        except OSError:
            # Shell exited / fd closed.
            data = b""
        if not data:
            loop.remove_reader(master_fd)
            asyncio.create_task(_shutdown("shell exited"))
            return
        # TEXT frame (frontend does term.write(e.data) without binaryType).
        text = data.decode("utf-8", errors="replace")
        asyncio.create_task(_safe_send(text))

    async def _safe_send(text: str):
        try:
            await websocket.send_text(text)
        except Exception:
            pass

    closing = asyncio.Event()

    async def _shutdown(reason: str):
        if closing.is_set():
            return
        closing.set()
        log.info("session %s: shutting down (%s)", session_id, reason)
        try:
            loop.remove_reader(master_fd)
        except Exception:
            pass
        session.close()
        SESSIONS.pop(session_id, None)
        try:
            await websocket.close()
        except Exception:
            pass

    loop.add_reader(master_fd, on_readable)

    # ---- websocket -> pty stdin (keystrokes) ----
    try:
        while True:
            msg = await websocket.receive()
            if msg["type"] == "websocket.disconnect":
                break
            data = msg.get("text")
            if data is None:
                b = msg.get("bytes")
                payload = b if b is not None else b""
            else:
                payload = data.encode("utf-8")
            if payload and session.master_fd is not None:
                try:
                    os.write(session.master_fd, payload)
                except OSError:
                    break
    except WebSocketDisconnect:
        pass
    except Exception:
        log.exception("session %s: receive loop error", session_id)
    finally:
        await _shutdown("client disconnect")


class ResizeReq(BaseModel):
    session_id: str
    cols: int
    rows: int


@app.post("/api/terminal/resize")
async def resize(req: ResizeReq):
    session = SESSIONS.get(req.session_id)
    if session is None:
        return JSONResponse(
            status_code=404,
            content={"ok": False, "error": f"no active session {req.session_id}"},
        )
    try:
        session.set_winsize(req.rows, req.cols)
    except Exception as exc:
        log.exception("resize failed for %s", req.session_id)
        return JSONResponse(status_code=500, content={"ok": False, "error": str(exc)})
    return {"ok": True, "session_id": req.session_id, "cols": req.cols, "rows": req.rows}


@app.get("/api/terminal/health")
async def health():
    return {
        "ok": True,
        "agentic_elevation": os.environ.get("SYNTHESUS_AGENTIC_ELEVATION") == "1",
        "terminal_root": str(terminal_root()),
        "sessions": list(SESSIONS.keys()),
    }


if __name__ == "__main__":
    log.info("God-mode terminal backend binding %s:%d (localhost only)", HOST, PORT)
    uvicorn.run(app, host=HOST, port=PORT, log_level="warning")
