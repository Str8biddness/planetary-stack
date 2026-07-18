# Launch checklist (QC gate)

Do **not** merge until each box has **pasted real output** (Law #2).  
Branches: `feat/launch-smoke` (includes native-kernel + polish + module-audit).

## A. Code on the machine that actually runs

- [ ] `main` (or release tag) includes launch-smoke merges
- [ ] Install dir synced with `tools/redeploy_install.sh` (preserves `.venv`, `synthesus.env`, `data/`)
- [ ] `grep SYNTHESUS_HUMAN_SESSION_SECRET ~/.local/share/synthesus/synthesus.env` is set
- [ ] `grep SYNTHESUS_JWT_SECRET ~/.local/share/synthesus/synthesus.env` is set
- [ ] `scikit-learn==1.8.0` in install venv (`pip show scikit-learn`)

## B. Automated smoke

```bash
# Start runtime first, then:
export SYNTHESUS_API_KEY=…   # from synthesus.env
./tools/launch_smoke.sh
```

**2026-07-11 live proof (dev box, runtime up):** `pass=8 fail=0 skip=0`

- [x] health 200  
- [x] query returns real text (`source=cognitive_hypervisor`)  
- [x] feedback without human proof does **not** upgrade  
- [x] image endpoint returns image (`bytes=7527`)  
- [x] sklearn embedder clean (`1.8.0 ok`)  
- [x] `zo_kernel` IPC if binary present  
- [x] VERBATIM + install human session secret checks

## C. Manual product checks

- [ ] Desktop 👍 confirm: mint → feedback → item `user_confirmed` / verification 2  
- [ ] Settings: Local Ollama / LM Studio save works **without** Pro  
- [ ] User doc with unique code → answer contains **exact** code  
- [ ] Server log: `KernelBridge mode=ipc` when binary present; fallback when removed  
- [ ] First ingest after restart: warm-up log present; second ingest not ~100s cold  

## D. Honest capability

- [ ] `CAPABILITY_LEDGER.md` reviewed — stubs not faked  
- [ ] Kernel README: IPC = production path; pybind ≠ ThreadPool native  
- [ ] No claim of CNC/G-code path or multi-model swarm copies  

## E. Security

- [ ] Runtime remains loopback-only and uses a unique `SYNTHESUS_API_KEY` (not `dev-key-change-me`)
- [ ] `/api/v1/security` imports (Dict/Any) — no silent NameError  

---

**Sign-off:** reviewer name + date + paste of `launch_smoke.sh` summary.
