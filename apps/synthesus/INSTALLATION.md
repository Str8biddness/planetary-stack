# Installing Synthesus

A step-by-step guide so you get a working install on the first try — including what to
expect, what the installer actually does, and how to fix the handful of things that can
go wrong. If anything here isn't clear, that's a doc bug — open an issue.

---

## 1. Prerequisites

| | Minimum | Recommended |
|---|---------|-------------|
| **OS** | 64-bit Debian 12 / Ubuntu 22.04+ / Mint 21+, or Windows 10/11 with **WSL2** | same |
| **Disk free** | ~10 GB | 20 GB+ |
| **RAM** | 4 GB | 8 GB+ |
| **CPU / GPU** | 2 cores (works, but chat is slow) | **4+ cores, or an NVIDIA/AMD GPU** |

**About speed (read this):** Synthesus runs a real LLM locally and its answer pipeline
makes several model calls per question. On a GPU or a decent multi-core CPU that's a few
seconds. **On a weak 2-core / eMMC machine (e.g. a low-end Chromebook) it can be very
slow — that's the hardware, not a bug.** If your machine is underpowered, either use a
better one, add a GPU (see §8), or point Synthesus at a faster model backend.

You need **`git`** and **`curl`** installed first:
```bash
sudo apt update && sudo apt install -y git curl
```

---

## 2. Install

```bash
git clone https://github.com/Str8biddness/synthesus.git
cd synthesus
./install.sh
```

It will ask for `sudo` **once** (to install system packages). Total time: ~5–15 min on a
normal connection (most of it is the ~2 GB model download). On a slow disk/network it's
longer — that's normal.

---

## 3. What the installer does (so nothing is a black box)

1. **System packages** (`sudo apt`): Python venv/pip, build tools, and the GTK/WebKit
   backend the desktop window needs.
