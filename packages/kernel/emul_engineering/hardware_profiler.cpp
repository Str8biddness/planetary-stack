#include "hardware_profiler.hpp"
#include <cpuid.h>
#include <fstream>
#include <sstream>
#include <iostream>
#include <algorithm>
#include <cstring>
#include <thread>

namespace synthesus::kernel::emul_engineering {

HardwareProfiler::HardwareProfiler() {}

HostHardwareMap HardwareProfiler::profile_host() {
    HostHardwareMap map;
    get_cpu_info(map.cpu);
    get_memory_info(map.memory);
    get_accelerator_info(map.accelerators);
    return map;
}

void HardwareProfiler::get_cpu_info(CPUInfo& info) {
    uint32_t eax, ebx, ecx, edx;

    info.cores = std::thread::hardware_concurrency();

    // Vendor ID
    if (__get_cpuid(0, &eax, &ebx, &ecx, &edx)) {
        char vendor[13];
        memcpy(vendor, &ebx, 4);
        memcpy(vendor + 4, &edx, 4);
        memcpy(vendor + 8, &ecx, 4);
        vendor[12] = '\0';
        info.vendor = vendor;
    }

    // Family, Model, Stepping
    if (__get_cpuid(1, &eax, &ebx, &ecx, &edx)) {
        info.stepping = eax & 0xF;
        info.model_id = (eax >> 4) & 0xF;
        info.family = (eax >> 8) & 0xF;
        if (info.family == 0xF) info.family += (eax >> 20) & 0xFF;
        if (info.family == 0x6 || info.family == 0xF) info.model_id += ((eax >> 16) & 0xF) << 4;
        
        // Features
        if (edx & bit_SSE2) info.features.push_back("sse2");
        if (ecx & bit_SSE3) info.features.push_back("sse3");
        if (ecx & bit_AVX) info.features.push_back("avx");
    }

    // Extended Features
    if (__get_cpuid_count(7, 0, &eax, &ebx, &ecx, &edx)) {
        if (ebx & bit_AVX2) info.features.push_back("avx2");
        if (ebx & bit_AVX512F) info.features.push_back("avx512");
    }

    // CPU Model Name
    char brand[48];
    memset(brand, 0, 48);
    for (uint32_t i = 0x80000002; i <= 0x80000004; ++i) {
        if (__get_cpuid(i, &eax, &ebx, &ecx, &edx)) {
            memcpy(brand + (i - 0x80000002) * 16, &eax, 4);
            memcpy(brand + (i - 0x80000002) * 16 + 4, &ebx, 4);
            memcpy(brand + (i - 0x80000002) * 16 + 8, &ecx, 4);
            memcpy(brand + (i - 0x80000002) * 16 + 12, &edx, 4);
        }
    }
    info.model = brand;
}

void HardwareProfiler::get_memory_info(MemoryInfo& info) {
    std::ifstream meminfo("/proc/meminfo");
    std::string line;
    while (std::getline(meminfo, line)) {
        if (line.compare(0, 8, "MemTotal") == 0) {
            std::stringstream ss(line);
            std::string label;
            uint64_t kb;
            ss >> label >> kb;
            info.total_ram_mb = kb / 1024;
            break;
        }
    }
    info.topology = "standard_smp"; // Placeholder
}

void HardwareProfiler::get_accelerator_info(std::vector<std::string>& info) {
    if (std::ifstream("/dev/nvidiactl")) {
        info.push_back("nvidia_gpu_detected");
    }
    if (std::ifstream("/dev/dri/renderD128")) {
        info.push_back("intel_amd_dri_detected");
    }
    if (info.empty()) {
        info.push_back("no_dedicated_gpu");
    }
}

} // namespace synthesus::kernel::emul_engineering
