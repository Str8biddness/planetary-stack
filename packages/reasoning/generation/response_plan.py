# core/generation/response_plan.py
from dataclasses import dataclass, field
from typing import List, Optional

@dataclass
class ResponsePlan:
    """Structured response plan for the probabilistic decoder."""
    intent: str                        # e.g. 'inform', 'clarify', 'warn', 'gm_dialogue'
    style: str                         # e.g. 'formal', 'casual', 'empathic', 'terse'
    safety_level: float                # 0.0 (open) to 1.0 (maximum safe)
    target_length: int                 # target token count for output
    personality: List[str] = field(default_factory=list)             # traits, voice directives, bio snippets
    key_points: List[str] = field(default_factory=list)              # must appear in generated output
    required_phrases: List[str] = field(default_factory=list)        # verbatim anchors
    forbidden_phrases: List[str] = field(default_factory=list)       # hard-stop blacklist
    domain: str = "general"            # maps to PolicyPrior organ domain config
    decoder_mode: str = "stochastic"   # 'deterministic' | 'stochastic' | 'template+slots'

@dataclass
class GenerationConfig:
    """Sampling parameters for the probabilistic decoder."""
    temperature: float = 1.0           # 0.1 (deterministic) to 1.4 (creative)
    top_k: int = 50                    # restrict vocab to top-k tokens
    top_p: float = 1.0                 # nucleus sampling threshold
    max_tokens: int = 128              # hard cap on generation length
    repetition_penalty: float = 1.1    # discourages repeating prior tokens
    num_candidates: int = 1            # parallel decodes for risk evaluation
    seed: Optional[int] = None         # for deterministic replay

@dataclass
class GenerationTrace:
    """Trace and metadata for a completed generation."""
    text: str                          # final decoded text
    token_logprobs: List[float] = field(default_factory=list)        # per-token log-probability
    mean_logprob: float = 0.0          # average confidence signal
    constraints_satisfied: bool = True # all key_points + required_phrases present
    forbidden_triggered: bool = False  # True if any forbidden phrase was sampled
    decode_attempts: int = 1           # number of regeneration loops taken
    config_used: Optional[GenerationConfig] = None
