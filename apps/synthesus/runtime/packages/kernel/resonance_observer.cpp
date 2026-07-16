#include "resonance_observer.hpp"
#include <iostream>
#include <cmath>

namespace zo {

ResonanceObserver::ResonanceObserver(std::shared_ptr<GeometricEngine> engine)
    : engine_(engine) {}

ResonanceObserver::AuditResult ResonanceObserver::sample_concept(const std::string& concept) {
    GeometricVector vec = engine_->word_to_vector(concept);
    
    // Calculate a basic confidence score based on Axis 5 (Scale)
    float confidence = vec[4]; 
    
    return {concept, vec, confidence, ""};
}

void ResonanceObserver::apply_bias_nudge(const std::string& concept, int axis, float nudge_value) {
    if (axis < 0 || axis >= GeometricEngine::SIMD_DIM) return;

    // Retrieve current vector
    GeometricVector vec = engine_->word_to_vector(concept);
    
    // Apply nudge (additive resonance adjustment)
    vec[axis] = std::clamp(vec[axis] + nudge_value, 0.0f, 1.0f);
    
    // Update the engine's grounding map with the 'steered' coordinate
    std::unordered_map<std::string, GeometricVector> single_update;
    single_update[concept] = vec;
    
    // Note: In a full impl, set_grounding_map would merge or we'd have an update_grounding method
    engine_->set_grounding_map(single_update);
    
    std::cout << "🎯 [OBSERVER] Applied nudge to '" << concept << "' axis " << axis 
              << " (New val: " << vec[axis] << ")" << std::endl;
}

float ResonanceObserver::calculate_logical_health() {
    // Audit core logical pairs to ensure they still resonate
    // e.g., 'True' vs 'False' should have low resonance (orthogonality)
    GeometricVector v_true = engine_->word_to_vector("true");
    GeometricVector v_false = engine_->word_to_vector("false");
    
    float resonance = engine_->calculate_resonance(v_true, v_false);
    
    // Health is high if opposites are geometrically distant
    float health = 1.0f - resonance; 
    
    return health;
}

} // namespace zo
