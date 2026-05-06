#include "causal.hpp"
#include <sstream>
namespace zo {
void CausalReasoner::add_variable(const CausalVar& v) { vars_[v.name] = v; }
void CausalReasoner::add_edge(const std::string& cause, const std::string& effect, float strength) {
    edges_[cause].push_back({effect, strength});
}
float CausalReasoner::propagate(const std::string& target,
        const std::unordered_map<std::string,float>& interventions) const {
    float total = 0.0f;
    for (auto& [cause, eflist] : edges_) {
        for (auto& [eff, str] : eflist) {
            if (eff == target) {
                float cv = interventions.count(cause) ? interventions.at(cause) :
                           (vars_.count(cause) ? vars_.at(cause).value : 0.0f);
                total += cv * str;
            }
        }
    }
    return total;
}
CausalResult CausalReasoner::do_intervention(const std::string& var, float value,
                                              const std::string& target) const {
    std::unordered_map<std::string,float> ivs{{var, value}};
    float effect = propagate(target, ivs);
    std::ostringstream ss;
    ss << "do(" << var << "=" << value << ") -> " << target << "=" << effect;
    return {target, effect, ss.str()};
}
CausalResult CausalReasoner::counterfactual(const std::string& var, float value,
                                             const std::string& target) const {
    // Counterfactual: abduction->action->prediction
    auto actual = propagate(target, {});
    auto ivs = std::unordered_map<std::string,float>{{var, value}};
    auto factual = propagate(target, ivs);
    std::ostringstream ss;
    ss << "CF: if " << var << "=" << value << " then " << target
       << " would be " << factual << " (actual: " << actual << ")";
    return {target, factual - actual, ss.str()};
}
} // namespace zo
