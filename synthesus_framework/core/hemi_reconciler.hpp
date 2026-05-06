#pragma once
// Synthesus 2.0 Phase 7 - HemiReconciler: left/right/visual hemisphere fusion
// L=0.50 / R=0.30 / V=0.20 + TRIPLE_AGREEMENT_BONUS=0.25
#include <string>
#include <vector>
namespace zo {
constexpr float HEMI_L = 0.50f;  // Left hemisphere weight (analytical)
constexpr float HEMI_R = 0.30f;  // Right hemisphere weight (pattern/creative)
constexpr float HEMI_V = 0.20f;  // Visual/vehicular weight
constexpr float TRIPLE_AGREEMENT_BONUS = 0.25f;
struct HemiInput {
    std::string left_response;   float left_confidence;
    std::string right_response;  float right_confidence;
    std::string visual_response; float visual_confidence;
};
struct HemiResult {
    std::string final_response;
    float final_confidence;
    bool triple_agreement;
    float bonus_applied;
    std::string reasoning_trace;
};
class HemiReconciler {
public:
    HemiResult reconcile(const HemiInput& input) const;
    static bool responses_agree(const std::string& a, const std::string& b, float threshold = 0.7f);
};
} // namespace zo
