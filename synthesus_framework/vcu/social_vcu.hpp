#pragma once
// Synthesus 2.0 - SocialVCU: multi-agent coordination and theory-of-mind
#include "vcu_base.hpp"
#include <string>
#include <map>
namespace zo {
struct AgentModel {
    std::string agent_id;
    float trust = 0.5f;
    float inferred_intent = 0.0f;
    std::string last_message;
};
class SocialVCU : public VCUBase {
public:
    SocialVCU() : VCUBase("social") {}
    VCUOutput process(const VCUInput& in) override;
    void update_agent(const std::string& id, float trust_delta, const std::string& msg);
    float get_trust(const std::string& agent_id) const;
    AgentModel get_agent(const std::string& id) const;
private:
    std::map<std::string, AgentModel> agents_;
    float infer_intent(const std::string& message) const;
};
} // namespace zo