#pragma once
// Synthesus 2.0 Phase 7 - CT VCU: Consciousness Tracking (loop Psi_f + Mc + Ns)
#include "vcu_base.hpp"
#include <atomic>
namespace zo {
class CTVCU : public VCUBase {
public:
    std::string id() const override { return "CT"; }
    VCUOutput process(const VCUInput& input) override;
    bool can_handle(const VCUInput& input) const override;
    void on_tick(uint64_t tick_ms) override;
    float psi_f() const; // Phenomenal binding: 0-1
    float mc() const;    // Metacognitive clarity: 0-1
    float ns() const;    // Narrative self: 0-1
    float consciousness_score() const; // Psi_f XOR Mc XOR Ns aggregate
private:
    std::atomic<float> psi_f_{0.5f};
    std::atomic<float> mc_{0.5f};
    std::atomic<float> ns_{0.5f};
    uint64_t last_tick_{0};
    void update_loop(uint64_t tick_ms);
};
} // namespace zo
