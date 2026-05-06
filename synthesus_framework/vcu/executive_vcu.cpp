#include "executive_vcu.hpp"
#include <algorithm>
namespace zo {
void ExecutiveVCU::add_goal(const Goal& g) {
    goals_.push_back(g);
    std::sort(goals_.begin(), goals_.end(),
        [](const Goal& a, const Goal& b){ return a.priority > b.priority; });
}
void ExecutiveVCU::inhibit(const std::string& id) {
    for (auto& g : goals_) if (g.id == id) g.active = false;
}
Goal ExecutiveVCU::top_goal() const {
    for (const auto& g : goals_) if (g.active) return g;
    return Goal{"idle", "No active goal", 0.0f, true};
}
std::vector<Goal> ExecutiveVCU::active_goals() const {
    std::vector<Goal> out;
    for (const auto& g : goals_) if (g.active) out.push_back(g);
    return out;
}
VCUOutput ExecutiveVCU::process(const VCUInput& in) {
    tick_++;
    Goal g = top_goal();
    VCUOutput out;
    out.vcu_id = "executive";
    out.result = "[EXEC] tick=" + std::to_string(tick_) + " goal=" + g.id;
    out.confidence = g.priority;
    out.tags = {"executive", "goal"};
    return out;
}
} // namespace zo