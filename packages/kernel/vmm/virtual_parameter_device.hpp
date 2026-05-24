#pragma once

#include "vmm.hpp"
#include <cstddef>
#include <cstdint>
#include <string>
#include <unordered_map>
#include <vector>

namespace synthesus::kernel::vmm {

struct ParameterRecord {
    std::string key;
    std::vector<uint8_t> bytes;
    uint64_t version{1};
};

struct VpdRegisterDump {
    std::string name;
    uint64_t offset{0};
    uint64_t absolute_address{0};
    uint64_t value{0};
    std::string access;
};

struct VpdSelectedParameterDump {
    bool available{false};
    uint64_t index{0};
    std::string key;
    uint64_t version{0};
    uint64_t size{0};
    uint64_t data_offset{0};
    uint64_t data_length{0};
    std::vector<uint8_t> bytes;
};

struct VpdDump {
    uint64_t base_address{0};
    uint64_t size{0};
    uint64_t data_window_offset{0};
    uint64_t parameter_count{0};
    std::vector<VpdRegisterDump> registers;
    VpdSelectedParameterDump selected_parameter;
};

class VirtualParameterDevice final : public MMIODevice {
public:
    static constexpr uint64_t kDefaultBase = 0xF0000000ull;
    static constexpr uint64_t kDefaultSize = 0x2000ull;
    static constexpr uint64_t kMagic = 0x56504431ull; // "VPD1"

    explicit VirtualParameterDevice(uint64_t base = kDefaultBase, uint64_t size = kDefaultSize);

    uint64_t base_address() const override { return base_; }
    uint64_t size() const override { return size_; }
    bool read(uint64_t offset, uint8_t* data, std::size_t len) override;
    bool write(uint64_t offset, const uint8_t* data, std::size_t len) override;

    std::size_t add_parameter(std::string key, std::vector<uint8_t> bytes, uint64_t version = 1);
    bool set_parameter(std::string key, std::vector<uint8_t> bytes, uint64_t version = 1);
    const ParameterRecord* get_parameter(const std::string& key) const;
    const ParameterRecord* selected_parameter() const;
    std::size_t parameter_count() const { return parameters_.size(); }
    VpdDump dump() const;

private:
    enum Register : uint64_t {
        kRegMagic = 0x00,
        kRegVersion = 0x08,
        kRegParameterCount = 0x10,
        kRegSelectedIndex = 0x18,
        kRegSelectedSize = 0x20,
        kRegDataOffset = 0x28,
        kRegDataLength = 0x30,
        kRegKeyHash = 0x38,
        kRegStatus = 0x40,
        kDataWindow = 0x100
    };

    uint64_t read_register(uint64_t offset) const;
    bool write_register(uint64_t offset, uint64_t value);
    bool write_scalar(uint8_t* data, std::size_t len, uint64_t value) const;
    uint64_t read_scalar(const uint8_t* data, std::size_t len) const;
    uint64_t selected_key_hash() const;

    uint64_t base_;
    uint64_t size_;
    std::vector<ParameterRecord> parameters_;
    std::unordered_map<std::string, std::size_t> index_by_key_;
    uint64_t selected_index_{0};
    uint64_t data_offset_{0};
    uint64_t data_length_{0};
};

} // namespace synthesus::kernel::vmm
