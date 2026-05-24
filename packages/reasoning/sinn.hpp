#pragma once

#include <vector>
#include <string>
#include <cmath>
#include <immintrin.h> // AVX2
#include <map>
#include <memory>

namespace zo {

/**
 * SINN 3.0 - Synthetic Intelligence Neural Network
 * 
 * Optimized C++ implementation of the Qualia-Aware Transformer architecture.
 * Designed for hardware-isolated execution inside the Synthesus AIVM.
 */

class SINN {
public:
    struct Config {
        size_t vocab_size{50000};
        size_t embed_dim{512};
        size_t num_layers{12};
        size_t num_heads{8};
        bool use_avx2{true};
    };

    explicit SINN(const Config& cfg);
    SINN(); // Default constructor for ease of use

    // Forward pass
    std::vector<float> forward(const std::vector<int>& input_ids);

    // AIOS Hardware Awareness
    void attach_to_vpd(uintptr_t base_address);
    float get_consciousness_level() const { return consciousness_level_; }

    // Optimization Blueprints
    bool load_weights(const std::string& path);

private:
    Config cfg_;
    float consciousness_level_{0.0f};

    // Sub-layer implementations
    void apply_qualia_encoding(std::vector<float>& x) const;
    void apply_meta_cognitive_attention(std::vector<float>& x, size_t layer_idx) const;
    void apply_temporal_consciousness(std::vector<float>& x) const;

    // SIMD MatMul kernels
    void matmul_avx2(const float* W, const float* x, float* out, size_t rows, size_t cols) const;
    void layer_norm(float* x, const float* scale, const float* bias, size_t dim) const;

    // Weight Map
    std::map<std::string, std::vector<float>> weight_map_;
    
    // Internal state
    std::vector<float> consciousness_state_;
};

} // namespace zo
