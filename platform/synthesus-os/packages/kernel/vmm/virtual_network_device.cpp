#include "virtual_network_device.hpp"
#include <algorithm>
#include <cstring>

namespace synthesus::kernel::vmm {

VirtualNetworkDevice::VirtualNetworkDevice(uint64_t base, uint64_t size)
    : base_(base), size_(std::max<uint64_t>(size, kDefaultSize)) {
    query_buffer_.resize(size_ - kRegQueryBuffer, 0);
}

bool VirtualNetworkDevice::read(uint64_t offset, uint8_t* data, std::size_t len) {
    if (!data || len == 0 || offset + len > size_) return false;
    std::lock_guard<std::mutex> lock(mutex_);
    
    if (offset >= kRegQueryBuffer) {
        const auto buf_offset = offset - kRegQueryBuffer;
        const auto copy_len = std::min<std::size_t>(len, query_buffer_.size() - buf_offset);
        std::memcpy(data, query_buffer_.data() + buf_offset, copy_len);
        return true;
    }

    return write_scalar(data, len, read_register(offset));
}

bool VirtualNetworkDevice::write(uint64_t offset, const uint8_t* data, std::size_t len) {
    if (!data || len == 0 || offset + len > size_) return false;
    std::lock_guard<std::mutex> lock(mutex_);

    if (offset >= kRegQueryBuffer) {
        const auto buf_offset = offset - kRegQueryBuffer;
        const auto copy_len = std::min<std::size_t>(len, query_buffer_.size() - buf_offset);
        std::memcpy(query_buffer_.data() + buf_offset, data, copy_len);
        return true;
    }

    const auto value = read_scalar(data, len);
    return write_register(offset, value);
}

void VirtualNetworkDevice::set_handler(NetworkHandler handler) {
    std::lock_guard<std::mutex> lock(mutex_);
    handler_ = std::move(handler);
}

void VirtualNetworkDevice::set_status(uint64_t status) {
    std::lock_guard<std::mutex> lock(mutex_);
    status_ = status;
}

uint64_t VirtualNetworkDevice::read_register(uint64_t offset) const {
    switch (offset) {
        case kRegMagic: return kMagic;
        case kRegVersion: return 1;
        case kRegStatus: return status_;
        case kRegQueryLen: {
            const char* buf_ptr = reinterpret_cast<const char*>(query_buffer_.data());
            return std::strlen(buf_ptr);
        }
        default: return 0;
    }
}

bool VirtualNetworkDevice::write_register(uint64_t offset, uint64_t value) {
    switch (offset) {
        case kRegCommand:
            if (value == 1 && handler_) {
                status_ = 1; // Busy
                const char* query_ptr = reinterpret_cast<const char*>(query_buffer_.data());
                last_query_ = query_ptr;
                // Launch handler (should be asynchronous on the caller side or in Python)
                handler_(last_query_);
            }
            return true;
        default:
            return false;
    }
}

VndDump VirtualNetworkDevice::dump() const {
    std::lock_guard<std::mutex> lock(mutex_);
    VndDump snapshot;
    snapshot.base_address = base_;
    snapshot.size = size_;
    snapshot.status = status_;
    snapshot.last_query = last_query_;

    const struct { const char* name; uint64_t offset; const char* access; } specs[] = {
        {"MAGIC", kRegMagic, "ro"},
        {"VERSION", kRegVersion, "ro"},
        {"STATUS", kRegStatus, "ro"},
        {"COMMAND", kRegCommand, "wo"},
        {"QLEN", kRegQueryLen, "ro"},
    };

    for (const auto& s : specs) {
        snapshot.registers.push_back({s.name, s.offset, base_ + s.offset, read_register(s.offset), s.access});
    }
    return snapshot;
}

bool VirtualNetworkDevice::write_scalar(uint8_t* data, std::size_t len, uint64_t value) const {
    const auto copy_len = std::min<std::size_t>(len, sizeof(value));
    std::memcpy(data, &value, copy_len);
    return true;
}

uint64_t VirtualNetworkDevice::read_scalar(const uint8_t* data, std::size_t len) const {
    uint64_t value = 0;
    std::memcpy(&value, data, std::min<std::size_t>(len, sizeof(value)));
    return value;
}

} // namespace synthesus::kernel::vmm
