#include "virtual_gpu_device.hpp"
#include <algorithm>
#include <cstring>

namespace synthesus::kernel::vmm {

VirtualGPUDevice::VirtualGPUDevice(uint64_t base, uint64_t size)
    : base_(base), size_(std::max<uint64_t>(size, kDefaultSize)) {}

bool VirtualGPUDevice::read(uint64_t offset, uint8_t* data, std::size_t len) {
    if (!data || len == 0 || offset + len > size_) return false;
    std::lock_guard<std::mutex> lock(mutex_);
    return write_scalar(data, len, read_register(offset));
}

bool VirtualGPUDevice::write(uint64_t offset, const uint8_t* data, std::size_t len) {
    if (!data || len == 0 || offset + len > size_) return false;
    const auto value = read_scalar(data, len);
    std::lock_guard<std::mutex> lock(mutex_);
    return write_register(offset, value);
}

void VirtualGPUDevice::set_gpu_info(std::string model, uint64_t vram_mb) {
    std::lock_guard<std::mutex> lock(mutex_);
    gpu_model_ = std::move(model);
    vram_total_mb_ = vram_mb;
    compute_units_ = vram_mb / 256; // Mock heuristic
}

uint64_t VirtualGPUDevice::read_register(uint64_t offset) const {
    switch (offset) {
        case kRegMagic: return kMagic;
        case kRegVersion: return 1;
        case kRegStatus: return status_;
        case kRegVramTotal: return vram_total_mb_;
        case kRegComputeUnits: return compute_units_;
        case kRegTensorLoad: return 0; // Dynamic
        case kRegLastErrorCode: return error_code_;
        default: return 0;
    }
}

bool VirtualGPUDevice::write_register(uint64_t offset, uint64_t value) {
    switch (offset) {
        case kRegCommand:
            if (value == 1) { // Trigger Mock Tensor Sync
                status_ = 2; // Busy
            } else if (value == 2) {
                status_ = 1; // Reset to Ready
            }
            return true;
        default:
            return false;
    }
}

VgdDump VirtualGPUDevice::dump() const {
    std::lock_guard<std::mutex> lock(mutex_);
    VgdDump snapshot;
    snapshot.base_address = base_;
    snapshot.size = size_;
    snapshot.gpu_model = gpu_model_;
    snapshot.vram_total_mb = vram_total_mb_;

    const struct { const char* name; uint64_t offset; const char* access; } specs[] = {
        {"MAGIC", kRegMagic, "ro"},
        {"VERSION", kRegVersion, "ro"},
        {"STATUS", kRegStatus, "ro"},
        {"VRAM_MB", kRegVramTotal, "ro"},
        {"C_UNITS", kRegComputeUnits, "ro"},
        {"COMMAND", kRegCommand, "wo"},
    };

    for (const auto& s : specs) {
        snapshot.registers.push_back({s.name, s.offset, base_ + s.offset, read_register(s.offset), s.access});
    }
    return snapshot;
}

bool VirtualGPUDevice::write_scalar(uint8_t* data, std::size_t len, uint64_t value) const {
    const auto copy_len = std::min<std::size_t>(len, sizeof(value));
    std::memcpy(data, &value, copy_len);
    return true;
}

uint64_t VirtualGPUDevice::read_scalar(const uint8_t* data, std::size_t len) const {
    uint64_t value = 0;
    std::memcpy(&value, data, std::min<std::size_t>(len, sizeof(value)));
    return value;
}

} // namespace synthesus::kernel::vmm
