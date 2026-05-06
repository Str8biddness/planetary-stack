#pragma once
// Synthesus 2.0 Phase 7 - Self Perception (metacognitive self-model)
#include <string>
#include <unordered_map>
#include <mutex>
namespace zo {
struct SelfState {
    float confidence{0.5f};     // 0-1: certainty in current reasoning
    float arousal{0.5f};        // 0-1: activation/energy level
    float valence{0.5f};        // 0-1: positive/negative affect
    float epistemic_load{0.0f}; // 0-1: how much is unknown
    std::string current_goal;
    std::string active_mode;    // "analytical"|"creative"|"cautious"|"social"
};
class SelfPerception {
public:
    SelfState get() const;
    void update(const SelfState& s);
    void set_confidence(float v);
    void set_arousal(float v);
    void set_valence(float v);
    void set_epistemic_load(float v);
    void set_goal(const std::string& g);
    void set_mode(const std::string& m);
    std::string introspect() const;
    void blend(const SelfState& other, float alpha = 0.1f);
private:
    mutable std::mutex mutex_;
    SelfState state_;
};
} // namespace zo
