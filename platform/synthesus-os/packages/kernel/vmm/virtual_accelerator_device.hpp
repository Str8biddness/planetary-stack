#pragma once

#include "vmm.hpp"
#include <cstddef>
#include <cstdint>
#include <string>
#include <vector>
#include <mutex>
#include <functional>

namespace synthesus::kernel::vmm {

struct VadRegisterDump {
    std::string name;
    uint64_t offset{0};
    uint64_t absolute_address{0};
    uint64_t value{0};
    std::string access;
};

struct VadDump {
    uint64_t base_address{0};
    uint64_t size{0};
    uint64_t status{0}; // 0=Idle, 1=Busy, 2=Ready, 3=Error
    uint64_t last_operator{0};
    std::vector<VadRegisterDump> registers;
};

class VirtualAcceleratorDevice final : public MMIODevice {
public:
    static constexpr uint64_t kDefaultBase = 0xF7000000ull;
    static constexpr uint64_t kDefaultSize = 0x4000ull;
    static constexpr uint64_t kMagic = 0x56414431ull; // "VAD1"

    enum Operator : uint64_t {
        kOpNone = 0,
        kOpEmbedProject = 1,
        kOpPatchTile = 2,
        kOpTemporalFrame = 3,
        kOpQkvLinear = 4,
        kOpAttnTile = 5,
        kOpNormResidual = 6,
        kOpFfnBlock = 7,
        kOpRouteFuse = 8,
        kOpStateWrite = 9
    };

    explicit VirtualAcceleratorDevice(uint64_t base = kDefaultBase, uint64_t size = kDefaultSize);

    uint64_t base_address() const override { return base_; }
    uint64_t size() const override { return size_; }
    bool read(uint64_t offset, uint8_t* data, std::size_t len) override;
    bool write(uint64_t offset, const uint8_t* data, std::size_t len) override;

    void set_status(uint64_t status);
    VadDump dump() const;

private:
    enum Register : uint64_t {
        kRegMagic = 0x00,
        kRegVersion = 0x08,
        kRegStatus = 0x10,
        kRegCommand = 0x18,      // Write Operator ID to trigger
        kRegModelDim = 0x20,
        kRegHeadCount = 0x28,
        kRegContextLen = 0x30,
        kRegTilingSize = 0x38,
        kRegLastOp = 0x40,
        kRegSramUsage = 0x48,    // Hardware Contract metrics
        kRegCycleEst = 0x50,
        kRegDataBuffer = 0x100   // General I/O buffer for tiles/latents
    };

    uint64_t read_register(uint64_t offset) const;
    bool write_register(uint64_t offset, uint64_t value);
    bool write_scalar(uint8_t* data, std::size_t len, uint64_t value) const;
    uint64_t read_scalar(const uint8_t* data, std::size_t len) const;

    // Core operator simulation
    void execute_operator(Operator op);

    uint64_t base_;
    uint64_t size_;
    uint64_t status_{0};
    uint64_t last_op_{0};
    
    uint64_t model_dim_{512};
    uint64_t head_count_{8};
    uint64_t context_len_{512};
    uint64_t tiling_size_{64};

    // Hardware Contract Metrics
    uint64_t sram_usage_bytes_{0};
    uint64_t cycle_estimate_{0};

    std::vector<uint8_t> data_buffer_;
    mutable std::mutex mutex_;
};

} // namespace synthesus::kernel::vmm
