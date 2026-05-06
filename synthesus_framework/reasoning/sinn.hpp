#pragma once
// Synthesus 2.0 Phase 7 - SINN: Synthetic Intuition Neural Network (2-layer MLP)
// Left hemisphere analog reasoning
#include <vector>
#include <string>
#include <cmath>
namespace zo {
struct SINNConfig { size_t input_dim{128}; size_t hidden_dim{256}; size_t output_dim{64}; float lr{0.001f}; };
class SINN {
public:
    explicit SINN(const SINNConfig& cfg = {});
    std::vector<float> forward(const std::vector<float>& x);
    void train(const std::vector<float>& x, const std::vector<float>& target);
    float confidence(const std::vector<float>& output) const;
    bool load(const std::string& path);
    bool save(const std::string& path) const;
private:
    SINNConfig cfg_;
    std::vector<float> W1_, b1_, W2_, b2_;
    std::vector<float> relu(const std::vector<float>& x) const;
    std::vector<float> softmax(const std::vector<float>& x) const;
    std::vector<float> matmul(const std::vector<float>& W, const std::vector<float>& x,
                              size_t rows, size_t cols) const;
    void init_weights();
};
} // namespace zo
