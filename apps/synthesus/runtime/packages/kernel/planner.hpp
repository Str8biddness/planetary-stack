#pragma once

#include <string>
#include <vector>

namespace synthesus::kernel {

struct PlannerStep {
  std::string id;
  std::string description;
  std::vector<std::string> dependencies;
};

class PlannerRouter {
public:
  std::vector<PlannerStep> plan(const std::string& query) const;
};

}  // namespace synthesus::kernel

