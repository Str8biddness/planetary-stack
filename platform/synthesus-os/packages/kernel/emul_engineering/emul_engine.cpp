#include "emul_engine.hpp"
#include "../voice_vcu.hpp"
#include <iostream>
#include <cstring>
#include <algorithm>
#include <sstream>
#include <cctype>

namespace synthesus::kernel::emul_engineering {

namespace {

std::string json_escape(const std::string& value) {
    std::ostringstream oss;
    for (const auto ch : value) {
        switch (ch) {
            case '\\': oss << "\\\\"; break;
            case '"': oss << "\\\""; break;
            case '\n': oss << "\\n"; break;
            case '\r': oss << "\\r"; break;
            case '\t': oss << "\\t"; break;
            default: oss << ch; break;
        }
    }
    return oss.str();
}

std::string lowercase(std::string value) {
    std::transform(value.begin(), value.end(), value.begin(), [](unsigned char ch) {
        return static_cast<char>(std::tolower(ch));
    });
    return value;
}

bool contains_token(const std::vector<std::string>& values, const std::string& token) {
    return std::find(values.begin(), values.end(), token) != values.end();
}

bool contains_text(const std::string& haystack, const std::string& needle) {
    return haystack.find(needle) != std::string::npos;
}

void append_io_marker(std::vector<uint8_t>& payload, uint8_t marker) {
    payload.push_back(0xB0); // mov al, imm8
    payload.push_back(marker);
    payload.push_back(0xE6); // out imm8, al
    payload.push_back(0x10);
}

} // namespace

EmulEngine::EmulEngine()
    : vmm_(std::make_unique<synthesus::kernel::vmm::VMM>()),
      parameter_device_(std::make_shared<synthesus::kernel::vmm::VirtualParameterDevice>()),
      quantum_device_(std::make_shared<synthesus::kernel::vmm::VirtualQuantumDevice>()),
      gpu_device_(std::make_shared<synthesus::kernel::vmm::VirtualGPUDevice>()),
      network_device_(std::make_shared<synthesus::kernel::vmm::VirtualNetworkDevice>()),
      mirror_device_(std::make_shared<synthesus::kernel::vmm::VirtualMirrorDevice>()),
      vpu_device_(std::make_shared<synthesus::kernel::vmm::VirtualVpuDevice>()),
      sllm_device_(std::make_shared<synthesus::kernel::vmm::VirtualSllmDevice>()),
      accelerator_device_(std::make_shared<synthesus::kernel::vmm::VirtualAcceleratorDevice>()),
      geometric_engine_(std::make_shared<zo::GeometricEngine>()),
      shard_manager_(std::make_unique<zo::ShardManager>(geometric_engine_)),
      resonance_observer_(std::make_unique<zo::ResonanceObserver>(geometric_engine_)) {
    
    // Set default geometric prediction handler using the ShardManager
    sllm_device_->set_predict_handler([this](const std::string& context) {
        static const std::vector<std::string> default_candidates = {
            "the", "a", "is", "of", "and", "to", "in", "it", "with", "that"
        };
        auto results = shard_manager_->predict_global(context, default_candidates, 1);
        if (!results.empty()) return results[0].word;
        return std::string("...");
    });
}

bool EmulEngine::initialize() {
    HardwareProfiler profiler;
    host_map_ = profiler.profile_host();
    
    std::cout << "[EmulEngine] Host Profiled: CPU=" << host_map_.cpu.model 
              << ", RAM=" << host_map_.memory.total_ram_mb << "MB" << std::endl;
    
    if (!host_map_.accelerators.empty()) {
        std::string gpu_name = "Host GPU";
        uint64_t vram = 4096;
        for (const auto& acc : host_map_.accelerators) {
            if (acc.find("nvidia") != std::string::npos) { gpu_name = "NVIDIA CUDA"; vram = 8192; break; }
            if (acc.find("dri") != std::string::npos) { gpu_name = "Intel/AMD DRI"; break; }
        }
        gpu_device_->set_gpu_info(gpu_name, vram);
    }

    return vmm_->initialize();
}

bool EmulEngine::generate_abstraction(const EmulConfig& config) {
    const auto blueprint_json = query_blueprints(config.target_hardware);
    selected_plan_ = select_optimization_plan(config, blueprint_json);
    generated_payload_ = reverse_engineer_payload(config);
    return !generated_payload_.empty();
}

std::vector<uint8_t> EmulEngine::reverse_engineer_payload(const EmulConfig&) {
    std::vector<uint8_t> payload;
    append_io_marker(payload, 0xA0);
    payload.insert(payload.end(), {0x67, 0x66, 0xA1, 0x00, 0x00, 0x00, 0xF0}); // VPD probe
    append_io_marker(payload, 0xAF);
    payload.push_back(0xF4);
    return payload;
}

bool EmulEngine::run_abstraction() {
    if (generated_payload_.empty()) return false;
    vmm_->set_required_xcr0(selected_plan_.required_xcr0);
    vmm_->clear_mmio_devices();
    vmm_->register_mmio_device(parameter_device_);
    vmm_->register_mmio_device(quantum_device_);
    vmm_->register_mmio_device(gpu_device_);
    vmm_->register_mmio_device(network_device_);
    vmm_->register_mmio_device(mirror_device_);
    vmm_->register_mmio_device(vpu_device_);
    vmm_->register_mmio_device(sllm_device_);
    vmm_->register_mmio_device(accelerator_device_);
    if (!vmm_->allocate_memory(0x1000) || !vmm_->setup_vcpu()) return false;
    vmm_->load_payload(generated_payload_);
    return vmm_->run();
}

void EmulEngine::set_blueprint_lookup(BlueprintLookup lookup) {
    std::lock_guard<std::mutex> lock(bridge_mutex_);
    blueprint_lookup_ = std::move(lookup);
}

void EmulEngine::clear_blueprint_lookup() {
    std::lock_guard<std::mutex> lock(bridge_mutex_);
    blueprint_lookup_ = nullptr;
}

void EmulEngine::set_parameter_lookup(ParameterLookup lookup) {
    std::lock_guard<std::mutex> lock(bridge_mutex_);
    parameter_lookup_ = std::move(lookup);
}

void EmulEngine::clear_parameter_lookup() {
    std::lock_guard<std::mutex> lock(bridge_mutex_);
    parameter_lookup_ = nullptr;
}

bool EmulEngine::map_parameter(const std::string& parameter_id) {
    ParameterLookup lookup;
    { std::lock_guard<std::mutex> lock(bridge_mutex_); lookup = parameter_lookup_; }
    if (!lookup) return false;
    auto bytes = lookup(parameter_id);
    if (bytes.empty()) return false;
    parameter_device_->set_parameter(parameter_id, std::move(bytes));
    return true;
}

std::size_t EmulEngine::mapped_parameter_count() const { return parameter_device_->parameter_count(); }

synthesus::kernel::vmm::VpdDump EmulEngine::dump_vpd() const { return parameter_device_->dump(); }
synthesus::kernel::vmm::VqdDump EmulEngine::dump_vqd() const { return quantum_device_->dump(); }
synthesus::kernel::vmm::VgdDump EmulEngine::dump_vgd() const { return gpu_device_->dump(); }
synthesus::kernel::vmm::VndDump EmulEngine::dump_vnd() const { return network_device_->dump(); }
synthesus::kernel::vmm::VmdDump EmulEngine::dump_vmd() const { return mirror_device_->dump(); }
synthesus::kernel::vmm::VvpuDump EmulEngine::dump_vvpu() const { return vpu_device_->dump(); }
synthesus::kernel::vmm::SllmDump EmulEngine::dump_sllm() const { return sllm_device_->dump(); }
synthesus::kernel::vmm::VadDump EmulEngine::dump_vad() const { return accelerator_device_->dump(); }

std::shared_ptr<synthesus::kernel::vmm::SerialConsole> EmulEngine::serial_console() const { return vmm_->serial_console(); }
std::string EmulEngine::read_console_output() const { return vmm_->serial_console()->read_output(); }
void EmulEngine::write_console_input(const std::string& input) { vmm_->serial_console()->write_input(input); }

void EmulEngine::set_network_handler(NetworkHandler handler) { network_device_->set_handler(std::move(handler)); }
void EmulEngine::set_network_status(uint64_t status) { network_device_->set_status(status); }
void EmulEngine::set_sync_handler(SyncTriggerHandler handler) { mirror_device_->set_trigger_handler(std::move(handler)); }
void EmulEngine::update_sync_state(uint64_t status, uint64_t timestamp) { mirror_device_->update_state(status, timestamp); }
void EmulEngine::register_vpu_node(const std::string& node_id, uint32_t role, int grade_l) { vpu_device_->register_node(node_id, role, grade_l); }
void EmulEngine::update_vpu_metrics(const std::string& node_id, float latency_ms, int queue_depth) { vpu_device_->update_node_metrics(node_id, latency_ms, queue_depth); }
void EmulEngine::set_vpu_dispatcher(VpuDispatchHandler handler) { vpu_device_->set_dispatch_handler(std::move(handler)); }
void EmulEngine::set_vpu_result(const std::vector<uint8_t>& result) { vpu_device_->set_result_buffer(result); }
void EmulEngine::set_sllm_handler(SllmPredictHandler handler) { sllm_device_->set_predict_handler(std::move(handler)); }
void EmulEngine::update_sllm_stats(uint64_t vocab_size, uint64_t pattern_count) { sllm_device_->update_stats(vocab_size, pattern_count); }

bool EmulEngine::set_secure_key(const std::vector<uint8_t>& key) {
    std::lock_guard<std::mutex> lock(secure_mutex_);
    secure_key_ = key;
    return true;
}

std::vector<uint8_t> EmulEngine::decrypt_secure(const std::vector<uint8_t>& ciphertext) {
    std::lock_guard<std::mutex> lock(secure_mutex_);
    if (secure_key_.empty()) return {};
    std::vector<uint8_t> plaintext = ciphertext;
    for (size_t i = 0; i < plaintext.size(); ++i) plaintext[i] ^= secure_key_[i % secure_key_.size()];
    return plaintext;
}

std::vector<uint8_t> EmulEngine::decrypt_ipc(const std::vector<uint8_t>& ciphertext) { return decrypt_secure(ciphertext); }
void EmulEngine::set_blueprint_top_k(std::size_t top_k) { blueprint_top_k_ = std::max<std::size_t>(1, top_k); }
std::string EmulEngine::query_blueprints(const std::string& hardware_id) {
    BlueprintLookup lookup;
    { std::lock_guard<std::mutex> lock(bridge_mutex_); lookup = blueprint_lookup_; }
    if (!lookup) return "{}";
    return lookup(hardware_id, blueprint_top_k_);
}

EmulEngine::OptimizationPlan EmulEngine::select_optimization_plan(const EmulConfig&, const std::string& blueprints) const {
    if (contains_text(blueprints, "avx2") && contains_token(host_map_.cpu.features, "avx2")) {
        return { OptimizationPlanKind::AVX2, "avx2_vector_probe", "Host supports AVX2", 0x7 };
    }
    return { OptimizationPlanKind::Scalar, "scalar_baseline", "Generic mode", 0x1 };
}

} // namespace synthesus::kernel::emul_engineering
