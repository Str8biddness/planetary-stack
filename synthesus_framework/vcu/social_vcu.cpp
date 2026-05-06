#include "social_vcu.hpp"
#include <algorithm>
namespace zo {
float SocialVCU::infer_intent(const std::string& msg) const {
    if (msg.find('?') != std::string::npos) return 0.3f;
    if (msg.find('!') != std::string::npos) return -0.1f;
    return 0.0f;
}
void SocialVCU::update_agent(const std::string& id, float delta, const std::string& msg) {
    auto& a = agents_[id];
    a.agent_id = id;
    a.trust = std::max(0.0f, std::min(1.0f, a.trust + delta));
    a.last_message = msg;
    a.inferred_intent = infer_intent(msg);
}
float SocialVCU::get_trust(const std::string& id) const {
    auto it = agents_.find(id);
    return it != agents_.end() ? it->second.trust : 0.5f;
}
AgentModel SocialVCU::get_agent(const std::string& id) const {
    auto it = agents_.find(id);
    if (it != agents_.end()) return it->second;
    return AgentModel{id, 0.5f, 0.0f, ""};
}
VCUOutput SocialVCU::process(const VCUInput& in) {
    update_agent(in.source_id, 0.01f, in.payload);
    float trust = get_trust(in.source_id);
    VCUOutput out;
    out.vcu_id = "social";
    out.result = "[SOCIAL] agent=" + in.source_id + " trust=" + std::to_string(trust);
    out.confidence = trust;
    out.tags = {"social", "agent"};
    return out;
}
} // namespace zo