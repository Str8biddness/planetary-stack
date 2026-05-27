#pragma once

#include <string>

namespace synthesus::kernel {

struct SinnState {
  std::string state_id;
  double activation = 0.0;
};

class SinnRouter {
public:
  SinnState step(const SinnState& state, const std::string& signal) const;
};

}  // namespace synthesus::kernel

