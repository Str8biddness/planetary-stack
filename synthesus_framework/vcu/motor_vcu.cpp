#include "motor_vcu.hpp"
#include <map>
namespace zo {
VCUOutput MotorVCU::process(const VCUInput& in) {
    VCUOutput out;
    out.vcu_id = "motor";
    bool ok = execute(in.action_hint, in.payload);
    out.result = ok ? "[MOTOR] action executed" : "[MOTOR] action failed";
    out.confidence = ok ? 0.90f : 0.20f;
    out.tags = {"motor", "action"};
    return out;
}
void MotorVCU::register_action(const std::string& name, ActionCallback cb) {
    actions_[name] = cb;
}
bool MotorVCU::execute(const std::string& action, const std::string& params) {
    if (dry_run_) return true;
    auto it = actions_.find(action);
    if (it != actions_.end()) { exec_count_++; return it->second(params); }
    return false;
}
std::vector<std::string> MotorVCU::available_actions() const {
    std::vector<std::string> v;
    for (auto& kv : actions_) v.push_back(kv.first);
    return v;
}
} // namespace zo