#include "geometric_engine.hpp"
#include <iostream>
#include <vector>
#include <string>
#include <cassert>

int main() {
    zo::GeometricEngine engine;

    std::cout << "--- Geometric Engine Unit Test ---" << std::endl;

    // Test 1: Determinism
    std::cout << "[Test 1] Deterministic Mapping..." << std::endl;
    auto v1 = engine.word_to_vector("intelligence");
    auto v2 = engine.word_to_vector("intelligence");
    
    for(int i=0; i<5; ++i) {
        if (v1[i] != v2[i]) {
            std::cerr << "FAILED: Non-deterministic mapping at axis " << i << std::endl;
            return 1;
        }
    }
    std::cout << "  - Vector: [" << v1[0] << ", " << v1[1] << ", " << v1[2] << ", " << v1[3] << ", " << v1[4] << "]" << std::endl;
    std::cout << "  - Status: PASSED" << std::endl;

    // Test 2: Resonance Calculation
    std::cout << "\n[Test 2] Resonance (Cosine Similarity)..." << std::endl;
    float resonance = engine.calculate_resonance(v1, v1);
    std::cout << "  - Identity Resonance: " << resonance << std::endl;
    if (std::abs(resonance - 1.0f) > 1e-5) {
        std::cerr << "FAILED: Identity resonance should be 1.0" << std::endl;
        return 1;
    }
    std::cout << "  - Status: PASSED" << std::endl;

    // Test 3: Prediction/Interference
    std::cout << "\n[Test 3] Context Prediction (Interference)..." << std::endl;
    std::string context = "artificial";
    std::vector<std::string> candidates = {"intelligence", "garden", "cloud", "robotics"};
    
    auto results = engine.predict_next(context, candidates, 2);
    
    std::cout << "  Context: \"" << context << "\"" << std::endl;
    for (const auto& res : results) {
        std::cout << "  -> Candidate: " << res.word << " (Resonance: " << res.resonance << ")" << std::endl;
    }

    if (results.empty()) {
        std::cerr << "FAILED: No prediction results" << std::endl;
        return 1;
    }
    std::cout << "  - Status: PASSED" << std::endl;

    std::cout << "\n--- All Geometric Engine Tests Passed ---" << std::endl;
    return 0;
}
