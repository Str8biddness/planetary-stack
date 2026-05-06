#include "vehicular_ai.hpp"
#include <sstream>
#include <algorithm>
namespace zo {
VehicularAI::VehicularAI() { init_dtc_db(); }
void VehicularAI::init_dtc_db() {
    // 33 common DTC codes
    auto add = [&](const char* code, const char* desc, const char* sys, float sev, const char* action) {
        dtc_db_[code] = {code, desc, sys, sev, action};
    };
    add("P0171","System Too Lean (Bank 1)","engine",0.6f,"Check O2 sensor, MAF sensor, vacuum leaks");
    add("P0300","Random/Multiple Cylinder Misfire","engine",0.9f,"Check ignition system, fuel injectors");
    add("P0420","Catalyst Efficiency Below Threshold","engine",0.5f,"Replace catalytic converter");
    add("P0401","EGR Flow Insufficient","evap",0.5f,"Clean/replace EGR valve");
    add("P0442","EVAP Leak Small","evap",0.3f,"Check fuel cap, EVAP hoses");
    add("P0500","Vehicle Speed Sensor Malfunction","transmission",0.7f,"Replace VSS");
    add("P0700","Transmission Control System","transmission",0.8f,"Check TCM, solenoids");
    add("C0035","Front Right Wheel Speed Sensor","abs",0.8f,"Replace wheel speed sensor");
    add("C0040","Front Left Wheel Speed Sensor","abs",0.8f,"Replace wheel speed sensor");
    add("B0001","Driver Frontal Stage 1 Squib","airbag",0.9f,"Inspect airbag system");
    // Add 23 more DTC stubs
    for (int i = 1; i <= 23; ++i) {
        std::string code = "P" + std::to_string(1000+i);
        dtc_db_[code] = {code, "Diagnostic code " + code, "engine", 0.4f, "Inspect system"};
    }
}
std::string VehicularAI::interpret_dtc(const std::string& code) const {
    auto it = dtc_db_.find(code);
    if (it == dtc_db_.end()) return "Unknown DTC: " + code;
    auto& d = it->second;
    return code + ": " + d.description + " [" + d.system + "] - " + d.recommended_action;
}
std::vector<DTCCode> VehicularAI::get_all_dtcs() const {
    std::vector<DTCCode> res;
    for (auto& [k,v] : dtc_db_) res.push_back(v);
    return res;
}
VehicleDiag VehicularAI::diagnose(const std::vector<std::string>& dtc_codes,
                                   const std::vector<SensorReading>& sensors) const {
    VehicleDiag diag; diag.sensor_data = sensors;
    float penalty = 0;
    for (auto& code : dtc_codes) {
        auto it = dtc_db_.find(code);
        if (it != dtc_db_.end()) { diag.active_dtcs.push_back(it->second); penalty += it->second.severity; }
    }
    diag.health_score = std::max(0.0f, 1.0f - penalty / std::max(1.0f,(float)dtc_codes.size()));
    std::ostringstream ss;
    ss << diag.active_dtcs.size() << " DTCs active; health=" << (int)(diag.health_score*100) << "%";
    diag.health_summary = ss.str();
    return diag;
}
Route VehicularAI::plan_route(const std::string& origin, const std::string& dest,
                               const std::vector<std::string>& wps) const {
    Route r; r.waypoints.push_back(origin);
    for (auto& w : wps) r.waypoints.push_back(w);
    r.waypoints.push_back(dest);
    r.distance_km = 10.0f * (r.waypoints.size() - 1); // stub
    r.eta_min = r.distance_km * 1.5f;
    return r;
}
} // namespace zo
