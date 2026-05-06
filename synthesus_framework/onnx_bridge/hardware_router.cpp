#include "hardware_router.hpp"
#include <chrono>
#include <sstream>
#include <cstdlib>
namespace zo {
HardwareRouter::HardwareRouter() { detect_hardware(); }
void HardwareRouter::detect_hardware() {
    // Check for NVIDIA CUDA
#if defined(USE_CUDA)
    cuda_available_ = true;
#else
    // Try to detect via nvidia-smi
    cuda_available_ = (std::system("nvidia-smi > /dev/null 2>&1") == 0);
#endif
    // ROCm detection (AMD)
#if defined(USE_ROCM)
    rocm_available_ = true;
#else
    rocm_available_ = (std::system("rocminfo > /dev/null 2>&1") == 0);
#endif
}
bool HardwareRouter::has_cuda() const { return cuda_available_; }
bool HardwareRouter::has_rocm() const { return rocm_available_; }
void HardwareRouter::set_preferred(HardwareTarget t) { preferred_ = t; }
HardwareTarget HardwareRouter::detect_best_hardware() const {
    if (preferred_ != HardwareTarget::AUTO) return preferred_;
    if (cuda_available_) return HardwareTarget::CUDA;
    if (rocm_available_) return HardwareTarget::ROCM;
    return HardwareTarget::CPU;
}
std::string HardwareRouter::hardware_info() const {
    std::ostringstream ss;
    ss << "CUDA:" << (cuda_available_ ? "yes" : "no")
       << " ROCm:" << (rocm_available_ ? "yes" : "no")
       << " best:" << (int)detect_best_hardware();
    return ss.str();
}
InferenceResult HardwareRouter::run(const InferenceRequest& req) {
    auto target = req.target == HardwareTarget::AUTO ? detect_best_hardware() : req.target;
    auto t0 = std::chrono::high_resolution_clock::now();
    // Stub: CPU fallback inference (actual ONNX runtime call goes here)
    std::vector<float> output(64, 0.0f);
    // If ONNX runtime available: use OrtSession to run inference
    // For now return zeros with fast latency
    for (size_t i = 0; i < std::min(req.input.size(), output.size()); ++i)
        output[i] = req.input[i] * 0.5f; // stub transform
    auto t1 = std::chrono::high_resolution_clock::now();
    float lat = std::chrono::duration<float, std::milli>(t1-t0).count();
    return {output, lat, target, true, ""};
}
} // namespace zo
