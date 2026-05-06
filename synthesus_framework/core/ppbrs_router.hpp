#pragma once
// Synthesus 2.0 - PPBRSRouter: hybrid PPBRS+SINN routing
#include <string>
#include <memory>
namespace zo {
struct RouterResult {
    std::string response;
    float confidence;
    std::string module_used;  // "ppbrs", "sinn", or "ensemble"
    std::string reasoning_trace;
};
class PPBRSRouter {
public:
    PPBRSRouter();
    ~PPBRSRouter();
    RouterResult route(const std::string& query, const std::string& context) const;
    void set_ppbrs_threshold(float t) { ppbrs_threshold_ = t; }
    void set_sinn_threshold(float t) { sinn_threshold_ = t; }
private:
    float ppbrs_threshold_ = 0.65f;
    float sinn_threshold_ = 0.50f;
    RouterResult try_ppbrs(const std::string& query, const std::string& context) const;
    RouterResult try_sinn(const std::string& query, const std::string& context) const;
};
} // namespace zo