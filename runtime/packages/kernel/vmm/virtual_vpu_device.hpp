#pragma once

#include "vmm.hpp"
#include <cstddef>
#include <cstdint>
#include <string>
#include <vector>
#include <mutex>
#include <functional>
#include <unordered_map>
#include <immintrin.h>

namespace synthesus::kernel::vmm {

struct VpuNodeState {
    uint32_t id_hash;
    float avg_latency_ms;
    float queue_ratio;
    float grade_penalty;
    float current_score;
    bool is_up;
};

struct VvpuRegisterDump {
    std::string name;
    uint64_t offset{0};
    uint64_t absolute_address{0};
    uint64_t value{0};
    std::string access;
};

struct VvpuDump {
    uint64_t base_address{0};
    uint64_t size{0};
    uint64_t status{0};
    uint64_t active_nodes{0};
    uint64_t last_routed_node_hash{0};
    std::vector<VvpuRegisterDump> registers;
};

class VirtualVpuDevice final : public MMIODevice {
public:
    static constexpr uint64_t kDefaultBase = 0xF5000000ull;
    static constexpr uint64_t kDefaultSize = 0x2000ull;
    static constexpr uint64_t kMagic = 0x56565055ull; // "VVPU"

    using DispatchHandler = std::function<void(uint32_t node_hash, uint32_t target_role)>;

    explicit VirtualVpuDevice(uint64_t base = kDefaultBase, uint64_t size = kDefaultSize);

    uint64_t base_address() const override { return base_; }
    uint64_t size() const override { return size_; }
    bool read(uint64_t offset, uint8_t* data, std::size_t len) override;
    bool write(uint64_t offset, const uint8_t* data, std::size_t len) override;

    // Node Management
    void register_node(const std::string& node_id, uint32_t role, int grade_l);
    void update_node_metrics(const std::string& node_id, float latency_ms, int queue_depth);
    void set_node_status(const std::string& node_id, bool is_up);

    void set_dispatch_handler(DispatchHandler handler);
    void set_result_buffer(const std::vector<uint8_t>& result);
    
    VvpuDump dump() const;

private:
    enum Register : uint64_t {
        kRegMagic = 0x00,
        kRegVersion = 0x08,
        kRegStatus = 0x10,      // 0=Idle, 1=Routing, 2=Executing, 3=Done, 4=Error
        kRegTargetRole = 0x18,  // Role enum to route to
        kRegCommand = 0x20,     // 1=Route & Execute
        kRegLastRouted = 0x28,  // Hash of the node that was selected
        kRegResultLen = 0x30,
        kRegResultBuffer = 0x100
    };

    uint64_t read_register(uint64_t offset) const;
    bool write_register(uint64_t offset, uint64_t value);
    bool write_scalar(uint8_t* data, std::size_t len, uint64_t value) const;
    uint64_t read_scalar(const uint8_t* data, std::size_t len) const;

    // AVX2 Routing Logic
    uint32_t route_request(uint32_t target_role);

    uint64_t base_;
    uint64_t size_;
    uint64_t status_{0};
    uint32_t target_role_{0};
    uint64_t last_routed_node_hash_{0};
    
    std::vector<uint8_t> result_buffer_;
    DispatchHandler dispatch_handler_;

    // Routing Weights
    float w_l_{0.6f};
    float w_q_{0.3f};
    float w_g_{0.1f};

    // Node State
    std::unordered_map<uint32_t, std::vector<VpuNodeState>> nodes_by_role_;
    std::unordered_map<std::string, uint32_t> node_id_to_hash_;
    std::unordered_map<std::string, uint32_t> node_id_to_role_;

    mutable std::mutex mutex_;
};

} // namespace synthesus::kernel::vmm
