# core/generation/decoder.py
import os
import math
from typing import List, Optional, Dict
from .response_plan import ResponsePlan, GenerationConfig, GenerationTrace
from .ngram_model import NgramModel
from .constrained_sampler import (
    apply_temperature, top_k_filter, top_p_filter, 
    apply_repetition_penalty, mask_forbidden_tokens, sample_token
)

# Global cache to avoid redundant PKL loads
MODEL_CACHE: Dict[str, NgramModel] = {}
MODELS_DIR = os.environ.get("GENERATION_MODELS_DIR", "data/models")


def set_models_dir(models_dir: str) -> None:
    """Configure the base directory used to load generation vocab models."""
    global MODELS_DIR, MODEL_CACHE
    MODELS_DIR = models_dir or "data/models"
    # Clear cache so domain models are reloaded from the updated path.
    MODEL_CACHE = {}


def _candidate_paths(domain: str) -> List[str]:
    return [
        os.path.join(MODELS_DIR, f"vocab_{domain}.pkl"),
        os.path.join(MODELS_DIR, "vocab_general.pkl"),
        f"data/vocab_{domain}.pkl",
        "data/vocab_general.pkl",
    ]

def get_model(domain: str) -> Optional[NgramModel]:
    """Retrieves or loads an NgramModel for the given domain."""
    if domain in MODEL_CACHE:
        return MODEL_CACHE[domain]

    for path in _candidate_paths(domain):
        if os.path.exists(path):
            try:
                model = NgramModel.load(path)
                MODEL_CACHE[domain] = model
                return model
            except Exception:
                continue
    return None

def decode_response(plan: ResponsePlan, config: GenerationConfig) -> GenerationTrace:
    """
    Autoregressive decoding loop that generates text from an N-gram model.
    Handles multiple candidate generations to satisfy constraints.
    """
    model = get_model(plan.domain)
    if not model:
        return GenerationTrace(
            text="[ERROR: No generation model available]", 
            constraints_satisfied=False
        )

    best_trace: Optional[GenerationTrace] = None

    
    # Try multiple candidates if requested (useful for risk-averse settings)
    for attempt in range(max(1, config.num_candidates)):
        tokens: List[str] = []
        logprobs: List[float] = []
        
        # Soft-prompt context (intent + style + personality traits)
        context = [plan.intent]
        if plan.style != "default":
            context.append(plan.style)
        context.extend(plan.personality)
        
        for i in range(config.max_tokens):
            # Get next-token distribution from n-gram model
            dist = model.get_distribution(context + tokens)
            if not dist:
                break
                
            # Applying constraints and sampling filters
            dist = apply_temperature(dist, config.temperature)
            dist = top_k_filter(dist, config.top_k)
            dist = top_p_filter(dist, config.top_p)
            dist = apply_repetition_penalty(dist, tokens, config.repetition_penalty)
            
            # Content Safety / Forbidden Masking
            dist = mask_forbidden_tokens(dist, plan.forbidden_phrases, context + tokens)
            
            if not dist:
                # If all paths are masked by forbidden phrases, try to fallback
                # or just break if we are at a dead end
                break
                
            token = sample_token(dist)
            if not token:
                break
                
            tokens.append(token)
            # Log probability as a confidence signal
            prob = max(dist.get(token, 1e-10), 1e-10)
            logprobs.append(math.log(prob))
            
            # Stop condition: sentence ending near target length
            if token in (".", "!", "?") and len(tokens) >= plan.target_length:
                break
                
            # Safety break for massive generations
            if i > config.max_tokens:
                break

        # Join tokens and perform basic punctuation cleaning
        text = " ".join(tokens)
        text = text.replace(" .", ".").replace(" ,", ",").replace(" !", "!").replace(" ?", "?")
        text = text.replace(" ' ", "'").replace("  ", " ").strip()
        
        # Constraint validation
        all_points_present = True
        for kp in plan.key_points:
            # Simple substring check for key points
            if kp.lower() not in text.lower():
                all_points_present = False
                break
        
        trace = GenerationTrace(
            text=text if text else "[Generation produced empty output]",
            token_logprobs=logprobs,
            mean_logprob=sum(logprobs) / len(logprobs) if logprobs else -20.0,
            constraints_satisfied=all_points_present,
            decode_attempts=attempt + 1,
            config_used=config
        )
        
        # Selection logic: prioritize constraint satisfaction, then confidence
        if best_trace is None:
            best_trace = trace
        else:
            # We have a candidate, compare it to the current best
            # 1. New trace is better if it satisfies constraints while best doesn't
            if trace.constraints_satisfied and not best_trace.constraints_satisfied:
                best_trace = trace
            # 2. Both satisfy, pick higher probability
            elif trace.constraints_satisfied and best_trace.constraints_satisfied:
                if trace.mean_logprob > best_trace.mean_logprob:
                    best_trace = trace
            # 3. Neither satisfy, pick higher probability (least bad)
            elif not trace.constraints_satisfied and not best_trace.constraints_satisfied:
                if trace.mean_logprob > best_trace.mean_logprob:
                    best_trace = trace
            
        # Early exit if we found a perfect candidate
        if trace.constraints_satisfied:
            break

    return best_trace if best_trace else GenerationTrace(text="[Generation Failed]", constraints_satisfied=False)
