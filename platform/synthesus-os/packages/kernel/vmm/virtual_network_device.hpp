#pragma once

#include "vmm.hpp"
#include <cstddef>
#include <cstdint>
#include <string>
#include <vector>
#include <mutex>
#include <functional>

namespace synthesus::kernel::vmm {

struct VndRegisterDump {
    std::string name;
    uint64_t offset{0};
    uint64_t absolute_address{0};
    uint64_t value{0};
    std::string access;
};

struct VndDump {
    uint64_t base_address{0};
    uint64_t size{0};
    uint64_t status{0};
    std::string last_query;
    std::vector<VndRegisterDump> registers;
};

class VirtualNetworkDevice final : public MMIODevice {
public:
    static constexpr uint64_t kDefaultBase = 0xF3000000ull;
    static constexpr uint64_t kDefaultSize = 0x2000ull; // Larger size for query buffer
    static constexpr uint64_t kMagic = 0x564E4431ull; // "VND1"

    using NetworkHandler = std::function<void(const std::string& query)>;

    explicit VirtualNetworkDevice(uint64_t base = kDefaultBase, uint64_t size = kDefaultSize);

    uint64_t base_address() const override { return base_; }
    uint64_t size() const override { return size_; }
    bool read(uint64_t offset, uint8_t* data, std::size_t len) override;
    bool write(uint64_t offset, const uint8_t* data, std::size_t len) override;

    void set_handler(NetworkHandler handler);
    void set_status(uint64_t status);
    VndDump dump() const;

private:
    enum Register : uint64_t {
        kRegMagic = 0x00,
        kRegVersion = 0x08,
        kRegStatus = 0x10,   // 0=Idle, 1=Busy, 2=Ready, 3=Error
        kRegCommand = 0x18,  // 1=Search
        kRegQueryLen = 0x20,
        kRegQueryBuffer = 0x100 // Start of query buffer
    };

    uint64_t read_register(uint64_t offset) const;
    bool write_register(uint64_t offset, uint64_t value);
    bool write_scalar(uint8_t* data, std::size_t len, uint64_t value) const;
    uint64_t read_scalar(const uint8_t* data, std::size_t len) const;

    uint64_t base_;
    uint64_t size_;
    uint64_t status_{0};
    std::string last_query_;
    std::vector<uint8_t> query_buffer_;
    NetworkHandler handler_;
    mutable std::mutex mutex_;
};

} // namespace synthesus::kernel::vmm
