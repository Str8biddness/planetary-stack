#pragma once
// Synthesus 2.0 - SensoryVCU: raw sensor integration (IMU, temp, proximity)
#include "vcu_base.hpp"
#include <string>
#include <map>
#include <cstdint>
namespace zo {
struct SensorReading {
    std::string sensor_id;
    float value = 0.0f;
    std::string unit;
    uint64_t timestamp_ms = 0;
};
class SensoryVCU : public VCUBase {
public:
    SensoryVCU() : VCUBase("sensory") {}
    VCUOutput process(const VCUInput& in) override;
    void ingest(const SensorReading& r);
    float get(const std::string& id) const;
    bool has(const std::string& id) const;
private:
    std::map<std::string, SensorReading> readings_;
};
} // namespace zo