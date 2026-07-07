#pragma once

#include "geometric_engine.hpp"
#include <string>
#include <vector>
#include <map>

namespace zo {

/**
 * ResonanceObserver - The 'Audit Interface' for Synthesus 5.
 * Allows external agents (Syntech/Zo LLMs) to sample resonance
 * and apply bias corrections to the 5-axis map.
 */
class ResonanceObserver {
public:
    struct AuditResult {
        std::string concept;
        GeometricVector current_vector;
        float confidence;
        std::string suggested_correction; // LLM feedback
    };

    ResonanceObserver(std::shared_ptr<GeometricEngine> engine);

    /**
     * Samples the resonance of a specific concept.
     * Used by Syntech to check for 'Geometric Drift'.
     */
    AuditResult sample_concept(const std::string& concept);

    /**
     * Applies a 'Bias Nudge' to a specific axis.
     * Allows LLMs to manually realign coordinates that have drifted.
     */
    void apply_bias_nudge(const std::string& concept, int axis, float nudge_value);

    /**
     * Runs a 'Logic Health Check' by calculating resonance between
     * known logical pairs (e.g., 'A implies B').
     */
    float calculate_logical_health();

private:
    std::shared_ptr<GeometricEngine> engine_;
    std::map<std::string, float> drift_history_;
};

} // namespace zo
