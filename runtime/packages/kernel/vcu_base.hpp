#pragma once
// Synthesus 2.0 Phase 7 - VCU Base (Virtual Cortex Unit abstract base)
#include <string>
#include <vector>
#include <functional>
#include <cstdint>
namespace zo {
struct VCUInput {
    std::string data;
    std::string context;
    std::string action_hint;
    std::string payload;
    std::string source_id;
    float urgency{0.5f};
};
struct VCUOutput {
    std::string result;
    float confidence{0.0f};
    std::string vcu_id;
    bool handled{false};
    std::vector<std::string> tags;
};
class VCUBase {
public:
    explicit VCUBase(const std::string& name = "") : name_(name) {}
    virtual ~VCUBase() = default;
    virtual std::string id() const { return name_; }
    virtual VCUOutput process(const VCUInput& input) = 0;
    virtual bool can_handle(const VCUInput& input) const { return true; }
    virtual void on_tick(uint64_t tick_ms) {}
    virtual void reset() {}
    bool enabled{true};
    float priority{1.0f};
protected:
    std::string name_;
};
} // namespace zo
