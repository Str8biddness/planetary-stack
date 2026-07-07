#include "virtual_sllm_device.hpp"
#include <algorithm>
#include <cstring>
#include <iostream>

namespace synthesus::kernel::vmm {

VirtualSllmDevice::VirtualSllmDevice(uint64_t base, uint64_t size)
    : base_(base), size_(std::max<uint64_t>(size, kDefaultSize)) {
    context_buffer_.resize(0xF00, 0); // Up to 3.8KB context
    result_buffer_.resize(0xF00, 0);  // Up to 3.8KB result
}

bool VirtualSllmDevice::read(uint64_t offset, uint8_t* data, std::size_t len) {
    if (!data || len == 0 || offset + len > size_) return false;
    std::lock_guard<std::mutex> lock(mutex_);

    if (offset >= kRegResultBuffer && offset < kRegResultBuffer + result_buffer_.size()) {
        const auto buf_offset = offset - kRegResultBuffer;
        const auto copy_len = std::min<std::size_t>(len, result_buffer_.size() - buf_offset);
        std::memcpy(data, result_buffer_.data() + buf_offset, copy_len);
        return true;
    }

    if (offset >= kRegContextBuffer && offset < kRegContextBuffer + context_buffer_.size()) {
        const auto buf_offset = offset - kRegContextBuffer;
        const auto copy_len = std::min<std::size_t>(len, context_buffer_.size() - buf_offset);
        std::memcpy(data, context_buffer_.data() + buf_offset, copy_len);
        return true;
    }

    return write_scalar(data, len, read_register(offset));
}

bool VirtualSllmDevice::write(uint64_t offset, const uint8_t* data, std::size_t len) {
    if (!data || len == 0 || offset + len > size_) return false;
    std::lock_guard<std::mutex> lock(mutex_);

    if (offset >= kRegContextBuffer && offset < kRegContextBuffer + context_buffer_.size()) {
        const auto buf_offset = offset - kRegContextBuffer;
        const auto copy_len = std::min<std::size_t>(len, context_buffer_.size() - buf_offset);
        std::memcpy(context_buffer_.data() + buf_offset, data, copy_len);
        return true;
    }

    const auto value = read_scalar(data, len);
    return write_register(offset, value);
}

void VirtualSllmDevice::set_predict_handler(PredictHandler handler) {
    std::lock_guard<std::mutex> lock(mutex_);
    predict_handler_ = std::move(handler);
}

void VirtualSllmDevice::update_stats(uint64_t vocab_size, uint64_t pattern_count) {
    std::lock_guard<std::mutex> lock(mutex_);
    vocab_size_ = vocab_size;
    pattern_count_ = pattern_count;
}

uint64_t VirtualSllmDevice::read_register(uint64_t offset) const {
    switch (offset) {
        case kRegMagic: return kMagic;
        case kRegVersion: return 1;
        case kRegStatus: return status_;
        case kRegVocabSize: return vocab_size_;
        case kRegPatternCount: return pattern_count_;
        case kRegContextLen: {
            const char* buf_ptr = reinterpret_cast<const char*>(context_buffer_.data());
            return std::strlen(buf_ptr);
        }
        case kRegResultLen: return std::strlen(reinterpret_cast<const char*>(result_buffer_.data()));
        default: return 0;
    }
}

bool VirtualSllmDevice::write_register(uint64_t offset, uint64_t value) {
    switch (offset) {
        case kRegCommand:
            if (value == 1 && predict_handler_) {
                status_ = 1; // Predicting
                const char* context_ptr = reinterpret_cast<const char*>(context_buffer_.data());
                std::string result = predict_handler_(context_ptr);
                
                std::memset(result_buffer_.data(), 0, result_buffer_.size());
                std::memcpy(result_buffer_.data(), result.c_str(), std::min(result.size(), result_buffer_.size() - 1));
                
                status_ = 2; // Ready
            }
            return true;
        default:
            return false;
    }
}

SllmDump VirtualSllmDevice::dump() const {
    std::lock_guard<std::mutex> lock(mutex_);
    SllmDump snapshot;
    snapshot.base_address = base_;
    snapshot.size = size_;
    snapshot.status = status_;
    snapshot.vocab_size = vocab_size_;
    snapshot.pattern_count = pattern_count_;

    const struct { const char* name; uint64_t offset; const char* access; } specs[] = {
        {"MAGIC", kRegMagic, "ro"},
        {"VERSION", kRegVersion, "ro"},
        {"STATUS", kRegStatus, "ro"},
        {"VOCAB", kRegVocabSize, "ro"},
        {"PATTERNS", kRegPatternCount, "ro"},
        {"COMMAND", kRegCommand, "wo"},
        {"CTX_LEN", kRegContextLen, "ro"},
        {"RES_LEN", kRegResultLen, "ro"},
    };

    for (const auto& s : specs) {
        snapshot.registers.push_back({s.name, s.offset, base_ + s.offset, read_register(s.offset), s.access});
    }
    return snapshot;
}

bool VirtualSllmDevice::write_scalar(uint8_t* data, std::size_t len, uint64_t value) const {
    const auto copy_len = std::min<std::size_t>(len, sizeof(value));
    std::memcpy(data, &value, copy_len);
    return true;
}

uint64_t VirtualSllmDevice::read_scalar(const uint8_t* data, std::size_t len) const {
    uint64_t value = 0;
    std::memcpy(&value, data, std::min<std::size_t>(len, sizeof(value)));
    return value;
}

} // namespace synthesus::kernel::vmm
