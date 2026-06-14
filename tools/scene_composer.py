#!/usr/bin/env python3
"""
Scene Composer — Synthesus 5
The buildable core of the "pattern-based image generation" blueprint, fused with
our data-grounded colour system:

    text -> entities + attributes + relations   (decomposition)
         -> shape primitive per entity          (atomic visual vocabulary)
         -> vertical layout from relations       (scene graph)
         -> grounded colour per entity           (color_grounding.kn, from data)
         -> flat vector render                    (PIL)

No neural net. Honest ceiling: this makes simple *vector illustrations*
(coloured shapes laid out by relation), not photographs. Recognisable objects
need a learned visual model.
"""
import sys, os, json, math
from pathlib import Path
from PIL import Image, ImageDraw

sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))
SHARD_DIR = Path("/home/dakin/dev/Synthesus_4.0/data/geometric_shards")

# atomic visual vocabulary: entity -> primitive role
SHAPES = {
    "sky": "bg", "space": "bg", "night": "bg",
    "grass": "ground", "sea": "ground", "ocean": "ground", "water": "ground",
    "ground": "ground", "field": "ground", "snow": "ground", "sand": "ground",
    "sun": "disc_top", "moon": "disc_top", "cloud": "cloud_top", "star": "star_top",
    "apple": "disc", "ball": "disc", "orange": "disc", "rock": "disc", "stone": "disc",
    "tree": "tree", "mountain": "triangle", "hill": "triangle", "pyramid": "triangle",
    "house": "house", "fire": "triangle",
}
# colour adjectives -> RGB (for explicit "red apple")
ADJ = {"red": (200, 40, 40), "green": (50, 150, 60), "blue": (60, 100, 210),
       "yellow": (235, 210, 60), "orange": (235, 140, 40), "purple": (150, 60, 190),
       "white": (235, 235, 235), "black": (30, 30, 32), "gray": (135, 135, 135),
       "brown": (120, 72, 32), "pink": (235, 145, 175), "golden": (220, 180, 45),
       "gold": (220, 180, 45)}
DEFAULT = {"bg": (150, 195, 235), "ground": (95, 150, 80), "disc": (200, 60, 50),
           "disc_top": (240, 215, 70), "cloud_top": (235, 235, 240),
           "star_top": (245, 225, 90), "tree": (60, 120, 55),
           "triangle": (120, 110, 105), "house": (170, 90, 70)}


def load_colors():
    p = SHARD_DIR / "color_grounding.kn"
    return json.load(open(p))["colors"] if p.exists() else {}


def parse(text, grounded):
    toks = [t.strip(".,") for t in text.lower().split()]
    rel = next((r for r in ("on", "over", "above", "in", "under", "below") if r in toks), None)
    items = []
    for i, t in enumerate(toks):
        if t in SHAPES:
            color = None
            if i and toks[i - 1] in ADJ:                  # explicit "red apple"
                color = ADJ[toks[i - 1]]
            elif t in grounded:                            # data-grounded colour
                color = tuple(grounded[t])
            items.append({"entity": t, "role": SHAPES[t],
                          "color": color or DEFAULT.get(SHAPES[t], (150, 150, 150))})
    return items, rel


def render(text, size=420, out=None):
    grounded = load_colors()
    items, rel = parse(text, grounded)
    img = Image.new("RGB", (size, size), (245, 245, 245))
    d = ImageDraw.Draw(img)
    horizon = int(size * 0.68)

    # paint in scene-graph order: background, ground, then objects
    order = {"bg": 0, "ground": 1, "cloud_top": 2, "disc_top": 2, "star_top": 2}
    for it in sorted(items, key=lambda x: order.get(x["role"], 5)):
        role, c = it["role"], it["color"]
        if role == "bg":
            for y in range(size):                          # soft vertical gradient sky
                f = 0.75 + 0.25 * (y / size)
                d.line([(0, y), (size, y)], fill=tuple(int(v * f) for v in c))
        elif role == "ground":
            d.rectangle([0, horizon, size, size], fill=c)
        elif role == "disc_top":
            d.ellipse([size*0.62, size*0.10, size*0.62+90, size*0.10+90], fill=c)
        elif role in ("cloud_top", "star_top"):
            d.ellipse([size*0.18, size*0.14, size*0.18+120, size*0.14+60], fill=c)
        elif role == "disc":                               # object resting on ground
            r = 52
            d.ellipse([size/2-r, horizon-2*r, size/2+r, horizon], fill=c)
            d.rectangle([size/2-4, horizon-2*r-14, size/2+4, horizon-2*r], fill=(90, 60, 40))
        elif role == "triangle":
            d.polygon([(size/2-120, horizon), (size/2+120, horizon), (size/2, horizon-180)], fill=c)
        elif role == "tree":
            d.rectangle([size/2-12, horizon-70, size/2+12, horizon], fill=(110, 70, 40))
            d.ellipse([size/2-70, horizon-180, size/2+70, horizon-40], fill=c)
        elif role == "house":
            d.rectangle([size/2-80, horizon-110, size/2+80, horizon], fill=c)
            d.polygon([(size/2-95, horizon-110), (size/2+95, horizon-110), (size/2, horizon-185)],
                      fill=(150, 70, 55))
    out = out or "scene_" + "_".join(i["entity"] for i in items) + ".png"
    img.save(out)
    desc = ", ".join(f"{i['entity']}={i['color']}" for i in items)
    print(f"🖼  {out}  | entities: {desc} | relation: {rel}")
    return out


if __name__ == "__main__":
    render(" ".join(sys.argv[1:]) if len(sys.argv) > 1 else "a red apple on green grass")
