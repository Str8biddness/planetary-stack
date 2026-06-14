#pragma once

#include "vcu_base.hpp"
#include "geometric_engine.hpp"
#include <string>
#include <vector>

namespace zo {

/**
 * VoiceVCU (The Larynx) - Bridges Symbolic Resonance to Acoustic Waveforms.
 * Implements the Synthesus 5 'Quantum Acoustics' logic.
 */
class VoiceVCU : public VCUBase {
public:
    struct VocalProfile {
        float pitch;      // Derived from Y axis
        float timbre;     // Derived from X/Z axes
        float resonance;  // Derived from Phase axis
        float amplitude;  // Derived from Scale axis
    };

    VoiceVCU(std::shared_ptr<GeometricEngine> engine);

    virtual std::string id() const override { return "larynx"; }

    // Renders text into a sequence of vocal profiles (simulated waveforms)
    virtual VCUOutput process(const VCUInput& in) override;

    // Maps a geometric vector to an acoustic profile
    VocalProfile vector_to_profile(const GeometricVector& vec);

private:
    std::shared_ptr<GeometricEngine> engine_;
    
    // Internal state for 'Harmonic Breath'
    float global_vibration_level_ = 0.5f;
};

} // namespace zo
