# Bootstrap (reproducible, pinned)

Checklist gate **F-010** — reproducible bootstrap + pinned versions.

This document describes the single command that prepares a fresh, supported
Linux machine to build and test the Planetary Stack, and the version matrix the
bootstrap pins.

## One command

From the repository root on a supported Linux host:

```bash
make bootstrap
```

That target runs [`scripts/bootstrap.sh`](../scripts/bootstrap.sh), which is
idempotent and safe to re-run. It:

1. Verifies required host tooling is present (`git`, `make`, `g++`, a Python
   interpreter). It **fails closed** with a clear message if any is missing —
   nothing is installed until all required tools are found.
2. Verifies the interpreter meets the pinned floor (Python `>= 3.12`, per
   `pyproject.toml` `requires-python`).
3. Creates (or reuses) a project virtual environment at `.venv`.
4. Installs the **exact** Python dependency pins from
   [`versions.lock`](../versions.lock).
5. Runs `make doctor` against the venv interpreter so the environment
   self-reports readiness.

Equivalent direct invocation (same result):

```bash
./scripts/bootstrap.sh
```

### Overrides

| Variable   | Default        | Purpose                                   |
| ---------- | -------------- | ----------------------------------------- |
| `PYTHON`   | `python3`      | Interpreter used to create the venv.      |
| `VENV_DIR` | `<repo>/.venv` | Virtual environment location.             |

Example: `PYTHON=/usr/bin/python3.12 VENV_DIR=/tmp/ps-venv ./scripts/bootstrap.sh`

After bootstrap, activate the environment with:

```bash
source .venv/bin/activate
```

## Version matrix

`versions.lock` is the single source of truth. Every pin below was **detected**
on a real host with `python --version` / `pip show` / `<tool> --version`, or is
a documented **expected/tested** version recorded in `AGENT_LOG.md`. Nothing is
invented.

### Interpreter

| Component | Pin      | Source                                                        |
| --------- | -------- | ------------------------------------------------------------- |
| Python    | `3.12.3` | detected (`python --version`); floor `>=3.12` in pyproject.toml |

### Python dependencies (installed by bootstrap)

All detected via `pip show` against
`/home/dakin/.local/share/synthesus/.venv/bin/python`:

| Package               | Pin        | Notes                                                        |
| --------------------- | ---------- | ------------------------------------------------------------ |
| `pydantic`            | `2.13.4`   | detected; matches pyproject pin                              |
| `cryptography`        | `41.0.7`   | detected; repo declares `>=41.0.0`; known validated point    |
| `rfc8785`             | `0.1.4`    | detected; matches pyproject pin                              |
| `jsonschema[format]`  | `4.26.0`   | detected; matches pyproject pin                              |
| `onnxruntime`         | `1.27.0`   | detected; repo declares `>=` floor only                      |
| `numpy`               | `2.5.1`    | detected; repo declares `>=` floor only                      |
| `fastapi`             | `0.139.0`  | detected; repo declares `>=` floor only                      |
| `uvicorn`             | `0.51.0`   | detected; repo declares `>=` floor only                      |
| `pytest`              | `9.1.1`    | detected; matches contracts pin                              |
| `setuptools`          | `78.1.0`   | detected; matches pyproject build-system pin                 |

### System tools

| Tool     | Version   | Status                                                                                       |
| -------- | --------- | -------------------------------------------------------------------------------------------- |
| `git`    | `2.43.0`  | detected (`git --version`)                                                                    |
| `make`   | `4.3`     | detected (GNU Make)                                                                           |
| `g++`    | `13.3.0`  | detected (Ubuntu 13.3.0)                                                                      |
| `podman` | `4.9.3`   | **expected/tested — not detected on the bootstrap host.** Recorded in `AGENT_LOG.md` (F-020 physical gate: rootless Podman 4.9.3, cgroups v2). Required only on nodes that execute AIVM workloads. |
| `ollama` | `0.32.0`  | client **detected** (`ollama --version`, server not running). The Ollama server plus the `llama3.2:3b` model are runtime dependencies of the Synthesus chat path, not of the contract/test bootstrap. |

## Scope and honesty notes

- Bootstrap pins and installs the Python toolchain and runs `make doctor`. It
  does **not** install system packages (`git`, `g++`, Podman, Ollama); those
  must already be present, and bootstrap fails closed listing what is missing.
- `podman` was not present on the bootstrap host; its version is the tested
  value from repository evidence, not a live detection. Verify with
  `podman --version` on any workload-executing node.
