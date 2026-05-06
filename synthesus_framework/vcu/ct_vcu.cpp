#include "ct_vcu.hpp"
#include <cmath>
namespace zo {
float CTVCU::psi_f() const { return psi_f_.load(); }
float CTVCU::mc() const { return mc_.load(); }
float CTVCU::ns() const { return ns_.load(); }
float CTVCU::consciousness_score() const {
    // Psi_f(t) XOR Mc(t) XOR Ns(t) - XOR approximation via harmonic mean
    float p = psi_f_.load(), m = mc_.load(), n = ns_.load();
    return (p * m * n) / std::max(1e-6f, (p*m + m*n + n*p) / 3.0f);
}
bool CTVCU::can_handle(const VCUInput& input) const {
    return input.data.find("consciousness") != std::string::npos ||
           input.data.find("aware") != std::string::npos ||
           input.data.find("self") != std::string::npos;
}
void CTVCU::update_loop(uint64_t tick_ms) {
    // Simulate consciousness oscillation
    float t = tick_ms / 1000.0f;
    psi_f_.store(0.5f + 0.4f * std::sin(t * 0.1f));
    mc_.store(0.5f + 0.3f * std::cos(t * 0.07f));
    ns_.store(0.5f + 0.35f * std::sin(t * 0.13f + 1.0f));
}
void CTVCU::on_tick(uint64_t tick_ms) {
    last_tick_ = tick_ms;
    update_loop(tick_ms);
}
VCUOutput CTVCU::process(const VCUInput& input) {
    float cs = consciousness_score();
    std::string result = "CT:" + std::to_string(cs)
        + " psi=" + std::to_string(psi_f())
        + " mc=" + std::to_string(mc())
        + " ns=" + std::to_string(ns());
    return {result, cs, id(), true};
}
} // namespace zo
