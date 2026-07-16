#include "bayesian.hpp"

#include <stdexcept>

namespace synthesus::kernel {

double BayesianRouter::update(const BayesianSignal& signal) const {
  (void)signal;
  // TODO: Implement benchmarked Bayesian update offload for PPBRS confidence scoring.
  throw std::logic_error("BayesianRouter::update is not implemented in the C++ kernel");
}

}  // namespace synthesus::kernel

