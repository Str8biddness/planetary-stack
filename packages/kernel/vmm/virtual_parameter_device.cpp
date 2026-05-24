#include "virtual_parameter_device.hpp"
#include <algorithm>
#include <cstring>
#include <functional>

namespace synthesus::kernel::vmm {

VirtualParameterDevice::VirtualParameterDevice(uint64_t base, uint64_t size)
    : base_(base), size_(std::max<uint64_t>(size, kDefaultSize)) {}

std::size_t VirtualParameterDevice::add_parameter(std::string key, std::vector<uint8_t> bytes, uint64_t version) {
    const auto existing = index_by_key_.find(key);
    if (existing != index_by_key_.end()) {
        parameters_[existing->second] = {std::move(key), std::move(bytes), version};
        return existing->second;
    }

    const auto index = parameters_.size();
    parameters_.push_back({std::move(key), std::move(bytes), version});
    index_by_key_[parameters_.back().key] = index;
    return index;
}

bool VirtualParameterDevice::set_parameter(std::string key, std::vector<uint8_t> bytes, uint64_t version) {
    add_parameter(std::move(key), std::move(bytes), version);
    return true;
}

const ParameterRecord* VirtualParameterDevice::get_parameter(const std::string& key) const {
    const auto it = index_by_key_.find(key);
    if (it == index_by_key_.end()) return nullptr;
    return &parameters_[it->second];
}

const ParameterRecord* VirtualParameterDevice::selected_parameter() const {
    if (selected_index_ >= parameters_.size()) return nullptr;
    return &parameters_[static_cast<std::size_t>(selected_index_)];
}

bool VirtualParameterDevice::read(uint64_t offset, uint8_t* data, std::size_t len) {
    if (!data || len == 0 || offset + len > size_) return false;

    if (offset < kDataWindow) {
        return write_scalar(data, len, read_register(offset));
    }

    std::memset(data, 0, len);
    const auto* param = selected_parameter();
    if (!param) return true;

    const uint64_t window_offset = offset - kDataWindow;
    const uint64_t source_offset = data_offset_ + window_offset;
    if (source_offset >= param->bytes.size()) return true;

    const auto available = static_cast<std::size_t>(
        std::min<uint64_t>(len, param->bytes.size() - source_offset)
    );
    const auto limited = data_length_ == 0
        ? available
        : std::min<std::size_t>(available, static_cast<std::size_t>(data_length_));
    std::memcpy(data, param->bytes.data() + source_offset, limited);
    return true;
}

bool VirtualParameterDevice::write(uint64_t offset, const uint8_t* data, std::size_t len) {
    if (!data || len == 0 || offset + len > size_) return false;
    if (offset >= kDataWindow) return true;
    return write_register(offset, read_scalar(data, len));
}

uint64_t VirtualParameterDevice::read_register(uint64_t offset) const {
    const auto* param = selected_parameter();
    switch (offset) {
        case kRegMagic:
            return kMagic;
        case kRegVersion:
            return param ? param->version : 1;
        case kRegParameterCount:
            return parameters_.size();
        case kRegSelectedIndex:
            return selected_index_;
        case kRegSelectedSize:
            return param ? param->bytes.size() : 0;
        case kRegDataOffset:
            return data_offset_;
        case kRegDataLength:
            return data_length_;
        case kRegKeyHash:
            return selected_key_hash();
        case kRegStatus:
            return param ? 1 : 0;
        default:
            return 0;
    }
}

VpdDump VirtualParameterDevice::dump() const {
    VpdDump snapshot;
    snapshot.base_address = base_;
    snapshot.size = size_;
    snapshot.data_window_offset = kDataWindow;
    snapshot.parameter_count = parameters_.size();

    const struct {
        const char* name;
        uint64_t offset;
        const char* access;
    } register_specs[] = {
        {"MAGIC", kRegMagic, "ro"},
        {"VERSION", kRegVersion, "ro"},
        {"PARAMETER_COUNT", kRegParameterCount, "ro"},
        {"SELECTED_INDEX", kRegSelectedIndex, "rw"},
        {"SELECTED_SIZE", kRegSelectedSize, "ro"},
        {"DATA_OFFSET", kRegDataOffset, "rw"},
        {"DATA_LENGTH", kRegDataLength, "rw"},
        {"KEY_HASH", kRegKeyHash, "ro"},
        {"STATUS", kRegStatus, "ro"},
    };

    snapshot.registers.reserve(sizeof(register_specs) / sizeof(register_specs[0]));
    for (const auto& spec : register_specs) {
        snapshot.registers.push_back({
            spec.name,
            spec.offset,
            base_ + spec.offset,
            read_register(spec.offset),
            spec.access
        });
    }

    snapshot.selected_parameter.index = selected_index_;
    snapshot.selected_parameter.data_offset = data_offset_;
    snapshot.selected_parameter.data_length = data_length_;

    const auto* param = selected_parameter();
    if (!param) {
        return snapshot;
    }

    snapshot.selected_parameter.available = true;
    snapshot.selected_parameter.key = param->key;
    snapshot.selected_parameter.version = param->version;
    snapshot.selected_parameter.size = param->bytes.size();

    if (data_offset_ >= param->bytes.size()) {
        return snapshot;
    }

    const auto source_offset = static_cast<std::size_t>(data_offset_);
    const auto available = param->bytes.size() - source_offset;
    const auto length = data_length_ == 0
        ? available
        : std::min<std::size_t>(available, static_cast<std::size_t>(data_length_));
    snapshot.selected_parameter.bytes.assign(
        param->bytes.begin() + static_cast<std::ptrdiff_t>(source_offset),
        param->bytes.begin() + static_cast<std::ptrdiff_t>(source_offset + length)
    );
    return snapshot;
}

bool VirtualParameterDevice::write_register(uint64_t offset, uint64_t value) {
    switch (offset) {
        case kRegSelectedIndex:
            selected_index_ = value;
            data_offset_ = 0;
            data_length_ = 0;
            return true;
        case kRegDataOffset:
            data_offset_ = value;
            return true;
        case kRegDataLength:
            data_length_ = value;
            return true;
        default:
            return true;
    }
}

bool VirtualParameterDevice::write_scalar(uint8_t* data, std::size_t len, uint64_t value) const {
    const auto copy_len = std::min<std::size_t>(len, sizeof(value));
    std::memcpy(data, &value, copy_len);
    if (len > copy_len) {
        std::memset(data + copy_len, 0, len - copy_len);
    }
    return true;
}

uint64_t VirtualParameterDevice::read_scalar(const uint8_t* data, std::size_t len) const {
    uint64_t value = 0;
    std::memcpy(&value, data, std::min<std::size_t>(len, sizeof(value)));
    return value;
}

uint64_t VirtualParameterDevice::selected_key_hash() const {
    const auto* param = selected_parameter();
    if (!param) return 0;
    return static_cast<uint64_t>(std::hash<std::string>{}(param->key));
}

} // namespace synthesus::kernel::vmm
