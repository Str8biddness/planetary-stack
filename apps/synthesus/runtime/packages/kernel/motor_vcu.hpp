#pragma once
// Synthesus 2.0 - MotorVCU: action output, command execution
#include "vcu_base.hpp"
#include <string>
#include <functional>
#include <map>
namespace zo {
using ActionCallback = std::function<bool(const std::string&)>;
class MotorVCU : public VCUBase {
public:
    MotorVCU() : VCUBase("motor") {}
    VCUOutput process(const VCUInput& in) override;
    void register_action(const std::string& name, ActionCallback cb);
    bool execute(const std::string& action, const std::string& params);
    std::vector<std::string> available_actions() const;
private:
    std::map<std::string, ActionCallback> actions_;
    int exec_count_ = 0;
    bool dry_run_ = false;
};
} // namespace zo