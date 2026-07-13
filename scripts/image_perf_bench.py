#!/usr/bin/env python3
"""Wall-clock SI image bench at 512/1024 (path_mode, look=raw).

Locks the bbox-fill perf claim: 1024 must complete well under 10s.
Run: PYTHONPATH=runtime/packages/reasoning:. python scripts/image_perf_bench.py
"""
from __future__ import annotations

import os
import sys
import tempfile
import time

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path[:0] = [
    os.path.join(ROOT, "runtime", "packages", "reasoning"),
    os.path.join(ROOT, "runtime", "packages"),
    ROOT,
]

from image_service import generate_image, clear_image_cache, ENGINE_VERSION  # noqa: E402


def main() -> int:
    clear_image_cache(disk=True)
    prompt = "a house and a tree on grass under a sky with a sun"
    print("ENGINE", ENGINE_VERSION)
    # Historical pre-bbox review measurement was ~79s at 1024 (Claude review).
    print("historical_1024_pre_bbox_s 79.0  # from review notes, not re-run here")
    ok = True
    with tempfile.TemporaryDirectory() as td:
        for res, budget in ((512, 5.0), (1024, 10.0)):
            out = os.path.join(td, f"r{res}.png")
            t0 = time.perf_counter()
            generate_image(
                prompt,
                out,
                res=res,
                look="raw",
                detail="standard",
                path_mode=True,
                use_cache=False,
                seed=7,
                compile_plan=True,
                use_llm_plan=False,
            )
            dt = time.perf_counter() - t0
            size = os.path.getsize(out)
            status = "OK" if dt <= budget and size > 1000 else "FAIL"
            if status != "OK":
                ok = False
            print(f"{status} res={res:4d}  {dt:7.3f}s  budget<={budget}  bytes={size}")
    print("RESULT", "PASS" if ok else "FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
