#!/usr/bin/env python3
"""
Dual-process image generation — Synthesus 5
===========================================

Wires the IMAGINATION hemisphere (Hopfield energy settling) to the pattern-based
image generator (tools/scene_composer.py):

  System 1 (imagination):  a vague / noisy visual cue -> Hopfield settles it into
                           the nearest grounded, RENDERABLE concept(s).
  System 2 (pattern-base):  scene_composer renders those concepts deterministically
                           (shape primitives + grounded colour + scene layout).

So the system "imagines what to draw" from an incomplete cue, then draws it.
The imagined concepts are recovered with the image-space batched fast path
(recall_batch), and the output is flagged as imagination (educated guess).

Run:  ./venv/bin/python packages/reasoning/vsa_imagine_image.py
"""
from __future__ import annotations
import os
import re
import sys

import numpy as np

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _HERE)
sys.path.insert(0, os.path.join(_HERE, "..", "..", "tools"))

from vsa_twolayer import cooccurrence, ppmi, svd_embed  # noqa: E402
from vsa_hopfield import ModernHopfield                 # noqa: E402
import scene_composer                                   # noqa: E402

# compact corpus grounding the RENDERABLE visual concepts in colour/scene context
VISUAL_CORPUS = """
the blue sky holds the bright sun and a white cloud above the green grass.
the red apple rests on the green grass under the blue sky.
the tall tree grows beside the green grass under the blue sky.
the grey mountain rises over the green grass under the blue sky.
the blue sea meets the yellow sand under the bright sun and blue sky.
the orange fire burns red and bright against the dark night.
the white moon and a bright star shine in the dark night sky.
the white snow covers the grey mountain under the pale sky.
the brown house stands on the green grass beside the tall tree.
sun and cloud and star sit in the sky; grass and sea and sand lie below.
the bright sun warms the blue sky while the green grass holds the red apple.
""".strip()

STOP = set("the a an and or of to in on under above below with sit lie sits lies "
           "holds rests grows rises meets burns shine shines covers stands warms "
           "while against bright pale dark below beside".split())


def tokenize(t):
    return [w for w in re.findall(r"[a-z]+", t.lower()) if w not in STOP]


def build():
    toks = tokenize(VISUAL_CORPUS)
    counts = {}
    for w in toks:
        counts[w] = counts.get(w, 0) + 1
    vocab = sorted(w for w, c in counts.items() if c >= 1)
    vidx = {w: i for i, w in enumerate(vocab)}
    E = svd_embed(ppmi(cooccurrence(toks, vidx, window=5)), min(32, len(vocab)))
    return E, vocab, vidx


def main():
    E, vocab, vidx = build()
    # attractors = grounded concepts the pattern-base can actually render
    renderable = [w for w in vocab if w in scene_composer.SHAPES]
    Xr = np.vstack([E[vidx[w]] for w in renderable])
    hop = ModernHopfield(Xr, renderable, beta=14.0)
    rng = np.random.default_rng(1)
    print(f"renderable grounded attractors: {renderable}\n")

    # each "scene" = a set of intended concepts; we corrupt them into vague cues
    scenes = [["apple", "grass"], ["sun", "sky", "cloud"], ["mountain", "grass", "sky"]]
    for intended in scenes:
        cues = []
        for c in intended:
            base = E[vidx[c]]
            n = rng.standard_normal(E.shape[1])
            n *= 0.6 / (np.linalg.norm(n) + 1e-9)        # vague cue (60% corruption)
            cues.append(base + n)
        settled = hop.recall_batch(np.vstack(cues))       # image-space fast path
        concepts = [lab for lab, _ in settled]
        text = " ".join(concepts)
        out = os.path.join(_HERE, "..", "..",
                           "imagined_" + "_".join(concepts) + ".png")
        scene_composer.render(text, out=os.path.abspath(out))
        ok = "OK" if concepts == intended else "~"
        print(f"  [{ok}] cue~{intended}  -> imagined {concepts}  "
              f"-> [educated guess] rendered\n")

    print("Dual-process: System-1 imagination (Hopfield) completes vague cues into\n"
          "renderable concepts; System-2 pattern-base renders them. Output flagged\n"
          "as imagination, grounded colours/shapes from data.")


if __name__ == "__main__":
    main()
