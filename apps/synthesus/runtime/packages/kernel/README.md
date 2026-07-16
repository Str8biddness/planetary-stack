# Synthesus C++ Kernel

## Two artifacts, two roles (do not confuse them)

| Artifact | How built | Used by runtime? | Role |
|----------|-----------|------------------|------|
| **`build/zo_kernel`** (cmake target `synthesus_kernel`, OUTPUT_NAME `zo_kernel`) | `cmake` + `make` | **YES — primary** | stdin/stdout **IPC** process for left-hemisphere routing |
| **`build/_synthesus_kernel*.so`** | same cmake with `-DBUILD_PYBIND=ON` | Optional / experimental | pybind exports `EmulEngine`, `GeometricEngine`, `GeometricOptics`, … |

### IPC is the production path

`HemisphereBridge` + `kernel/bridge.py` launch the **executable** and exchange JSON lines:

- Request (plain text) or `{"query":"...","rag_context":"..."}`
- Response: `{"response":"...","confidence":0.7,"module_used":"ppbrs","found":true,...}`

If the binary is missing, the bridge **degrades to pure Python** (loud log, no crash).

### Why not “native” pybind for the left hemisphere?

`bridge.py` `_init_native` expects `ThreadPool` / `MessageBus` / `ContextMemory` / `PPBRSRouter` / `Watchdog`.  
The current pybind module exports **EmulEngine / geometric** types instead — an API mismatch.  
Do **not** force NATIVE mode until those symbols match. Prefer **IPC**.

### Build

```bash
cd runtime/packages/kernel
mkdir -p build && cd build
CXXFLAGS="-march=native" cmake .. \
  -DPython3_EXECUTABLE=$HOME/synthesus/.venv/bin/python \
  -DBUILD_PYBIND=ON
make -j4
# artifacts: ./zo_kernel  and  ./_synthesus_kernel*.so
```

Optional env: `SYNTHESUS_KERNEL_BIN=/absolute/path/to/zo_kernel`
