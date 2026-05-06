#include "firmware_re.hpp"
#include <fstream>
#include <sstream>
namespace zo {
std::string FirmwareRE::detect_arch(const uint8_t* hdr, size_t sz) const {
    if (sz < 20) return "unknown";
    // ELF magic check
    if (hdr[0]==0x7f && hdr[1]=='E' && hdr[2]=='L' && hdr[3]=='F') {
        uint16_t machine = hdr[18] | (hdr[19]<<8);
        if (machine == 0x3E) return "x86_64";
        if (machine == 0x28) return "arm";
        if (machine == 0x08) return "mips";
    }
    return "unknown";
}
void FirmwareRE::load_cve_db(const std::string& path) {
    std::ifstream f(path);
    if (!f) return;
    // Simple line format: CVE_ID|desc|severity|mitigation
    std::string line;
    while (std::getline(f, line)) {
        std::istringstream ss(line);
        std::string id, desc, sev, mit;
        std::getline(ss, id, '|'); std::getline(ss, desc, '|');
        std::getline(ss, sev, '|'); std::getline(ss, mit, '|');
        cve_db_[id].push_back({id, desc, std::stof(sev.empty()?"0":sev), mit});
    }
}
std::vector<std::string> FirmwareRE::extract_strings(const std::string& path, size_t min_len) const {
    std::ifstream f(path, std::ios::binary);
    if (!f) return {};
    std::vector<std::string> res;
    std::string cur;
    char c;
    while (f.get(c)) {
        if (c >= 0x20 && c < 0x7F) cur += c;
        else { if (cur.size() >= min_len) res.push_back(cur); cur.clear(); }
    }
    if (cur.size() >= min_len) res.push_back(cur);
    return res;
}
std::vector<CVEEntry> FirmwareRE::check_cve(const std::string& comp, const std::string& ver) const {
    std::vector<CVEEntry> res;
    for (auto& [id, entries] : cve_db_)
        for (auto& e : entries)
            if (e.description.find(comp) != std::string::npos) res.push_back(e);
    return res;
}
FirmwareAnalysis FirmwareRE::analyze(const std::string& path) const {
    FirmwareAnalysis fa; fa.filename = path;
    std::ifstream f(path, std::ios::binary);
    if (!f) { fa.summary = "File not found"; return fa; }
    uint8_t hdr[64] = {}; f.read((char*)hdr, 64);
    fa.arch = detect_arch(hdr, 64);
    fa.strings_found = extract_strings(path);
    fa.summary = fa.arch + "; " + std::to_string(fa.strings_found.size()) + " strings";
    return fa;
}
} // namespace zo
