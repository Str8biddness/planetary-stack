#include "self_perception.hpp"
#include <sstream>
#include <algorithm>
namespace zo {
static float clamp01(float v) { return std::max(0.0f, std::min(1.0f, v)); }
SelfState SelfPerception::get() const { std::lock_guard<std::mutex> lk(mutex_); return state_; }
void SelfPerception::update(const SelfState& s) { std::lock_guard<std::mutex> lk(mutex_); state_ = s; }
void SelfPerception::set_confidence(float v) { std::lock_guard<std::mutex> lk(mutex_); state_.confidence = clamp01(v); }
void SelfPerception::set_arousal(float v) { std::lock_guard<std::mutex> lk(mutex_); state_.arousal = clamp01(v); }
void SelfPerception::set_valence(float v) { std::lock_guard<std::mutex> lk(mutex_); state_.valence = clamp01(v); }
void SelfPerception::set_epistemic_load(float v) { std::lock_guard<std::mutex> lk(mutex_); state_.epistemic_load = clamp01(v); }
void SelfPerception::set_goal(const std::string& g) { std::lock_guard<std::mutex> lk(mutex_); state_.current_goal = g; }
void SelfPerception::set_mode(const std::string& m) { std::lock_guard<std::mutex> lk(mutex_); state_.active_mode = m; }
std::string SelfPerception::introspect() const {
    std::lock_guard<std::mutex> lk(mutex_);
    std::ostringstream ss;
    ss << "{confidence:" << state_.confidence
       << ",arousal:" << state_.arousal
       << ",valence:" << state_.valence
       << ",epistemic_load:" << state_.epistemic_load
       << ",mode:\"" << state_.active_mode << "\""
       << ",goal:\"" << state_.current_goal << "\"}";
    return ss.str();
}
void SelfPerception::blend(const SelfState& other, float alpha) {
    std::lock_guard<std::mutex> lk(mutex_);
    state_.confidence = clamp01(state_.confidence * (1-alpha) + other.confidence * alpha);
    state_.arousal = clamp01(state_.arousal * (1-alpha) + other.arousal * alpha);
    state_.valence = clamp01(state_.valence * (1-alpha) + other.valence * alpha);
    state_.epistemic_load = clamp01(state_.epistemic_load * (1-alpha) + other.epistemic_load * alpha);
}
} // namespace zo
