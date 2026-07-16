#pragma once

#include <string>
#include <vector>

namespace synthesus::kernel {

struct SynthesisCandidate {
  std::string text;
  double confidence = 0.0;
};

class EnsembleSynthRouter {
public:
  SynthesisCandidate synthesize(const std::vector<SynthesisCandidate>& candidates) const;
};

}  // namespace synthesus::kernel

