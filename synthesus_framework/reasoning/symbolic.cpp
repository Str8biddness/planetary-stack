#include "symbolic.hpp"
#include <sstream>
namespace zo {
CNF SymbolicReasoner::unit_propagate(CNF formula, std::unordered_map<int,bool>& assignment) const {
    bool changed = true;
    while (changed) {
        changed = false;
        for (auto it = formula.begin(); it != formula.end(); ) {
            if (it->size() == 1) {
                int lit = (*it)[0];
                assignment[std::abs(lit)] = lit > 0;
                CNF next;
                for (auto& cl : formula) {
                    bool sat = false;
                    Clause ncl;
                    for (int l : cl) {
                        if (assignment.count(std::abs(l)) &&
                            assignment[std::abs(l)] == (l > 0)) { sat = true; break; }
                        if (!assignment.count(std::abs(l))) ncl.push_back(l);
                    }
                    if (!sat) next.push_back(ncl);
                }
                formula = next; changed = true; break;
            } else ++it;
        }
    }
    return formula;
}
int SymbolicReasoner::choose_literal(const CNF& formula) const {
    for (auto& cl : formula) for (int l : cl) return l;
    return 0;
}
bool SymbolicReasoner::dpll(CNF formula, std::unordered_map<int,bool>& assignment) const {
    formula = unit_propagate(formula, assignment);
    if (formula.empty()) return true;
    for (auto& cl : formula) if (cl.empty()) return false;
    int lit = choose_literal(formula);
    auto a1 = assignment; a1[std::abs(lit)] = lit > 0;
    CNF f1; for (auto& cl : formula) {
        bool sat = false; Clause nc;
        for (int l : cl) { if (a1.count(std::abs(l)) && a1[std::abs(l)]==(l>0)){sat=true;break;}
            if (!a1.count(std::abs(l))) nc.push_back(l); }
        if (!sat) f1.push_back(nc);
    }
    if (dpll(f1, a1)) { assignment = a1; return true; }
    auto a2 = assignment; a2[std::abs(lit)] = lit <= 0;
    CNF f2; for (auto& cl : formula) {
        bool sat = false; Clause nc;
        for (int l : cl) { if (a2.count(std::abs(l)) && a2[std::abs(l)]==(l>0)){sat=true;break;}
            if (!a2.count(std::abs(l))) nc.push_back(l); }
        if (!sat) f2.push_back(nc);
    }
    if (dpll(f2, a2)) { assignment = a2; return true; }
    return false;
}
SymbolicResult SymbolicReasoner::solve(const CNF& formula) const {
    SymbolicResult r;
    r.satisfiable = dpll(formula, r.assignment);
    return r;
}
bool SymbolicReasoner::entails(const CNF& kb, const Clause& query) const {
    CNF negated_query = kb;
    for (int lit : query) negated_query.push_back({-lit});
    return !solve(negated_query).satisfiable;
}
std::string SymbolicReasoner::explain(const SymbolicResult& r) const {
    if (!r.satisfiable) return "UNSAT";
    std::ostringstream ss;
    ss << "SAT: ";
    for (auto& [v,b] : r.assignment) ss << (b?"":"!") << v << " ";
    return ss.str();
}
} // namespace zo
