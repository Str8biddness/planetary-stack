# Synthesus

**A local, private AI desktop.** Synthesus runs entirely on your own machine — the
model, your files, and every conversation stay on your computer. Nothing leaves it.
It grounds its answers in *your* documents through an expansion drive you control, and
gives you a full AI desktop: chat, a real terminal, and file-grounded retrieval, with
no cloud account and no per-token bill.

> Runs on [Ollama](https://ollama.com) locally. No API keys. No telemetry. Your data
> never leaves the machine — and because the code is open, you can verify that.

## Install (Debian / Ubuntu / Mint)

```bash
./install.sh
```

The installer sets up system packages (needs `sudo` once), a Python virtualenv, and
Ollama with a small local model, then installs a launcher. When it finishes:

```bash
~/.local/bin/synthesus      # or find "Synthesus" in your applications menu
```

Everything runs on `127.0.0.1` — the desktop shell, the runtime, and the model.

## Headless / server use

No display, or running on a box you reach over SSH? Run the web UI headless:

```bash
SYNTHESUS_HEADLESS=1 ~/.local/bin/synthesus     # then open http://localhost:8081
```

To use a headless install from another machine, forward the port over an **SSH tunnel**
— do **not** expose the ports directly (one of them is a real shell). Full guide:
[`desktop/docs/HEADLESS.md`](desktop/docs/HEADLESS.md).

## What's in this repo

| Path | What it is |
|------|-----------|
| `desktop/` | The desktop shell — window manager, chat UI, terminal, file explorer |
| `runtime/` | The reasoning runtime — retrieval, grounding, the character engine, the API |
| `install.sh` | One-touch installer |

## Open core

The **code** is open source under **AGPL-3.0** (see [`LICENSE`](LICENSE)). You can run
it, read it, modify it, and self-host it. If you run a modified version as a network
service, the AGPL asks you to share your changes.

What is **not** in this repo, and stays proprietary: the curated Core knowledge corpus,
the five evolved premium personas (their trained genomes), and the hosted service. The
**character engine** is here and fully functional — the base Synthesus identity ships,
and you can author your own characters with it. The premium personas are a separate,
closed pack.

## License

[GNU AGPL-3.0](LICENSE) © 2026 Dakin Ellegood.
