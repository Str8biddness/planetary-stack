#pragma once

#include "vmm.hpp"
#include <cstddef>
#include <cstdint>
#include <string>
#include <vector>
#include <mutex>
#include <functional>
#include <unordered_map>

namespace synthesus::kernel::vmm {

struct SllmRegisterDump {
    std::string name;
    uint64_t offset{0};
    uint64_t absolute_address{0};
    uint64_t value{0};
    std::string access;
};

struct SllmDump {
    uint64_t base_address{0};
    uint64_t size{0};
    uint64_t status{0};
    uint64_t vocab_size{0};
    uint64_t pattern_count{0};
    std::vector<SllmRegisterDump> registers;
};

class VirtualSllmDevice final : public MMIODevice {
public:
    static constexpr uint64_t kDefaultBase = 0xF6000000ull;
    static constexpr uint64_t kDefaultSize = 0x4000ull;
    static constexpr uint64_t kMagic = 0x534C4C4Dull; // "SLLM"

    using PredictHandler = std::function<std::string(const std::string& context)>;

    explicit VirtualSllmDevice(uint64_t base = kDefaultBase, uint64_t size = kDefaultSize);

    uint64_t base_address() const override { return base_; }
    uint64_t size() const override { return size_; }
    bool read(uint64_t offset, uint8_t* data, std::size_t len) override;
    bool write(uint64_t offset, const uint8_t* data, std::size_t len) override;

    void set_predict_handler(PredictHandler handler);
    void update_stats(uint64_t vocab_size, uint64_t pattern_count);
    SllmDump dump() const;

private:
    enum Register : uint64_t {
        kRegMagic = 0x00,
        kRegVersion = 0x08,
        kRegStatus = 0x10,      // 0=Idle, 1=Predicting, 2=Ready, 3=Error
        kRegVocabSize = 0x18,
        kRegPatternCount = 0x20,
        kRegCommand = 0x28,     // 1=Predict Next Token
        kRegContextLen = 0x30,
        kRegResultLen = 0x38,
        kRegContextBuffer = 0x100,
        kRegResultBuffer = 0x1000
    };

    uint64_t read_register(uint64_t offset) const;
    bool write_register(uint64_t offset, uint64_t value);
    bool write_scalar(uint8_t* data, std::size_t len, uint64_t value) const;
    uint64_t read_scalar(const uint8_t* data, std::size_t len) const;

    uint64_t base_;
    uint64_t size_;
    uint64_t status_{0};
    uint64_t vocab_size_{0};
    uint64_t pattern_count_{0};

    std::vector<uint8_t> context_buffer_;
    std::vector<uint8_t> result_buffer_;
    PredictHandler predict_handler_;

    mutable std::mutex mutex_;
};

} // namespace synthesus::kernel::vmm
