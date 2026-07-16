# Running Synthesus headless (and reaching it remotely, safely)

Synthesus runs two ways. Both serve the **exact same OS** — the desktop is a web
app served on `http://localhost:8081`; the only difference is whether a window is
opened for you.

| Mode | How | For |
|---|---|---|
| **Graphical** (default) | `synthesus` | A machine with a display — opens the frameless desktop window. |
| **Headless** | `SYNTHESUS_HEADLESS=1 synthesus` | A server / homelab box with no display (or no GTK/WebKit). No window — you open it in a browser. |
| **Agentic elevation** | `synthesus --agentic` | Explicit local development mode; asks once before launch and revokes sudo authorization on exit. |

If pywebview has no display backend, Synthesus **falls back to headless automatically** and prints the URL.

---

## Headless: run it, then open it in a browser

```bash
SYNTHESUS_HEADLESS=1 synthesus
```
It starts the runtime + terminal backend + the web UI and prints:
```
[*] HEADLESS — open Synthesus in your browser:
[*]     http://localhost:8081
```
Open that in any browser **on the same machine** and you get the full desktop.

Everything stays bound to `127.0.0.1` — nothing is exposed to your network. That's
deliberate (see the warning below).

---

## Reaching a headless box from another machine — use an SSH tunnel

This is the **standard, secure** way to use a headless server's web UI remotely, and
it needs **no configuration in Synthesus** — it stays localhost-only, and SSH does the
encryption + authentication for you.

On your **laptop**, forward the port over SSH to the box running Synthesus:

```bash
ssh -L 8081:localhost:8081 you@your-synthesus-box
```

Leave that running, then on your laptop open:

```
http://localhost:8081
```

You're now using the headless box's Synthesus, over an encrypted, authenticated SSH
channel. When you close the SSH session, the tunnel closes with it. Nothing on the
box was ever exposed to the network.

> Tip: keep the tunnel up in the background with `ssh -fN -L 8081:localhost:8081 you@box`.

---

## ⚠️ Do NOT expose Synthesus's ports directly to a network

Do **not** bind Synthesus to `0.0.0.0`, port-forward it on your router, or put it on a
public IP without a proper authenticating reverse proxy. Here's why, specifically:

- **`:8082` is the god-mode terminal — a real shell.** It spawns `bash` as your user
  over a WebSocket. Bound to localhost it's fine; reachable from a network it is an
  **unauthenticated remote shell** — anyone who can reach the port gets a terminal on
  your machine. Internet-facing, it will be found by automated scanners and abused.
- Agentic elevation intentionally makes the current user's short sudo timestamp
  available to all local PTYs while that desktop session is active. Any process
  already running as that user can potentially use the same ticket. Enable it only
  on a trusted workstation, and never combine it with network-exposed Synthesus ports.
- `:8081` (UI + proxied APIs) and `:5010` (the runtime) are also built for a trusted
  local environment, not the open network.

**The SSH tunnel above gives you remote access without any of this risk** — the ports
stay on `127.0.0.1` and only your authenticated SSH session can reach them.

Native remote access (built-in auth + TLS, no tunnel needed) is planned for a future
release, built deliberately with a security review — not something to improvise by
opening ports.
