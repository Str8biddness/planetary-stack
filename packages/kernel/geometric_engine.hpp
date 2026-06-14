#pragma once

#include <string>
#include <vector>
#include <unordered_map>
#include <array>

namespace zo {

/**
 * Symbolic concept vector. Widened from 5 to GEO_DIM axes: real text needs
 * many dimensions to separate cleanly (5 dims collapse on a real vocabulary;
 * see tools/cooccurrence_grounding.py). GEO_DIM is a multiple of 8 so it stays
 * AVX-friendly and a multiple of 4 for the SSE resonance loop.
 */
constexpr int GEO_DIM = 64;
using GeometricVector = std::array<float, GEO_DIM>;

struct ResonanceResult {
    std::string word;
    float resonance;
};

/**
 * GeometricEngine - C++ implementation of the 5-Axis SLLM Core.
 * Handles deterministic vector mapping and constructive interference.
 */
class GeometricEngine {
public:
    static constexpr int DIM = GEO_DIM;
    static constexpr int SIMD_DIM = GEO_DIM;

    GeometricEngine();

    // Deterministically maps a word to a 5-axis vector
    GeometricVector word_to_vector(const std::string& word);

    // Injects empirical grounding vectors (overrides hashes)
    void set_grounding_map(const std::unordered_map<std::string, GeometricVector>& map);

    // Predicts next tokens based on context resonance
    std::vector<ResonanceResult> predict_next(const std::string& context, 
                                             const std::vector<std::string>& candidates,
                                             int top_n = 5);

    // Calculate resonance (cosine similarity) using SIMD (SSE4.2)
    float calculate_resonance(const GeometricVector& v1, const GeometricVector& v2);

private:
    std::unordered_map<std::string, GeometricVector> vector_cache_;
    std::unordered_map<std::string, GeometricVector> grounding_map_;
    
    // MD5 helper for deterministic coordinates (simple implementation)
    GeometricVector generate_vector_from_hash(const std::string& word);
};

} // namespace zo
