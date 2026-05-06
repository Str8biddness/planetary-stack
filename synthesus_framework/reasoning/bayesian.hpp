#pragma once
// Synthesus 2.0 Phase 7 - Bayesian Reasoner (Bayes' theorem + naive Bayes classifier)
#include <string>
#include <unordered_map>
#include <vector>
namespace zo {
struct BayesNode { std::string name; float prior{0.5f}; std::vector<std::string> parents; };
struct BayesResult { float posterior; std::string hypothesis; std::string evidence_used; };
class BayesianReasoner {
public:
    void add_node(const BayesNode& n);
    void set_likelihood(const std::string& h, const std::string& e, float p_e_given_h);
    BayesResult infer(const std::string& hypothesis, const std::vector<std::string>& evidence) const;
    float update(float prior, float likelihood, float marginal) const;
private:
    std::unordered_map<std::string, BayesNode> nodes_;
    std::unordered_map<std::string, std::unordered_map<std::string, float>> likelihoods_;
};
} // namespace zo
