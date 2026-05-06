# core/generation/organ_param_mapper.py
from typing import Dict, Any, List
from .response_plan import ResponsePlan, GenerationConfig

def map_organs_to_config(organ_scores: Dict[str, float]) -> GenerationConfig:
    """
    Maps PolicyPrior, RiskOutcome, and Attention scores to a GenerationConfig.
    
    Rules:
    - PolicyPrior (S): higher safety/compliance (0.0-1.0) -> lower temperature, smaller top-p/k.
    - RiskOutcome (R): higher risk (0.0-1.0) -> more candidates, higher repetition penalty.
    - Attention (F): higher focus (0.0-1.0) -> longer max_tokens.
    """
    s = organ_scores.get("policy_prior", 0.5)
    r = organ_scores.get("risk_outcome", 0.1)
    f = organ_scores.get("attention", 0.5)

    # Temperature: 1.4 down to 0.2
    temperature = 1.4 - (s * 1.2)
    
    # Top-p: 1.0 down to 0.5
    top_p = 1.0 - (s * 0.5)
    
    # Top-k: 50 down to 5
    top_k = max(5, 50 - int(s * 45))
    
    # Repetition penalty: 1.0 up to 1.3
    repetition_penalty = 1.0 + (r * 0.3)
    
    # Number of candidates: 1 up to 5
    num_candidates = 1 + int(r * 4)
    
    # Max tokens: base 64 up to 192 (based on focus)
    max_tokens = int(64 * (1 + f * 2))

    # Domain Overrides (Optional refinement)
    # These would typically be handled at the build_response_plan level
    # but could influence baseline config here if needed.

    return GenerationConfig(
        temperature=max(0.1, temperature),
        top_k=top_k,
        top_p=max(0.1, top_p),
        repetition_penalty=repetition_penalty,
        num_candidates=num_candidates,
        max_tokens=max_tokens
    )

def build_response_plan(
    event_dict: Dict[str, Any], 
    organ_scores: Dict[str, float]
) -> ResponsePlan:
    """
    Constructs a ResponsePlan from narrative event data and current organ scores.
    """
    intent = event_dict.get("intent", "inform")
    style = event_dict.get("style", event_dict.get("role", "default"))
    domain = event_dict.get("domain", "general")
    
    # Extract key points from engine summaries, attention entities, or actions_taken
    key_points = event_dict.get("key_points", [])
    
    # Include tool results as key points
    actions = event_dict.get("actions_taken", [])
    for action in actions:
        if action.get("type") == "tool_use" or "result" in action:
            res = action.get("result", {})
            if isinstance(res, dict):
                content = res.get("context") or res.get("content") or (res.get("raw_result", {}).get("content") if isinstance(res.get("raw_result"), dict) else None)
                if content:
                    # Truncate content for key point
                    content_snippet = content[:200]
                    key_points.append(f"Tool {action.get('action') or 'use'} results: {content_snippet}")
                elif "description" in action:
                    key_points.append(action["description"])
            elif isinstance(res, str) and res:
                key_points.append(f"Action result: {res[:200]}")
            elif "description" in action:
                key_points.append(action["description"])

    if not key_points and "summary" in event_dict:
        key_points = [event_dict["summary"]]
        
    plan = ResponsePlan(
        intent=intent,
        style=style,
        safety_level=organ_scores.get("policy_prior", 0.5),
        target_length=64, # Base target
        personality=event_dict.get("personality", []),
        key_points=key_points,
        required_phrases=event_dict.get("required_phrases", []),
        forbidden_phrases=event_dict.get("forbidden_phrases", []),
        domain=domain
    )
    
    # Apply domain-specific overrides
    if domain == "gm_dialogue":
        plan.decoder_mode = "stochastic"
    elif domain == "sysops":
        plan.decoder_mode = "deterministic"
    else:
        plan.decoder_mode = "stochastic"
        
    return plan
