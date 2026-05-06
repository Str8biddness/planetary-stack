#include "bayesian.hpp"
namespace zo {
void BayesianReasoner::add_node(const BayesNode& n) { nodes_[n.name] = n; }
void BayesianReasoner::set_likelihood(const std::string& h, const std::string& e, float p) {
    likelihoods_[h][e] = p;
}
float BayesianReasoner::update(float prior, float likelihood, float marginal) const {
    return marginal > 0 ? (likelihood * prior) / marginal : prior;
}
BayesResult BayesianReasoner::infer(const std::string& hypothesis,
                                    const std::vector<std::string>& evidence) const {
    auto nit = nodes_.find(hypothesis);
    float prior = nit != nodes_.end() ? nit->second.prior : 0.5f;
    float combined = prior;
    std::string ev_used;
    auto lit = likelihoods_.find(hypothesis);
    if (lit != likelihoods_.end()) {
        for (auto& e : evidence) {
            auto eit = lit->second.find(e);
            if (eit != lit->second.end()) {
                // Bayesian update: P(H|E) = P(E|H)*P(H)/P(E) [assume P(E)=0.5]
                combined = update(combined, eit->second, 0.5f);
                ev_used += e + " ";
            }
        }
    }
    return {combined, hypothesis, ev_used};
}
} // namespace zo
