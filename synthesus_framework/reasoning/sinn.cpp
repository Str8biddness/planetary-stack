#include "sinn.hpp"
#include <random>
#include <fstream>
#include <cstring>
#include <algorithm>
#include <cmath>
namespace zo {
SINN::SINN(const SINNConfig& cfg) : cfg_(cfg) { init_weights(); }
void SINN::init_weights() {
    std::mt19937 rng(42);
    std::normal_distribution<float> dist(0.0f, 0.1f);
    W1_.resize(cfg_.hidden_dim * cfg_.input_dim);
    b1_.resize(cfg_.hidden_dim, 0.0f);
    W2_.resize(cfg_.output_dim * cfg_.hidden_dim);
    b2_.resize(cfg_.output_dim, 0.0f);
    for (auto& w : W1_) w = dist(rng);
    for (auto& w : W2_) w = dist(rng);
}
std::vector<float> SINN::relu(const std::vector<float>& x) const {
    std::vector<float> r(x.size());
    for (size_t i = 0; i < x.size(); ++i) r[i] = x[i] > 0 ? x[i] : 0;
    return r;
}
std::vector<float> SINN::softmax(const std::vector<float>& x) const {
    float mx = *std::max_element(x.begin(), x.end());
    std::vector<float> r(x.size());
    float sum = 0;
    for (size_t i = 0; i < x.size(); ++i) { r[i] = std::exp(x[i] - mx); sum += r[i]; }
    for (auto& v : r) v /= sum;
    return r;
}
std::vector<float> SINN::matmul(const std::vector<float>& W, const std::vector<float>& x,
                                 size_t rows, size_t cols) const {
    std::vector<float> out(rows, 0.0f);
    for (size_t i = 0; i < rows; ++i)
        for (size_t j = 0; j < cols; ++j)
            out[i] += W[i * cols + j] * x[j];
    return out;
}
std::vector<float> SINN::forward(const std::vector<float>& x) {
    auto h = matmul(W1_, x, cfg_.hidden_dim, cfg_.input_dim);
    for (size_t i = 0; i < h.size(); ++i) h[i] += b1_[i];
    h = relu(h);
    auto out = matmul(W2_, h, cfg_.output_dim, cfg_.hidden_dim);
    for (size_t i = 0; i < out.size(); ++i) out[i] += b2_[i];
    return softmax(out);
}
void SINN::train(const std::vector<float>& x, const std::vector<float>& target) {
    // Simplified SGD backprop
    auto output = forward(x);
    auto h = relu(matmul(W1_, x, cfg_.hidden_dim, cfg_.input_dim));
    // Output layer gradient
    std::vector<float> dout(cfg_.output_dim);
    for (size_t i = 0; i < cfg_.output_dim; ++i) dout[i] = output[i] - target[i];
    // W2 update
    for (size_t i = 0; i < cfg_.output_dim; ++i)
        for (size_t j = 0; j < cfg_.hidden_dim; ++j)
            W2_[i * cfg_.hidden_dim + j] -= cfg_.lr * dout[i] * h[j];
}
float SINN::confidence(const std::vector<float>& output) const {
    if (output.empty()) return 0.0f;
    return *std::max_element(output.begin(), output.end());
}
bool SINN::load(const std::string& path) {
    std::ifstream f(path, std::ios::binary);
    if (!f) return false;
    f.read((char*)W1_.data(), W1_.size() * 4);
    f.read((char*)b1_.data(), b1_.size() * 4);
    f.read((char*)W2_.data(), W2_.size() * 4);
    f.read((char*)b2_.data(), b2_.size() * 4);
    return f.good();
}
bool SINN::save(const std::string& path) const {
    std::ofstream f(path, std::ios::binary);
    if (!f) return false;
    f.write((char*)W1_.data(), W1_.size() * 4);
    f.write((char*)b1_.data(), b1_.size() * 4);
    f.write((char*)W2_.data(), W2_.size() * 4);
    f.write((char*)b2_.data(), b2_.size() * 4);
    return f.good();
}
} // namespace zo
