#pragma once

#include <string>

namespace synthesus::kernel {

struct BayesianSignal {
  std::string hypothesis;
  double prior = 0.5;
  double likelihood = 0.5;
};

class BayesianRouter {
public:
  double update(const BayesianSignal& signal) const;
};

}  // namespace synthesus::kernel

