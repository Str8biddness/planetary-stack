#pragma once
// Synthesus 2.0 Phase 7 - VPU Router: routes VCU inputs to appropriate VCU
#include "vcu_base.hpp"
#include <vector>
#include <memory>
namespace zo {
class VPURouter {
public:
    void register_vcu(std::shared_ptr<VCUBase> vcu);
    VCUOutput route(const VCUInput& input);
    VCUOutput route_all(const VCUInput& input); // broadcast
    std::vector<std::string> list_vcus() const;
    void set_fallback_vcu(std::shared_ptr<VCUBase> vcu);
private:
    std::vector<std::shared_ptr<VCUBase>> vcus_;
    std::shared_ptr<VCUBase> fallback_;
};
} // namespace zo
