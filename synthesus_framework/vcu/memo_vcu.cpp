#include "memo_vcu.hpp"
namespace zo {
bool MemoVCU::can_handle(const VCUInput& input) const {
    return input.data.find("remember") != std::string::npos ||
           input.data.find("recall") != std::string::npos ||
           input.data.find("memory") != std::string::npos ||
           input.data.find("forget") != std::string::npos;
}
VCUOutput MemoVCU::process(const VCUInput& input) {
    // Push to working memory
    wm_.push({"user", input.data, 0});
    // Check long-term memory for relevant context
    auto ltm_results = ltm_.search(input.data, 3);
    std::string context;
    for (auto& n : ltm_results) context += n.key + ": " + n.value + " | ";
    // Check episodic memory
    auto ep_results = em_.recall(input.data, 2);
    for (auto& ep : ep_results) context += ep.summary + " | ";
    std::string result = context.empty() ? "No relevant memories found" : "Recalled: " + context;
    return {result, ltm_results.empty() && ep_results.empty() ? 0.2f : 0.8f, id(), true};
}
} // namespace zo
