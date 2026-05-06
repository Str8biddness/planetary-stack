#pragma once
// Synthesus 2.0 Phase 7 - Telemetry (performance metrics + health reporting)
#include <string>
#include <unordered_map>
#include <mutex>
#include <chrono>
namespace zo {
struct MetricValue { float value; uint64_t timestamp_ms; std::string unit; };
class Telemetry {
public:
    static Telemetry& instance();
    void record(const std::string& metric, float value, const std::string& unit = "");
    MetricValue get(const std::string& metric) const;
    std::unordered_map<std::string, MetricValue> snapshot() const;
    std::string json_report() const;
    void reset(const std::string& metric);
    void reset_all();
private:
    Telemetry() = default;
    mutable std::mutex mutex_;
    std::unordered_map<std::string, MetricValue> metrics_;
};
} // namespace zo
