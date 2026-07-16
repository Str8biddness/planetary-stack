#pragma once

#include <string>
#include <vector>

namespace synthesus::kernel {

struct CausalEdge {
  std::string cause;
  std::string effect;
  double weight = 1.0;
};

class CausalRouter {
public:
  std::vector<CausalEdge> infer(const std::vector<CausalEdge>& graph, const std::string& observation) const;
};

}  // namespace synthesus::kernel

