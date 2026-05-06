#include "perception_vcu.hpp"
namespace zo {
VCUOutput PerceptionVCU::process(const VCUInput& in) {
    if (modality_ == "audio") return process_audio(in);
    return process_text(in);
}
VCUOutput PerceptionVCU::process_text(const VCUInput& in) {
    VCUOutput out;
    out.vcu_id = "perception";
    out.result = "[PERCEPT:text] " + in.payload.substr(0, 80);
    out.confidence = 0.85f;
    out.tags = {"text", "perception"};
    return out;
}
VCUOutput PerceptionVCU::process_audio(const VCUInput& in) {
    VCUOutput out;
    out.vcu_id = "perception";
    out.result = "[PERCEPT:audio] transcription stub";
    out.confidence = 0.70f;
    out.tags = {"audio", "perception"};
    return out;
}
VCUOutput PerceptionVCU::fuse_modalities(std::vector<VCUOutput>& outs) {
    if (outs.empty()) return {};
    VCUOutput best = outs[0];
    for (auto& o : outs) if (o.confidence > best.confidence) best = o;
    best.tags.push_back("fused");
    return best;
}
} // namespace zo