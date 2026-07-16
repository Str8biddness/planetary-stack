from typing import Dict, Any, List
import logging
from conscious_state import FluidState, CrystallizedState, NarrativeState, IntegratedConsciousnessState

logger = logging.getLogger(__name__)

class ConsciousnessIntegrator:
    """
    Computes the C(t) Consciousness State equation:
    C(t) = Psi_f(t) ⊕ M_c(t) ⊕ N_s(t)
    
    Treats ⊕ as a dynamic fusion function.
    """
    def __init__(self):
        # In a full neural deployment, this would load ML weights.
        # For this implementation, we use deterministic heuristics based on the architectural spec.
        self.params = {
            "fluid_weight_base": 0.4,
            "crystal_weight_base": 0.3,
            "narrative_weight_base": 0.3
        }

    def _encode_fluid(self, state: FluidState, params: Dict) -> Dict[str, float]:
        """Projects fluid state into a latent space (simulated)."""
        salience = state.novelty_score + state.uncertainty
        if hasattr(state, 'active_hypotheses') and state.active_hypotheses:
            salience += 0.2
        return {"weight_modifier": min(0.5, salience), "emotion_push": "alert" if salience > 0.5 else "calm"}

    def _encode_crystal(self, state: CrystallizedState, params: Dict) -> Dict[str, float]:
        """Projects crystallized state into a latent space (simulated)."""
        stability = sum(state.traits.values()) / max(1, len(state.traits)) if state.traits else 0.5
        return {"weight_modifier": stability * 0.2, "motive_push": "adhere_to_traits"}

    def _encode_narrative(self, state: NarrativeState, params: Dict) -> Dict[str, float]:
        """Projects narrative state into a latent space (simulated)."""
        arousal = state.emotional_tone.get("arousal", 0.5)
        return {"weight_modifier": arousal * 0.3, "emotion_push": "anxious" if arousal > 0.7 else "focused"}

    def integrate(self, fluid: FluidState, crystal: CrystallizedState, narrative: NarrativeState, t: int) -> IntegratedConsciousnessState:
        """
        Fuses the three states to produce C(t).
        """
        # Feature Extraction
        z_f = self._encode_fluid(fluid, self.params)
        z_m = self._encode_crystal(crystal, self.params)
        z_n = self._encode_narrative(narrative, self.params)

        # Attention-style dynamic weighting (Softmax approximation)
        w_f = self.params["fluid_weight_base"] + z_f["weight_modifier"]
        w_m = self.params["crystal_weight_base"] + z_m["weight_modifier"]
        w_n = self.params["narrative_weight_base"] + z_n["weight_modifier"]
        
        total_w = w_f + w_m + w_n
        w_f, w_m, w_n = w_f / total_w, w_m / total_w, w_n / total_w

        # Fusion & Decoding into C(t)
        c_t = IntegratedConsciousnessState(t=t)
        
        # 1. Determine Dominant Emotion
        if w_f > w_n:
            c_t.dominant_emotion = z_f["emotion_push"]
        else:
            c_t.dominant_emotion = z_n["emotion_push"]

        # 2. Determine Action Biases
        action_biases = []
        if fluid.active_hypotheses:
            action_biases.append({"action": "investigate_anomaly", "weight": w_f * 0.9})
        if narrative.goals:
            action_biases.append({"action": "pursue_goal", "weight": w_n * 0.8})
        
        c_t.action_biases = sorted(action_biases, key=lambda x: x["weight"], reverse=True)
        
        # 3. Confidence
        c_t.confidence = 1.0 - (fluid.uncertainty * w_f)
        
        # 4. Update Directives (What to learn/forget)
        if fluid.novelty_score > 0.7:
            c_t.update_directives["memory"]["should_store_episode"] = True
            c_t.update_directives["memory"]["promote_to_crystal"] = fluid.active_hypotheses[:1]
        
        logger.debug(f"[Consciousness Integrator] t={t} Fused States: W_f={w_f:.2f}, W_m={w_m:.2f}, W_n={w_n:.2f}")

        return c_t
