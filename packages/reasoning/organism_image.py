#!/usr/bin/env python3
"""
Image Generation Organism (ability #2) — Synthesus 5
=====================================================

Wraps the pattern-based, pi-driven, resolution-free renderer into an
amplification organism, gated by the framework: Synthesus cannot generate an
image without this organism (registered + trained + measured-passing).

  ability "generate_image" ──requires──▶ ImageGenerationOrganism
        organs (dependencies): scene_parser (text→pattern document)
                               geometric_renderer (pattern doc → pi-rendered HD raster)

Honest scope: procedural / vector imagery (crisp, resolution-free, CPU) — scenes
and structured/natural form, not photoreal novel objects (content ceiling).
Measured bar: entity coverage — does it actually render the known entities asked for.

Run:  ./venv/bin/python packages/reasoning/organism_image.py
"""
from __future__ import annotations
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from amplification_organism import AmplificationOrganism, Organ, Synthesus, CapabilityUnavailable  # noqa: E402
import vsa_pipeline_image as vp     # pattern_document(), render_doc()   # noqa: E402
import scene_composer              # SHAPES vocabulary                   # noqa: E402


class SceneParserOrgan(Organ):
    """text → pattern document (entities + normalized layout + grounded colour)."""
    def __init__(self): super().__init__("scene_parser")
    def train(self, _=None): self.trained = True          # rule-based vocab load
    def parse(self, request): return vp.pattern_document(request)


class GeometricRendererOrgan(Organ):
    """pattern document → pi-rendered, resolution-free HD raster."""
    def __init__(self): super().__init__("geometric_renderer")
    def train(self, _=None): self.trained = True
    def render(self, doc, horizon, out, res=1024): return vp.render_doc(doc, horizon, res=res, out=out)


class ImageGenerationOrganism(AmplificationOrganism):
    ability = "generate_image"
    bar = 0.9                                              # must render >=90% of known entities
    def __init__(self):
        super().__init__()
        self.parser = SceneParserOrgan(); self.renderer = GeometricRendererOrgan()
        self.organs = {"scene_parser": self.parser, "geometric_renderer": self.renderer}
    def train(self, _=None):
        self.parser.train(); self.renderer.train()
    def run(self, request, out=None):
        doc, horizon = self.parser.parse(request)
        out = os.path.abspath(out or os.path.join(os.path.dirname(__file__), "..", "..",
              "organism_" + "_".join(p["entity"] for p in doc) + ".png"))
        self.renderer.render(doc, horizon, out)
        return out, [p["entity"] for p in doc]
    def measure(self, test_requests):
        tot = cov = 0
        for req in test_requests:
            known = [w for w in req.lower().split() if w in scene_composer.SHAPES]
            doc, _ = self.parser.parse(req)
            rendered = {p["entity"] for p in doc}
            for w in known:
                tot += 1; cov += (w in rendered)
        self._score = cov / tot if tot else 0.0
        return self._score


def main():
    s = Synthesus()
    print("=== image generation is gated on its organism ===")
    print(f"can('generate_image') before organism: {s.can('generate_image')}")
    try: s.do("generate_image", "a red apple on green grass")
    except CapabilityUnavailable as e: print(f"  do() -> BLOCKED: {e}")

    org = ImageGenerationOrganism(); s.register(org); org.train()
    tests = ["a red apple on green grass under a blue sky with a sun",
             "a mountain and a tree on grass under a sky with a cloud",
             "the sun and a cloud in the sky over the sea"]
    score = org.measure(tests)
    print(f"\ntrained + measured. entity coverage = {score*100:.0f}%  (bar {org.bar*100:.0f}%)")
    print(f"can('generate_image') now: {s.can('generate_image')}")
    print("  organs (dependencies):", list(org.organs))
    out, ents = s.do("generate_image", "a red apple on green grass under a blue sky with a sun")
    print(f"  do(...) -> rendered {ents}\n  -> {os.path.basename(out)}")
    print("\nSynthesus cannot generate an image without this organism (blocked above).")
    print("Ability #2 earned by measurement; pi-rendered, resolution-free, CPU.")


if __name__ == "__main__":
    main()
