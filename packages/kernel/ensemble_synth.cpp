#include "ensemble_synth.hpp"

#include <stdexcept>

namespace synthesus::kernel {

SynthesisCandidate EnsembleSynthRouter::synthesize(
    const std::vector<SynthesisCandidate>& candidates) const {
  (void)candidates;
  // TODO: Implement kernel synthesis only after Python arbitration behavior is benchmarked.
  throw std::logic_error("EnsembleSynthRouter::synthesize is not implemented in the C++ kernel");
}

}  // namespace synthesus::kernel

