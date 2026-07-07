#pragma once
// Synthesus 2.0 Phase 7 - EnsembleSynth: multi-module reasoning combiner
// Combines SINN + PPBRS + Symbolic + Bayesian + Causal results
#include <string>
#include <vector>
#include <memory>
#include <unordered_map>
namespace zo {
struct ReasonerOutput { std::string source; std::string response; float confidence; float weight; };
struct EnsembleResult {
    std::string final_response;
    float consensus_confidence;
    std::vector<ReasonerOutput> contributors;
    std::string reasoning_trace;
};
class EnsembleSynth {
public:
    void add_output(const ReasonerOutput& out);
    EnsembleResult synthesize() const;
    // Weighted voting
    EnsembleResult vote(float threshold = 0.5f) const;
    // Cascade: use highest confidence above threshold, else fallback
    EnsembleResult cascade(float threshold = 0.6f) const;
    void clear();
    void set_weight(const std::string& source, float w);
private:
    std::vector<ReasonerOutput> outputs_;
    std::unordered_map<std::string,float> weights_;
};
} // namespace zo
