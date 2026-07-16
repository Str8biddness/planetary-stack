#include "virtual_mirror_device.hpp"
#include <algorithm>
#include <cstring>

namespace synthesus::kernel::vmm {

VirtualMirrorDevice::VirtualMirrorDevice(uint64_t base, uint64_t size)
    : base_(base), size_(std::max<uint64_t>(size, kDefaultSize)) {}

bool VirtualMirrorDevice::read(uint64_t offset, uint8_t* data, std::size_t len) {
    if (!data || len == 0 || offset + len > size_) return false;
    std::lock_guard<std::mutex> lock(mutex_);
    return write_scalar(data, len, read_register(offset));
}

bool VirtualMirrorDevice::write(uint64_t offset, const uint8_t* data, std::size_t len) {
    if (!data || len == 0 || offset + len > size_) return false;
    const auto value = read_scalar(data, len);
    std::lock_guard<std::mutex> lock(mutex_);
    return write_register(offset, value);
}

void VirtualMirrorDevice::set_trigger_handler(SyncTriggerHandler handler) {
    std::lock_guard<std::mutex> lock(mutex_);
    trigger_handler_ = std::move(handler);
}

void VirtualMirrorDevice::update_state(uint64_t status, uint64_t timestamp) {
    std::lock_guard<std::mutex> lock(mutex_);
    status_ = status;
    last_sync_ts_ = timestamp;
}

uint64_t VirtualMirrorDevice::read_register(uint64_t offset) const {
    switch (offset) {
        case kRegMagic: return kMagic;
        case kRegVersion: return 1;
        case kRegStatus: return status_;
        case kRegLastSyncTs: return last_sync_ts_;
        default: return 0;
    }
}

bool VirtualMirrorDevice::write_register(uint64_t offset, uint64_t value) {
    switch (offset) {
        case kRegCommand:
            if (value == 1 && trigger_handler_) {
                status_ = 1; // Syncing
                trigger_handler_();
            }
            return true;
        default:
            return false;
    }
}

VmdDump VirtualMirrorDevice::dump() const {
    std::lock_guard<std::mutex> lock(mutex_);
    VmdDump snapshot;
    snapshot.base_address = base_;
    snapshot.size = size_;
    snapshot.status = status_;
    snapshot.last_sync_ts = last_sync_ts_;

    const struct { const char* name; uint64_t offset; const char* access; } specs[] = {
        {"MAGIC", kRegMagic, "ro"},
        {"VERSION", kRegVersion, "ro"},
        {"STATUS", kRegStatus, "ro"},
        {"LAST_SYNC", kRegLastSyncTs, "ro"},
        {"COMMAND", kRegCommand, "wo"},
    };

    for (const auto& s : specs) {
        snapshot.registers.push_back({s.name, s.offset, base_ + s.offset, read_register(s.offset), s.access});
    }
    return snapshot;
}

bool VirtualMirrorDevice::write_scalar(uint8_t* data, std::size_t len, uint64_t value) const {
    const auto copy_len = std::min<std::size_t>(len, sizeof(value));
    std::memcpy(data, &value, copy_len);
    return true;
}

uint64_t VirtualMirrorDevice::read_scalar(const uint8_t* data, std::size_t len) const {
    uint64_t value = 0;
    std::memcpy(&value, data, std::min<std::size_t>(len, sizeof(value)));
    return value;
}

} // namespace synthesus::kernel::vmm
