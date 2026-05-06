#include "planner.hpp"
#include <queue>
#include <unordered_set>
#include <unordered_map>
#include <random>
namespace zo {
Plan Planner::astar(const std::string& start, const std::string& goal,
                    TransitionFn transitions, HeuristicFn heuristic, size_t max_nodes) const {
    using QElem = std::pair<float,PlanNode>;
    std::priority_queue<QElem, std::vector<QElem>, std::greater<QElem>> open;
    std::unordered_map<std::string, std::string> came_from;
    std::unordered_map<std::string, float> g_score;
    g_score[start] = 0;
    open.push({heuristic(start, goal), {start, "", 0, heuristic(start, goal), ""}});
    size_t nodes = 0;
    while (!open.empty() && nodes++ < max_nodes) {
        auto [f, curr] = open.top(); open.pop();
        if (curr.state == goal) {
            // reconstruct path
            Plan plan; plan.found = true; plan.total_cost = g_score[goal];
            std::string s = goal;
            while (s != start && came_from.count(s)) { plan.actions.push_back(s); s = came_from[s]; }
            std::reverse(plan.actions.begin(), plan.actions.end());
            return plan;
        }
        for (auto& [next, cost] : transitions(curr.state)) {
            float ng = g_score[curr.state] + cost;
            if (!g_score.count(next) || ng < g_score[next]) {
                g_score[next] = ng;
                came_from[next] = curr.state;
                open.push({ng + heuristic(next, goal), {next, "", ng, heuristic(next, goal), curr.state}});
            }
        }
    }
    return {{}, 0, false};
}
Plan Planner::mcts(const std::string& start, const std::string& goal,
                   TransitionFn transitions, size_t iterations) const {
    // Simplified random rollout MCTS
    std::mt19937 rng(std::random_device{}());
    std::vector<std::string> best_path;
    float best_score = -1e9f;
    for (size_t i = 0; i < iterations; ++i) {
        std::string state = start;
        std::vector<std::string> path = {state};
        float score = 0;
        for (size_t step = 0; step < 50; ++step) {
            if (state == goal) { score = 100.0f - step; break; }
            auto nexts = transitions(state);
            if (nexts.empty()) break;
            auto [ns, cost] = nexts[rng() % nexts.size()];
            state = ns; path.push_back(ns); score -= cost;
        }
        if (score > best_score) { best_score = score; best_path = path; }
    }
    bool found = !best_path.empty() && best_path.back() == goal;
    return {best_path, -best_score, found};
}
} // namespace zo
