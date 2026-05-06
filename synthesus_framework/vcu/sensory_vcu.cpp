#include "sensory_vcu.hpp"
#include <chrono>
namespace zo {
static uint64_t now_ms() {
    return (uint64_t)std::chrono::duration_cast<std::chrono::milliseconds>(
        std::chrono::system_clock::now().time_since_epoch()).count();
}
void SensoryVCU::ingest(const SensorReading& r) {
    auto copy = r;
    copy.timestamp_ms = now_ms();
    readings_[r.sensor_id] = copy;
}
float SensoryVCU::get(const std::string& id) const {
    auto it = readings_.find(id);
    return it != readings_.end() ? it->second.value : 0.0f;
}
bool SensoryVCU::has(const std::string& id) const {
    return readings_.count(id) > 0;
}
VCUOutput SensoryVCU::process(const VCUInput& in) {
    VCUOutput out;
    out.vcu_id = "sensory";
    out.result = "[SENSORY] " + std::to_string(readings_.size()) + " sensors active";
    out.confidence = readings_.empty() ? 0.0f : 0.85f;
    out.tags = {"sensory"};
    return out;
}
} // namespace zo