#include "sinn.hpp"

#include <stdexcept>

namespace synthesus::kernel {

SinnState SinnRouter::step(const SinnState& state, const std::string& signal) const {
  (void)state;
  (void)signal;
  // TODO: Define the SINN state-transition kernel after the Python contract settles.
  throw std::logic_error("SinnRouter::step is not implemented in the C++ kernel");
}

}  // namespace synthesus::kernel

