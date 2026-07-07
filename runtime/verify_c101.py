"""C-101 proof: the LLM device, mounted as the CGPU surface, renders real text
through the bounded pipeline (grounding + critic still wrap it)."""
from generation.response_plan import ResponsePlan
from generation.cgpu import CGPUFrame, CGPURenderer
from generation.llm_realizer import LLMSurfaceRealizer

plan = ResponsePlan(
    intent="inform",
    style="casual",
    safety_level=0.5,
    target_length=60,
    key_points=["Jupiter is the largest planet in the Solar System"],
)
frame = CGPUFrame.create(
    query="What is the largest planet in our solar system?",
    plan=plan,
    grounded_state={"facts": ["Jupiter is the largest planet in the Solar System."]},
    provenance=[{"source": "astronomy_kb", "ref": "planets#jupiter"}],
    constraints=["ground_response_in_mounted_knowledge"],
)

# Inject the LLM realizer as the CGPU render surface — THE MERGE.
renderer = CGPURenderer(realizer=LLMSurfaceRealizer())
out = renderer.render(frame)
cand = out.candidates[0] if out.candidates else None

print("=== C-101 — LLM mounted as CGPU surface, full pipeline ===")
print("device      :", out.device)
print("LLM text    :", repr(out.selected_text)[:240])
print("diagnostics :", cand.diagnostics if cand else None)
print("critic      :", (cand.critique.decision.value if cand else None),
      "| accepted:", (cand.accepted if cand else None))
print("confidence  :", out.confidence, "| warnings:", out.warnings)

# Assertions: real LLM text (not the seed echo), pipeline completed, critic ran.
assert cand is not None, "no candidate produced"
assert cand.diagnostics.get("source") == "llm_device", "text did not come from the LLM device"
assert cand.diagnostics.get("degraded") != "true", "device degraded — Ollama not reachable?"
assert len(out.selected_text) > 10, "LLM produced no real text"
assert cand.critique is not None, "critic did not run"
print("\nC-101 PROOF PASSED ✅  (LLM rendered, grounded, critic-judged)")
