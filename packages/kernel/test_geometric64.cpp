// Standalone correctness test for the 64-dim widened kernel.
// Proves the SSE-blocked resonance == naive scalar cosine, and that
// determinism / grounding override still hold.
#include "geometric_engine.hpp"
#include <cstdio>
#include <cmath>
#include <random>

using namespace zo;

static float scalar_cosine(const GeometricVector& a, const GeometricVector& b) {
    double dot = 0, m1 = 0, m2 = 0;
    for (int i = 0; i < GEO_DIM; ++i) { dot += a[i]*b[i]; m1 += a[i]*a[i]; m2 += b[i]*b[i]; }
    double d = std::sqrt(m1) * std::sqrt(m2);
    return d == 0 ? 0.f : (float)(dot / d);
}

int main() {
    printf("--- 64-Dim Kernel Test (GEO_DIM=%d) ---\n", GEO_DIM);
    GeometricEngine engine;

    // 1. Dimensionality + determinism
    auto v1 = engine.word_to_vector("intelligence");
    auto v2 = engine.word_to_vector("intelligence");
    bool det = true; for (int i = 0; i < GEO_DIM; ++i) det &= (v1[i] == v2[i]);
    printf("[1] vector width = %zu, deterministic = %s\n", v1.size(), det ? "yes" : "no");

    // 2. SSE resonance vs scalar cosine over random 64-vectors
    std::mt19937 rng(42); std::uniform_real_distribution<float> U(0, 1);
    float max_err = 0;
    for (int t = 0; t < 1000; ++t) {
        GeometricVector a{}, b{};
        for (int i = 0; i < GEO_DIM; ++i) { a[i] = U(rng); b[i] = U(rng); }
        float err = std::fabs(engine.calculate_resonance(a, b) - scalar_cosine(a, b));
        max_err = std::max(max_err, err);
    }
    printf("[2] max |SSE - scalar| over 1000 random pairs = %.3e  -> %s\n",
           max_err, max_err < 1e-5 ? "PASS" : "FAIL");

    // 3. Identity resonance == 1
    printf("[3] identity resonance = %.6f\n", engine.calculate_resonance(v1, v1));

    // 4. Grounding override still wins over hash
    GeometricVector g{}; g.fill(0.5f);
    std::unordered_map<std::string, GeometricVector> gm{{"water", g}};
    engine.set_grounding_map(gm);
    auto w = engine.word_to_vector("water");
    printf("[4] grounding override: water[0]=%.3f (expect 0.500) -> %s\n",
           w[0], std::fabs(w[0]-0.5f) < 1e-6 ? "PASS" : "FAIL");

    printf("--- done ---\n");
    return 0;
}
