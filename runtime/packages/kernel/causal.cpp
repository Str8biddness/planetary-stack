#include "causal.hpp"

#include <stdexcept>

namespace synthesus::kernel {

std::vector<CausalEdge> CausalRouter::infer(
    const std::vector<CausalEdge>& graph,
    const std::string& observation) const {
  (void)graph;
  (void)observation;
  // TODO: Implement causal traversal only after Python reasoning graph metrics are stable.
  throw std::logic_error("CausalRouter::infer is not implemented in the C++ kernel");
}

}  // namespace synthesus::kernel

