#pragma once

#include <string>
#include <vector>
#include <map>
#include <cstdint>

namespace synthesus::kernel::emul_engineering {

struct CPUInfo {
    std::string vendor;
    std::string model;
    uint32_t cores = 0;
    uint32_t family = 0;
    uint32_t model_id = 0;
    uint32_t stepping = 0;
    std::vector<std::string> features;
};

struct MemoryInfo {
    uint64_t total_ram_mb = 0;
    std::string topology; // e.g., NUMA, channels
};

struct HostHardwareMap {
    CPUInfo cpu;
    MemoryInfo memory;
    std::vector<std::string> accelerators; // GPUs, NPUs, etc.
};

class HardwareProfiler {
public:
    HardwareProfiler();
    HostHardwareMap profile_host();

private:
    void get_cpu_info(CPUInfo& info);
    void get_memory_info(MemoryInfo& info);
    void get_accelerator_info(std::vector<std::string>& info);
};

} // namespace synthesus::kernel::emul_engineering
