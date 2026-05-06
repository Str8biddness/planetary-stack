#include "ppbrs_router.hpp"
#include "../reasoning/ppbrs.hpp"
#include "../reasoning/sinn.hpp"
#include <algorithm>
namespace zo {
PPBRSRouter::PPBRSRouter() {}
PPBRSRouter::~PPBRSRouter() {}
RouterResult PPBRSRouter::try_ppbrs(const std::string& query, const std::string& context) const {
    RouterResult r;
    r.module_used = "ppbrs";
    r.confidence = 0.70f;
    r.response = "[PPBRS] Pattern match for: " + query.substr(0, 40);
    r.reasoning_trace = "ppbrs_pattern_match";
    return r;
}
RouterResult PPBRSRouter::try_sinn(const std::string& query, const std::string& context) const {
    RouterResult r;
    r.module_used = "sinn";
    r.confidence = 0.55f;
    r.response = "[SINN] Neural inference for: " + query.substr(0, 40);
    r.reasoning_trace = "sinn_neural";
    return r;
}
RouterResult PPBRSRouter::route(const std::string& query, const std::string& context) const {
    auto pr = try_ppbrs(query, context);
    if (pr.confidence >= ppbrs_threshold_) return pr;
    auto sr = try_sinn(query, context);
    if (sr.confidence >= sinn_threshold_) return sr;
    // Ensemble fallback
    RouterResult r;
    r.module_used = "ensemble";
    r.confidence = (pr.confidence + sr.confidence) * 0.5f;
    r.response = pr.confidence > sr.confidence ? pr.response : sr.response;
    r.reasoning_trace = "ensemble_fallback";
    return r;
}
} // namespace zo