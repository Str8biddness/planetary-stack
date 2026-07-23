import re
from services.forge_render.engine import RecipeV2, NodeV2
from apps.synthesus.runtime.packages.reasoning.scene_plan import _mood_from_prompt

def prompt_to_recipe_v2(prompt: str) -> RecipeV2:
    hue = 285
    glow = 60
    palette = 0
    cam = 42
    
    mood = _mood_from_prompt(prompt)
    if mood:
        tod = mood.get("time_of_day")
        if tod == 0.95 or mood.get("style") == "night":
            palette = 2
            glow = 80
        elif tod == 0.18:
            palette = 1
            hue = 300
        elif tod == 0.82:
            palette = 1
            hue = 359
            glow = 70
            
        look = mood.get("look")
        if look == "cinema":
            cam = 35
        elif look == "vivid":
            hue = (hue + 45) % 360
        elif look == "tv":
            cam = 48
            
    nodes = []
    text = prompt.lower()
    
    primitives = {
        "sphere": (0, (1.0, 0, 0, 0, 0, 0)),
        "box": (1, (0.8, 0.8, 0.8, 0, 0, 0)),
        "cube": (1, (0.8, 0.8, 0.8, 0, 0, 0)),
        "torus": (2, (1.0, 0.3, 0, 0, 0, 0)),
        "capsule": (3, (0.8, 0.3, 0, 0, 0, 0)),
        "cylinder": (4, (0.8, 0.3, 0, 0, 0, 0)),
        "cone": (5, (1.0, 0.8, 0, 0, 0, 0)),
        "octahedron": (6, (1.0, 0, 0, 0, 0, 0)),
        "prism": (7, (0.8, 0.5, 0, 0, 0, 0)),
        "plane": (8, (0.0, 0, 0, 0, 0, 0)),
        "menger": (60, (4, 0, 0, 0, 0, 0)),
        "sponge": (60, (4, 0, 0, 0, 0, 0)),
        "gyroid": (61, (3.0, 0.05, 0, 0, 0, 0)),
        "lattice": (61, (3.0, 0.05, 0, 0, 0, 0)),
        "mandelbulb": (62, (5, 8.0, 0, 0, 0, 0)),
        "fractal": (62, (5, 8.0, 0, 0, 0, 0)),
        "apollonian": (63, (6, 1.2, 0, 0, 0, 0)),
    }
    
    found_prims = []
    # Collect all primitives mentioned in prompt, preserving order roughly by just iterating text? 
    # Or just iterate primitives.
    # To be deterministic, order matters. Let's sort keys and find first match indices
    matches = []
    for k, v in primitives.items():
        for m in re.finditer(r"\b" + k + r"\b", text):
            matches.append((m.start(), v))
    
    matches.sort(key=lambda x: x[0])
    for _, v in matches:
        if v not in found_prims:
            found_prims.append(v)
            
    if not found_prims:
        found_prims.append(primitives["sphere"])
        
    for p_op, p_args in found_prims:
        nodes.append(NodeV2(op=p_op, p=p_args))
        
    root = 0
    if len(nodes) > 1:
        current_root = 0
        for i in range(1, len(found_prims)):
            x_off = i * 1.5 - (len(found_prims)-1)*0.75
            t_node = NodeV2(op=40, a=i, p=(x_off, 0, 0, 0, 0, 0))
            nodes.append(t_node)
            t_idx = len(nodes) - 1
            
            u_node = NodeV2(op=23, a=current_root, b=t_idx, p=(0.3, 0, 0, 0, 0, 0))
            nodes.append(u_node)
            current_root = len(nodes) - 1
            
        root = current_root

    if re.search(r"\b(repeat|grid|tile)\b", text):
        nodes.append(NodeV2(op=48, a=root, p=(4.0, 0, 4.0, 0, 0, 0)))
        root = len(nodes) - 1
        
    if re.search(r"\b(twist)\b", text):
        nodes.append(NodeV2(op=45, a=root, p=(2.0, 0, 0, 0, 0, 0)))
        root = len(nodes) - 1

    if re.search(r"\b(bend)\b", text):
        nodes.append(NodeV2(op=46, a=root, p=(1.5, 0, 0, 0, 0, 0)))
        root = len(nodes) - 1

    return RecipeV2(
        nodes=nodes,
        root=root,
        hue=hue,
        glow=glow,
        palette=palette,
        cam=cam
    )
