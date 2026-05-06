#pragma once
// Synthesus 2.0 Phase 7 - PPBRS: Probabilistic Pattern-Based Reasoning System
// Core right hemisphere engine - pattern matching + probability weighting
#include <string>
#include <vector>
#include <unordered_map>
#include <functional>
namespace zo {
struct Pattern {
    std::string id;
    std::vector<std::string> tokens;
    float weight{1.0f};
    std::string response_template;
    std::vector<std::string> tags;
};
struct PPBRSResult {
    std::string response;
    float confidence{0.0f};
    std::string matched_pattern;
    std::vector<std::string> matched_tags;
};
class PPBRS {
public:
    void add_pattern(const Pattern& p);
    PPBRSResult match(const std::string& input) const;
    bool load_patterns(const std::string& json_path);
    size_t pattern_count() const;
    void set_threshold(float t);
private:
    std::vector<Pattern> patterns_;
    float threshold_{0.3f};
    float score(const Pattern& p, const std::string& input) const;
};
} // namespace zo
