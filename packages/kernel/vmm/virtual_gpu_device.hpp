#pragma once

#include "vmm.hpp"
#include <cstddef>
#include <cstdint>
#include <string>
#include <vector>
#include <mutex>

namespace synthesus::kernel::vmm {

struct VgdRegisterDump {
    std::string name;
    uint64_t offset{0};
    uint64_t absolute_address{0};
    uint64_t value{0};
    std::string access;
};

struct VgdDump {
    uint64_t base_address{0};
    uint64_t size{0};
    std::string gpu_model;
    uint64_t vram_total_mb{0};
    std::vector<VgdRegisterDump> registers;
};

class VirtualGPUDevice final : public MMIODevice {
public:
    static constexpr uint64_t kDefaultBase = 0xF2000000ull;
    static constexpr uint64_t kDefaultSize = 0x1000ull;
    static constexpr uint64_t kMagic = 0x56474431ull; // "VGD1"

    explicit VirtualGPUDevice(uint64_t base = kDefaultBase, uint64_t size = kDefaultSize);

    uint64_t base_address() const override { return base_; }
    uint64_t size() const override { return size_; }
    bool read(uint64_t offset, uint8_t* data, std::size_t len) override;
    bool write(uint64_t offset, const uint8_t* data, std::size_t len) override;

    void set_gpu_info(std::string model, uint64_t vram_mb);
    VgdDump dump() const;

private:
    enum Register : uint64_t {
        kRegMagic = 0x00,
        kRegVersion = 0x08,
        kRegStatus = 0x10,
        kRegVramTotal = 0x18,
        kRegComputeUnits = 0x20,
        kRegTensorLoad = 0x28,
        kRegCommand = 0x30,
        kRegLastErrorCode = 0x38
    };

    uint64_t read_register(uint64_t offset) const;
    bool write_register(uint64_t offset, uint64_t value);
    bool write_scalar(uint8_t* data, std::size_t len, uint64_t value) const;
    uint64_t read_scalar(const uint8_t* data, std::size_t len) const;

    uint64_t base_;
    uint64_t size_;
    uint64_t status_{1}; // 1 = Ready
    std::string gpu_model_{"Unknown GPU"};
    uint64_t vram_total_mb_{0};
    uint64_t compute_units_{0};
    uint64_t error_code_{0};
    mutable std::mutex mutex_;
};

} // namespace synthesus::kernel::vmm
