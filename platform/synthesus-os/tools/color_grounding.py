#!/usr/bin/env python3
"""
Color Grounding — Synthesus 5
Derive a concept's COLOR from real co-occurrence with colour words, instead of
hashing a word to an arbitrary hue. apple-near-red, sky-near-blue emerge from
statistics. Pure counting + PMI, no neural net.

    color(concept) = PMI-weighted blend of colour-anchor RGBs
"""
import sys, os, json, math
from pathlib import Path
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))
from geometric_refinery import GeometricRefinery

SHARD_DIR = Path("/home/dakin/dev/Synthesus_4.0/data/geometric_shards")
CORPUS_FILE = "data/corpus/color_corpus.txt"

# colour anchor words -> reference RGB
COLORS = {
    "red": (200, 35, 35), "crimson": (170, 20, 40), "scarlet": (205, 30, 25),
    "green": (40, 150, 55), "emerald": (20, 150, 90),
    "blue": (55, 95, 210), "azure": (75, 135, 220),
    "yellow": (230, 210, 45), "golden": (220, 180, 45), "gold": (220, 180, 45),
    "orange": (230, 140, 35),
    "purple": (140, 55, 190), "violet": (145, 85, 200),
    "brown": (120, 72, 32),
    "black": (28, 28, 30), "white": (235, 235, 235),
    "gray": (135, 135, 135), "grey": (135, 135, 135), "silver": (190, 190, 200),
    "pink": (235, 145, 175),
}


def build(tokens, window=6):
    counts, total = {}, len(tokens)
    for t in tokens:
        counts[t] = counts.get(t, 0) + 1
    cooc = {}                                   # cooc[word][color] = count
    for i, w in enumerate(tokens):
        lo, hi = max(0, i - window), min(total, i + window + 1)
        near = set()
        for j in range(lo, hi):
            if j != i and tokens[j] in COLORS:
                near.add(tokens[j])
        if near:
            d = cooc.setdefault(w, {})
            for c in near:
                d[c] = d.get(c, 0) + 1
    return counts, cooc, total


def color_of(word, counts, cooc, total):
    if word not in cooc:
        return None, {}
    weights = {}
    for c, n in cooc[word].items():
        # positive PMI: how much more than chance do word and colour co-occur
        pmi = math.log((n * total) / (counts[word] * counts[c]) + 1e-9)
        if pmi > 0:
            weights[c] = pmi * n            # weight by strength and evidence
    if not weights:
        return None, {}
    s = sum(weights.values())
    rgb = [0.0, 0.0, 0.0]
    for c, wt in weights.items():
        for k in range(3):
            rgb[k] += COLORS[c][k] * wt / s
    top = sorted(weights, key=weights.get, reverse=True)[:3]
    return tuple(int(round(x)) for x in rgb), {c: round(weights[c] / s, 2) for c in top}


if __name__ == "__main__":
    r = GeometricRefinery()
    toks = r.clean_and_tokenize(open(CORPUS_FILE, encoding="utf-8").read())
    counts, cooc, total = build(toks)
    print(f"corpus {total} tokens; mining colour associations\n")

    out = {}
    probes = ["apple", "sky", "grass", "blood", "sun", "rose", "snow", "night",
              "gold", "sea", "forest", "fire", "cloud", "emerald", "leaf", "hair",
              "eyes", "water", "wood", "silver", "coat", "cheeks"]
    print(f"{'concept':10} {'RGB':>16}   top colour drivers")
    for w in probes:
        rgb, drivers = color_of(w, counts, cooc, total)
        if rgb:
            out[w] = rgb
            print(f"  {w:9} {str(rgb):>16}   {drivers}")
        else:
            print(f"  {w:9} {'(no colour assoc.)':>16}")

    SHARD_DIR.mkdir(parents=True, exist_ok=True)
    json.dump({"metadata": {"source": "color_grounding.py", "space": "RGB"},
               "colors": out},
              open(SHARD_DIR / "color_grounding.kn", "w"), indent=2)
    print(f"\n💾 saved {SHARD_DIR/'color_grounding.kn'} ({len(out)} grounded colours)")
