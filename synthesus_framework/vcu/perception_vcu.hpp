#pragma once
// Synthesus 2.0 - PerceptionVCU: multi-modal sensory input processing
#include "vcu_base.hpp"
#include <string>
#include <vector>
namespace zo {
class PerceptionVCU : public VCUBase {
public:
    PerceptionVCU() : VCUBase("perception") {}
    VCUOutput process(const VCUInput& in) override;
    std::string get_modality() const { return modality_; }
    void set_modality(const std::string& m) { modality_ = m; }
private:
    std::string modality_ = "text"; // text|audio|vision|multimodal
    VCUOutput process_text(const VCUInput& in);
    VCUOutput process_audio(const VCUInput& in);
    VCUOutput fuse_modalities(std::vector<VCUOutput>& outs);
};
} // namespace zo