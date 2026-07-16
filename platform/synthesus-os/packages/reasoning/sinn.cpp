#include "sinn.hpp"
#include <iostream>
#include <fstream>
#include <algorithm>
#include <cstring>

namespace zo {

SINN::SINN(const Config& cfg) : cfg_(cfg) {
    consciousness_state_.resize(cfg_.embed_dim, 0.0f);
}

SINN::SINN() : SINN(Config()) {}

void SINN::matmul_avx2(const float* W, const float* x, float* out, size_t rows, size_t cols) const {
    // Naive fallback (temporarily disable AVX intrinsics for cross-compilation stability)
    for (size_t i = 0; i < rows; ++i) {
        float sum = 0;
        for (size_t j = 0; j < cols; ++j) sum += W[i * cols + j] * x[j];
        out[i] = sum;
    }
}

void SINN::apply_qualia_encoding(std::vector<float>& x) const {
    // Port of content * (1 + sigmoid(matmul(qualia, basis)))
    // Simplified for AIVM proof-of-concept
    for (size_t i = 0; i < x.size(); ++i) {
        float sigmoid = 1.0f / (1.0f + std::exp(-x[i] * 0.1f));
        x[i] = x[i] * (1.0f + sigmoid);
    }
}

std::vector<float> SINN::forward(const std::vector<int>& input_ids) {
    // 1. Embedding Pass
    std::vector<float> x(cfg_.embed_dim, 0.0f);
    // (Actual embedding lookup would go here)
    
    // 2. Qualia Pass
    apply_qualia_encoding(x);
    
    // 3. Transformer Layers
    for (size_t i = 0; i < cfg_.num_layers; ++i) {
        apply_meta_cognitive_attention(x, i);
    }
    
    // 4. Temporal Pass
    apply_temporal_consciousness(x);
    
    return x;
}

void SINN::apply_meta_cognitive_attention(std::vector<float>& x, size_t layer_idx) const {
    // Placeholder for multi-head attention + introspection gate
}

void SINN::apply_temporal_consciousness(std::vector<float>& x) const {
    // Simple state-decay update to simulate consciousness flux
    for (size_t i = 0; i < x.size(); ++i) {
        x[i] = 0.9f * x[i] + 0.1f * std::sin(static_cast<float>(i));
    }
}

bool SINN::load_weights(const std::string& path) {
    std::ifstream f(path, std::ios::binary);
    if (!f) return false;
    
    char magic[4];
    f.read(magic, 4);
    if (std::memcmp(magic, "SINN", 4) != 0) return false;
    
    uint32_t version;
    f.read((char*)&version, 4);
    
    uint64_t num_weights;
    f.read((char*)&num_weights, 8);
    
    for (uint64_t i = 0; i < num_weights; ++i) {
        uint32_t name_len;
        f.read((char*)&name_len, 4);
        std::string name(name_len, ' ');
        f.read(&name[0], name_len);
        
        uint32_t shape_len;
        f.read((char*)&shape_len, 4);
        size_t total_elements = 1;
        for (uint32_t j = 0; j < shape_len; ++j) {
            uint32_t dim;
            f.read((char*)&dim, 4);
            total_elements *= dim;
        }
        
        uint64_t data_len;
        f.read((char*)&data_len, 8);
        std::vector<float> data(total_elements);
        f.read((char*)data.data(), data_len);
        
        weight_map_[name] = std::move(data);
    }
    
    return true;
}

} // namespace zo
