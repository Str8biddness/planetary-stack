#include "voice_vcu.hpp"
#include <sstream>
#include <cmath>
#include <iomanip>

namespace zo {

VoiceVCU::VoiceVCU(std::shared_ptr<GeometricEngine> engine)
    : engine_(engine) {}

VoiceVCU::VocalProfile VoiceVCU::vector_to_profile(const GeometricVector& vec) {
    VocalProfile p;
    // Map the 5 CHAL axes to Acoustic properties
    p.pitch = 220.0f + (vec[1] * 660.0f);   // Y Axis maps to Pitch (220Hz - 880Hz)
    p.timbre = (vec[0] + vec[2]) / 2.0f;    // X/Z average maps to Timbre color
    p.resonance = vec[3];                   // Phase Axis maps to Resonance
    p.amplitude = vec[4];                   // Scale Axis maps to Intensity/Volume
    return p;
}

VCUOutput VoiceVCU::process(const VCUInput& in) {
    std::stringstream ss;
    std::stringstream trace;
    
    // Simulate phonetic streaming
    trace << "larynx::render_start(text=\"" << in.payload << "\")\n";
    
    std::string word;
    std::stringstream ps(in.payload);
    float avg_confidence = 0.0f;
    int word_count = 0;

    while (ps >> word) {
        GeometricVector vec = engine_->word_to_vector(word);
        VocalProfile p = vector_to_profile(vec);
        
        // Render a simulated 'Phonetic Harmonic' string
        // In a real implementation, this would feed a PCM buffer
        ss << "[" << std::fixed << std::setprecision(2) 
           << p.pitch << "Hz|" << (p.resonance * 100) << "%] ";
           
        trace << "  word=\"" << word << "\" -> resonance=" << p.resonance << " pitch=" << p.pitch << "\n";
        
        avg_confidence += (p.resonance + p.amplitude) / 2.0f;
        word_count++;
    }

    if (word_count > 0) avg_confidence /= word_count;
    else avg_confidence = 0.9f; // default silence confidence

    trace << "larynx::render_complete()";

    return {
        ss.str(),
        avg_confidence,
        "Larynx (Quantum Acoustics)",
        !ss.str().empty()
    };
}

} // namespace zo