2. **Ollama + model**: installs [Ollama](https://ollama.com) and pulls `llama3.2:3b` (~2 GB).
3. **Python environment**: a virtualenv at `~/.local/share/synthesus/.venv`, with a
   **CPU-only PyTorch** (so it does *not* download the multi-GB CUDA build) plus the
   runtime + desktop dependencies. Critical deps (`flask-cors`, `PyJWT`, `faiss`,
   `fastembed`, …) are installed explicitly so a partial failure can't silently break boot.
4. **Per-install key**: a private API key in `~/.local/share/synthesus/synthesus.env`
   (localhost only, `chmod 600`).
5. **Launcher**: `~/.local/bin/synthesus` + a "Synthesus" app-menu entry.
6. **Self-check** (§4).

Everything lands under `~/.local/share/synthesus/`. Nothing is installed globally except
the apt packages and Ollama.

---

## 4. The self-check — real path vs. fallbacks

At the end the installer verifies the **real** path works. Fallbacks (canned replies)
exist only to prevent a crash — they are **not** the product, and you shouldn't see them.

- ✅ **`SELF-CHECK PASSED`** → all critical deps import, Ollama + model are ready. You're good.
- ⚠️ **`SELF-CHECK found gaps`** → it prints exactly what's missing and the command to fix
  it. Fix it before launching, or chat/grounding will degrade. Common fix it prints:
  ```bash
  ~/.local/share/synthesus/.venv/bin/pip install <missing-packages>
  ```

---

## 5. First launch

**Graphical desktop:**
```bash
~/.local/bin/synthesus         # or click "Synthesus" in your app menu
```

**Optional agentic elevation:**

Standard Synthesus remains unprivileged. To let development agents use audited
`sudo` commands without repeated prompts during one desktop session, install
the short-lived timestamp policy once:

```bash
sudo ~/.local/share/synthesus/tools/configure_agentic_elevation.sh --install "$USER"
```

Then launch the separate **Synthesus Agentic** menu entry or run:

```bash
~/.local/bin/synthesus --agentic
```

Agentic mode invalidates any old sudo ticket, asks for your password once
before the desktop opens, validates the authorization from a separate PTY,
refreshes it only while Synthesus is running, and revokes it on exit. It does
not install `NOPASSWD` rules. If the launcher crashes, the ticket expires
within one minute.

To remove the cross-PTY timestamp policy:

```bash
sudo ~/.local/share/synthesus/tools/configure_agentic_elevation.sh --remove "$USER"
```

**Headless (no display / server):**
```bash
SYNTHESUS_HEADLESS=1 ~/.local/bin/synthesus     # then open http://localhost:8081
```

**Expect a slow *first* message.** The first chat after boot loads the model into RAM —
a one-time cold start (seconds on a GPU/good CPU, longer on a weak one). After that it's
warm and faster. If the very first reply looks canned, it's almost always the cold load —
wait and try again.

---

## 6. Verify it's actually working

With it running (headless or graphical), from the same machine:
```bash
# stack healthy? (should show status: online, ollama_reachable: true)
curl -s http://localhost:8081/api/health

# a real answer? (first call is the slow cold load)
curl -s -X POST http://localhost:8081/api/chat \
  -H 'Content-Type: application/json' \
  -d '{"message":"In one sentence, what are you?"}'
```
A real answer means `"source": "chal_runtime"`. If you get `"source": "degraded_direct"`
with an `[AUTONOMIC REFLEX]` message, the runtime didn't answer in time — see below.

---

## 7. Troubleshooting

| Symptom | Cause & fix |
|---------|-------------|
| **`ModuleNotFoundError` on launch** | A dep didn't install. Run the self-check's fix line: `~/.local/share/synthesus/.venv/bin/pip install <name>`. |
| **Chat returns `[AUTONOMIC REFLEX]` / "degraded"** | The runtime didn't answer in time. Usually (a) **cold model load** — retry once warm; or (b) **Ollama not running** — `ollama serve &` then `ollama pull llama3.2:3b`; or (c) **hardware too slow** — see §1/§8. |
| **`No space left on device` during install** | Need ~10 GB free. Check `df -h`. On LVM setups (some distros) your space may be on a different partition (e.g. `/home`) — install there with `SYNTHESUS_HOME=/home/you/synthesus ./install.sh`. |
| **Very slow replies** | Underpowered CPU. Add a GPU (§8), use a smaller/faster model, or a faster backend. Not a bug. |
| **`pygobject` / GTK build error** | Handled — the installer pins `pygobject<3.52` for Debian 12. If it still fails, `sudo apt install -y libgirepository1.0-dev gir1.2-gtk-3.0`. |
| **Port already in use (5010/8081/8082)** | Another instance is running. `pkill -f production_server.py; pkill -f synthesus_native_shell.py` and relaunch. |
| **Agentic launch says the policy is not configured** | Run the one-time `configure_agentic_elevation.sh --install "$USER"` command above. The policy shares a one-minute sudo timestamp across local PTYs but grants no passwordless commands. |
| **Can't reach it from another machine** | Don't expose the ports — **SSH-tunnel** them. See [`desktop/docs/HEADLESS.md`](desktop/docs/HEADLESS.md). Port `:8082` is a real shell; never expose it. |
| **WSL2: GUI won't open** | Expected — use **headless mode** and open `http://localhost:8081` in your Windows browser (WSL forwards localhost automatically). |

To read what actually failed at runtime: `cat ~/.synthesus/runtime.log` (or relaunch from
a terminal and watch the output).

---

## 8. GPU acceleration (optional, big speedup)

Synthesus runs through Ollama, which uses your GPU automatically **if the drivers are set
up**. A helper is included:
```bash
bash tools/enable_gpu.sh
```
It detects an NVIDIA/AMD GPU, tells you whether Ollama is using it, and prints the exact
driver/CUDA (or ROCm) steps if not. A GPU turns slow CPU inference into near-instant replies.

---

## 9. Updating

```bash
cd synthesus
git pull
./install.sh          # re-runs safely; refreshes code + deps
```

## 10. Uninstalling

```bash
rm -rf ~/.local/share/synthesus ~/.local/bin/synthesus \
       ~/.local/share/applications/synthesus.desktop ~/.synthesus
# optionally: remove the model + Ollama
ollama rm llama3.2:3b
```

## 11. Where your data lives

Everything is local, under `~/.local/share/synthesus/` (code, venv, your key) and the
ingested-file index the app builds. Your conversations and documents never leave the
machine.
