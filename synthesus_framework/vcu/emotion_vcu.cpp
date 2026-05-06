#include "emotion_vcu.hpp"
#include <cmath>
namespace zo {
std::string EmotionVCU::classify(float v, float a) const {
    if (v > 0.3f && a > 0.5f) return "joy";
    if (v > 0.3f && a <= 0.5f) return "contentment";
    if (v < -0.3f && a > 0.5f) return "anger";
    if (v < -0.3f && a <= 0.5f) return "sadness";
    if (std::abs(v) <= 0.3f && a > 0.7f) return "surprise";
    return "neutral";
}
void EmotionVCU::set_state(float v, float a) {
    state_.valence = std::max(-1.0f, std::min(1.0f, v));
    state_.arousal = std::max(0.0f, std::min(1.0f, a));
    state_.dominant = classify(state_.valence, state_.arousal);
}
VCUOutput EmotionVCU::process(const VCUInput& in) {
    state_.valence *= (1.0f - decay_rate_);
    state_.arousal = state_.arousal * (1.0f - decay_rate_) + 0.5f * decay_rate_;
    state_.dominant = classify(state_.valence, state_.arousal);
    VCUOutput out;
    out.vcu_id = "emotion";
    out.result = "[EMOT] " + state_.dominant;
    out.confidence = 0.75f;
    out.tags = {"emotion", state_.dominant};
    return out;
}
} // namespace zo