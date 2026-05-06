#include "ppbrs.hpp"
#include <sstream>
#include <algorithm>
#include <fstream>
namespace zo {
void PPBRS::add_pattern(const Pattern& p) { patterns_.push_back(p); }
void PPBRS::set_threshold(float t) { threshold_ = t; }
size_t PPBRS::pattern_count() const { return patterns_.size(); }
float PPBRS::score(const Pattern& p, const std::string& input) const {
    float s = 0.0f;
    for (auto& tok : p.tokens)
        if (input.find(tok) != std::string::npos) s += 1.0f;
    return (p.tokens.empty() ? 0.0f : s / p.tokens.size()) * p.weight;
}
PPBRSResult PPBRS::match(const std::string& input) const {
    PPBRSResult best;
    for (auto& p : patterns_) {
        float s = score(p, input);
        if (s > best.confidence) {
            best.confidence = s;
            best.matched_pattern = p.id;
            best.response = p.response_template;
            best.matched_tags = p.tags;
        }
    }
    if (best.confidence < threshold_) best.response = "";
    return best;
}
bool PPBRS::load_patterns(const std::string& json_path) {
    // Minimal JSON loader for pattern arrays
    // Full impl would use nlohmann::json or simdjson
    std::ifstream f(json_path);
    if (!f) return false;
    // TODO: implement full JSON parse - stub returns true if file opens
    return true;
}
} // namespace zo
