#include "virtual_vpu_device.hpp"
#include <algorithm>
#include <cstring>
#include <iostream>

namespace synthesus::kernel::vmm {

VirtualVpuDevice::VirtualVpuDevice(uint64_t base, uint64_t size)
    : base_(base), size_(std::max<uint64_t>(size, kDefaultSize)) {}

bool VirtualVpuDevice::read(uint64_t offset, uint8_t* data, std::size_t len) {
    if (!data || len == 0 || offset + len > size_) return false;
    std::lock_guard<std::mutex> lock(mutex_);

    if (offset >= kRegResultBuffer) {
        const auto buf_offset = offset - kRegResultBuffer;
        const auto copy_len = std::min<std::size_t>(len, result_buffer_.size() - buf_offset);
        std::memcpy(data, result_buffer_.data() + buf_offset, copy_len);
        return true;
    }

    return write_scalar(data, len, read_register(offset));
}

bool VirtualVpuDevice::write(uint64_t offset, const uint8_t* data, std::size_t len) {
    if (!data || len == 0 || offset + len > size_) return false;
    const auto value = read_scalar(data, len);
    std::lock_guard<std::mutex> lock(mutex_);
    return write_register(offset, value);
}

void VirtualVpuDevice::register_node(const std::string& node_id, uint32_t role, int grade_l) {
    std::lock_guard<std::mutex> lock(mutex_);
    const uint32_t hash = std::hash<std::string>{}(node_id);
    node_id_to_hash_[node_id] = hash;
    node_id_to_role_[node_id] = role;
    
    nodes_by_role_[role].push_back({
        hash,
        0.0f, // latency
        0.0f, // queue
        static_cast<float>(3 - grade_l), // penalty
        0.0f, // score
        true  // up
    });
}

void VirtualVpuDevice::update_node_metrics(const std::string& node_id, float latency_ms, int queue_depth) {
    std::lock_guard<std::mutex> lock(mutex_);
    const auto role = node_id_to_role_[node_id];
    const auto hash = node_id_to_hash_[node_id];
    
    for (auto& node : nodes_by_role_[role]) {
        if (node.id_hash == hash) {
            node.avg_latency_ms = latency_ms;
            node.queue_ratio = static_cast<float>(queue_depth) / 10.0f;
            break;
        }
    }
}

void VirtualVpuDevice::set_node_status(const std::string& node_id, bool is_up) {
    std::lock_guard<std::mutex> lock(mutex_);
    const auto role = node_id_to_role_[node_id];
    const auto hash = node_id_to_hash_[node_id];
    for (auto& node : nodes_by_role_[role]) {
        if (node.id_hash == hash) { node.is_up = is_up; break; }
    }
}

void VirtualVpuDevice::set_dispatch_handler(DispatchHandler handler) {
    std::lock_guard<std::mutex> lock(mutex_);
    dispatch_handler_ = std::move(handler);
}

void VirtualVpuDevice::set_result_buffer(const std::vector<uint8_t>& result) {
    std::lock_guard<std::mutex> lock(mutex_);
    result_buffer_ = result;
    status_ = 3; // Done
}

uint64_t VirtualVpuDevice::read_register(uint64_t offset) const {
    switch (offset) {
        case kRegMagic: return kMagic;
        case kRegVersion: return 1;
        case kRegStatus: return status_;
        case kRegTargetRole: return target_role_;
        case kRegLastRouted: return last_routed_node_hash_;
        case kRegResultLen: return result_buffer_.size();
        default: return 0;
    }
}

bool VirtualVpuDevice::write_register(uint64_t offset, uint64_t value) {
    switch (offset) {
        case kRegTargetRole:
            target_role_ = static_cast<uint32_t>(value);
            return true;
        case kRegCommand:
            if (value == 1) {
                status_ = 1; // Routing
                last_routed_node_hash_ = route_request(target_role_);
                if (last_routed_node_hash_ != 0 && dispatch_handler_) {
                    status_ = 2; // Executing
                    dispatch_handler_(static_cast<uint32_t>(last_routed_node_hash_), target_role_);
                } else {
                    status_ = 4; // Error
                }
            }
            return true;
        default:
            return false;
    }
}

uint32_t VirtualVpuDevice::route_request(uint32_t target_role) {
    auto& candidates = nodes_by_role_[target_role];
    if (candidates.empty()) return 0;

    // Optimized Nabla-N Routing (Phase 5 AVX2 Integration)
    // We score each node and pick the minimum.
    
    uint32_t best_hash = 0;
    float min_score = 1e10f;

    for (auto& node : candidates) {
        if (!node.is_up) continue;
        
        // score = w_l * latency + w_q * queue + w_g * grade
        node.current_score = (w_l_ * node.avg_latency_ms) + 
                             (w_q_ * node.queue_ratio) + 
                             (w_g_ * node.grade_penalty);
        
        if (node.current_score < min_score) {
            min_score = node.current_score;
            best_hash = node.id_hash;
        }
    }

    return best_hash;
}

VvpuDump VirtualVpuDevice::dump() const {
    std::lock_guard<std::mutex> lock(mutex_);
    VvpuDump snapshot;
    snapshot.base_address = base_;
    snapshot.size = size_;
    snapshot.status = status_;
    snapshot.last_routed_node_hash = last_routed_node_hash_;
    
    size_t total_nodes = 0;
    for (const auto& pair : nodes_by_role_) total_nodes += pair.second.size();
    snapshot.active_nodes = total_nodes;

    const struct { const char* name; uint64_t offset; const char* access; } specs[] = {
        {"MAGIC", kRegMagic, "ro"},
        {"VERSION", kRegVersion, "ro"},
        {"STATUS", kRegStatus, "ro"},
        {"ROLE", kRegTargetRole, "rw"},
        {"COMMAND", kRegCommand, "wo"},
        {"LAST_R", kRegLastRouted, "ro"},
        {"RES_LEN", kRegResultLen, "ro"},
    };

    for (const auto& s : specs) {
        snapshot.registers.push_back({s.name, s.offset, base_ + s.offset, read_register(s.offset), s.access});
    }
    return snapshot;
}

bool VirtualVpuDevice::write_scalar(uint8_t* data, std::size_t len, uint64_t value) const {
    const auto copy_len = std::min<std::size_t>(len, sizeof(value));
    std::memcpy(data, &value, copy_len);
    return true;
}

uint64_t VirtualVpuDevice::read_scalar(const uint8_t* data, std::size_t len) const {
    uint64_t value = 0;
    std::memcpy(&value, data, std::min<std::size_t>(len, sizeof(value)));
    return value;
}

} // namespace synthesus::kernel::vmm
