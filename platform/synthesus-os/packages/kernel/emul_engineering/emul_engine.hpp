#pragma once

#include "hardware_profiler.hpp"
#include "../vmm/vmm.hpp"
#include "../vmm/serial_console.hpp"
#include "../vmm/virtual_parameter_device.hpp"
#include "../vmm/virtual_quantum_device.hpp"
#include "../vmm/virtual_gpu_device.hpp"
#include "../vmm/virtual_network_device.hpp"
#include "../vmm/virtual_mirror_device.hpp"
#include "../vmm/virtual_vpu_device.hpp"
#include "../vmm/virtual_sllm_device.hpp"
#include "../vmm/virtual_accelerator_device.hpp"
#include "../geometric_engine.hpp"
#include "../shard_manager.hpp"
#include "../resonance_observer.hpp"
#include <string>
#include <vector>
#include <memory>
#include <functional>
#include <mutex>
#include <cstdint>

namespace synthesus::kernel::emul_engineering {

struct EmulConfig {
    std::string target_hardware; // e.g., "intel_npu_v1", "ddr2_emulation"
    std::vector<std::string> optimization_flags;
};

class EmulEngine {
public:
    using BlueprintLookup = std::function<std::string(const std::string& hardware_id, std::size_t top_k)>;
    using ParameterLookup = std::function<std::vector<uint8_t>(const std::string& parameter_id)>;
    using NetworkHandler = std::function<void(const std::string& query)>;
    using SyncTriggerHandler = std::function<void()>;
    using VpuDispatchHandler = std::function<void(uint32_t node_hash, uint32_t role)>;
    using SllmPredictHandler = std::function<std::string(const std::string& context)>;

    EmulEngine();
    
    // Initialize the engine and profile the host
    bool initialize();
    
    // Analyze host hardware and generate a virtual hardware abstraction layer
    bool generate_abstraction(const EmulConfig& config);
    
    // Run the generated abstraction in a KVM sandbox
    bool run_abstraction();

    HostHardwareMap get_host_map() const { return host_map_; }

    // Install a hot-path lookup function supplied by the pybind11 bridge.
    void set_blueprint_lookup(BlueprintLookup lookup);
    void clear_blueprint_lookup();
    void set_blueprint_top_k(std::size_t top_k);
    std::size_t get_blueprint_top_k() const { return blueprint_top_k_; }

    // Query hardware/emulation blueprints through the installed FAISS bridge.
    std::string query_blueprints(const std::string& hardware_id);

    // Install a Knowledge Cloud parameter fetcher for virtual parameter targets.
    void set_parameter_lookup(ParameterLookup lookup);
    void clear_parameter_lookup();
    bool map_parameter(const std::string& parameter_id);
    std::size_t mapped_parameter_count() const;
    
    // Device Access
    synthesus::kernel::vmm::VpdDump dump_vpd() const;
    synthesus::kernel::vmm::VqdDump dump_vqd() const;
    synthesus::kernel::vmm::VgdDump dump_vgd() const;
    synthesus::kernel::vmm::VndDump dump_vnd() const;
    synthesus::kernel::vmm::VmdDump dump_vmd() const;
    synthesus::kernel::vmm::VvpuDump dump_vvpu() const;
    synthesus::kernel::vmm::SllmDump dump_sllm() const;
    synthesus::kernel::vmm::VadDump dump_vad() const;
    
    std::shared_ptr<synthesus::kernel::vmm::SerialConsole> serial_console() const;
    std::string read_console_output() const;
    void write_console_input(const std::string& input);

    // Step 3: Cloud Ingress
    void set_network_handler(NetworkHandler handler);
    void set_network_status(uint64_t status);

    // Step 5: Mirror Sync
    void set_sync_handler(SyncTriggerHandler handler);
    void update_sync_state(uint64_t status, uint64_t timestamp);

    // Step 5: VPU Routing
    void register_vpu_node(const std::string& node_id, uint32_t role, int grade_l);
    void update_vpu_metrics(const std::string& node_id, float latency_ms, int queue_depth);
    void set_vpu_dispatcher(VpuDispatchHandler handler);
    void set_vpu_result(const std::vector<uint8_t>& result);

    // Step 6: Synthetic LLM (Phase 9)
    void set_sllm_handler(SllmPredictHandler handler);
    void update_sllm_stats(uint64_t vocab_size, uint64_t pattern_count);

    // Step 4: Hardware-Secured TrustZone
    bool set_secure_key(const std::vector<uint8_t>& key);
    std::vector<uint8_t> decrypt_secure(const std::vector<uint8_t>& ciphertext);
    std::vector<uint8_t> decrypt_ipc(const std::vector<uint8_t>& ciphertext);

private:
    enum class OptimizationPlanKind {
        Scalar,
        SSE2,
        AVX2
    };

    struct OptimizationPlan {
        OptimizationPlanKind kind = OptimizationPlanKind::Scalar;
        std::string name = "scalar_baseline";
        std::string rationale;
        uint64_t required_xcr0 = 0x1;
    };

    HostHardwareMap host_map_;
    std::unique_ptr<synthesus::kernel::vmm::VMM> vmm_;
    std::vector<uint8_t> generated_payload_;
    OptimizationPlan selected_plan_;
    
    BlueprintLookup blueprint_lookup_;
    ParameterLookup parameter_lookup_;
    std::size_t blueprint_top_k_{5};
    
    mutable std::mutex bridge_mutex_;
    std::shared_ptr<synthesus::kernel::vmm::VirtualParameterDevice> parameter_device_;
    std::shared_ptr<synthesus::kernel::vmm::VirtualQuantumDevice> quantum_device_;
    std::shared_ptr<synthesus::kernel::vmm::VirtualGPUDevice> gpu_device_;
    std::shared_ptr<synthesus::kernel::vmm::VirtualNetworkDevice> network_device_;
    std::shared_ptr<synthesus::kernel::vmm::VirtualMirrorDevice> mirror_device_;
    std::shared_ptr<synthesus::kernel::vmm::VirtualVpuDevice> vpu_device_;
    std::shared_ptr<synthesus::kernel::vmm::VirtualSllmDevice> sllm_device_;
    std::shared_ptr<synthesus::kernel::vmm::VirtualAcceleratorDevice> accelerator_device_;
    std::unique_ptr<zo::GeometricEngine> geometric_engine_;
    std::unique_ptr<zo::ShardManager> shard_manager_;
    std::unique_ptr<zo::ResonanceObserver> resonance_observer_;

    // Secure Enclave
    std::vector<uint8_t> secure_key_;
    mutable std::mutex secure_mutex_;

    // Core "AIOS" methodology logic
    std::vector<uint8_t> reverse_engineer_payload(const EmulConfig& config);
    OptimizationPlan select_optimization_plan(const EmulConfig& config, const std::string& blueprint_json) const;
};

} // namespace synthesus::kernel::emul_engineering
