#include "telemetry.hpp"
#include <sstream>
namespace zo {
Telemetry& Telemetry::instance() { static Telemetry t; return t; }
void Telemetry::record(const std::string& metric, float value, const std::string& unit) {
    auto now = (uint64_t)std::chrono::duration_cast<std::chrono::milliseconds>(
        std::chrono::system_clock::now().time_since_epoch()).count();
    std::lock_guard<std::mutex> lk(mutex_);
    metrics_[metric] = {value, now, unit};
}
MetricValue Telemetry::get(const std::string& metric) const {
    std::lock_guard<std::mutex> lk(mutex_);
    auto it = metrics_.find(metric);
    return it != metrics_.end() ? it->second : MetricValue{0.0f, 0, ""};
}
std::unordered_map<std::string, MetricValue> Telemetry::snapshot() const {
    std::lock_guard<std::mutex> lk(mutex_); return metrics_;
}
std::string Telemetry::json_report() const {
    std::lock_guard<std::mutex> lk(mutex_);
    std::ostringstream ss; ss << "{";
    bool first = true;
    for (auto& [k, v] : metrics_) {
        if (!first) ss << ",";
        ss << "\"" << k << "\":{\"value\":" << v.value
           << ",\"ts\":" << v.timestamp_ms
           << ",\"unit\":\"" << v.unit << "\"}";
        first = false;
    }
    ss << "}"; return ss.str();
}
void Telemetry::reset(const std::string& metric) {
    std::lock_guard<std::mutex> lk(mutex_); metrics_.erase(metric);
}
void Telemetry::reset_all() {
    std::lock_guard<std::mutex> lk(mutex_); metrics_.clear();
}
} // namespace zo
