#pragma once
// Synthesus 2.0 Phase 7 - Symbolic Reasoning (DPLL-based SAT + predicate logic)
#include <string>
#include <vector>
#include <unordered_map>
namespace zo {
using Clause = std::vector<int>; // positive = true literal, negative = negated
using CNF = std::vector<Clause>;
struct SymbolicResult { bool satisfiable; std::unordered_map<int,bool> assignment; std::string explanation; };
class SymbolicReasoner {
public:
    SymbolicResult solve(const CNF& formula) const;
    bool entails(const CNF& kb, const Clause& query) const;
    std::string explain(const SymbolicResult& r) const;
private:
    bool dpll(CNF formula, std::unordered_map<int,bool>& assignment) const;
    CNF unit_propagate(CNF formula, std::unordered_map<int,bool>& assignment) const;
    int choose_literal(const CNF& formula) const;
};
} // namespace zo
