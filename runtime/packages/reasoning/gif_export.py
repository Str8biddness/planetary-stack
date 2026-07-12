#!/usr/bin/env python3
"""
GIF/WebP export for SI multi-frame sequences — local, no cloud.
==============================================================

Assembles PNG frames (paths or base64) into an animated GIF or WebP.
Uses Pillow only. Deterministic frame order.

Run: python packages/reasoning/gif_export.py
"""
from __future__ import annotations

import base64
import io
import os
from typing import Any, List, Optional, Sequence, Union

from PIL import Image


def _load_frame(src: Union[str, bytes, dict]) -> Image.Image:
    if isinstance(src, dict):
        if src.get("image_base64"):
            raw = base64.b64decode(src["image_base64"])
            return Image.open(io.BytesIO(raw)).convert("RGBA")
        if src.get("path") and os.path.isfile(src["path"]):
            return Image.open(src["path"]).convert("RGBA")
        raise ValueError("frame dict needs image_base64 or path")
    if isinstance(src, (bytes, bytearray)):
        return Image.open(io.BytesIO(src)).convert("RGBA")
    if isinstance(src, str) and os.path.isfile(src):
        return Image.open(src).convert("RGBA")
    if isinstance(src, str) and len(src) > 64:
        # assume base64
        return Image.open(io.BytesIO(base64.b64decode(src))).convert("RGBA")
    raise ValueError(f"cannot load frame: {type(src)}")


def frames_to_gif_bytes(
    frames: Sequence[Any],
    *,
    duration_ms: int = 400,
    loop: int = 0,
    optimize: bool = True,
) -> bytes:
    """Encode frames as animated GIF bytes."""
    if not frames:
        raise ValueError("no frames")
    imgs = [_load_frame(f) for f in frames]
    # unify size to first frame
    w, h = imgs[0].size
    norm = []
    for im in imgs:
        if im.size != (w, h):
            im = im.resize((w, h), Image.Resampling.LANCZOS)
        # GIF wants palette; convert via RGB
        norm.append(im.convert("RGB"))
    buf = io.BytesIO()
    norm[0].save(
        buf,
        format="GIF",
        save_all=True,
        append_images=norm[1:],
        duration=max(50, int(duration_ms)),
        loop=int(loop),
        optimize=optimize,
    )
    return buf.getvalue()


def frames_to_webp_bytes(
    frames: Sequence[Any],
    *,
    duration_ms: int = 400,
    quality: int = 80,
    loop: int = 0,
) -> bytes:
    """Encode frames as animated WebP (smaller than GIF usually)."""
    if not frames:
        raise ValueError("no frames")
    imgs = [_load_frame(f) for f in frames]
    w, h = imgs[0].size
    norm = []
    for im in imgs:
        if im.size != (w, h):
            im = im.resize((w, h), Image.Resampling.LANCZOS)
        norm.append(im.convert("RGBA"))
    buf = io.BytesIO()
    norm[0].save(
        buf,
        format="WEBP",
        save_all=True,
        append_images=norm[1:],
        duration=max(50, int(duration_ms)),
        loop=int(loop),
        quality=int(quality),
        method=4,
    )
    return buf.getvalue()


def frames_to_data_url(
    frames: Sequence[Any],
    *,
    fmt: str = "gif",
    duration_ms: int = 400,
) -> dict:
    """Return {mime_type, image_base64, bytes, frame_count, format}."""
    fmt = (fmt or "gif").lower().strip()
    if fmt == "webp":
        raw = frames_to_webp_bytes(frames, duration_ms=duration_ms)
        mime = "image/webp"
    else:
        raw = frames_to_gif_bytes(frames, duration_ms=duration_ms)
        mime = "image/gif"
        fmt = "gif"
    return {
        "format": fmt,
        "mime_type": mime,
        "image_base64": base64.b64encode(raw).decode("ascii"),
        "bytes": len(raw),
        "frame_count": len(frames),
        "duration_ms": duration_ms,
    }


def demo():
    # synthetic two-frame
    import numpy as np
    frames = []
    for i, col in enumerate([(40, 80, 160), (200, 100, 40)]):
        im = Image.new("RGB", (64, 48), col)
        buf = io.BytesIO()
        im.save(buf, format="PNG")
        frames.append({"image_base64": base64.b64encode(buf.getvalue()).decode("ascii")})
    out = frames_to_data_url(frames, fmt="gif", duration_ms=200)
    path = "/tmp/si_demo.gif"
    with open(path, "wb") as f:
        f.write(base64.b64decode(out["image_base64"]))
    print("wrote", path, out["bytes"], "bytes", out["frame_count"], "frames")


if __name__ == "__main__":
    demo()
