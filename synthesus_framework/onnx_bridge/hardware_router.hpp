#pragma once
// Synthesus 2.0 Phase 7 - Hardware Router (GPU/CPU ONNX dispatch)
#include <string>
#include <vector>
namespace zo {
enum class HardwareTarget { AUTO, CPU, CUDA, ROCM, COREML, DIRECTML };
struct TensorSpec { std::string name; std::vector<int64_t> shape; std::string dtype; };
struct InferenceRequest {
    std::string model_path;
    std::vector<float> input;
    TensorSpec input_spec;
    HardwareTarget target{HardwareTarget::AUTO};
};
struct InferenceResult {
    std::vector<float> output;
    float latency_ms;
    HardwareTarget used_target;
    bool success;
    std::string error;
};
class HardwareRouter {
public:
    HardwareRouter();
    InferenceResult run(const InferenceRequest& req);
    HardwareTarget detect_best_hardware() const;
    bool has_cuda() const;
    bool has_rocm() const;
    std::string hardware_info() const;
    void set_preferred(HardwareTarget t);
private:
    HardwareTarget preferred_{HardwareTarget::AUTO};
    bool cuda_available_{false};
    bool rocm_available_{false};
    void detect_hardware();
};
} // namespace zo
