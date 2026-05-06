#pragma once
// Synthesus 2.0 - ExecutiveVCU: goal management, task scheduling, inhibition
#include "vcu_base.hpp"
#include <string>
#include <vector>
namespace zo {
struct Goal {
    std::string id;
    std::string description;
    float priority = 0.5f;
    bool active = true;
};
class ExecutiveVCU : public VCUBase {
public:
    ExecutiveVCU() : VCUBase("executive") {}
    VCUOutput process(const VCUInput& in) override;
    void add_goal(const Goal& g);
    void inhibit(const std::string& goal_id);
    Goal top_goal() const;
    std::vector<Goal> active_goals() const;
private:
    std::vector<Goal> goals_;
    int tick_ = 0;
};
} // namespace zo