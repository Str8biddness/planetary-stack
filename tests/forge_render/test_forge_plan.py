import pytest
import sys
from pathlib import Path

# Add paths for imports
root = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(root))
sys.path.insert(0, str(root / "apps" / "synthesus" / "desktop"))
sys.path.insert(0, str(root / "apps" / "synthesus" / "runtime" / "packages"))
sys.path.insert(0, str(root / "apps" / "synthesus" / "runtime" / "packages" / "reasoning"))

from apps.synthesus.runtime.packages.reasoning.image_intent import classify_intent
from forge_compiler import prompt_to_recipe_v2
from services.forge_render.engine import RecipeV2

def test_intent_routing():
    # SI prompts -> draw
    draw_intent = classify_intent("draw a house")
    assert draw_intent["mode"] == "draw"

    # Forge prompts -> forge
    forge_intent = classify_intent("/forge a gyroid")
    assert forge_intent["mode"] == "forge"
    assert forge_intent["prompt"] == "a gyroid"

def test_prompt_determinism():
    # same prompt -> same graph
    r1 = prompt_to_recipe_v2("a gyroid at midnight")
    r2 = prompt_to_recipe_v2("a gyroid at midnight")
    
    # same graph, same recipe
    assert r1.to_code() == r2.to_code()
    
    # "at midnight" should set palette=2
    assert r1.palette == 2

def test_prompt_combinators():
    # multiple primitives should create union
    r = prompt_to_recipe_v2("a box and a sphere")
    assert len(r.nodes) > 1
    
    # root should be the union or transform
    assert r.nodes[r.root].op in (23, 48, 45, 46)

def test_modifiers():
    # repeat
    r = prompt_to_recipe_v2("a box repeat")
    assert r.nodes[r.root].op == 48
    
    # twist
    r2 = prompt_to_recipe_v2("a box twist")
    assert r2.nodes[r2.root].op == 45
    
    # bend
    r3 = prompt_to_recipe_v2("a box bend")
    assert r3.nodes[r3.root].op == 46
