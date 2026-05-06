#include "ensemble_synth.hpp"
#include <sstream>
#include <algorithm>
namespace zo {
void EnsembleSynth::add_output(const ReasonerOutput& out) { outputs_.push_back(out); }
void EnsembleSynth::clear() { outputs_.clear(); }
void EnsembleSynth::set_weight(const std::string& source, float w) { weights_[source] = w; }
EnsembleResult EnsembleSynth::synthesize() const { return vote(); }
EnsembleResult EnsembleSynth::vote(float threshold) const {
    if (outputs_.empty()) return {"", 0.0f, {}, "no inputs"};
    // Weighted confidence voting
    std::unordered_map<std::string, float> scores;
    float total_weight = 0;
    std::ostringstream trace;
    std::vector<ReasonerOutput> contribs;
    for (auto& out : outputs_) {
        float w = weights_.count(out.source) ? weights_.at(out.source) : 1.0f;
        float ws = out.confidence * w;
        scores[out.response] += ws;
        total_weight += w;
        trace << out.source << "(" << out.confidence << ") ";
        if (out.confidence >= threshold) contribs.push_back(out);
    }
    auto best = std::max_element(scores.begin(), scores.end(),
        [](auto& a, auto& b){ return a.second < b.second; });
    float consensus = total_weight > 0 ? best->second / total_weight : 0;
    return {best->first, consensus, contribs, trace.str()};
}
EnsembleResult EnsembleSynth::cascade(float threshold) const {
    if (outputs_.empty()) return {"", 0.0f, {}, "no inputs"};
    // Find highest confidence output above threshold
    const ReasonerOutput* best = nullptr;
    for (auto& out : outputs_)
        if (out.confidence >= threshold && (!best || out.confidence > best->confidence))
            best = &out;
    if (best) return {best->response, best->confidence, {*best}, "cascade:" + best->source};
    // Fallback: use highest confidence regardless
    auto it = std::max_element(outputs_.begin(), outputs_.end(),
        [](auto& a, auto& b){ return a.confidence < b.confidence; });
    return {it->response, it->confidence, {*it}, "fallback:" + it->source};
}
} // namespace zo
