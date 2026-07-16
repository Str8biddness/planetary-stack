# Synthesus

**A local, private AI desktop.** Synthesus runs entirely on your own machine — the
model, your files, and every conversation stay on your computer. Nothing leaves it.
It grounds its answers in *your* documents through an expansion drive you control, and
gives you a full AI desktop: chat, a real terminal, and file-grounded retrieval, with
no cloud account and no per-token bill.

> Runs on [Ollama](https://ollama.com) locally. No API keys. No telemetry. Your data
> never leaves the machine — and because the code is open, you can verify that.

## Requirements

- **OS:** 64-bit **Debian 12 / Ubuntu 22.04+ / Linux Mint 21+** (or Windows via **WSL2**).
- **Disk:** ~**10 GB free** (Python env + deps + a ~2 GB local model).
- **RAM:** 4 GB minimum; **8 GB recommended** (the 3B model needs ~2–3 GB to run).
- **CPU/GPU:** works CPU-only, but **4+ cores or an NVIDIA/AMD GPU is strongly
  recommended.** On a weak 2-core machine the model runs, just slowly — that's hardware,
  not a bug. A GPU makes it dramatically faster.

## Install (Debian / Ubuntu / Mint / WSL2)

```bash
git clone https://github.com/Str8biddness/synthesus.git
cd synthesus
./install.sh
```

The installer sets up system packages (needs `sudo` once), a Python virtualenv, Ollama +
a small local model, a launcher, and then runs a **self-check** that tells you whether the
real path is ready or something will degrade. Full step-by-step + troubleshooting:
**[INSTALLATION.md](INSTALLATION.md)**.

When it finishes:

```bash
~/.local/bin/synthesus      # or find "Synthesus" in your applications menu
```

Everything runs on `127.0.0.1` — the desktop shell, the runtime, and the model.

> **First message is slow, then fast.** Your first chat after boot loads the model into
> memory (a one-time cold start — seconds on a GPU/decent CPU, longer on a weak one).
> After that it's warm. If the *first* reply looks canned, it's the cold-load; give it a
> moment or see [INSTALLATION.md](INSTALLATION.md#troubleshooting).

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
| `install.sh` | One-touch installer + post-install self-check |
| `INSTALLATION.md` | Detailed install guide + troubleshooting |

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
