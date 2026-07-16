#pragma once

#include "vmm.hpp"
#include <cstddef>
#include <cstdint>
#include <string>
#include <vector>
#include <mutex>
#include <functional>

namespace synthesus::kernel::vmm {

struct VmdRegisterDump {
    std::string name;
    uint64_t offset{0};
    uint64_t absolute_address{0};
    uint64_t value{0};
    std::string access;
};

struct VmdDump {
    uint64_t base_address{0};
    uint64_t size{0};
    uint64_t status{0};
    uint64_t last_sync_ts{0};
    std::vector<VmdRegisterDump> registers;
};

class VirtualMirrorDevice final : public MMIODevice {
public:
    static constexpr uint64_t kDefaultBase = 0xF4000000ull;
    static constexpr uint64_t kDefaultSize = 0x1000ull;
    static constexpr uint64_t kMagic = 0x564D4431ull; // "VMD1"

    using SyncTriggerHandler = std::function<void()>;

    explicit VirtualMirrorDevice(uint64_t base = kDefaultBase, uint64_t size = kDefaultSize);

    uint64_t base_address() const override { return base_; }
    uint64_t size() const override { return size_; }
    bool read(uint64_t offset, uint8_t* data, std::size_t len) override;
    bool write(uint64_t offset, const uint8_t* data, std::size_t len) override;

    void set_trigger_handler(SyncTriggerHandler handler);
    void update_state(uint64_t status, uint64_t timestamp);
    VmdDump dump() const;

private:
    enum Register : uint64_t {
        kRegMagic = 0x00,
        kRegVersion = 0x08,
        kRegStatus = 0x10,      // 0=Idle, 1=Syncing, 2=Synced, 3=Stale, 4=Error
        kRegLastSyncTs = 0x18,
        kRegCommand = 0x20,     // 1=Trigger Sync
    };

    uint64_t read_register(uint64_t offset) const;
    bool write_register(uint64_t offset, uint64_t value);
    bool write_scalar(uint8_t* data, std::size_t len, uint64_t value) const;
    uint64_t read_scalar(const uint8_t* data, std::size_t len) const;

    uint64_t base_;
    uint64_t size_;
    uint64_t status_{0};
    uint64_t last_sync_ts_{0};
    SyncTriggerHandler trigger_handler_;
    mutable std::mutex mutex_;
};

} // namespace synthesus::kernel::vmm
