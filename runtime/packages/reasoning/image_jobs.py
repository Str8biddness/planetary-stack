#!/usr/bin/env python3
"""
In-process async SI image job queue — soft-DoS guard for high-res / multi-frame.
===============================================================================

Small thread pool (default 2 workers). Jobs are process-local (not distributed).
Status: queued → running → done | failed. Result payload is the same shape as
sync /api/v1/image (minus huge fields until done).

Env:
  SYNTHESUS_IMAGE_JOB_WORKERS  (default 2)
  SYNTHESUS_IMAGE_JOB_TTL_S    (default 600) — drop finished jobs after TTL

Run: python packages/reasoning/image_jobs.py
"""
from __future__ import annotations

import os
import threading
import time
import traceback
import uuid
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Callable, Dict, Optional

_WORKERS = max(1, min(4, int(os.environ.get("SYNTHESUS_IMAGE_JOB_WORKERS", "2"))))
_TTL = max(60, int(os.environ.get("SYNTHESUS_IMAGE_JOB_TTL_S", "600")))
_MAX_JOBS = 64

_lock = threading.Lock()
_jobs: Dict[str, Dict[str, Any]] = {}
_executor = ThreadPoolExecutor(max_workers=_WORKERS, thread_name_prefix="si-img")


def _purge_locked(now: Optional[float] = None) -> None:
    now = time.time() if now is None else now
    dead = [
        jid for jid, j in _jobs.items()
        if j.get("status") in ("done", "failed")
        and (now - float(j.get("finished_at") or now)) > _TTL
    ]
    for jid in dead:
        _jobs.pop(jid, None)
    # hard cap: drop oldest finished
    if len(_jobs) > _MAX_JOBS:
        finished = sorted(
            ((j.get("finished_at") or 0, jid) for jid, j in _jobs.items()
             if j.get("status") in ("done", "failed")),
        )
        for _, jid in finished[: max(0, len(_jobs) - _MAX_JOBS)]:
            _jobs.pop(jid, None)


def submit_job(
    kind: str,
    params: Dict[str, Any],
    runner: Callable[[Dict[str, Any], Callable[[str, float], None]], Dict[str, Any]],
) -> str:
    """Queue a job. runner(params, progress_cb) -> result dict."""
    jid = "imgjob-" + uuid.uuid4().hex[:16]
    with _lock:
        _purge_locked()
        if sum(1 for j in _jobs.values() if j["status"] in ("queued", "running")) >= _WORKERS + 8:
            raise RuntimeError("image job queue full — retry later or lower resolution")
        _jobs[jid] = {
            "job_id": jid,
            "kind": kind,
            "status": "queued",
            "progress": 0.0,
            "message": "queued",
            "created_at": time.time(),
            "started_at": None,
            "finished_at": None,
            "params_summary": {
                k: (str(params.get(k))[:120] if k == "prompt" else params.get(k))
                for k in (
                    "prompt", "resolution", "style", "look", "views", "frames",
                    "orbit_day", "orbit_frames", "path_mode", "preset",
                )
            },
            "result": None,
            "error": None,
        }

    def _run():
        def progress(msg: str, p: float = 0.0) -> None:
            with _lock:
                job = _jobs.get(jid)
                if not job:
                    return
                job["message"] = str(msg)[:200]
                job["progress"] = float(max(0.0, min(1.0, p)))
                if job["status"] == "queued":
                    job["status"] = "running"
                    job["started_at"] = time.time()

        with _lock:
            job = _jobs.get(jid)
            if job:
                job["status"] = "running"
                job["started_at"] = time.time()
                job["message"] = "running"
                job["progress"] = 0.05
        try:
            result = runner(params, progress)
            with _lock:
                job = _jobs.get(jid)
                if job:
                    job["status"] = "done"
                    job["progress"] = 1.0
                    job["message"] = "done"
                    job["finished_at"] = time.time()
                    job["result"] = result
        except Exception as e:
            with _lock:
                job = _jobs.get(jid)
                if job:
                    job["status"] = "failed"
                    job["progress"] = 1.0
                    job["message"] = "failed"
                    job["finished_at"] = time.time()
                    job["error"] = f"{type(e).__name__}: {e}"
                    job["traceback"] = traceback.format_exc()[-2000:]

    _executor.submit(_run)
    return jid


def get_job(job_id: str) -> Optional[Dict[str, Any]]:
    with _lock:
        _purge_locked()
        job = _jobs.get(job_id)
        if not job:
            return None
        # shallow copy without mutating
        out = {k: v for k, v in job.items() if k != "traceback"}
        return out


def job_public_view(job: Dict[str, Any], *, include_result: bool = True) -> Dict[str, Any]:
    """API-safe job envelope."""
    out = {
        "ok": True,
        "job_id": job["job_id"],
        "kind": job.get("kind"),
        "status": job["status"],
        "progress": job.get("progress", 0.0),
        "message": job.get("message"),
        "created_at": job.get("created_at"),
        "started_at": job.get("started_at"),
        "finished_at": job.get("finished_at"),
        "params_summary": job.get("params_summary"),
        "async": True,
    }
    if job["status"] == "failed":
        out["error"] = job.get("error")
        out["ok"] = False
    if include_result and job["status"] == "done" and job.get("result") is not None:
        out["result"] = job["result"]
    return out


def should_force_async(resolution: int, multi: bool = False) -> bool:
    """High-res or multi-frame work should not block the API worker indefinitely."""
    if multi:
        return True
    return int(resolution) >= 1024


def demo():
    def runner(params, progress):
        progress("start", 0.1)
        time.sleep(0.05)
        progress("mid", 0.5)
        time.sleep(0.05)
        progress("end", 0.9)
        return {"ok": True, "echo": params.get("prompt")}

    jid = submit_job("demo", {"prompt": "hi", "resolution": 512}, runner)
    for _ in range(20):
        j = get_job(jid)
        print(j["status"], j["progress"], j.get("message"))
        if j["status"] in ("done", "failed"):
            print("result", j.get("result") or j.get("error"))
            break
        time.sleep(0.02)


if __name__ == "__main__":
    demo()
