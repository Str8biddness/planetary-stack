#include "vpu_router.hpp"
namespace zo {
void VPURouter::register_vcu(std::shared_ptr<VCUBase> vcu) { vcus_.push_back(vcu); }
void VPURouter::set_fallback_vcu(std::shared_ptr<VCUBase> vcu) { fallback_ = vcu; }
std::vector<std::string> VPURouter::list_vcus() const {
    std::vector<std::string> ids;
    for (auto& v : vcus_) ids.push_back(v->id());
    return ids;
}
VCUOutput VPURouter::route(const VCUInput& input) {
    // Route to highest priority VCU that can handle input
    std::shared_ptr<VCUBase> best;
    float best_priority = -1;
    for (auto& v : vcus_) {
        if (v->enabled && v->can_handle(input) && v->priority > best_priority) {
            best = v; best_priority = v->priority;
        }
    }
    if (best) return best->process(input);
    if (fallback_) return fallback_->process(input);
    return {"No VCU handled input", 0.0f, "none", false};
}
VCUOutput VPURouter::route_all(const VCUInput& input) {
    // Broadcast to all handling VCUs, combine responses
    std::string combined;
    float max_conf = 0;
    for (auto& v : vcus_) {
        if (v->enabled && v->can_handle(input)) {
            auto out = v->process(input);
            combined += "[" + v->id() + "]" + out.result + " ";
            if (out.confidence > max_conf) max_conf = out.confidence;
        }
    }
    return {combined, max_conf, "VPU", !combined.empty()};
}
} // namespace zo
