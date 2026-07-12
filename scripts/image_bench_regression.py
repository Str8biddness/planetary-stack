#!/usr/bin/env python3
"""Fixed-prompt SI image regression bench (latency + smoke quality).

Run from repo root:
  PYTHONPATH=runtime/packages/reasoning:. python scripts/image_bench_regression.py

Exit 0 if all prompts render and optional latency budgets hold.
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

from image_service import generate_image, apply_scene_pass, clear_image_cache, ENGINE_VERSION
import image_session as sess

PROMPTS = [
    ("house", "a house and a tree on grass under a sky with a sun", 2.5),
    ("vase_crate", "a vase and a crate on grass under a sky", 2.5),
    ("espresso", "espresso machine on grass under a sky", 3.0),
    ("cabin_dusk", "a lonely cabin by a creek at golden hour", 3.0),
]


def main() -> int:
    clear_image_cache(disk=True)
    sess.clear_sessions(disk=False)
    print("ENGINE", ENGINE_VERSION)
    ok = True
    with tempfile.TemporaryDirectory() as td:
        for name, prompt, budget in PROMPTS:
            out = os.path.join(td, f"{name}.png")
            t0 = time.perf_counter()
            m = generate_image(
                prompt, out, res=256, look="raw", detail="standard",
                seed=7, use_cache=False, use_llm_plan=False, keep_session=True,
            )
            dt = time.perf_counter() - t0
            size = os.path.getsize(out)
            status = "OK" if size > 500 and dt <= budget else "FAIL"
            if status != "OK":
                ok = False
            print(f"{status:4s} {name:12s} {dt:6.3f}s budget={budget} size={size} "
                  f"build={m.get('construction')} lathe={m.get('lathe_parts')} "
                  f"extrude={m.get('extrude_parts')} sid={bool(m.get('scene_id'))}")
            if m.get("scene_id") and name == "vase_crate":
                t1 = time.perf_counter()
                m2 = apply_scene_pass(m["scene_id"], os.path.join(td, "pass.png"), yaw_deg=20, grade="warm")
                dt2 = time.perf_counter() - t1
                print(f"     pass         {dt2:6.3f}s yaw={m2.get('yaw_deg')} pic={bool(m2.get('picture_edit'))}")
    print("RESULT", "PASS" if ok else "FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
