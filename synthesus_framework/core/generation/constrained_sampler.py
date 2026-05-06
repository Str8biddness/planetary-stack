# core/generation/constrained_sampler.py
import math
import random
from typing import Dict, List, Set

def apply_temperature(dist: Dict[str, float], temperature: float) -> Dict[str, float]:
    """
    Scales probabilities by temperature.
    - T < 1.0: sharpens the distribution (more deterministic)
    - T > 1.0: flattens the distribution (more creative)
    """
    if not dist or temperature <= 0:
        return dist
        
    if temperature == 1.0:
        return dist

    # Scale probabilities via log-space (logits)
    scaled = {}
    for token, prob in dist.items():
        # Use log(p) / T to scale
        p = max(prob, 1e-10) # Avoid log(0)
        scaled[token] = math.exp(math.log(p) / temperature)
        
    # Re-normalize
    total = sum(scaled.values())
    if total == 0:
        return dist
    return {k: v / total for k, v in scaled.items()}

def top_k_filter(dist: Dict[str, float], k: int) -> Dict[str, float]:
    """Restricts distribution to the top-k most likely tokens."""
    if not dist or k <= 0 or k >= len(dist):
        return dist
        
    sorted_items = sorted(dist.items(), key=lambda x: x[1], reverse=True)
    top_k_items = []
    # Safeguard against indexing beyond list length
    for i in range(min(k, len(sorted_items))):
        top_k_items.append(sorted_items[i])
    
    # Re-normalize
    total = sum(item[1] for item in top_k_items)
    if total == 0:
        return dist
    return {k: v / total for k, v in top_k_items}

def top_p_filter(dist: Dict[str, float], p: float) -> Dict[str, float]:
    """
    Nucleus sampling: restricts to the smallest set of tokens 
    whose cumulative probability exceeds p.
    """
    if not dist or p >= 1.0 or p <= 0:
        return dist
        
    sorted_items = sorted(dist.items(), key=lambda x: x[1], reverse=True)
    
    cumulative_prob = 0.0
    keep_count = 0
    for item in sorted_items:
        cumulative_prob += item[1]
        keep_count += 1
        if cumulative_prob >= p:
            break
            
    # Using explicit loop
    top_p_items = []
    for i in range(keep_count):
        top_p_items.append(sorted_items[i])
    
    # Re-normalize
    total = sum(item[1] for item in top_p_items)
    if total == 0:
        return dist
    return {k: v / total for k, v in top_p_items}

def apply_repetition_penalty(dist: Dict[str, float], generated_tokens: List[str], penalty: float) -> Dict[str, float]:
    """
    Penalizes tokens that have already been generated to encourage variety.
    Penalty should be > 1.0.
    """
    if not dist or penalty <= 1.0 or not generated_tokens:
        return dist
        
    penalized = {}
    seen = set(generated_tokens)
    for token, prob in dist.items():
        if token in seen:
            penalized[token] = prob / penalty
        else:
            penalized[token] = prob
            
    # Re-normalize
    total = sum(penalized.values())
    if total == 0:
        return dist
    return {k: v / total for k, v in penalized.items()}

def mask_forbidden_tokens(dist: Dict[str, float], forbidden_phrases: List[str], current_context: List[str]) -> Dict[str, float]:
    """
    Zeroes out probabilities of tokens that would complete a forbidden phrase.
    """
    if not dist or not forbidden_phrases:
        return dist
        
    masked = dist.copy()
    context_str = " ".join(current_context).lower()
    
    for token in dist.keys():
        # Check if adding this token completes or continues a forbidden phrase
        # We check trailing content + token
        candidate = f"{context_str} {token}".strip()
        for phrase in forbidden_phrases:
            if phrase.lower() in candidate:
                masked[token] = 0.0
                
    # Re-normalize if any were masked
    total = sum(masked.values())
    if total == 0:
        # Return empty dict if everything is masked to signal dead end
        return {}
    return {k: v / total for k, v in masked.items()}

def sample_token(dist: Dict[str, float]) -> str:
    """Randomly samples a single token from the probability distribution."""
    if not dist:
        return ""
    
    tokens = list(dist.keys())
    weights = list(dist.values())
    
    # random.choices uses weights and returns a list
    return random.choices(tokens, weights=weights, k=1)[0]
