#include "language_vcu.hpp"
#include <algorithm>
#include <sstream>
namespace zo {
VCUOutput LanguageVCU::process(const VCUInput& in) {
    VCUOutput out;
    out.vcu_id = "language";
    out.result = generate(in.payload, 128);
    out.confidence = 0.80f;
    out.tags = {"language", "nlp"};
    return out;
}
std::string LanguageVCU::tokenize(const std::string& text) const {
    std::ostringstream ss;
    std::istringstream iss(text);
    std::string word;
    int i = 0;
    while (iss >> word) ss << "[" << i++ << ":" << word << "]";
    return ss.str();
}
float LanguageVCU::sentiment(const std::string& text) const {
    // Simple keyword heuristic
    float score = 0.0f;
    const char* pos[] = {"good","great","excellent","love","best","happy"};
    const char* neg[] = {"bad","worst","hate","terrible","awful","fail"};
    std::string lower = text;
    std::transform(lower.begin(), lower.end(), lower.begin(), ::tolower);
    for (auto& p : pos) if (lower.find(p) != std::string::npos) score += 0.2f;
    for (auto& n : neg) if (lower.find(n) != std::string::npos) score -= 0.2f;
    return std::max(-1.0f, std::min(1.0f, score));
}
std::string LanguageVCU::generate(const std::string& prompt, int max_tokens) const {
    // Stub - replaced by SLM when llama-cpp-python is available
    return "[LANG] Response to: " + prompt.substr(0, std::min((int)prompt.size(), 60));
}
} // namespace zo