import os
import hashlib
from pathlib import Path
import sys

# Ensure services module is available
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from services.forge_render import Recipe, render_full

fixture_dir = Path(__file__).parent / "fixtures"
fixture_dir.mkdir(parents=True, exist_ok=True)

recipes = [
    Recipe(mode=0, hue=285, glow=60, palette=0),
    Recipe(mode=1, hue=300, glow=40, palette=1),
    Recipe(mode=2, hue=320, glow=20, palette=2),
    Recipe(mode=3, hue=260, glow=80, palette=3),
]

for i, rc in enumerate(recipes):
    surf = render_full(rc, 32, 32, quality=16)
    with open(fixture_dir / f"v1_rc_{i}.bin", "wb") as f:
        f.write(surf.data)

print(f"Generated {len(recipes)} fixtures.")
