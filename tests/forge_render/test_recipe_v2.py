import pytest
import hashlib
from pathlib import Path
from services.forge_render import Recipe, render_full
from services.forge_render.engine import RecipeV2, NodeV2, render_full_v2, render_tile_v2
from services.forge_render.engine import native_available

FIXTURE_DIR = Path(__file__).parent / "fixtures"

def _digest(surface) -> str:
    return hashlib.sha256(bytes(surface.data)).hexdigest()

def test_v1_byte_identity():
    recipes = [
        Recipe(mode=0, hue=285, glow=60, palette=0),
        Recipe(mode=1, hue=300, glow=40, palette=1),
        Recipe(mode=2, hue=320, glow=20, palette=2),
        Recipe(mode=3, hue=260, glow=80, palette=3),
    ]

    for i, rc in enumerate(recipes):
        surf = render_full(rc, 32, 32, quality=16)
        with open(FIXTURE_DIR / f"v1_rc_{i}.bin", "rb") as f:
            expected = f.read()
        assert bytes(surf.data) == expected, f"v1 byte identity failed for recipe {i}"

def test_sf2_roundtrip():
    nodes = [
        NodeV2(op=0, p=(1.0, 0, 0, 0, 0, 0)),
        NodeV2(op=40, a=0, p=(0.5, 0.5, 0.5, 0, 0, 0))
    ]
    rc = RecipeV2(nodes=nodes, root=1, hue=300, glow=50, palette=1, cam=40)
    code = rc.to_code()
    
    assert code.startswith("SF2.")
    rc2 = RecipeV2.from_code(code)
    
    assert len(rc2.nodes) == 2
    assert rc2.nodes[0].op == 0
    assert rc2.nodes[1].a == 0
    assert rc2.root == 1
    assert rc2.hue == 300

def test_malformed_codes_rejected():
    with pytest.raises(ValueError, match="not an SF2 recipe code"):
        RecipeV2.from_code("SF1.0.6.35.285.60.0.42")
    with pytest.raises(ValueError, match="invalid base64 encoding"):
        RecipeV2.from_code("SF2.invalid!!")
    with pytest.raises(ValueError, match="data too short"):
        RecipeV2.from_code("SF2.abcd")

def test_graph_validation_rejected():
    # Forward/self child reference
    with pytest.raises(ValueError, match="invalid child a index"):
        RecipeV2(nodes=[NodeV2(op=20, a=1), NodeV2(op=0)], root=0)
    
    # Self reference
    with pytest.raises(ValueError, match="invalid child a index"):
        RecipeV2(nodes=[NodeV2(op=20, a=0)], root=0)

    # Unknown op
    with pytest.raises(ValueError, match="unknown op code"):
        RecipeV2(nodes=[NodeV2(op=999)], root=0)

    # Oversized graph
    with pytest.raises(ValueError, match="invalid node count"):
        RecipeV2(nodes=[NodeV2(op=0) for _ in range(65)], root=0)

@pytest.mark.skipif(not native_available(), reason="native core not built")
def test_determinism():
    nodes = [
        NodeV2(op=0, p=(1.0, 0, 0, 0, 0, 0)),
        NodeV2(op=40, a=0, p=(0.5, 0.5, 0.5, 0, 0, 0))
    ]
    rc = RecipeV2(nodes=nodes, root=1)
    s1 = render_full_v2(rc, 32, 32, quality=16)
    s2 = render_full_v2(rc, 32, 32, quality=16)
    assert _digest(s1) == _digest(s2)

@pytest.mark.skipif(not native_available(), reason="native core not built")
def test_tile_whole_frame_agreement():
    nodes = [NodeV2(op=0, p=(1.0, 0, 0, 0, 0, 0))]
    rc = RecipeV2(nodes=nodes, root=0)
    full = render_full_v2(rc, 32, 32, quality=16)
    tile = render_tile_v2(rc, 32, 32, (0, 0, 16, 32), quality=16)
    for y in range(32):
        for x in range(16):
            assert tile.px(x, y) == full.px(x, y)

def test_native_missing_refusal(monkeypatch):
    import services.forge_render.engine as engine
    monkeypatch.setattr(engine, "_native", lambda: None)
    
    nodes = [NodeV2(op=0, p=(1.0, 0, 0, 0, 0, 0))]
    rc = RecipeV2(nodes=nodes, root=0)
    with pytest.raises(RuntimeError, match="native core is missing"):
        render_full_v2(rc, 32, 32)
