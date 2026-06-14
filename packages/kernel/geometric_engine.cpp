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
    // Deterministic fallback for ungrounded words (real coordinates come from
    // the grounding map / co-occurrence pipeline). djb2 + fnv1a seed, then a
    // splitmix64 finisher per axis to fill all GEO_DIM dimensions.
    uint64_t h1 = 5381;
    uint64_t h2 = 0x811c9dc5;
    for (char c : word) {
        h1 = ((h1 << 5) + h1) + c;   // djb2
        h2 = (h2 ^ c) * 0x01000193;  // fnv1a
    }

    GeometricVector vec{};
    for (int i = 0; i < SIMD_DIM; ++i) {
        uint64_t z = h1 ^ (h2 + static_cast<uint64_t>(i) * 0x9E3779B97F4A7C15ULL);
        z ^= z >> 33; z *= 0xff51afd7ed558ccdULL;   // splitmix64 mix
        z ^= z >> 33; z *= 0xc4ceb9fe1a85ec53ULL;
        z ^= z >> 33;
        vec[i] = static_cast<float>(z & 0xFFFF) / 65535.0f;
    }
    return vec;
}

float GeometricEngine::calculate_resonance(const GeometricVector& v1, const GeometricVector& v2) {
    // SSE Cosine Similarity over GEO_DIM axes, accumulated in 4-wide blocks.
    static_assert(GEO_DIM % 4 == 0, "GEO_DIM must be a multiple of 4 for the SSE loop");
    __m128 acc_dot = _mm_setzero_ps();
    __m128 acc_m1  = _mm_setzero_ps();
    __m128 acc_m2  = _mm_setzero_ps();

    for (int i = 0; i < SIMD_DIM; i += 4) {
        __m128 a = _mm_loadu_ps(&v1[i]);
        __m128 b = _mm_loadu_ps(&v2[i]);
        acc_dot = _mm_add_ps(acc_dot, _mm_mul_ps(a, b));
        acc_m1  = _mm_add_ps(acc_m1,  _mm_mul_ps(a, a));
        acc_m2  = _mm_add_ps(acc_m2,  _mm_mul_ps(b, b));
    }

    auto hsum = [](__m128 v) -> float {
        v = _mm_hadd_ps(v, v);
        v = _mm_hadd_ps(v, v);
        float r; _mm_store_ss(&r, v); return r;
    };

    float dot = hsum(acc_dot);
    float denom = std::sqrt(hsum(acc_m1)) * std::sqrt(hsum(acc_m2));
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

    GeometricVector interference_point{};
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
