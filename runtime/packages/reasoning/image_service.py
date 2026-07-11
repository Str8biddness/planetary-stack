"""Synthesus image generation service (SI, not AI).

VSA / pattern-geometric text-to-image: a text request is reasoned into a
resolution-free scene graph, then rendered to an HD raster. Deterministic,
CPU-only, no diffusion, no neural weights — it renders concepts in its visual
vocabulary (``scene_composer.SHAPES``). Wraps the proven ``vsa_pipeline_image``
pipeline (see its ``main()``) as a reusable, cached service.
"""
from __future__ import annotations

import threading

import numpy as np

import scene_composer
from vsa_twolayer import cooccurrence, ppmi, svd_embed
from vsa_hopfield import ModernHopfield
import vsa_pipeline_image as vpi

# The imagination is grounded in the renderable vocabulary so unknown words can
# map to the nearest renderable concept. Built once, reused across requests.
_VOCAB = sorted(scene_composer.SHAPES.keys())
_lock = threading.Lock()
_state: dict | None = None


def renderable_vocabulary() -> list[str]:
    """The concepts this engine can render today (honest capability surface)."""
    return list(_VOCAB)


def _imagination():
    global _state
    if _state is None:
        with _lock:
            if _state is None:
                tk = [w for w in _VOCAB if w in scene_composer.SHAPES]
                vidx = {w: i for i, w in enumerate(sorted(set(tk)))}
                E = svd_embed(ppmi(cooccurrence(tk * 3, vidx, window=4)),
                              min(16, len(vidx)))
                imag = ModernHopfield(
                    np.vstack([E[vidx[w]] for w in vidx]), list(vidx), beta=12.0
                )
                _state = {"imag": imag, "vidx": vidx, "E": E}
    return _state


def generate_image(prompt: str, out_path: str, res: int = 1024) -> dict:
    """Reason ``prompt`` into a scene graph and render it to ``out_path`` (PNG).

    Returns real metadata (the entities that made it into the scene, resolution).
    Raises on failure — the caller degrades loudly (never a fabricated image).
    """
    if not prompt or not prompt.strip():
        raise ValueError("prompt is required")
    res = int(res)
    s = _imagination()
    doc, horizon = vpi.pattern_document(prompt, s["imag"], s["vidx"], s["E"])
    vpi.render_doc(doc, horizon, res=res, out=out_path)
    entities = [p.get("entity") for p in doc if isinstance(p, dict) and p.get("entity")]
    return {
        "prompt": prompt,
        "path": out_path,
        "resolution": res,
        "entities": entities,
        "entity_count": len(entities),
        "vocabulary_size": len(s["vidx"]),
    }


if __name__ == "__main__":
    import os, tempfile
    out = os.path.join(tempfile.gettempdir(), "synth_image_service_test.png")
    meta = generate_image("a house on a green hill under a bright sun with a tree", out)
    ok = os.path.exists(out) and os.path.getsize(out) > 1000
    print("meta:", meta)
    print("PNG written:", ok, os.path.getsize(out) if ok else 0, "bytes ->", out)
    assert ok, "no real PNG produced"
