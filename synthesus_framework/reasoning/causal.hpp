#pragma once
// Synthesus 2.0 Phase 7 - Causal Reasoning (Pearl do-calculus)
#include <string>
#include <vector>
#include <unordered_map>
namespace zo {
struct CausalVar { std::string name; float value{0.0f}; bool observed{false}; };
struct CausalResult { std::string outcome; float effect_size; std::string explanation; };
class CausalReasoner {
public:
    void add_variable(const CausalVar& v);
    void add_edge(const std::string& cause, const std::string& effect, float strength = 1.0f);
    // do(X=x): interventional distribution
    CausalResult do_intervention(const std::string& var, float value, const std::string& target) const;
    // Counterfactual: what would Y be if X had been x?
    CausalResult counterfactual(const std::string& var, float value, const std::string& target) const;
private:
    std::unordered_map<std::string, CausalVar> vars_;
    std::unordered_map<std::string, std::vector<std::pair<std::string,float>>> edges_; // cause->[(effect,strength)]
    float propagate(const std::string& target, const std::unordered_map<std::string,float>& interventions) const;
};
} // namespace zo
