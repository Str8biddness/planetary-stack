#include "geometric_engine.hpp"
#include <cmath>
#include <algorithm>
#include <numeric>
#include <sstream>
#include <cstdint>
#include <immintrin.h>

namespace zo {

GeometricEngine::GeometricEngine() {}

GeometricVector GeometricEngine::word_to_vector(const std::string& word) {
    std::string normalized = word;
    std::transform(normalized.begin(), normalized.end(), normalized.begin(), ::tolower);
    
    // 1. Check Grounding Shard (Empirical Truth)
    if (grounding_map_.count(normalized)) {
        return grounding_map_[normalized];
    }

    // 2. Check Cache
    if (vector_cache_.count(normalized)) {
        return vector_cache_[normalized];
    }

    GeometricVector vec = generate_vector_from_hash(normalized);
    vector_cache_[normalized] = vec;
    return vec;
}

void GeometricEngine::set_grounding_map(const std::unordered_map<std::string, GeometricVector>& map) {
    grounding_map_ = map;
    vector_cache_.clear(); // Invalidate cache to force re-grounding
}

GeometricVector GeometricEngine::generate_vector_from_hash(const std::string& word) {
    // Simple deterministic hash function
    uint64_t h1 = 5381;
    uint64_t h2 = 0x811c9dc5;
    
    for (char c : word) {
        h1 = ((h1 << 5) + h1) + c; // djb2
        h2 = (h2 ^ c) * 0x01000193; // fnv1a
    }

    // Map to 8-axis (5 active CHAL axes + 3 padding) for SIMD alignment
    float x = static_cast<float>(h1 & 0xFFFF) / 65535.0f;
    float y = static_cast<float>((h1 >> 16) & 0xFFFF) / 65535.0f;
    float z = static_cast<float>((h1 >> 32) & 0xFFFF) / 65535.0f;
    float phase = static_cast<float>((h1 >> 48) & 0xFFFF) / 65535.0f;
    float scale = static_cast<float>(h2 & 0xFFFF) / 65535.0f;

    return {x, y, z, phase, scale, 0.0f, 0.0f, 0.0f};
}

float GeometricEngine::calculate_resonance(const GeometricVector& v1, const GeometricVector& v2) {
    // SSE4.2 Optimized Cosine Similarity (4-wide floats)
    // We process the 8-axis vector in two 4-wide blocks
    __m128 m_v1_low = _mm_loadu_ps(&v1[0]);
    __m128 m_v1_high = _mm_loadu_ps(&v1[4]);
    __m128 m_v2_low = _mm_loadu_ps(&v2[0]);
    __m128 m_v2_high = _mm_loadu_ps(&v2[4]);

    // Dot product: (v1.low * v2.low) + (v1.high * v2.high)
    __m128 dot_low = _mm_mul_ps(m_v1_low, m_v2_low);
    __m128 dot_high = _mm_mul_ps(m_v1_high, m_v2_high);
    __m128 dot_all = _mm_add_ps(dot_low, dot_high);
    
    // Horizontal sum using _mm_hadd_ps (SSE3+)
    __m128 hsum = _mm_hadd_ps(dot_all, dot_all);
    hsum = _mm_hadd_ps(hsum, hsum);
    float dot;
    _mm_store_ss(&dot, hsum);

    // Magnitudes: sqrt(sum(v1^2)) * sqrt(sum(v2^2))
    __m128 m1_sq = _mm_add_ps(_mm_mul_ps(m_v1_low, m_v1_low), _mm_mul_ps(m_v1_high, m_v1_high));
    __m128 m2_sq = _mm_add_ps(_mm_mul_ps(m_v2_low, m_v2_low), _mm_mul_ps(m_v2_high, m_v2_high));

    __m128 hsum1 = _mm_hadd_ps(m1_sq, m1_sq);
    hsum1 = _mm_hadd_ps(hsum1, hsum1);
    float mag1_sq;
    _mm_store_ss(&mag1_sq, hsum1);

    __m128 hsum2 = _mm_hadd_ps(m2_sq, m2_sq);
    hsum2 = _mm_hadd_ps(hsum2, hsum2);
    float mag2_sq;
    _mm_store_ss(&mag2_sq, hsum2);

    float denom = std::sqrt(mag1_sq) * std::sqrt(mag2_sq);
    return (denom == 0) ? 0.0f : dot / denom;
}

std::vector<ResonanceResult> GeometricEngine::predict_next(const std::string& context, 
                                                         const std::vector<std::string>& candidates,
                                                         int top_n) {
    if (context.empty() || candidates.empty()) return {};

    std::vector<std::string> words;
    std::stringstream ss(context);
    std::string w;
    while (ss >> w) words.push_back(w);

    GeometricVector interference_point = {0, 0, 0, 0, 0, 0, 0, 0};
    float total_weight = 0;

    for (size_t i = 0; i < words.size(); ++i) {
        GeometricVector v = word_to_vector(words[i]);
        float recency = static_cast<float>(i + 1) / words.size();
        float weight = recency * v[4]; // recency * scale axis
        
        for (int d = 0; d < SIMD_DIM; ++d) {
            interference_point[d] += v[d] * weight;
        }
        total_weight += weight;
    }

    if (total_weight > 0) {
        for (int d = 0; d < SIMD_DIM; ++d) interference_point[d] /= total_weight;
    }

    std::vector<ResonanceResult> results;
    for (const auto& cand : candidates) {
        GeometricVector cv = word_to_vector(cand);
        results.push_back({cand, calculate_resonance(interference_point, cv)});
    }

    std::sort(results.begin(), results.end(), [](const auto& a, const auto& b) {
        return a.resonance > b.resonance;
    });

    if (results.size() > static_cast<size_t>(top_n)) {
        results.resize(top_n);
    }

    return results;
}

} // namespace zo
