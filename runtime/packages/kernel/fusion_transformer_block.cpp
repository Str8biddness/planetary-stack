#include "fusion_transformer_block.hpp"
#include <cmath>
#include <algorithm>
#include <cstring>
#include <iostream>

namespace synthesus::kernel {

FusionTransformerBlock::FusionTransformerBlock() : FusionTransformerBlock(Config{}) {}

FusionTransformerBlock::FusionTransformerBlock(const Config& cfg) : cfg_(cfg) {
    // Initialize weights with random values (Simulation)
    const size_t d = cfg_.model_dim;
    w_q.resize(d * d, 0.01f);
    w_k.resize(d * d, 0.01f);
    w_v.resize(d * d, 0.01f);
    w_o.resize(d * d, 0.01f);
    w_ff1.resize(d * d * cfg_.ffn_expansion, 0.01f);
    w_ff2.resize(d * d * cfg_.ffn_expansion, 0.01f);
    w_route.resize(d * 4, 0.01f); // 4 fabrics: CPU, GPU, Media, Audio

    sram_scratch_.resize(cfg_.tiling_size * d * 4, 0);
}

std::vector<float> FusionTransformerBlock::forward(const std::vector<float>& input_tokens) {
    const size_t n = input_tokens.size() / cfg_.model_dim;
    std::vector<float> x = input_tokens;
    std::vector<float> Q(n * cfg_.model_dim), K(n * cfg_.model_dim), V(n * cfg_.model_dim);
    std::vector<float> attn_out(n * cfg_.model_dim);

    // Stage 1: Input Normalization
    input_normalization(x.data(), n);

    // Stage 2: QKV Projection (Tensor Fabric)
    qkv_projection(x.data(), Q.data(), K.data(), V.data(), n);

    // Stage 3: Tiled Attention (Memory-Aware Dataflow)
    tiled_attention(Q.data(), K.data(), V.data(), attn_out.data(), n);

    // Stage 4: Cross-Modal Routing (Dynamic Hardware Dispatch)
    uint32_t target_fabric = cross_modal_routing(attn_out.data(), n);
    (void)target_fabric; // In simulation, we proceed to FFN

    // Stage 5: FFN (Tensor Fabric)
    feed_forward_network(attn_out.data(), n);

    // Stage 6: State Emission
    state_emission(attn_out.data(), n);

    return attn_out;
}

void FusionTransformerBlock::input_normalization(float* x, size_t n) {
    const size_t d = cfg_.model_dim;
    for (size_t i = 0; i < n; ++i) {
        float sum = 0;
        for (size_t j = 0; j < d; ++j) sum += x[i * d + j];
        float mean = sum / d;
        float var = 0;
        for (size_t j = 0; j < d; ++j) var += std::pow(x[i * d + j] - mean, 2);
        float std = std::sqrt(var / d + 1e-5f);
        for (size_t j = 0; j < d; ++j) x[i * d + j] = (x[i * d + j] - mean) / std;
    }
}

void FusionTransformerBlock::qkv_projection(const float* x, float* Q, float* K, float* V, size_t n) {
    matmul_avx2(x, w_q.data(), Q, n, cfg_.model_dim, cfg_.model_dim);
    matmul_avx2(x, w_k.data(), K, n, cfg_.model_dim, cfg_.model_dim);
    matmul_avx2(x, w_v.data(), V, n, cfg_.model_dim, cfg_.model_dim);
}

void FusionTransformerBlock::tiled_attention(const float* Q, const float* K, const float* V, float* out, size_t n) {
    const size_t d = cfg_.model_dim;
    const size_t h = cfg_.num_heads;
    const size_t head_dim = cfg_.head_dim;
    const size_t tile = cfg_.tiling_size;

    // Simulate tiled execution loop
    for (size_t i_tile = 0; i_tile < n; i_tile += tile) {
        size_t current_tile_n = std::min(tile, n - i_tile);
        
        // Scratchpad caching simulation
        // (Actual implementation would load Q[i_tile], K, V into SRAM)
        
        for (size_t head = 0; head < h; ++head) {
            // Compute Attention scores in tiles
            // out = softmax(Q*K.T) * V
        }
    }

    // Placeholder for functional output
    std::memcpy(out, V, n * d * sizeof(float)); 
}

uint32_t FusionTransformerBlock::cross_modal_routing(const float* x, size_t n) {
    // Stage 3: learned routing stage decides whether outputs should remain in the tensor domain...
    // In simulation: 0=GPU, 1=Media, 2=Audio, 3=CPU
    return 0; 
}

void FusionTransformerBlock::feed_forward_network(float* x, size_t n) {
    const size_t d = cfg_.model_dim;
    const size_t expand = d * cfg_.ffn_expansion;
    std::vector<float> hidden(n * expand);

    matmul_avx2(x, w_ff1.data(), hidden.data(), n, d, expand);
    // ReLU
    for (auto& v : hidden) if (v < 0) v = 0;
    matmul_avx2(hidden.data(), w_ff2.data(), x, n, expand, d);
}

void FusionTransformerBlock::state_emission(const float* x, size_t n) {
    // write summarized latent state into a persistent memory region
}

void FusionTransformerBlock::matmul_avx2(const float* A, const float* B, float* C, size_t M, size_t K, size_t N) {
    for (size_t i = 0; i < M; ++i) {
        for (size_t j = 0; j < N; ++j) {
            float sum = 0;
            for (size_t k = 0; k < K; ++k) {
                sum += A[i * K + k] * B[k * N + j];
            }
            C[i * N + j] = sum;
        }
    }
}

} // namespace synthesus::kernel
