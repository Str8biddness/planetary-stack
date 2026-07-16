#include "planner.hpp"

#include <stdexcept>

namespace synthesus::kernel {

std::vector<PlannerStep> PlannerRouter::plan(const std::string& query) const {
  (void)query;
  // TODO: Offload Python planner hot-path after profiling confirms the boundary.
  throw std::logic_error("PlannerRouter::plan is not implemented in the C++ kernel");
}

}  // namespace synthesus::kernel

