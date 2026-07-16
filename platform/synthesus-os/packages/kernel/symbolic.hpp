#pragma once

#include <string>
#include <vector>

namespace synthesus::kernel {

struct SymbolicRule {
  std::string trigger;
  std::string conclusion;
};

class SymbolicRouter {
public:
  std::vector<std::string> match(const std::string& query, const std::vector<SymbolicRule>& rules) const;
};

}  // namespace synthesus::kernel

