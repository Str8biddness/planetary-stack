#pragma once
// Synthesus 2.0 - EmotionVCU: affective state modeling (valence/arousal)
#include "vcu_base.hpp"
#include <string>
namespace zo {
struct EmotionState {
    float valence = 0.0f;   // -1 (negative) to +1 (positive)
    float arousal = 0.5f;   // 0 (calm) to 1 (excited)
    std::string dominant = "neutral";
};
class EmotionVCU : public VCUBase {
public:
    EmotionVCU() : VCUBase("emotion") {}
    VCUOutput process(const VCUInput& in) override;
    EmotionState get_state() const { return state_; }
    void set_state(float v, float a);
    std::string classify(float valence, float arousal) const;
private:
    EmotionState state_;
    float decay_rate_ = 0.05f;
};
} // namespace zo