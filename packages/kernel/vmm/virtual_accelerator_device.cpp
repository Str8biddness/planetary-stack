#include "virtual_accelerator_device.hpp"
#include <algorithm>
#include <cstring>
#include <iostream>

namespace synthesus::kernel::vmm {

VirtualAcceleratorDevice::VirtualAcceleratorDevice(uint64_t base, uint64_t size)
    : base_(base), size_(std::max<uint64_t>(size, kDefaultSize)) {
    data_buffer_.resize(size_ - kRegDataBuffer, 0);
}

bool VirtualAcceleratorDevice::read(uint64_t offset, uint8_t* data, std::size_t len) {
    if (!data || len == 0 || offset + len > size_) return false;
    std::lock_guard<std::mutex> lock(mutex_);

    if (offset >= kRegDataBuffer) {
        const auto buf_offset = offset - kRegDataBuffer;
        const auto copy_len = std::min<std::size_t>(len, data_buffer_.size() - buf_offset);
        std::memcpy(data, data_buffer_.data() + buf_offset, copy_len);
        return true;
    }

    return write_scalar(data, len, read_register(offset));
}

bool VirtualAcceleratorDevice::write(uint64_t offset, const uint8_t* data, std::size_t len) {
    if (!data || len == 0 || offset + len > size_) return false;
    std::lock_guard<std::mutex> lock(mutex_);

    if (offset >= kRegDataBuffer) {
        const auto buf_offset = offset - kRegDataBuffer;
        const auto copy_len = std::min<std::size_t>(len, data_buffer_.size() - buf_offset);
        std::memcpy(data_buffer_.data() + buf_offset, data, copy_len);
        return true;
    }

    const auto value = read_scalar(data, len);
    return write_register(offset, value);
}

void VirtualAcceleratorDevice::set_status(uint64_t status) {
    std::lock_guard<std::mutex> lock(mutex_);
    status_ = status;
}

uint64_t VirtualAcceleratorDevice::read_register(uint64_t offset) const {
    switch (offset) {
        case kRegMagic: return kMagic;
        case kRegVersion: return 1;
        case kRegStatus: return status_;
        case kRegModelDim: return model_dim_;
        case kRegHeadCount: return head_count_;
        case kRegContextLen: return context_len_;
        case kRegTilingSize: return tiling_size_;
        case kRegLastOp: return last_op_;
        case kRegSramUsage: return sram_usage_bytes_;
        case kRegCycleEst: return cycle_estimate_;
        default: return 0;
    }
}

bool VirtualAcceleratorDevice::write_register(uint64_t offset, uint64_t value) {
    switch (offset) {
        case kRegModelDim: model_dim_ = value; return true;
        case kRegHeadCount: head_count_ = value; return true;
        case kRegContextLen: context_len_ = value; return true;
        case kRegTilingSize: tiling_size_ = value; return true;
        case kRegCommand:
            last_op_ = value;
            execute_operator(static_cast<Operator>(value));
            return true;
        default:
            return false;
    }
}

void VirtualAcceleratorDevice::execute_operator(Operator op) {
    status_ = 1; // Busy
    
    // Simulate hardware contract logic
    switch (op) {
        case kOpAttnTile:
            // attention performance often limited more by memory traffic than by raw arithmetic throughput
            sram_usage_bytes_ = tiling_size_ * (model_dim_ / head_count_) * 4 * 3; // Q,K,V tiles
            cycle_estimate_ = (tiling_size_ * tiling_size_) / 4; // Mock tiling acceleration
            break;
        case kOpQkvLinear:
            sram_usage_bytes_ = model_dim_ * model_dim_ * 4;
            cycle_estimate_ = (model_dim_ * model_dim_) / 64; // Optimized Tensor Fabric
            break;
        case kOpFfnBlock:
            sram_usage_bytes_ = model_dim_ * model_dim_ * 8; // 4x expansion
            cycle_estimate_ = (model_dim_ * model_dim_ * 4) / 64;
            break;
        case kOpPatchTile:
            // TV/media fabric: Vision and spatial preprocessing
            cycle_estimate_ = 100; // Fixed latency transform
            break;
        case kOpTemporalFrame:
            // Audio DSP lane: temporal compression
            cycle_estimate_ = 50;
            break;
        default:
            sram_usage_bytes_ = 0;
            cycle_estimate_ = 10;
            break;
    }
    
    status_ = 2; // Ready
}

VadDump VirtualAcceleratorDevice::dump() const {
    std::lock_guard<std::mutex> lock(mutex_);
    VadDump snapshot;
    snapshot.base_address = base_;
    snapshot.size = size_;
    snapshot.status = status_;
    snapshot.last_operator = last_op_;

    const struct { const char* name; uint64_t offset; const char* access; } specs[] = {
        {"MAGIC", kRegMagic, "ro"},
        {"VERSION", kRegVersion, "ro"},
        {"STATUS", kRegStatus, "ro"},
        {"COMMAND", kRegCommand, "wo"},
        {"DIM", kRegModelDim, "rw"},
        {"HEADS", kRegHeadCount, "rw"},
        {"CTX", kRegContextLen, "rw"},
        {"TILE", kRegTilingSize, "rw"},
        {"SRAM", kRegSramUsage, "ro"},
        {"CYCLES", kRegCycleEst, "ro"},
    };

    for (const auto& s : specs) {
        snapshot.registers.push_back({s.name, s.offset, base_ + s.offset, read_register(s.offset), s.access});
    }
    return snapshot;
}

bool VirtualAcceleratorDevice::write_scalar(uint8_t* data, std::size_t len, uint64_t value) const {
    const auto copy_len = std::min<std::size_t>(len, sizeof(value));
    std::memcpy(data, &value, copy_len);
    return true;
}

uint64_t VirtualAcceleratorDevice::read_scalar(const uint8_t* data, std::size_t len) const {
    uint64_t value = 0;
    std::memcpy(&value, data, std::min<std::size_t>(len, sizeof(value)));
    return value;
}

} // namespace synthesus::kernel::vmm
