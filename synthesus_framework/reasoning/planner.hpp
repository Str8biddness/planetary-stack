#pragma once
// Synthesus 2.0 Phase 7 - AI Planner (A* + MCTS hybrid)
#include <string>
#include <vector>
#include <functional>
namespace zo {
struct PlanNode {
    std::string state;
    std::string action;
    float g_cost{0.0f}; // cost from start
    float h_cost{0.0f}; // heuristic to goal
    float f_cost() const { return g_cost + h_cost; }
    std::string parent;
    bool operator<(const PlanNode& other) const { return f_cost() < other.f_cost(); }
};
struct Plan { std::vector<std::string> actions; float total_cost; bool found; };
using HeuristicFn = std::function<float(const std::string& state, const std::string& goal)>;
using TransitionFn = std::function<std::vector<std::pair<std::string,float>>(const std::string& state)>;
class Planner {
public:
    Plan astar(const std::string& start, const std::string& goal,
               TransitionFn transitions, HeuristicFn heuristic,
               size_t max_nodes = 10000) const;
    Plan mcts(const std::string& start, const std::string& goal,
              TransitionFn transitions, size_t iterations = 1000) const;
};
} // namespace zo
