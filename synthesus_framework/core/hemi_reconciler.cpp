#include "hemi_reconciler.hpp"
#include <sstream>
#include <algorithm>
namespace zo {
bool HemiReconciler::responses_agree(const std::string& a, const std::string& b, float threshold) {
    if (a.empty() || b.empty()) return false;
    // Jaccard-style token overlap
    size_t matches = 0, total = 0;
    size_t i = 0, j = 0;
    while (i < a.size() && j < b.size()) {
        if (std::tolower(a[i]) == std::tolower(b[j])) { ++matches; ++i; ++j; }
        else if (a[i] < b[j]) ++i;
        else ++j;
        ++total;
    }
    total = std::max({a.size(), b.size(), (size_t)1});
    return (float)matches / total >= threshold;
}
HemiResult HemiReconciler::reconcile(const HemiInput& input) const {
    // Weighted combination: L=0.50, R=0.30, V=0.20
    float L_score = input.left_confidence * HEMI_L;
    float R_score = input.right_confidence * HEMI_R;
    float V_score = input.visual_confidence * HEMI_V;
    float total = L_score + R_score + V_score;
    // Check for triple agreement
    bool lr_agree = responses_agree(input.left_response, input.right_response);
    bool lv_agree = responses_agree(input.left_response, input.visual_response);
    bool rv_agree = responses_agree(input.right_response, input.visual_response);
    bool triple = lr_agree && lv_agree && rv_agree;
    float bonus = triple ? TRIPLE_AGREEMENT_BONUS : 0.0f;
    total += bonus;
    // Select best response weighted by adjusted scores
    std::string best_response;
    float best_score = -1;
    auto check = [&](const std::string& r, float s) {
        if (s > best_score) { best_score = s; best_response = r; }
    };
    check(input.left_response, L_score);
    check(input.right_response, R_score);
    check(input.visual_response, V_score);
    std::ostringstream trace;
    trace << "L=" << L_score << " R=" << R_score << " V=" << V_score
          << (triple ? " +TRIPLE_BONUS" : "") << " final=" << total;
    return {best_response, std::min(1.0f, total), triple, bonus, trace.str()};
}
} // namespace zo
