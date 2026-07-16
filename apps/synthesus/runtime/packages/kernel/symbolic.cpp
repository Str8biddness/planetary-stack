#include "symbolic.hpp"

#include <stdexcept>

namespace synthesus::kernel {

std::vector<std::string> SymbolicRouter::match(
    const std::string& query,
    const std::vector<SymbolicRule>& rules) const {
  (void)query;
  (void)rules;
  // TODO: Move symbolic matching here only after PPBRS Python indexes are measured.
  throw std::logic_error("SymbolicRouter::match is not implemented in the C++ kernel");
}

}  // namespace synthesus::kernel

